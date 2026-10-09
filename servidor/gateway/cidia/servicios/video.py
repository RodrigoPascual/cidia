"""Tratamiento de vídeo con ffmpeg y ffprobe (programas externos, compilación LGPL).

Rutas de los programas: variables de entorno CIDIA_FFMPEG y CIDIA_FFPROBE (por defecto,
«ffmpeg» y «ffprobe» del PATH). Se leen en cada llamada, así las pruebas pueden cambiarlas.

* `info()` y `duracion()`: metadatos del fichero.
* `extraer_audio()`: WAV de 16 kHz mono, lo que espera el servicio de voz.
* `escenas()`: cambios de plano con el filtro scdet de ffmpeg (sin OpenCV ni PySceneDetect,
  que llevarían FFmpeg dentro del proceso).
* `fotograma()`, `miniatura()`: imágenes JPG.
* `clip()`: tramo ligero en WebM VP9 (o VP8; si no hay libvpx, H.264 con libopenh264 en MP4).
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger("cidia.video")

ANCHO_CLIP = 640
ANCHO_FOTOGRAMA = 1280
ANCHO_MINIATURA = 480


class ErrorVideo(RuntimeError):
    """ffmpeg no está disponible o no ha podido tratar el fichero."""


def _ffmpeg() -> str:
    return os.environ.get("CIDIA_FFMPEG") or "ffmpeg"


def _ffprobe() -> str:
    return os.environ.get("CIDIA_FFPROBE") or "ffprobe"


def _ejecutar(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    """Ejecuta un programa externo y devuelve su salida. Lanza ErrorVideo si falla."""
    try:
        r = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as e:
        raise ErrorVideo("No se encuentra ffmpeg en el servidor. Pide a la administración que lo instale.") from e
    except subprocess.TimeoutExpired as e:
        raise ErrorVideo("El tratamiento del vídeo ha tardado demasiado y se ha detenido.") from e
    if r.returncode != 0:
        # El detalle técnico (con rutas internas) va al registro; a la persona, un mensaje claro.
        ultimas = " ".join((r.stderr or "").strip().splitlines()[-3:])[:500]
        log.warning("Falló %s: %s", Path(args[0]).name, ultimas)
        raise ErrorVideo("No se ha podido tratar el fichero: puede estar dañado o en un formato no compatible.")
    return r


# Solo se leen ficheros locales: un vídeo subido podría ser en realidad una lista de reproducción
# (HLS, concat) que apunte a URLs internas o a ficheros del servidor, y ffmpeg la seguiría.
_SOLO_FICHEROS = ["-protocol_whitelist", "file"]


def _entrada(ruta: str | Path) -> list[str]:
    """Argumentos de entrada de ffmpeg para un fichero local."""
    return [*_SOLO_FICHEROS, "-i", str(ruta)]


def disponible() -> bool:
    """¿Están ffmpeg y ffprobe instalados y responden?"""
    try:
        _ejecutar([_ffmpeg(), "-hide_banner", "-version"], 20)
        _ejecutar([_ffprobe(), "-hide_banner", "-version"], 20)
        return True
    except ErrorVideo:
        return False


@functools.lru_cache(maxsize=4)
def _codificadores(binario: str) -> frozenset[str]:
    """Nombres de los codificadores de esta compilación de ffmpeg (se consulta una vez)."""
    r = _ejecutar([binario, "-hide_banner", "-encoders"], 30)
    nombres = set()
    for linea in r.stdout.splitlines():
        m = re.match(r"^\s*[VAS][\w.]{5}\s+(\S+)", linea)
        if m:
            nombres.add(m.group(1))
    return frozenset(nombres)


# --------------------------------------------------------------------------- metadatos


def info(ruta: str | Path) -> dict[str, Any]:
    """{duracion, tiene_video, tiene_audio, ancho, alto} de un fichero de vídeo o audio."""
    r = _ejecutar([_ffprobe(), "-v", "error", *_SOLO_FICHEROS, "-show_format", "-show_streams", "-of", "json",
                   str(ruta)], 60)
    try:
        j = json.loads(r.stdout or "{}")
    except json.JSONDecodeError as e:
        raise ErrorVideo("No se pueden leer los datos del vídeo.") from e
    flujos = j.get("streams") or []
    video = next((s for s in flujos if s.get("codec_type") == "video"
                  and not (s.get("disposition") or {}).get("attached_pic")), None)
    dur = _numero((j.get("format") or {}).get("duration"))
    if dur is None:
        dur = max((_numero(s.get("duration")) or 0.0 for s in flujos), default=0.0) or None
    return {
        "duracion": dur,
        "tiene_video": video is not None,
        "tiene_audio": any(s.get("codec_type") == "audio" for s in flujos),
        "ancho": video.get("width") if video else None,
        "alto": video.get("height") if video else None,
    }


def duracion(ruta: str | Path) -> float:
    """Duración en segundos. Los WebM grabados en el navegador no la llevan en la cabecera:
    en ese caso se decodifica el fichero y se toma la última marca de tiempo."""
    d = info(ruta)["duracion"]
    if d:
        return float(d)
    r = _ejecutar([_ffmpeg(), "-hide_banner", "-nostats", "-progress", "pipe:1", *_entrada(ruta),
                   "-f", "null", "-"], 600)
    marcas = re.findall(r"out_time_us=(\d+)", r.stdout)
    if not marcas:
        raise ErrorVideo("No se puede calcular la duración del fichero.")
    return int(marcas[-1]) / 1_000_000


def _numero(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None


# --------------------------------------------------------------------------- audio y escenas


def extraer_audio(ruta: str | Path, destino: str | Path) -> Path:
    """Pista de audio en WAV PCM 16 kHz mono."""
    destino = Path(destino)
    _ejecutar([_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", *_entrada(ruta), "-vn", "-sn", "-dn",
               "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(destino)], 900)
    if not destino.exists() or destino.stat().st_size == 0:
        raise ErrorVideo("El vídeo no tiene audio.")
    return destino


def escenas(ruta: str | Path, umbral: float = 10.0, separacion_minima: float = 2.0) -> list[dict[str, float]]:
    """Cambios de escena [{t, puntuacion}] con el filtro scdet.

    `umbral` es la puntuación mínima (0-100) para considerar un cambio de plano; 10 es el valor
    por defecto de ffmpeg. Se analiza a 320 px de ancho para que sea rápido. Los cambios a menos
    de `separacion_minima` segundos del anterior se descartan (movimientos bruscos de cámara)."""
    filtro = f"scale=320:-2,scdet=threshold={umbral:g}:sc_pass=1,metadata=print:file=-"
    r = _ejecutar([_ffmpeg(), "-hide_banner", "-nostats", *_entrada(ruta), "-an", "-sn", "-dn",
                   "-vf", filtro, "-f", "null", "-"], 1800)
    salida: list[dict[str, float]] = []
    puntuacion: float | None = None
    for linea in r.stdout.splitlines():
        linea = linea.strip()
        if linea.startswith("lavfi.scd.score="):
            puntuacion = _numero(linea.split("=", 1)[1])
        elif linea.startswith("lavfi.scd.time="):
            t = _numero(linea.split("=", 1)[1])
            if t is None:
                continue
            if salida and t - salida[-1]["t"] < separacion_minima:
                continue
            salida.append({"t": round(t, 3), "puntuacion": round(puntuacion or 0.0, 2)})
            puntuacion = None
    return salida


# --------------------------------------------------------------------------- imágenes


def fotograma(ruta: str | Path, t: float, destino: str | Path, ancho: int = ANCHO_FOTOGRAMA) -> Path:
    """Fotograma en el segundo `t` como JPG (como mucho `ancho` píxeles de ancho)."""
    destino = Path(destino)
    # Si `t` cae al final del fichero no hay fotograma: se reintenta un poco antes y al principio.
    for instante in dict.fromkeys((max(0.0, t), max(0.0, t - 1.0), 0.0)):
        destino.unlink(missing_ok=True)
        try:
            _ejecutar([_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{instante:.3f}",
                       *_entrada(ruta), "-frames:v", "1", "-vf", f"scale='trunc(min({ancho},iw)/2)*2':-2",
                       "-q:v", "3", "-update", "1", str(destino)], 120)
        except ErrorVideo:
            continue
        if destino.exists() and destino.stat().st_size > 0:
            return destino
    raise ErrorVideo("No se ha podido sacar una imagen del vídeo.")


def miniatura(ruta: str | Path, destino: str | Path, t: float | None = None) -> Path:
    """Imagen pequeña para listas (por defecto, al 10 % del vídeo)."""
    if t is None:
        try:
            t = duracion(ruta) * 0.1
        except ErrorVideo:
            t = 0.0
    return fotograma(ruta, t, destino, ancho=ANCHO_MINIATURA)


# --------------------------------------------------------------------------- clips


def formato_clip() -> tuple[str, list[str], list[str]]:
    """(extensión, argumentos de vídeo, argumentos de audio) según los codificadores disponibles."""
    cods = _codificadores(_ffmpeg())
    opus = ["-c:a", "libopus", "-b:a", "48k", "-ac", "1"] if "libopus" in cods else ["-c:a", "libvorbis", "-q:a", "2", "-ac", "1"]
    if "libvpx-vp9" in cods:
        return ".webm", ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1",
                         "-crf", "42", "-b:v", "0"], opus
    if "libvpx" in cods:
        return ".webm", ["-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8", "-crf", "34",
                         "-b:v", "700k"], opus
    if "libopenh264" in cods:
        return ".mp4", ["-c:v", "libopenh264", "-b:v", "700k", "-movflags", "+faststart"], \
            ["-c:a", "aac", "-b:a", "64k", "-ac", "1"]
    raise ErrorVideo("La versión de ffmpeg del servidor no tiene codificador de vídeo libre (libvpx u openh264).")


def clip(ruta: str | Path, t_inicio: float, t_fin: float, destino_sin_extension: str | Path,
         ancho: int = ANCHO_CLIP) -> Path:
    """Recorta [t_inicio, t_fin) en un clip ligero. Devuelve la ruta con su extensión."""
    ext, args_video, args_audio = formato_clip()
    destino = Path(destino_sin_extension).with_suffix(ext)
    dur = max(0.5, float(t_fin) - float(t_inicio))
    _ejecutar([
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{max(0.0, t_inicio):.3f}", *_entrada(ruta), "-t", f"{dur:.3f}",
        "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn",
        "-vf", f"scale='trunc(min({ancho},iw)/2)*2':-2", "-pix_fmt", "yuv420p",
        *args_video, *args_audio, str(destino),
    ], max(180.0, dur * 6))
    if not destino.exists() or destino.stat().st_size == 0:
        raise ErrorVideo("No se ha podido recortar el clip.")
    return destino
