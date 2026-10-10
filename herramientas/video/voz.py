"""Voz en castellano para los vídeos de CidIA, sintetizada en local.

    python herramientas/video/voz.py narrar <proyecto.json | escena.json> --salida <carpeta de voces>
    python herramientas/video/voz.py frase "¿Qué llave uso para apretar los tornillos?" --salida llave.wav --microfono
    python herramientas/video/voz.py comparar --salida <carpeta> [--asr --secretos cidia.env]
    python herramientas/video/voz.py voces

Voces («motor:voz»):
  kokoro:em_alex, kokoro:ef_dora   Kokoro-82M (Apache-2.0), la elegida: narrador em_alex y
                                   preguntas al micrófono ef_dora (ver README)
  piper:es_ES-carlfm-x_low         Piper (MIT) con voz de dominio público (calidad baja)
  piper:es_ES-davefx-medium        solo para comparar (afinada desde lessac: uso comercial dudoso)
  onecore:Microsoft Laura | Pablo | Helena, sapi:Microsoft Helena Desktop   voces de Windows

`narrar` genera un WAV por fragmento de narración de cada pieza (tarjetas y escenas) en
<salida>/<id>/NN.wav y un <salida>/<id>.json con el texto, lo que se dice (tras pronunciacion.json),
la duración y la marca a la que va asociado. Solo vuelve a sintetizar lo que ha cambiado.
Pausas: entre frases (--pausa-frase), tras dos puntos o punto y coma (la mitad) y con «[pausa 600]»
dentro del texto. Velocidad: 0,95 para narrar (unas 158 palabras por minuto) y 1,0 para `frase`;
cada pieza puede llevar su "voz" y su "velocidad". Todo se guarda a 48 kHz, mono, 16 bits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from comun import AQUI, HERR, cargar_proyecto, correr, ffmpeg  # noqa: E402

NARRADOR = 'kokoro:em_alex'
VOZ_MICROFONO = 'kokoro:ef_dora'
TASA = 48000
FRASE_COMPARAR = ('Carmen es la que sabe montar la brida B de la línea 2. Cuando se jubile, ese conocimiento se pierde. '
                  'CidIA lo captura, lo enseña en el puesto y mide quién lo domina: cuatro tornillos en cruz a 25 N·m, '
                  'con llave dinamométrica de 1/2".')
PREGUNTA_COMPARAR = '¿Qué llave uso para apretar los tornillos?'


# ---------- Texto ----------
def pronunciar(texto: str) -> str:
    reglas = json.loads((AQUI / 'pronunciacion.json').read_text(encoding='utf-8'))['reemplazos']
    for patron, por in reglas:
        texto = re.sub(patron, por, texto)
    return re.sub(r'\s+', ' ', texto).strip()


def trocear(texto: str, pausa_frase: float) -> list[tuple[str, float]]:
    """Frases con el silencio que va detrás de cada una."""
    partes: list[tuple[str, float]] = []
    for bloque in re.split(r'(\[pausa \d+\])', texto):
        m = re.fullmatch(r'\[pausa (\d+)\]', bloque)
        if m:
            if partes:
                partes[-1] = (partes[-1][0], partes[-1][1] + int(m.group(1)) / 1000)
            else:
                partes.append(('', int(m.group(1)) / 1000))
            continue
        for frase in re.split(r'(?<=[.!?…:;])\s+', bloque.strip()):
            if frase.strip():
                partes.append((frase.strip(), pausa_frase if frase.rstrip()[-1:] in '.!?…' else pausa_frase / 2))
    if partes:
        partes[-1] = (partes[-1][0], 0.0)
    return partes


# ---------- Motores ----------
_kokoro = None


def sintetizar_bruto(spec: str, texto: str, velocidad: float, destino: Path) -> None:
    """Escribe en `destino` un WAV con la voz `spec` (en su frecuencia propia)."""
    motor, _, voz = spec.partition(':')
    if motor == 'kokoro':
        global _kokoro
        import numpy as np
        import soundfile as sf
        if _kokoro is None:
            from kokoro_onnx import Kokoro
            _kokoro = Kokoro(str(HERR / 'kokoro' / 'kokoro-v1.0.onnx'), str(HERR / 'kokoro' / 'voices-v1.0.bin'))
        muestras, sr = _kokoro.create(texto, voice=voz, speed=velocidad, lang='es')
        sf.write(str(destino), np.asarray(muestras, dtype='float32'), sr, subtype='PCM_16')
    elif motor == 'piper':
        exe = HERR / 'piper' / 'piper' / 'piper.exe'
        modelo = HERR / 'piper' / 'voces' / f'{voz}.onnx'
        subprocess.run([str(exe), '--model', str(modelo), '--output_file', str(destino), '--length_scale', f'{1 / velocidad:.3f}',
                        '--sentence_silence', '0'], input=texto.encode('utf-8'), capture_output=True, check=True)
    elif motor in ('onecore', 'sapi'):
        with tempfile.NamedTemporaryFile('w', suffix='.txt', encoding='utf-8', delete=False) as f:
            f.write(texto)
        try:
            correr(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(AQUI / 'voz_windows.ps1'),
                    '-Motor', motor, '-Voz', voz, '-Texto', f.name, '-Salida', str(destino), '-Velocidad', str(velocidad)])
        finally:
            Path(f.name).unlink(missing_ok=True)
    else:
        raise ValueError(f'Motor de voz desconocido: {spec}')


def a_48k(origen: Path, destino: Path, recortar: bool = True) -> None:
    """Remuestrea a 48 kHz mono con soxr y quita el silencio de los extremos."""
    filtros = ['aresample=48000:resampler=soxr', 'highpass=f=60']
    if recortar:
        filtros = ['silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.03',
                   'areverse', 'silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.06', 'areverse'] + filtros
    correr([ffmpeg(), '-y', '-hide_banner', '-loglevel', 'error', '-i', str(origen), '-af', ','.join(filtros),
            '-ac', '1', '-ar', str(TASA), '-sample_fmt', 's16', str(destino)])


def leer_pcm(p: Path) -> bytes:
    with wave.open(str(p), 'rb') as w:
        assert w.getframerate() == TASA and w.getnchannels() == 1 and w.getsampwidth() == 2, p
        return w.readframes(w.getnframes())


def escribir_pcm(p: Path, pcm: bytes) -> None:
    with wave.open(str(p), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TASA)
        w.writeframes(pcm)


def silencio(seg: float) -> bytes:
    return b'\x00\x00' * int(round(seg * TASA))


def duracion(p: Path) -> float:
    with wave.open(str(p), 'rb') as w:
        return w.getnframes() / w.getframerate()


def decir(spec: str, texto: str, destino: Path, velocidad: float = 1.0, pausa_frase: float = 0.32,
          antes: float = 0.0, despues: float = 0.0) -> float:
    """Sintetiza `texto` (ya pronunciado) frase a frase con sus pausas; WAV de 48 kHz en `destino`."""
    pcm = bytearray(silencio(antes))
    with tempfile.TemporaryDirectory() as tmp:
        for k, (frase, pausa) in enumerate(trocear(texto, pausa_frase)):
            if frase:
                bruto, limpio = Path(tmp) / f'{k}.wav', Path(tmp) / f'{k}-48.wav'
                sintetizar_bruto(spec, frase, velocidad, bruto)
                a_48k(bruto, limpio)
                pcm += leer_pcm(limpio)
            pcm += silencio(pausa)
    pcm += silencio(despues)
    destino.parent.mkdir(parents=True, exist_ok=True)
    escribir_pcm(destino, bytes(pcm))
    return duracion(destino)


# ---------- Órdenes ----------
def narrar(a: argparse.Namespace) -> None:
    _, piezas = cargar_proyecto(a.entrada)
    salida = Path(a.salida).resolve()
    total = 0.0
    for p in piezas:
        frags = p.get('narracion') or []
        if not frags or (a.solo and p.get('id') not in a.solo.split(',')):
            continue
        spec = p.get('voz', a.voz)
        vel = float(p.get('velocidad', a.velocidad))
        indice = salida / f"{p['id']}.json"
        previo = json.loads(indice.read_text(encoding='utf-8')) if indice.exists() else {'fragmentos': []}
        anteriores = {f['hash']: f for f in previo.get('fragmentos', [])}
        resultado = []
        for n, fr in enumerate(frags, 1):
            texto = fr['texto'] if isinstance(fr, dict) else str(fr)
            dicho = pronunciar(texto)
            h = hashlib.sha1(f'{spec}|{vel}|{a.pausa_frase}|{dicho}'.encode()).hexdigest()[:16]
            wav = salida / p['id'] / f'{n:02d}.wav'
            if h in anteriores and wav.exists() and not a.forzar and anteriores[h]['wav'] == str(wav):
                d = anteriores[h]['duracion']
            else:
                t = time.time()
                d = decir(spec, dicho, wav, vel, a.pausa_frase)
                print(f"  {p['id']} {n:02d}  {d:5.1f} s  ({time.time() - t:.1f} s)  {texto[:70]}")
            total += d
            resultado.append({'n': n, 'texto': texto, 'dicho': dicho, 'marca': fr.get('marca') if isinstance(fr, dict) else None,
                              'tras': fr.get('tras', 0) if isinstance(fr, dict) else 0,
                              'wav': str(wav), 'duracion': round(d, 3), 'hash': h})
        indice.parent.mkdir(parents=True, exist_ok=True)
        indice.write_text(json.dumps({'id': p['id'], 'voz': spec, 'velocidad': vel, 'fragmentos': resultado},
                                     ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Narración total: {total / 60:.1f} min')


def frase(a: argparse.Namespace) -> None:
    spec = a.voz if a.voz != NARRADOR or not a.microfono else VOZ_MICROFONO
    d = decir(spec, pronunciar(a.texto), Path(a.salida), a.velocidad, a.pausa_frase,
              antes=0.45 if a.microfono else 0.0, despues=1.0 if a.microfono else 0.0)
    print(json.dumps({'wav': str(Path(a.salida).resolve()), 'voz': spec, 'duracion_s': round(d, 2),
                      'mantener_ms': int(d * 1000 + 300)}, ensure_ascii=False))


def _normal(t: str) -> list[str]:
    t = unicodedata.normalize('NFKD', t.lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.findall(r'[a-z0-9ñ]+', t)


def _wer(ref: str, hip: str) -> float:
    r, h = _normal(ref), _normal(hip)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
    return d[len(h)] / max(1, len(r))


def _medidas(spec: str, texto: str) -> dict:
    """Medidas objetivas sobre la salida nativa del motor: frecuencia, ancho de banda que contiene el
    99,5 % de la energía (voz apagada si es bajo) y variación de la entonación en semitonos (voz monótona
    si es baja), con un detector de tono por autocorrelación."""
    import numpy as np
    import soundfile as sf
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / 'b.wav'
        sintetizar_bruto(spec, texto, 1.0, p)
        x, sr = sf.read(str(p), dtype='float32')
    if x.ndim > 1:
        x = x.mean(axis=1)
    espectro = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    banda = float(np.fft.rfftfreq(len(x), 1 / sr)[np.searchsorted(np.cumsum(espectro) / espectro.sum(), 0.995)])
    n, salto, tonos = int(0.04 * sr), int(0.01 * sr), []
    for i in range(0, len(x) - n, salto):
        t = x[i:i + n] * np.hanning(n)
        if np.sqrt(np.mean(t ** 2)) < 0.02:
            continue
        ac = np.correlate(t, t, 'full')[n - 1:]
        lo, hi = int(sr / 400), int(sr / 70)
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] / (ac[0] + 1e-9) > 0.45:
            tonos.append(sr / k)
    v = np.array(tonos)
    return {'frecuencia_nativa': sr, 'banda_995_hz': round(banda),
            'f0_mediana_hz': round(float(np.median(v))) if len(v) else None,
            'variacion_entonacion_st': round(float(np.std(12 * np.log2(v / np.median(v)))), 2) if len(v) else None}


def comparar(a: argparse.Namespace) -> None:
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    candidatas = ['kokoro:em_alex', 'kokoro:ef_dora', 'piper:es_ES-carlfm-x_low', 'piper:es_ES-davefx-medium',
                  'onecore:Microsoft Laura', 'onecore:Microsoft Pablo', 'onecore:Microsoft Helena', 'sapi:Microsoft Helena Desktop']
    token = None
    if a.asr:
        import urllib.request
        env = dict(l.split('=', 1) for l in Path(a.secretos).read_text(encoding='utf-8').splitlines() if '=' in l)
        req = urllib.request.Request(a.base + '/api/auth/login', method='POST', headers={'content-type': 'application/json'},
                                     data=json.dumps({'usuario': a.usuario, 'contrasena': env['CIDIA_DEMO_CONTRASENA'].strip().strip('"\'')}).encode())
        token = json.loads(urllib.request.urlopen(req, timeout=30).read())['token']
    filas = []
    for spec in candidatas:
        motor, _, voz = spec.partition(':')
        if motor == 'piper' and not (HERR / 'piper' / 'voces' / f'{voz}.onnx').exists():
            continue
        nombre = re.sub(r'[^a-z0-9]+', '-', spec.lower()).strip('-')
        fila = {'voz': spec}
        try:
            t = time.time()
            d = decir(spec, pronunciar(FRASE_COMPARAR), salida / f'{nombre}.wav')
            fila.update(duracion_s=round(d, 1), rtf=round((time.time() - t) / d, 2),
                        palabras_min=round(len(FRASE_COMPARAR.split()) / d * 60))
            fila.update(_medidas(spec, pronunciar(FRASE_COMPARAR)))
            dq = decir(spec, pronunciar(PREGUNTA_COMPARAR), salida / f'{nombre}-pregunta.wav', antes=0.45, despues=1.0)
            fila['pregunta_s'] = round(dq, 1)
            if token:
                for clave, ref, f in (('asr_narracion', FRASE_COMPARAR, f'{nombre}.wav'), ('asr_pregunta', PREGUNTA_COMPARAR, f'{nombre}-pregunta.wav')):
                    texto = _transcribir(a.base, token, salida / f)
                    fila[clave] = texto
                    fila['wer_' + clave[4:]] = round(_wer(ref, texto), 2)
        except Exception as e:  # noqa: BLE001
            fila['error'] = str(e)[:300]
        filas.append(fila)
        print(json.dumps(fila, ensure_ascii=False))
    (salida / 'comparacion.json').write_text(json.dumps(filas, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Muestras y tabla en {salida}: escúchalas antes de cambiar de voz (la elegida está en NARRADOR).")


def _transcribir(base: str, token: str, wav: Path) -> str:
    import urllib.request
    limite = '----cidia' + hashlib.sha1(wav.name.encode()).hexdigest()[:12]
    cuerpo = (f'--{limite}\r\nContent-Disposition: form-data; name="audio"; filename="{wav.name}"\r\n'
              f'Content-Type: audio/wav\r\n\r\n').encode() + wav.read_bytes() + f'\r\n--{limite}--\r\n'.encode()
    req = urllib.request.Request(base + '/api/voz/transcribir', data=cuerpo, method='POST',
                                 headers={'content-type': f'multipart/form-data; boundary={limite}', 'authorization': f'Bearer {token}'})
    return json.loads(urllib.request.urlopen(req, timeout=180).read()).get('texto', '')


def voces(_: argparse.Namespace) -> None:
    print('kokoro:', 'em_alex, ef_dora, em_santa' if (HERR / 'kokoro' / 'voices-v1.0.bin').exists() else '(falta: preparar.py)')
    d = HERR / 'piper' / 'voces'
    print('piper:', ', '.join(p.stem for p in sorted(d.glob('*.onnx'))) if d.exists() else '(falta: preparar.py --solo piper)')
    print('onecore y sapi: las voces es-ES instaladas en Windows (Configuración › Hora e idioma › Voz)')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='orden', required=True)
    for nombre in ('narrar', 'frase', 'comparar', 'voces'):
        s = sub.add_parser(nombre)
        s.add_argument('--voz', default=NARRADOR)
        s.add_argument('--velocidad', type=float, default=0.95 if nombre == 'narrar' else 1.0)
        s.add_argument('--pausa-frase', type=float, default=0.32)
        if nombre == 'narrar':
            s.add_argument('entrada')
            s.add_argument('--salida', required=True)
            s.add_argument('--solo')
            s.add_argument('--forzar', action='store_true')
        elif nombre == 'frase':
            s.add_argument('texto')
            s.add_argument('--salida', required=True)
            s.add_argument('--microfono', action='store_true', help='voz de las preguntas, con silencio delante y detrás')
        elif nombre == 'comparar':
            s.add_argument('--salida', required=True)
            s.add_argument('--asr', action='store_true', help='transcribe cada muestra con el servidor CidIA (Whisper)')
            s.add_argument('--secretos')
            s.add_argument('--usuario', default='lucia')
            s.add_argument('--base', default='http://127.0.0.1:18700')
    a = ap.parse_args()
    if a.orden != 'voces' and (a.voz.startswith('kokoro') or a.orden == 'comparar'):
        from comun import en_entorno
        en_entorno(['kokoro_onnx', 'soundfile', 'numpy'])
    {'narrar': narrar, 'frase': frase, 'comparar': comparar, 'voces': voces}[a.orden](a)
