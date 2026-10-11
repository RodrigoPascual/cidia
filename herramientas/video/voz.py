"""Voz en castellano para los vídeos de CidIA, sintetizada en local.

    python herramientas/video/voz.py narrar <proyecto.json | escena.json> --salida <carpeta de voces>
    python herramientas/video/voz.py frase "¿Qué llave uso para apretar los tornillos?" --salida llave.wav --microfono
    python herramientas/video/voz.py comparar --salida <carpeta> [--asr --secretos cidia.env]
    python herramientas/video/voz.py voces

Voces («motor:voz»):
  supertonic:M1                    Supertonic 3 (OpenRAIL-M + MIT): el narrador de la v2 (--perfil v2)
  kokoro:em_alex, kokoro:ef_dora   Kokoro-82M (Apache-2.0): narrador de la v1 y preguntas al micrófono
                                   de la v1 y la v2 (ef_dora; ver README, apartado 6)
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
def motor_de(spec: str) -> str:
    return spec.partition(':')[0]


def pronunciar(texto: str, motor: str = 'kokoro') -> str:
    """Lo que dice la voz: pronunciacion.json (comunes y del motor) y, si el motor lo necesita, números en letras."""
    from voz_texto import pronunciar as _pronunciar
    return _pronunciar(texto, motor)


# ---------- Voces de voz_voces.json (motores en su propio entorno) ----------
def catalogo() -> dict:
    return json.loads((AQUI / 'voz_voces.json').read_text(encoding='utf-8'))


def voz_externa(spec: str) -> dict | None:
    """Configuración exacta de una voz que corre en otro entorno (voz_motores.py), o None si es de las de v1."""
    if motor_de(spec) in ('kokoro', 'piper', 'onecore', 'sapi') and spec not in catalogo()['voces']:
        return None
    v = catalogo()['voces'].get(spec)
    if v is None:
        raise ValueError(f'Voz desconocida: {spec} (mira voz.py voces)')
    cfg = json.loads(json.dumps(v, ensure_ascii=False).replace('{voces}', (AQUI / 'voces').as_posix()))
    return cfg


def perfil(a: argparse.Namespace) -> dict:
    """Narrador, micrófono y velocidad según --perfil o --motor (por defecto, los de la versión 1)."""
    cat = catalogo()
    if getattr(a, 'motor', None):
        return cat['por_motor'][a.motor]
    return cat['perfiles'][getattr(a, 'perfil', None) or 'v1']


def sintetizar_externo(spec: str, trabajos: list[dict], velocidad: float = 1.0, semilla: int | None = None) -> None:
    """Sintetiza de una vez (el modelo se carga una sola vez) los `trabajos` [{dicho, wav, antes, despues}] con la
    voz `spec` en su entorno y deja cada WAV a 48 kHz. «[pausa N]» parte el texto y mete N ms de silencio.
    Con `semilla`, el resultado se repite igual (Supertonic, Chatterbox...); otra semilla da otra toma."""
    from voz_motores import python_de
    v = voz_externa(spec)
    config = dict(v.get('config') or {})
    if semilla is not None:
        config['semilla'] = int(semilla)
    if velocidad != 1.0 and v['motor'] in ('supertonic', 'omnivoice'):
        config['velocidad'] = round(float(config.get('velocidad', 1.0)) * velocidad, 3)
    with tempfile.TemporaryDirectory() as tmp:
        items, planes = [], []
        for k, t in enumerate(trabajos):
            plan = []
            for j, trozo in enumerate(re.split(r'(\[pausa \d+\])', t['dicho'])):
                m = re.fullmatch(r'\[pausa (\d+)\]', trozo)
                if m:
                    plan.append(('pausa', int(m.group(1)) / 1000))
                elif trozo.strip():
                    bruto = Path(tmp) / f'{k}-{j}.wav'
                    items.append({'id': f'{k}-{j}', 'texto': trozo.strip(), 'salida': str(bruto)})
                    plan.append(('voz', bruto))
            planes.append(plan)
        lote = Path(tmp) / 'lote.json'
        lote.write_text(json.dumps({'motor': v['motor'], 'config': config, 'por_frases': v.get('por_frases', False),
                                    'pausa_frase': v.get('pausa_frase', 0.32), 'items': items}, ensure_ascii=False), encoding='utf-8')
        r = subprocess.run([str(python_de(v['motor'])), str(AQUI / 'voz_motores.py'), str(lote)], capture_output=True,
                           text=True, encoding='utf-8', errors='replace')
        if r.returncode != 0:
            raise RuntimeError(f'{v["motor"]} falló:\n{r.stderr[-3000:]}')
        for t, plan in zip(trabajos, planes):
            pcm = bytearray(silencio(t.get('antes', 0.0)))
            for tipo, x in plan:
                if tipo == 'pausa':
                    pcm += silencio(x)
                else:
                    limpio = x.with_name(x.stem + '-48.wav')
                    a_48k(x, limpio)
                    pcm += leer_pcm(limpio)
            pcm += silencio(t.get('despues', 0.0))
            Path(t['wav']).parent.mkdir(parents=True, exist_ok=True)
            escribir_pcm(Path(t['wav']), bytes(pcm))


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
    _, piezas = cargar_proyecto(a.entrada, incluir_omitidas=a.incluir_omitidas)
    salida = Path(a.salida).resolve()
    pf = perfil(a)
    voz_def = a.voz or pf['narrador']
    vel_def = a.velocidad if a.velocidad is not None else float(pf.get('velocidad', 1.0))
    indices, pendientes = [], {}
    for p in piezas:
        frags = p.get('narracion') or []
        if not frags or (a.solo and p.get('id') not in a.solo.split(',')):
            continue
        spec = p.get('voz', voz_def)
        vel = float(p.get('velocidad', vel_def))
        externa = voz_externa(spec)
        if externa and a.semilla is not None:
            externa = {**externa, 'config': {**(externa.get('config') or {}), 'semilla': a.semilla}}
        firma = json.dumps(externa, sort_keys=True, ensure_ascii=False) if externa else ''
        indice = salida / f"{p['id']}.json"
        previo = json.loads(indice.read_text(encoding='utf-8')) if indice.exists() else {'fragmentos': []}
        anteriores = {f['hash']: f for f in previo.get('fragmentos', [])}
        resultado = []
        for n, fr in enumerate(frags, 1):
            texto = fr['texto'] if isinstance(fr, dict) else str(fr)
            dicho = pronunciar(texto, motor_de(spec) if not externa else externa['motor'])
            # «semilla» en el fragmento: la toma elegida a oído (por ejemplo, la única en que Whisper oye «CidIA» como una
            # sola palabra). Entra en la firma, así que cambiarla vuelve a sintetizar solo ese fragmento.
            sem = fr.get('semilla') if isinstance(fr, dict) and fr.get('semilla') is not None else a.semilla
            firma_fr = firma
            if externa and sem != a.semilla:
                firma_fr = json.dumps({**externa, 'config': {**(externa.get('config') or {}), 'semilla': sem}}, sort_keys=True,
                                      ensure_ascii=False)
            clave = f'{spec}|{firma_fr}|{vel}|{a.pausa_frase}|{dicho}' if externa else f'{spec}|{vel}|{a.pausa_frase}|{dicho}'  # v1: misma caché
            h = hashlib.sha1(clave.encode()).hexdigest()[:16]
            wav = salida / p['id'] / f'{n:02d}.wav'
            item = {'n': n, 'texto': texto, 'dicho': dicho, 'marca': fr.get('marca') if isinstance(fr, dict) else None,
                    'tras': fr.get('tras', 0) if isinstance(fr, dict) else 0, 'wav': str(wav), 'duracion': None, 'hash': h}
            if sem != a.semilla:
                item['semilla'] = sem
            if h in anteriores and wav.exists() and not a.forzar and anteriores[h]['wav'] == str(wav):
                item['duracion'] = anteriores[h]['duracion']
                for k in ('semilla', 'velocidad'):  # tomas rehechas por voz_revisar.py (otra semilla o más despacio)
                    if k in anteriores[h]:
                        item[k] = anteriores[h][k]
            elif externa:
                pendientes.setdefault((spec, vel, sem), []).append(item)
            else:
                t = time.time()
                item['duracion'] = round(decir(spec, dicho, wav, vel, a.pausa_frase), 3)
                print(f"  {p['id']} {n:02d}  {item['duracion']:5.1f} s  ({time.time() - t:.1f} s)  {texto[:70]}")
            resultado.append(item)
        indices.append((indice, {'id': p['id'], 'voz': spec, 'velocidad': vel, 'fragmentos': resultado}))
    for (spec, vel, sem), items in pendientes.items():
        t = time.time()
        print(f'  {spec}: {len(items)} fragmentos en un solo lote (semilla {sem})...', flush=True)
        sintetizar_externo(spec, items, vel, sem)
        for it in items:
            it['duracion'] = round(duracion(Path(it['wav'])), 3)
        print(f'  {spec}: {sum(i["duracion"] for i in items):.1f} s de voz en {time.time() - t:.0f} s')
    total = 0.0
    for indice, datos in indices:
        total += sum(f['duracion'] for f in datos['fragmentos'])
        indice.parent.mkdir(parents=True, exist_ok=True)
        indice.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Narración total: {total / 60:.1f} min')


def frase(a: argparse.Namespace) -> None:
    pf = perfil(a)
    spec = a.voz or (pf['microfono'] if a.microfono else pf['narrador'])
    vel = a.velocidad if a.velocidad is not None else float(pf.get('velocidad_microfono', 1.0) if a.microfono and not a.voz else 1.0)
    antes, despues = (0.45, 1.0) if a.microfono else (0.0, 0.0)
    externa = voz_externa(spec)
    if externa:
        sintetizar_externo(spec, [{'dicho': pronunciar(a.texto, externa['motor']), 'wav': str(Path(a.salida)),
                                   'antes': antes, 'despues': despues}], vel, a.semilla)
        d = duracion(Path(a.salida))
    else:
        d = decir(spec, pronunciar(a.texto, motor_de(spec)), Path(a.salida), vel, a.pausa_frase, antes=antes, despues=despues)
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
    from voz_motores import python_de
    print('kokoro:', 'em_alex, ef_dora, em_santa' if (HERR / 'kokoro' / 'voices-v1.0.bin').exists() else '(falta: preparar.py)')
    d = HERR / 'piper' / 'voces'
    print('piper:', ', '.join(p.stem for p in sorted(d.glob('*.onnx'))) if d.exists() else '(falta: preparar.py --solo piper)')
    print('onecore y sapi: las voces es-ES instaladas en Windows (Configuración › Hora e idioma › Voz)')
    cat = catalogo()
    print('\nVoces de voz_voces.json (cada motor en su entorno de .herramientas/tts; elección en 04_VIDEO/v2/muestras-voz/indice.md):')
    for spec, v in cat['voces'].items():
        listo = 'listo' if python_de(v['motor']).exists() else 'falta el entorno'
        print(f'  {spec:28s} {listo:17s} {v.get("licencia", "")[:70]}')
    print('\nPerfiles (--perfil):', ', '.join(f'{k} = {v["narrador"]} + {v["microfono"]}' for k, v in cat['perfiles'].items()))
    print('Por motor (--motor):', ', '.join(f'{k} = {v["narrador"]} + {v["microfono"]}' for k, v in cat['por_motor'].items()))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='orden', required=True)
    for nombre in ('narrar', 'frase', 'comparar', 'voces'):
        s = sub.add_parser(nombre)
        s.add_argument('--voz', default=None if nombre in ('narrar', 'frase') else NARRADOR,
                       help='motor:voz; sin ella, la del perfil (narrador, o micrófono con --microfono)')
        s.add_argument('--perfil', help='v1 (por defecto: Kokoro em_alex + ef_dora) o v2 (la elegida en 04_VIDEO/v2/muestras-voz)')
        s.add_argument('--motor', help='usa el narrador y el micrófono elegidos de ese motor (voz_voces.json, por_motor)')
        s.add_argument('--velocidad', type=float, default=None if nombre in ('narrar', 'frase') else 1.0,
                       help='por defecto, la del perfil al narrar (0,95 en v1) y 1,0 en frase')
        s.add_argument('--pausa-frase', type=float, default=0.32)
        s.add_argument('--semilla', type=int, default=None,
                       help='voces de voz_voces.json: misma semilla, mismo audio (otra semilla, otra toma)')
        if nombre == 'narrar':
            s.add_argument('entrada')
            s.add_argument('--salida', required=True)
            s.add_argument('--solo')
            s.add_argument('--forzar', action='store_true')
            s.add_argument('--incluir-omitidas', action='store_true',
                           help='narra también las piezas con "omitir" (tomas nuevas aún sin grabar)')
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
    if a.orden != 'voces':
        # Kokoro de la v1 corre en este proceso; los demás motores, en su propio entorno (voz_motores.py).
        from comun import en_entorno
        en_entorno(['kokoro_onnx', 'soundfile', 'numpy'])
    {'narrar': narrar, 'frase': frase, 'comparar': comparar, 'voces': voces}[a.orden](a)
