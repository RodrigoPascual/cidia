"""Montaje del vídeo de CidIA: escenas grabadas + narración + tarjetas de capítulo + rótulos.

    python herramientas/video/montaje.py <proyecto.json> --grabaciones <carpeta> --voces <carpeta>
           --salida <video.mp4> [--quemar-subtitulos] [--solo id1,id2] [--sin-transiciones]
           [--trabajo <carpeta>] [--conservar] [--bitrate 8M]

Qué hace con cada pieza del proyecto:
  * tarjeta: fondo #1F2328 con la marca, etiqueta, título y subtítulo en Fira Sans que entran con un
    fundido; dura lo que su narración (o «duracion_s», 3,2 s por defecto).
  * escena: el MP4 del grabador con su línea de tiempo rehecha:
      - las esperas largas marcadas por el grabador (esperarTexto...) se aceleran hasta
        «espera_objetivo_s» (1,8 s) y se rotulan: «Procesando en el servidor · acelerado ×N (X s reales)»;
      - cada fragmento de narración con «marca» empieza cuando la acción de esa marca; si la voz anterior
        aún no ha terminado, el vídeo se congela en esa marca hasta que termine (nunca se adelanta la voz);
      - el final se congela si la voz es más larga, o se recorta si sobra vídeo (se respeta hasta el
        final de la última acción, o hasta la marca «fin» si la hay);
      - rótulo inferior con «titulo» y «Bases: ...» los primeros «rotulo_s» segundos (7 por defecto).
Después: fundidos encadenados entre piezas (xfade de 0,5 s), narración completa normalizada a
-16 LUFS con loudnorm en dos pasadas, H.264 (libopenh264) + AAC a 1920x1080 y 30 fps, subtítulos .srt
(también como pista del MP4 y, con --quemar-subtitulos, dibujados en la imagen), capítulos en el MP4
(y en <salida>.capitulos.txt con el formato de YouTube) y un informe <salida>.informe.json.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from comun import en_entorno  # noqa: E402

en_entorno(['PIL', 'numpy'])

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

from comun import ACENTO, FUENTES, TINTA, cargar_proyecto, correr, ffmpeg, fuente, resolver  # noqa: E402

W, H, FPS, TASA = 1920, 1080, 30, 48000
XF = 0.5


# ---------- Utilidades ----------
def hex_rgb(h: str, a: int = 255) -> tuple[int, int, int, int]:
    h = h.lstrip('#')
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a


def F(peso: str, tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(fuente(peso), tam)


def envolver(texto: str, f: ImageFont.FreeTypeFont, ancho: int) -> list[str]:
    d = ImageDraw.Draw(Image.new('L', (1, 1)))
    lineas, actual = [], ''
    for w in texto.split():
        prueba = f'{actual} {w}'.strip()
        if d.textlength(prueba, font=f) <= ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = w
    if actual:
        lineas.append(actual)
    return lineas


def mmss(s: float) -> str:
    s = int(round(s))
    return f'{s // 60} min {s % 60:02d} s' if s >= 60 else f'{s} s'


def leer_wav(p: Path) -> np.ndarray:
    with wave.open(str(p), 'rb') as w:
        assert w.getframerate() == TASA and w.getnchannels() == 1 and w.getsampwidth() == 2, p
        return np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float32) / 32768


def escribir_wav(p: Path, x: np.ndarray) -> None:
    with wave.open(str(p), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TASA)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype('<i2').tobytes())


# ---------- Gráficos (Pillow) ----------
def logo(img: Image.Image, x: int, y: int, lado: int) -> None:
    """La marca CidIA (cuadrado amarillo con la C y el punto), dibujada a 4x y reducida."""
    s = 4
    L = lado * s
    capa = Image.new('RGBA', (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    k = L / 40
    d.rounded_rectangle([0, 0, L - 1, L - 1], radius=11 * k, fill=hex_rgb(ACENTO))
    cx, cy, r, g = 20.79 * k, 20 * k, 9.2 * k, 4.4 * k
    d.arc([cx - r - g / 2, cy - r - g / 2, cx + r + g / 2, cy + r + g / 2], 44, 316, fill=hex_rgb(TINTA), width=int(g))
    for ang in (44, 316):
        px, py = cx + r * math.cos(math.radians(ang)), cy + r * math.sin(math.radians(ang))
        d.ellipse([px - g / 2, py - g / 2, px + g / 2, py + g / 2], fill=hex_rgb(TINTA))
    d.ellipse([29.2 * k - 2.7 * k, cy - 2.7 * k, 29.2 * k + 2.7 * k, cy + 2.7 * k], fill=hex_rgb(TINTA))
    img.alpha_composite(capa.resize((lado, lado), Image.LANCZOS), (x, y))


def tarjeta_png(p: dict, fondo: Path, arco: Path, texto: Path) -> None:
    base = Image.new('RGBA', (W, H), hex_rgb(TINTA))  # liso: un degradado tan suave sale con bandas en H.264
    logo(base, 120, 92, 64)
    ImageDraw.Draw(base).text((202, 100), 'CidIA', font=F('bold', 44), fill=(255, 255, 255, 255))
    pie = p.get('pie', 'V DESAFÍO industrial · POLO positivo · Universidad de Burgos')
    ImageDraw.Draw(base).text((120, H - 110), pie, font=F('regular', 26), fill=(154, 163, 174, 255))
    base.convert('RGB').save(fondo)

    # Arco grande de la marca, muy tenue, que se desplaza despacio (capa aparte).
    s = 2
    capa = Image.new('RGBA', (900 * s, 900 * s), (0, 0, 0, 0))
    dc = ImageDraw.Draw(capa)
    dc.arc([60 * s, 60 * s, 840 * s, 840 * s], 44, 316, fill=hex_rgb(ACENTO, 34), width=110 * s)
    dc.ellipse([700 * s, 395 * s, 810 * s, 505 * s], fill=hex_rgb(ACENTO, 34))
    capa.resize((900, 900), Image.LANCZOS).save(arco)

    t = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dt = ImageDraw.Draw(t)
    x, ancho = 160, 1180
    ft, fs, fe = F('bold', int(p.get('tam_titulo', 92))), F('regular', 42), F('semibold', 30)
    lt = envolver(p.get('titulo', ''), ft, ancho)
    ls = envolver(p.get('subtitulo', ''), fs, ancho) if p.get('subtitulo') else []
    alto = (64 if p.get('etiqueta') else 0) + len(lt) * int(ft.size * 1.12) + (28 + len(ls) * int(fs.size * 1.32) if ls else 0)
    y = (H - alto) // 2 + 10
    if p.get('etiqueta'):
        dt.text((x, y), p['etiqueta'].upper(), font=fe, fill=hex_rgb(ACENTO))
        y += 64
    dt.rounded_rectangle([x - 44, y + 10, x - 34, y + len(lt) * int(ft.size * 1.12) - 14], radius=5, fill=hex_rgb(ACENTO))
    for l in lt:
        dt.text((x, y), l, font=ft, fill=(255, 255, 255, 255))
        y += int(ft.size * 1.12)
    if ls:
        y += 28
        for l in ls:
            dt.text((x, y), l, font=fs, fill=(214, 219, 225, 255))
            y += int(fs.size * 1.32)
    t.save(texto)


def panel(contenido: Image.Image, radio: int = 16, sombra: int = 22, borde_izq: bool = True) -> Image.Image:
    w, h = contenido.size
    out = Image.new('RGBA', (w + 2 * sombra, h + 2 * sombra), (0, 0, 0, 0))
    sm = Image.new('L', out.size, 0)
    ImageDraw.Draw(sm).rounded_rectangle([sombra, sombra + 6, sombra + w, sombra + h + 6], radius=radio, fill=120)
    sm = sm.filter(ImageFilter.GaussianBlur(sombra / 2))
    out.paste((0, 0, 0, 255), (0, 0), sm)
    caja = Image.new('RGBA', (w, h), hex_rgb(TINTA))
    if borde_izq:
        ImageDraw.Draw(caja).rectangle([0, 0, 6, h], fill=hex_rgb(ACENTO))
    mascara = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, w - 1, h - 1], radius=radio, fill=242)
    caja.putalpha(mascara)
    caja.alpha_composite(contenido)
    out.alpha_composite(caja, (sombra, sombra))
    return out


def rotulo_png(titulo: str, bases: str, destino: Path) -> tuple[int, int]:
    f1, f2b, f2 = F('semibold', 31), F('bold', 25), F('regular', 25)
    px, py, maxw = 34, 18, 900
    d0 = ImageDraw.Draw(Image.new('L', (1, 1)))
    if bases and not bases.lower().startswith('bases'):
        bases = 'Bases: ' + bases
    etiqueta, _, resto = bases.partition(':') if bases else ('', '', '')
    lt = envolver(titulo, f1, maxw) if titulo else []
    ancho_et = d0.textlength(etiqueta + ': ', font=f2b) if bases else 0
    lb = envolver(resto.strip(), f2, int(maxw - ancho_et)) if bases else []
    anchos = [d0.textlength(l, font=f1) for l in lt] + [ancho_et + (d0.textlength(lb[0], font=f2) if lb else 0)] + [ancho_et + d0.textlength(l, font=f2) for l in lb[1:]]
    w = int(max(anchos or [200])) + 2 * px + 8
    h = py * 2 + len(lt) * 40 + (8 if lt and lb else 0) + len(lb) * 33
    c = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    y = py - 2
    for l in lt:
        d.text((px + 8, y), l, font=f1, fill=(255, 255, 255, 255))
        y += 40
    if lb:
        y += 8
        d.text((px + 8, y), etiqueta + ':', font=f2b, fill=hex_rgb(ACENTO))
        for i, l in enumerate(lb):
            d.text((px + 8 + ancho_et, y), l, font=f2, fill=(226, 230, 234, 255))
            y += 33
    img = panel(c)
    img.save(destino)
    return img.size


def acelerado_png(texto: str, destino: Path) -> tuple[int, int]:
    f = F('semibold', 26)
    d0 = ImageDraw.Draw(Image.new('L', (1, 1)))
    tw = int(d0.textlength(texto, font=f))
    w, h = tw + 96, 56
    c = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    # Icono de avance rápido (dos triángulos).
    for dx in (24, 42):
        d.polygon([(dx, 17), (dx, 39), (dx + 17, 28)], fill=hex_rgb(ACENTO))
    d.text((74, 12), texto, font=f, fill=(255, 255, 255, 255))
    img = panel(c, radio=28, borde_izq=False)
    img.save(destino)
    return img.size


# ---------- Fondo musical ----------
def fondo_musical(n: int, voz: np.ndarray, nivel_db: float = -17.0) -> np.ndarray:
    """Colchón de acordes suaves sintetizado aquí (no usa ninguna grabación ni muestra de terceros):
    La m9 · Fa maj7 · Do maj7 · Sol 6, 7 s por acorde con fundidos largos, senos con armónicos suaves y
    un leve desafinado (nada pasa de 1,2 kHz) y una respiración muy lenta. Se agacha 7 dB mientras habla el
    narrador. `nivel_db`: RMS del fondo respecto al RMS de la voz cuando suena."""
    nota = lambda m: 440.0 * 2 ** ((m - 69) / 12)  # noqa: E731
    acordes = [[45, 52, 55, 59, 60, 64], [41, 48, 52, 57, 60, 64], [48, 55, 59, 62, 64, 67], [43, 50, 52, 55, 59, 62]]
    dur, xf = 7.0, 2.5
    t_total = n / TASA
    salida = np.zeros(n, dtype=np.float32)
    k, t0 = 0, 0.0
    rng = np.random.default_rng(7)
    while t0 < t_total:
        a0, a1 = max(0.0, t0 - xf), min(t_total, t0 + dur + xf)
        i0, i1 = int(a0 * TASA), int(a1 * TASA)
        tt = np.arange(i1 - i0, dtype=np.float64) / TASA
        env = np.ones_like(tt)
        sube = np.clip(tt / xf, 0, 1)
        baja = np.clip((tt[-1] - tt) / xf, 0, 1)
        env = np.sin(np.pi / 2 * np.minimum(sube, baja)) ** 2
        seg = np.zeros_like(tt)
        for j, m in enumerate(acordes[k % len(acordes)]):
            f = nota(m)
            peso = 1.0 if j else 1.3
            for d in (-0.0016, 0.0016):
                fase = rng.uniform(0, 2 * np.pi)
                seg += peso * (np.sin(2 * np.pi * f * (1 + d) * tt + fase) + 0.22 * np.sin(4 * np.pi * f * (1 + d) * tt + fase)
                               + 0.06 * np.sin(6 * np.pi * f * (1 + d) * tt + fase))
        seg *= env * (0.85 + 0.15 * np.sin(2 * np.pi * 0.09 * (tt + a0)))
        salida[i0:i1] += seg.astype(np.float32)
        t0 += dur
        k += 1
    # Sin filtro: los parciales más agudos (3 × Sol 4) no pasan de 1,2 kHz, así que ya suena cálido.
    y = salida
    # Nivel: RMS del fondo = RMS de la voz (donde suena) + nivel_db; se agacha 7 dB bajo la voz.
    activa = np.abs(voz) > 0.01
    rms_voz = float(np.sqrt(np.mean(voz[activa] ** 2))) if activa.any() else 0.1
    y *= (rms_voz * 10 ** (nivel_db / 20)) / max(1e-9, float(np.sqrt(np.mean(y ** 2))))
    # Envolvente de la voz a 100 Hz (bloques de 10 ms), suavizada, y de vuelta a 48 kHz.
    blq = TASA // 100
    nb = int(np.ceil(n / blq))
    v = np.zeros(nb * blq, dtype=np.float32)
    v[:len(voz)] = np.abs(voz)
    env = v.reshape(nb, blq).mean(axis=1)

    def media_movil(x: np.ndarray, w: int) -> np.ndarray:
        c = np.concatenate([[0.0], np.cumsum(x, dtype=np.float64)])
        i = np.arange(len(x))
        a0, b0 = np.clip(i - w // 2, 0, len(x)), np.clip(i + w // 2 + 1, 0, len(x))
        return (c[b0] - c[a0]) / (b0 - a0)

    hay = media_movil(np.clip(media_movil(env, 25) / 0.02, 0, 1), 60)
    hay_voz = np.repeat(hay.astype(np.float32), blq)[:n]
    y *= (1 - (1 - 10 ** (-7 / 20)) * hay_voz).astype(np.float32)
    fade = int(2.5 * TASA)
    y[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
    y[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return y.astype(np.float32)


# ---------- Subtítulos ----------
_ENLACES = {'a', 'al', 'con', 'de', 'del', 'el', 'en', 'la', 'las', 'lo', 'los', 'para', 'por', 'que', 'se', 'su', 'sus',
            'un', 'una', 'y', 'o', 'e', 'ni', 'sin', 'como', 'mas', 'más', 'le', 'les', 'muy', 'si', 'sí', 'qué', 'cada'}


def trocear_subtitulo(texto: str, maximo: int = 90) -> list[str]:
    """Trozos de subtítulo de hasta `maximo` caracteres: una frase por trozo y, si es larga, partida en
    trozos de longitud parecida, mejor detrás de una coma que en cualquier espacio."""
    trozos: list[str] = []
    for fr in (f for f in re.split(r'(?<=[.!?…:;])\s+', texto.strip()) if f):
        n = math.ceil(len(fr) / maximo)
        cortes, inicio = [], 0
        for k in range(1, n):
            ideal = k * len(fr) / n
            comas = [m.end() for m in re.finditer(r'[,;:]\s', fr) if abs(m.end() - ideal) <= 16 and m.end() > inicio + 12]
            espacios = [m.end() for m in re.finditer(' ', fr) if m.end() > inicio + 12]
            c = min(comas or espacios or [int(ideal)], key=lambda c: abs(c - ideal))
            # Un trozo no debe acabar en «para la», «de», «y»...: el corte pasa delante de esas palabras.
            for _ in range(3):
                antes = fr[inicio:c].rstrip().rsplit(' ', 1)
                if len(antes) == 2 and antes[1].lower() in _ENLACES and c - len(antes[1]) - 1 > inicio + 12:
                    c = inicio + len(antes[0]) + 1
                else:
                    break
            cortes.append(c)
            inicio = c
        trozos += [fr[i:j].strip() for i, j in zip([0, *cortes], [*cortes, len(fr)]) if fr[i:j].strip()]
    # Un trozo muy corto («Esto es CidIA:», «Todo bien:», «y la publica.») se junta con el siguiente (o, si es el
    # último, con el anterior) cuando caben: solo, estaría en pantalla menos de un segundo.
    juntos: list[str] = []
    for z in trozos:
        if juntos and len(juntos[-1]) < 28 and len(juntos[-1]) + 1 + len(z) <= maximo + 8:
            juntos[-1] = f'{juntos[-1]} {z}'
        else:
            juntos.append(z)
    if len(juntos) > 1 and len(juntos[-1]) < 20 and len(juntos[-2]) + 1 + len(juntos[-1]) <= maximo + 4:
        juntos[-2:] = [f'{juntos[-2]} {juntos[-1]}']
    return juntos


def ordenar_subtitulos(cues: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """En orden de aparición (la voz del micrófono se coloca después que la narración) y sin solaparse: cada uno
    dura al menos 0,8 s, pero sin pisar al siguiente."""
    cues = sorted(cues, key=lambda c: c[0])
    fuera = []
    for k, (x0, x1, z) in enumerate(cues):
        fin = max(x1, x0 + 0.8)
        if k + 1 < len(cues):
            fin = min(fin, max(x1, cues[k + 1][0] - 0.04))
        fuera.append((x0, fin, z))
    return fuera


def t_srt(s: float) -> str:
    ms = int(round(s * 1000))
    return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'


def t_ass(s: float) -> str:
    cs = int(round(s * 100))
    return f'{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}'


def partir_lineas(t: str, maximo: int = 46) -> str:
    """Dos líneas equilibradas si el texto es largo; mejor detrás de una coma cerca del centro."""
    if len(t) <= maximo:
        return t
    mitad = len(t) / 2
    cands = []
    for m in re.finditer(' ', t):
        c = m.start()
        coste = abs(c - mitad) - (10 if t[c - 1] in ',;:' else 0)
        coste += 12 if t[:c].rsplit(' ', 1)[-1].lower() in _ENLACES else 0
        coste += 14 if t[c + 1:c + 2].isdigit() else 0  # no separar «nivel 3», «prensa 3», «paso 5»
        coste += 2 * max(0, max(c, len(t) - c - 1) - maximo)  # ninguna línea mucho más larga que la otra
        cands.append((coste, c))
    if not cands:
        return t
    c = min(cands)[1]
    return t[:c] + '\n' + t[c + 1:]


# ---------- Línea de tiempo de una escena ----------
def planificar(p: dict, inf: dict, voz: dict | None, a: argparse.Namespace) -> dict:
    D = inf['duracion_ms'] / 1000
    marcas = {m['nombre']: m['t'] / 1000 for m in inf.get('marcas', [])}
    umbral = float(p.get('umbral_espera_s', 2.5))
    objetivo = float(p.get('espera_objetivo_s', 1.8))
    tramos, t = [], 0.0
    # «recortes»: tramos de la grabación que se quitan (s, en tiempo de grabación), por ejemplo un rato con
    # la pantalla quieta. Se tratan como tramos con velocidad infinita y sin rótulo.
    eventos = [(e['inicio'] / 1000, e['fin'] / 1000, e) for e in inf.get('esperas', [])]
    eventos += [(float(a0), float(b0), None) for a0, b0 in p.get('recortes', [])]
    # «acelerar_tramos»: ratos sin espera del servidor que se alargan (por ejemplo, un tecleo largo) y que el
    # montaje acelera con su rótulo, igual que las esperas. Se indican con las acciones del informe que abarcan
    # («acciones»: [primera, última], desde el final de la anterior) o en segundos («desde», «hasta»).
    acciones = inf.get('acciones', [])
    for tr in p.get('acelerar_tramos', []):
        if 'acciones' in tr:
            i0, i1 = tr['acciones']
            a0 = acciones[i0 - 1]['fin'] / 1000 if i0 > 0 else 0.0
            b0 = acciones[i1]['fin'] / 1000
        else:
            a0, b0 = float(tr['desde']), float(tr['hasta'])
        eventos.append((a0, b0, {'inicio': a0 * 1000, 'fin': b0 * 1000, 'acelerar': tr.get('etiqueta') or 'Acelerado',
                                 'factor': float(tr['factor'])}))
    for ini, fin, e in sorted(eventos, key=lambda x: x[0]):
        if e is None:
            if ini < t or fin <= ini:
                continue
            if ini > t:
                tramos.append({'a': t, 'b': ini, 'f': 1.0})
            tramos.append({'a': ini, 'b': min(fin, D), 'f': 1e9, 'corte': True})
            t = min(fin, D)
            continue
        if e.get('acelerar', True) is False or fin - ini <= umbral or ini < t:
            continue
        f = float(e.get('factor') or (fin - ini) / objetivo)
        if f < 1.4:
            continue
        if ini > t:
            tramos.append({'a': t, 'b': ini, 'f': 1.0})
        etiqueta = e['acelerar'] if isinstance(e.get('acelerar'), str) else 'Procesando en el servidor'
        tramos.append({'a': ini, 'b': fin, 'f': f, 'etiqueta': etiqueta, 'real': fin - ini})
        t = fin
    tramos.append({'a': t, 'b': D, 'f': 1.0})
    congelar: dict[float, float] = {}

    def M(ts: float) -> float:
        out = 0.0
        for tr in tramos:
            if ts <= tr['a']:
                break
            out += (min(ts, tr['b']) - tr['a']) / tr['f']
        return out + sum(v for k, v in congelar.items() if k <= ts)

    hueco, inicio_voz, desfase = float(p.get('hueco_voz_s', 0.35)), float(p.get('inicio_voz_s', 0.6)), 0.15
    colocados, fin_prev, avisos = [], None, []
    for fr in (voz or {}).get('fragmentos', []):
        ini_min = inicio_voz if fin_prev is None else fin_prev + (fr.get('tras') or hueco)
        m = fr.get('marca')
        if m and m not in marcas:
            avisos.append(f'la marca «{m}» no está en la grabación')
            m = None
        if m:
            k = marcas[m]
            ancla = M(k) + desfase
            if ini_min > ancla + 0.2:
                congelar[k] = congelar.get(k, 0) + (ini_min - ancla)
                ancla = M(k) + desfase
            ini = max(ancla, ini_min)
        else:
            ini = ini_min
        colocados.append({'ini': ini, 'fin': ini + fr['duracion'], 'wav': fr['wav'], 'texto': fr['texto'], 'n': fr['n']})
        fin_prev = ini + fr['duracion']

    V = M(D)
    if 'fin' in marcas:
        fin_min = M(marcas['fin']) + 0.3
    else:
        utiles = [x for x in inf.get('acciones', []) if x['tipo'] not in ('esperar', 'marca', 'esperarVoz', 'microfono')]
        fin_min = (M(utiles[-1]['fin'] / 1000) if utiles else V) + float(p.get('cola_accion_s', 0.9))
    if p.get('recortar', True) is False:
        fin_min = V
    final = max((fin_prev or 0) + float(p.get('cola_voz_s', 1.0)), min(fin_min, V), float(p.get('duracion_min_s', 2.0)))
    if final > V + 1 / FPS:
        congelar[D] = congelar.get(D, 0) + (final - V)

    # Segmentos para ffmpeg: tramos partidos en los puntos de congelación.
    cortes = sorted({0.0, D, *[tr['a'] for tr in tramos], *[k for k in congelar if 0 < k < D]})
    segs = []
    for x0, x1 in zip(cortes, cortes[1:]):
        if x1 - x0 < 1e-6:
            continue
        tr = next(tr for tr in tramos if tr['a'] - 1e-6 <= x0 < tr['b'] - 1e-6)
        segs.append({'a': x0, 'b': x1, 'f': tr['f'], 'pad_fin': congelar.get(x1, 0.0), 'corte': tr.get('corte', False)})
    # Un segmento de menos de un fotograma no da imagen: su congelación pasa al anterior. Los recortes no
    # se montan (su congelación, si la hay, también pasa al anterior).
    limpios = []
    for s in segs:
        if s['corte']:
            if limpios:
                limpios[-1]['pad_fin'] += s['pad_fin']
            continue
        if (s['b'] - s['a']) / s['f'] < 1.5 / FPS and limpios:
            limpios[-1]['b'] = s['b']
            limpios[-1]['pad_fin'] += s['pad_fin']
        else:
            limpios.append(s)
    pad_ini = congelar.get(0.0, 0.0)
    etiquetas = [{'ini': M(tr['a']), 'fin': M(tr['b']) - sum(v for k, v in congelar.items() if tr['a'] < k <= tr['b']),
                  'texto': f"{tr['etiqueta']} · acelerado ×{tr['f']:.0f} ({mmss(tr['real'])} reales)"}
                 for tr in tramos if tr['f'] > 1 and not tr.get('corte')]
    # «oir_microfono»: lo que «dice» el micrófono falso (la pregunta por voz) también se oye en el vídeo,
    # cuando empieza a grabar (y solo si ese rato no va acelerado). Con «texto_microfono», lleva subtítulo.
    oido = []
    if p.get('oir_microfono') and p.get('microfono') and inf.get('micro'):
        wav = resolver(p['microfono'], Path(p.get('_dir', '.')), {'voces': str(Path(a.voces).resolve())})
        with wave.open(str(wav), 'rb') as w:
            dur_wav = w.getnframes() / w.getframerate()
        for m in inf['micro']:
            tm = m['t'] / 1000
            tr = next((tr for tr in tramos if tr['a'] - 1e-6 <= tm < tr['b']), None)
            if tr is None or tr['f'] > 1:
                continue
            ini = M(tm) + float(p.get('desfase_microfono_s', 0.15))
            texto = p.get('texto_microfono')
            oido.append({'ini': ini, 'fin': ini + dur_wav, 'wav': str(wav), 'texto': f'«{texto}»' if texto else '', 'n': 0,
                         'microfono': True, 'ganancia': float(p.get('ganancia_microfono', 0.85))})
    return {'duracion': round(final, 3), 'segmentos': limpios, 'pad_ini': pad_ini, 'voz': colocados + oido, 'etiquetas': etiquetas,
            'congelado_s': round(sum(congelar.values()), 2),
            'acelerado': [round(tr['f'], 1) for tr in tramos if tr['f'] > 1 and not tr.get('corte')],
            'recortado_s': round(sum(tr['b'] - tr['a'] for tr in tramos if tr.get('corte')), 2), 'avisos': avisos}


# ---------- Render de piezas ----------
def overlay_png(fc: list, entrada: int, cur: str, sig: str, x: str, y: str, t0: float, t1: float, d: float = 0.35) -> None:
    fc.append(f'[{entrada}:v]format=rgba,fade=t=in:st={t0:.3f}:d={d}:alpha=1,fade=t=out:st={max(t0 + d, t1 - d):.3f}:d={d}:alpha=1,'
              f'scale=out_color_matrix=bt709:out_range=tv,format=yuva420p[o{entrada}]')
    fc.append(f'[{cur}][o{entrada}]overlay=x={x}:y={y}:format=auto[{sig}]')


def claves(tiempos: list[float]) -> list[str]:
    """Fotogramas clave forzados justo después de que desaparezca un rótulo: OpenH264 deja a veces un
    rastro tenue del rótulo en zonas oscuras y casi quietas hasta el siguiente fotograma clave."""
    t = sorted({round(x, 2) for x in tiempos if x > 0.1})
    return ['-force_key_frames', ','.join(f'{x:.2f}' for x in t)] if t else []


def codificar(args: list[str], fc: list[str], salida: Path, dur: float, bitrate: str, cwd: Path, fk: list[float] | None = None) -> None:
    correr([ffmpeg(), '-y', '-hide_banner', '-loglevel', 'error', *args, '-filter_complex', ';'.join(fc), '-map', '[v]', '-an',
            *claves(fk or []),
            '-c:v', 'libopenh264', '-profile:v', 'high', '-b:v', bitrate, '-maxrate', '40M', '-g', '30', '-r', str(FPS),
            '-t', f'{dur:.3f}', '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
            str(salida)], cwd=cwd)


def render_tarjeta(p: dict, voz: dict | None, trab: Path) -> dict:
    pid = p['id']
    fondo, arco, texto = trab / f'{pid}-fondo.png', trab / f'{pid}-arco.png', trab / f'{pid}-texto.png'
    tarjeta_png(p, fondo, arco, texto)
    colocados, t = [], float(p.get('inicio_voz_s', 0.8))
    for fr in (voz or {}).get('fragmentos', []):
        colocados.append({'ini': t, 'fin': t + fr['duracion'], 'wav': fr['wav'], 'texto': fr['texto'], 'n': fr['n']})
        t += fr['duracion'] + float(fr.get('tras') or 0.35)
    fin_voz = colocados[-1]['fin'] if colocados else 0
    dur = round(max(float(p.get('duracion_s', 3.2)), fin_voz + 1.0), 3)
    clip = trab / f'{pid}.mp4'
    args = []
    for f in (fondo, arco, texto):
        args += ['-loop', '1', '-framerate', str(FPS), '-t', f'{dur:.3f}', '-i', f.name]
    fc = ['[0:v]scale=out_color_matrix=bt709:out_range=tv,format=yuv420p[f]',
          '[1:v]format=rgba,scale=out_color_matrix=bt709:out_range=tv,format=yuva420p[a]',
          "[f][a]overlay=x='1180-t*7':y=150:format=auto[fa]",
          '[2:v]format=rgba,fade=t=in:st=0.3:d=0.7:alpha=1,scale=out_color_matrix=bt709:out_range=tv,format=yuva420p[t]',
          "[fa][t]overlay=x=0:y='if(lt(t,0.3),28,if(lt(t,1.0),28*(1-(t-0.3)/0.7),0))':format=auto,format=yuv420p[v]"]
    codificar(args, fc, clip, dur, '12M', trab)
    return {'id': pid, 'tipo': 'tarjeta', 'duracion': dur, 'clip': clip, 'voz': colocados, 'claves': []}


def render_escena(p: dict, voz: dict | None, a: argparse.Namespace, trab: Path) -> dict:
    pid = p['id']
    video = Path(a.grabaciones) / f'{pid}.mp4'
    inf = json.loads((Path(a.grabaciones) / f'{pid}.json').read_text(encoding='utf-8'))
    if not video.exists():
        raise FileNotFoundError(f'Falta la grabación de {pid}: {video}')
    plan = planificar(p, inf, voz, a)
    dur = plan['duracion']
    args = ['-i', str(video)]
    segs = plan['segmentos']
    fc = [f'[0:v]split={len(segs)}' + ''.join(f'[e{i}]' for i in range(len(segs)))]
    for i, s in enumerate(segs):
        c = f"[e{i}]trim=start={s['a']:.4f}:end={s['b']:.4f},setpts=(PTS-STARTPTS)/{s['f']:.5f}"
        if s['f'] != 1:
            c += f',fps={FPS}'
        if i == 0 and plan['pad_ini'] > 0:
            c += f",tpad=start_mode=clone:start_duration={plan['pad_ini']:.3f}"
        if s['pad_fin'] > 0:
            c += f",tpad=stop_mode=clone:stop_duration={s['pad_fin']:.3f}"
        fc.append(c + f'[s{i}]')
    fc.append(''.join(f'[s{i}]' for i in range(len(segs))) + f'concat=n={len(segs)}:v=1:a=0,fps={FPS},'
              f'trim=duration={dur:.3f},setpts=PTS-STARTPTS[b0]')
    cur, n_in, fk = 'b0', 1, []
    if (p.get('titulo') or p.get('bases')) and dur > 3:
        png = trab / f'{pid}-rotulo.png'
        _, h = rotulo_png(p.get('titulo', ''), p.get('bases', ''), png)
        args += ['-loop', '1', '-framerate', str(FPS), '-t', f'{dur:.3f}', '-i', png.name]
        y = H - h - (150 if a.quemar_subtitulos else 24)
        t1 = min(dur - 0.5, 0.45 + float(p.get('rotulo_s', 7.0)))
        x = '14' if p.get('rotulo_pos', 'izquierda') == 'izquierda' else f'W-w-14'
        overlay_png(fc, n_in, cur, f'b{n_in}', x, str(y), 0.45, t1)
        cur, n_in = f'b{n_in}', n_in + 1
        fk.append(t1 + 0.05)
    for k, et in enumerate(plan['etiquetas']):
        if et['fin'] - et['ini'] < 0.4:
            continue
        png = trab / f'{pid}-acelerado-{k}.png'
        acelerado_png(et['texto'], png)
        args += ['-loop', '1', '-framerate', str(FPS), '-t', f'{dur:.3f}', '-i', png.name]
        overlay_png(fc, n_in, cur, f'b{n_in}', '(W-w)/2', '18', et['ini'], et['fin'], 0.2)
        cur, n_in = f'b{n_in}', n_in + 1
        fk.append(et['fin'] + 0.05)
    fc.append(f'[{cur}]format=yuv420p[v]')
    clip = trab / f'{pid}.mp4'
    codificar(args, fc, clip, dur, '16M', trab, fk)
    problemas = (inf.get('fallos') or []) + (inf.get('excepciones') or []) + (inf.get('peticiones_fallidas') or [])
    return {'id': pid, 'tipo': 'escena', 'duracion': dur, 'clip': clip, 'voz': plan['voz'], 'claves': fk,
            'plan': {k: plan[k] for k in ('congelado_s', 'acelerado', 'recortado_s', 'avisos')}, 'problemas_grabacion': problemas,
            'grabado_s': round(inf['duracion_ms'] / 1000, 1)}


# ---------- Programa ----------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('proyecto')
    ap.add_argument('--grabaciones', required=True)
    ap.add_argument('--voces', required=True)
    ap.add_argument('--salida', required=True)
    ap.add_argument('--trabajo')
    ap.add_argument('--solo', help='ids de piezas separados por comas (para revisar una parte)')
    ap.add_argument('--quemar-subtitulos', action='store_true')
    ap.add_argument('--sin-transiciones', action='store_true')
    ap.add_argument('--bitrate', default='8M')
    ap.add_argument('--conservar', action='store_true', help='no borra la carpeta de trabajo')
    ap.add_argument('--musica', action='store_true', help='fondo musical sintetizado aquí mismo (sin licencias de terceros)')
    ap.add_argument('--musica-db', default='-17', help='nivel del fondo respecto a la voz, en dB (por defecto -17)')
    a = ap.parse_args()

    proyecto, piezas = cargar_proyecto(a.proyecto)
    salida = Path(a.salida).resolve()
    salida.parent.mkdir(parents=True, exist_ok=True)
    trab = Path(a.trabajo).resolve() if a.trabajo else salida.with_name('.montaje-' + salida.stem)
    trab.mkdir(parents=True, exist_ok=True)
    voces = Path(a.voces).resolve()
    solo = set(a.solo.split(',')) if a.solo else None

    hechas = []
    for p in piezas:
        if solo and p['id'] not in solo:
            continue
        fv = voces / f"{p['id']}.json"
        voz = json.loads(fv.read_text(encoding='utf-8')) if fv.exists() else None
        for fr in (voz or {}).get('fragmentos', []):
            # Si la carpeta de voces se ha movido, los WAV están junto a su índice (<voces>/<id>/NN.wav).
            if not Path(fr['wav']).exists():
                fr['wav'] = str(voces / p['id'] / Path(fr['wav']).name)
        if p.get('narracion') and not voz:
            print(f"  aviso: {p['id']} tiene narración pero no está sintetizada (voz.py narrar)")
        r = render_tarjeta(p, voz, trab) if p['tipo'] == 'tarjeta' else render_escena(p, voz, a, trab)
        r['capitulo'] = p.get('capitulo')
        hechas.append(r)
        extra = f" congelado {r['plan']['congelado_s']} s, acelerado {r['plan']['acelerado']}" if r['tipo'] == 'escena' else ''
        print(f"  {r['id']:<28} {r['duracion']:6.1f} s{extra}")

    xf = 0 if a.sin_transiciones or len(hechas) < 2 else XF
    inicios, t = [], 0.0
    for r in hechas:
        inicios.append(t)
        t += r['duracion'] - xf
    total = t + xf

    # Narración completa (una sola pista) y subtítulos con los tiempos finales.
    pista = np.zeros(int(total * TASA) + TASA, dtype=np.float32)
    cues = []
    for r, t0 in zip(hechas, inicios):
        for c in r['voz']:
            x = leer_wav(Path(c['wav'])) * float(c.get('ganancia', 1.0))
            i = int(round((t0 + c['ini']) * TASA))
            pista[i:i + len(x)] += x[:len(pista) - i]
            trozos = trocear_subtitulo(c['texto'])
            pesos = [len(z) for z in trozos]
            acum, dur = 0, c['fin'] - c['ini']
            for z, w in zip(trozos, pesos):
                ini = t0 + c['ini'] + dur * acum / sum(pesos)
                acum += w
                cues.append((ini, t0 + c['ini'] + dur * acum / sum(pesos), z))
    pista = pista[:int(total * TASA)]
    if a.musica:
        pista = pista + fondo_musical(len(pista), pista, float(a.musica_db))
    wav = trab / 'narracion.wav'
    escribir_wav(wav, pista)

    cues = ordenar_subtitulos(cues)
    srt = salida.with_suffix('.srt')
    srt.write_text(''.join(f'{i}\n{t_srt(x0)} --> {t_srt(x1)}\n{partir_lineas(z)}\n\n' for i, (x0, x1, z) in enumerate(cues, 1)),
                   encoding='utf-8')
    shutil.copy(srt, trab / 'subtitulos.srt')

    # Capítulos: en el MP4 (ffmetadata) y en texto para YouTube.
    caps = []  # un capítulo por cada cambio de «capitulo» (varias piezas seguidas comparten capítulo)
    for r, t0 in zip(hechas, inicios):
        if r.get('capitulo') and (not caps or caps[-1][1] != r['capitulo']):
            caps.append((t0, r['capitulo']))
    if caps and caps[0][0] > 0:
        caps.insert(0, (0.0, 'Inicio'))
    meta = [';FFMETADATA1', f"title={proyecto.get('titulo', 'CidIA')}", 'artist=CidIA', 'language=spa']
    for k, (t0, nombre) in enumerate(caps):
        t1 = caps[k + 1][0] if k + 1 < len(caps) else total
        meta += ['[CHAPTER]', 'TIMEBASE=1/1000', f'START={int(t0 * 1000)}', f'END={int(t1 * 1000)}', f'title={nombre}']
    (trab / 'capitulos.ffmeta').write_text('\n'.join(meta) + '\n', encoding='utf-8')
    salida.with_suffix('.capitulos.txt').write_text(
        ''.join(f'{int(t0 // 60)}:{int(t0 % 60):02d} {nombre}\n' for t0, nombre in caps), encoding='utf-8')

    # Volumen: loudnorm en dos pasadas sobre la narración completa.
    med = correr([ffmpeg(), '-hide_banner', '-nostats', '-i', str(wav), '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'])
    m = json.loads(med.stderr[med.stderr.rindex('{'):med.stderr.rindex('}') + 1])
    norm = 'anull' if not cues or 'inf' in str(m['input_i']) else (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
            f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")

    # Subtítulos dibujados (opcional): ASS con Fira Sans y caja oscura.
    if a.quemar_subtitulos:
        dir_f = trab / 'fuentes'
        dir_f.mkdir(exist_ok=True)
        for f in FUENTES.glob('*.ttf'):
            shutil.copy(f, dir_f / f.name)
        cab = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 0\nYCbCr Matrix: TV.709\n\n'
               '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, '
               'Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
               'Style: CidIA,Fira Sans Medium,44,&H00FFFFFF,&H00FFFFFF,&H28282321,&H00000000,0,0,0,0,100,100,0,0,3,12,0,2,240,240,46,1\n\n'
               '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
        (trab / 'subtitulos.ass').write_text(cab + ''.join(
            f"Dialogue: 0,{t_ass(x0)},{t_ass(x1)},CidIA,,0,0,0,,{partir_lineas(z).replace(chr(10), chr(92) + 'N')}\n"
            for x0, x1, z in cues), encoding='utf-8')

    n = len(hechas)
    args = []
    for r in hechas:
        args += ['-i', r['clip'].name]
    args += ['-i', wav.name, '-i', 'capitulos.ffmeta', '-i', 'subtitulos.srt']
    fc = [f'[{i}:v]fps={FPS},format=yuv420p,setsar=1,settb=AVTB[v{i}]' for i in range(n)]
    if n == 1:
        ult = 'v0'
    elif xf:
        prev = 'v0'
        for i in range(1, n):
            off = inicios[i]
            fc.append(f'[{prev}][v{i}]xfade=transition=fade:duration={xf}:offset={off:.3f}[x{i}]')
            prev = f'x{i}'
        ult = prev
    else:
        fc.append(''.join(f'[v{i}]' for i in range(n)) + f'concat=n={n}:v=1:a=0[xc]')
        ult = 'xc'
    fc.append(f'[{ult}]' + ('subtitles=filename=subtitulos.ass:fontsdir=fuentes,' if a.quemar_subtitulos else '') + 'format=yuv420p[v]')
    fc.append(f'[{n}:a]{norm},aformat=channel_layouts=stereo[a]')
    tmp = trab / ('final' + salida.suffix)
    # Claves forzadas: tras cada rótulo y al final de cada fundido entre piezas.
    fk = [t0 + x for r, t0 in zip(hechas, inicios) for x in r['claves']] + [t0 + xf for t0 in inicios[1:]]
    correr([ffmpeg(), '-y', '-hide_banner', '-loglevel', 'error', *args, '-filter_complex', ';'.join(fc),
            '-map', '[v]', '-map', '[a]', '-map', f'{n + 2}:s', '-map_metadata', str(n + 1), '-map_chapters', str(n + 1),
            *claves(fk),
            '-c:v', 'libopenh264', '-profile:v', 'high', '-b:v', a.bitrate, '-maxrate', '16M', '-g', '60', '-r', str(FPS),
            '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
            '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-c:s', 'mov_text', '-metadata:s:s:0', 'language=spa',
            '-metadata:s:a:0', 'language=spa', '-t', f'{total:.3f}', '-movflags', '+faststart', tmp.name], cwd=trab)
    shutil.move(str(tmp), salida)

    informe = {'salida': str(salida), 'duracion_s': round(total, 2), 'subtitulos': str(srt), 'capitulos': [[round(t0, 2), c] for t0, c in caps],
               'loudnorm_entrada': {k: m[k] for k in ('input_i', 'input_tp', 'input_lra')},
               'piezas': [{k: v for k, v in r.items() if k not in ('clip', 'voz', 'claves')} | {'inicio_s': round(t0, 2)} for r, t0 in zip(hechas, inicios)]}
    salida.with_suffix('.informe.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    if not a.conservar:
        shutil.rmtree(trab, ignore_errors=True)
    print(f'Listo: {salida}  ({total / 60:.1f} min, {len(cues)} subtítulos, {len(caps)} capítulos)')


if __name__ == '__main__':
    main()
