"""Genera los medios sintéticos de la demostración de CidIA (en Windows).

* `datos-demo/video/brida-b-sintetico.mp4`: vídeo narrado de un minuto del montaje de la brida B
  (IT-023), con una escena por paso, para probar la captura (vídeo → instrucción). Cada escena
  tiene un fondo de color distinto para que el detector de cambios de escena encuentre los pasos.
* `datos-demo/audio/aportacion-*.ogg`: notas de voz sintéticas de las aportaciones de Pedro y de
  Lucía. Se copian también a `servidor/gateway/cidia/semilla_datos/audio/` para que la semilla
  las adjunte a sus aportaciones.

Todo es sintético: imágenes esquemáticas de la semilla y voz de la síntesis de Windows.

Requisitos
  * Windows con System.Speech y una voz en castellano (por ejemplo «Microsoft Helena Desktop»).
  * ffmpeg: la compilación LGPL de BtbN en servidor/gateway/.herramientas/ (o cualquiera del PATH).
  * El entorno del gateway (Pillow).

Uso (desde la raíz del repositorio):
  servidor/gateway/.venv/Scripts/python datos-demo/video/generar_medios.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GATEWAY = REPO / "servidor" / "gateway"
sys.path.insert(0, str(GATEWAY))

from PIL import Image  # noqa: E402

from cidia.semilla_datos import actividad, imagenes, instrucciones  # noqa: E402

SALIDA_VIDEO = REPO / "datos-demo" / "video" / "brida-b-sintetico.mp4"
SALIDA_AUDIO = REPO / "datos-demo" / "audio"
AUDIO_SEMILLA = GATEWAY / "cidia" / "semilla_datos" / "audio"
PAUSA = 1.0  # segundos de silencio al final de cada escena
FONDOS = ["#1f2328", "#2f6fbf", "#1f8a70", "#c8442f", "#8a6d00", "#6b4fa0", "#d97a00", "#0f6d7a", "#1f2328"]

PS_VOZ = r"""
param([string]$Lista)
Add-Type -AssemblyName System.Speech
$voz = New-Object System.Speech.Synthesis.SpeechSynthesizer
$es = $voz.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'es-*' } | Select-Object -First 1
if ($es) { $voz.SelectVoice($es.VoiceInfo.Name) } else { Write-Error 'No hay ninguna voz en castellano instalada'; exit 2 }
$voz.Rate = 1
$formato = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(22050, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($t in (Get-Content -Raw -Encoding UTF8 $Lista | ConvertFrom-Json)) {
  $voz.SetOutputToWaveFile($t.salida, $formato)
  $voz.Speak($t.texto)
}
$voz.SetOutputToNull()
Write-Output $es.VoiceInfo.Name
"""


def buscar_ffmpeg() -> str:
    for exe in sorted((GATEWAY / ".herramientas").glob("*/bin/ffmpeg.exe")):
        return str(exe)
    encontrado = shutil.which("ffmpeg")
    if not encontrado:
        sys.exit("No se encuentra ffmpeg: descarga la compilación LGPL de BtbN en servidor/gateway/.herramientas/")
    return encontrado


def codificador(ffmpeg: str, preferidos: list[str]) -> str:
    salida = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    for c in preferidos:
        if f" {c} " in salida:
            return c
    return preferidos[-1]


def sintetizar(textos: list[tuple[str, Path]], tmp: Path) -> None:
    """Voz de Windows (System.Speech) en WAV de 22,05 kHz, 16 bits, mono."""
    lista = tmp / "voz.json"
    lista.write_text(json.dumps([{"texto": t, "salida": str(p)} for t, p in textos], ensure_ascii=False),
                     encoding="utf-8")
    script = tmp / "voz.ps1"
    script.write_text(PS_VOZ, encoding="utf-8-sig")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                        "-Lista", str(lista)], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"La síntesis de voz ha fallado: {r.stderr.strip()}")
    print(f"Voz: {r.stdout.strip()}")


def duracion(wav: Path) -> float:
    with wave.open(str(wav)) as w:
        return w.getnframes() / w.getframerate()


def unir_wav(partes: list[Path], destino: Path, pausa: float) -> None:
    with wave.open(str(partes[0])) as w:
        params = w.getparams()
    silencio = b"\x00\x00" * int(params.framerate * pausa)
    with wave.open(str(destino), "wb") as out:
        out.setparams(params)
        for p in partes:
            with wave.open(str(p)) as w:
                out.writeframes(w.readframes(w.getnframes()))
            out.writeframes(silencio)


def escena(fondo: str, imagen: Image.Image) -> Image.Image:
    """Fotograma 1280×720: fondo de color propio de la escena y la imagen del paso encima."""
    lienzo = Image.new("RGB", (1280, 720), fondo)
    lienzo.paste(imagen.resize((1120, 630)), (80, 45))
    return lienzo


def video(ffmpeg: str, tmp: Path) -> None:
    defi = next(d for d in instrucciones.INSTRUCCIONES if d["codigo"] == "IT-023")
    narracion = defi["narracion"]
    textos = [narracion["inicio"], *narracion["pasos"], narracion["cierre"]]
    wavs = [tmp / f"voz-{i:02d}.wav" for i in range(len(textos))]
    sintetizar(list(zip(textos, wavs, strict=True)), tmp)

    color = "#d97a00"  # Producción
    cuadros = [imagenes.tarjeta("Montaje de la brida B", "IT-023 · Línea 2, estación E2 · Vídeo narrado de ejemplo",
                                color, "Metalúrgica Arlanza, S. L. (empresa ficticia) · vídeo sintético")]
    for i, p in enumerate(defi["pasos"], start=1):
        cuadros.append(imagenes.imagen_paso("IT-023", defi["titulo"], 1, i, len(defi["pasos"]), p["titulo"],
                                            p["dibujo"], color, p.get("dato", ""), bool(p.get("critico")),
                                            bool(p.get("seguridad"))))
    cuadros.append(imagenes.tarjeta("Brida B montada", "Conjunto registrado, etiquetado y en el carro de salida.",
                                    color, "Fin del vídeo de ejemplo"))
    lineas = []
    for i, (im, wav) in enumerate(zip(cuadros, wavs, strict=True)):
        png = tmp / f"escena-{i:02d}.png"
        escena(FONDOS[i % len(FONDOS)], im).save(png)
        lineas += [f"file '{png.as_posix()}'", f"duration {duracion(wav) + PAUSA:.3f}"]
    lineas.append(f"file '{(tmp / f'escena-{len(cuadros) - 1:02d}.png').as_posix()}'")  # el último se repite
    (tmp / "escenas.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    unir_wav(wavs, tmp / "narracion.wav", PAUSA)

    vcodec = codificador(ffmpeg, ["libopenh264", "libx264", "mpeg4"])
    SALIDA_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(tmp / "escenas.txt"), "-i", str(tmp / "narracion.wav"),
        "-vf", "fps=25,format=yuv420p", "-c:v", vcodec, "-b:v", "700k",
        "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-shortest", "-movflags", "+faststart",
        "-metadata", "title=Montaje de la brida B (vídeo sintético de CidIA)", "-metadata", "language=spa",
        str(SALIDA_VIDEO),
    ], check=True)
    total = sum(duracion(w) + PAUSA for w in wavs)
    print(f"Vídeo: {SALIDA_VIDEO.relative_to(REPO)} ({total:.0f} s, {SALIDA_VIDEO.stat().st_size // 1024} KB, {vcodec})")


def notas_de_voz(ffmpeg: str, tmp: Path) -> None:
    notas = [(a["clave"], a["transcripcion"]) for a in actividad.APORTACIONES if a.get("transcripcion")]
    wavs = [(t, tmp / f"nota-{c}.wav") for c, t in notas]
    sintetizar(wavs, tmp)
    acodec = codificador(ffmpeg, ["libopus", "libvorbis"])
    SALIDA_AUDIO.mkdir(parents=True, exist_ok=True)
    AUDIO_SEMILLA.mkdir(parents=True, exist_ok=True)
    for (clave, _), (_, wav) in zip(notas, wavs, strict=True):
        destino = SALIDA_AUDIO / f"aportacion-{clave}.ogg"
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav), "-ac", "1",
                        "-c:a", acodec, "-b:a", "24k", str(destino)], check=True)
        shutil.copyfile(destino, AUDIO_SEMILLA / destino.name)
        print(f"Nota de voz: {destino.relative_to(REPO)} ({duracion(wav):.0f} s, {destino.stat().st_size // 1024} KB)")


def main() -> None:
    ffmpeg = buscar_ffmpeg()
    print(f"ffmpeg: {ffmpeg}")
    with tempfile.TemporaryDirectory(prefix="cidia-medios-") as d:
        tmp = Path(d)
        video(ffmpeg, tmp)
        notas_de_voz(ffmpeg, tmp)


if __name__ == "__main__":
    main()
