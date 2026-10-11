"""Mide las muestras de voz del banco de pruebas (voz_banco.json) con criterios objetivos.

    <venv medida>/python herramientas/video/voz_banco.py medir <carpeta de muestras> [--modelo medium]

Cada voz es una subcarpeta con <fragmento>.wav (apertura, tecnico, cierre, prensa, llave) y un meta.json
con el motor, la configuración, la licencia y los segundos que tardó cada síntesis. Mide:

* Inteligibilidad: transcribe con faster-whisper (medium, castellano, sin texto de ayuda) y calcula el WER
  frente al texto escrito (sin contar los términos clave) y si se reconocen los términos clave
  (CidIA, IT-023, 25 N·m, ILUO, prensa 3...) con las expresiones de voz_banco.json.
* Naturalidad: UTMOS (predictor de MOS de naturalidad, UTMOS22 strong, MIT), variación de la entonación en
  semitonos, ritmo (palabras por minuto) y pausas internas (número, media y máxima).
* Defectos: silencios internos de más de 1,2 s (cortes o atascos), saturación y final cortado.
* Velocidad: factor de tiempo real de la síntesis (segundos de cálculo / segundos de audio).

Escribe <carpeta>/medidas.json y <carpeta>/medidas.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

AQUI = Path(__file__).resolve().parent
BANCO: dict = {}
FRAGMENTOS: dict = {}


def usar_banco(ruta: str | Path) -> None:
    """Carga el banco de textos (voz_banco.json, el de la v1, o voz_banco_v2.json, el del guion v2)."""
    global BANCO, FRAGMENTOS
    ruta = Path(ruta)
    if not ruta.is_absolute() and not ruta.exists():
        ruta = AQUI / ruta
    BANCO = json.loads(ruta.read_text(encoding='utf-8'))
    FRAGMENTOS = ({f['id']: {**f, 'papel': 'narrador'} for f in BANCO['narrador']}
                  | {f['id']: {**f, 'papel': 'empleado'} for f in BANCO['empleado']})


usar_banco(AQUI / 'voz_banco.json')

UNIDADES = 'cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciseis diecisiete dieciocho diecinueve veinte'.split()
VEINTI = 'veinte veintiuno veintidos veintitres veinticuatro veinticinco veintiseis veintisiete veintiocho veintinueve'.split()
DECENAS = {3: 'treinta', 4: 'cuarenta', 5: 'cincuenta', 6: 'sesenta', 7: 'setenta', 8: 'ochenta', 9: 'noventa'}


def numero(n: int) -> str:
    if n <= 20:
        return UNIDADES[n]
    if n < 30:
        return VEINTI[n - 20]
    if n < 100:
        d, u = divmod(n, 10)
        return DECENAS[d] + ('' if u == 0 else ' y ' + UNIDADES[u])
    if n < 1000:
        c, r = divmod(n, 100)
        cientos = {1: 'ciento' if r else 'cien', 5: 'quinientos', 7: 'setecientos', 9: 'novecientos'}.get(c, UNIDADES[c] + 'cientos')
        return cientos + ('' if r == 0 else ' ' + numero(r))
    m, r = divmod(n, 1000)
    return ('mil' if m == 1 else numero(m) + ' mil') + ('' if r == 0 else ' ' + numero(r))


def normalizar(t: str) -> str:
    t = t.replace('·', ' ').replace('’', "'")
    t = re.sub(r'(?<=[A-Za-z])(?=\d)', ' ', t)  # «IT023» como «IT 023»: si no, el 0 inicial no se lee como «cero»
    t = re.sub(r'(\d+)\s*(n\s*m|newtons?\s*(por\s*)?metros?)\b', r'\1 newton metro', t, flags=re.I)
    t = re.sub(r'\b0(\d+)\b', lambda m: ' '.join(UNIDADES[int(c)] for c in '0' + m.group(1)), t)
    t = re.sub(r'(\d+)\.(\d{3})\b', r'\1\2', t)
    t = re.sub(r'\d+', lambda m: numero(int(m.group(0))) if int(m.group(0)) < 1000000 else m.group(0), t)
    t = unicodedata.normalize('NFKD', t.lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'[^a-z0-9ñ ]+', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def wer(ref: list[str], hip: list[str]) -> tuple[float, int]:
    d = list(range(len(hip) + 1))
    for i in range(1, len(ref) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(hip) + 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ref[i - 1] != hip[j - 1]))
    return d[len(hip)] / max(1, len(ref)), d[len(hip)]


def quitar_terminos(t: str, claves: list[str]) -> str:
    for k in claves:
        t = re.sub(BANCO['terminos'][k], ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def analizar_audio(x, sr) -> dict:
    import numpy as np
    if x.ndim > 1:
        x = x.mean(axis=1)
    x = x.astype('float32')
    marco = int(0.02 * sr)
    n = len(x) // marco
    rms = np.sqrt(np.mean(x[:n * marco].reshape(n, marco) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    ref = np.percentile(db, 95)
    voz = db > ref - 38
    idx = np.where(voz)[0]
    if len(idx) == 0:
        return {'error': 'sin voz'}
    ini, fin = idx[0], idx[-1]
    pausas, k = [], ini
    while k <= fin:
        if not voz[k]:
            j = k
            while j <= fin and not voz[j]:
                j += 1
            dur = (j - k) * 0.02
            if dur >= 0.15:
                pausas.append(dur)
            k = j
        else:
            k += 1
    habla = (fin - ini + 1) * 0.02
    # Tono por autocorrelación (como voz.py).
    paso, ventana, tonos = int(0.01 * sr), int(0.04 * sr), []
    lo, hi = int(sr / 400), int(sr / 65)
    for i in range(ini * marco, min(len(x), (fin + 1) * marco) - ventana, paso):
        t = x[i:i + ventana] * np.hanning(ventana)
        if np.sqrt(np.mean(t ** 2)) < 10 ** ((ref - 25) / 20):
            continue
        ac = np.correlate(t, t, 'full')[ventana - 1:]
        kk = lo + int(np.argmax(ac[lo:hi]))
        if ac[kk] / (ac[0] + 1e-9) > 0.5:
            tonos.append(sr / kk)
    v = np.array(tonos)
    if len(v) > 10:
        med = np.median(v)
        st = 12 * np.log2(v / med)
        st = st[np.abs(st) < 12]  # fuera saltos de octava del detector
        var = float(np.std(st))
    else:
        med, var = float('nan'), float('nan')
    espectro = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    banda = float(np.fft.rfftfreq(len(x), 1 / sr)[np.searchsorted(np.cumsum(espectro) / espectro.sum(), 0.995)])
    cola = db[max(0, len(db) - 3):]
    return {
        'duracion_s': round(len(x) / sr, 2), 'habla_s': round(habla, 2), 'frecuencia': sr,
        'pausas': len(pausas), 'pausa_media_s': round(float(np.mean(pausas)), 2) if pausas else 0.0,
        'pausa_max_s': round(max(pausas), 2) if pausas else 0.0,
        'silencios_largos': sum(1 for p in pausas if p > 1.2),
        'f0_mediana_hz': round(float(med), 1) if med == med else None,
        'entonacion_st': round(var, 2) if var == var else None,
        'saturacion_pct': round(100 * float(np.mean(np.abs(x) > 0.99)), 3),
        'final_cortado': bool(np.max(cola) > ref - 12),
        'banda_995_hz': round(banda),
    }


class Acento:
    """Distinción /θ/ - /s/ (castellano de España) con un reconocedor de fonemas: wav2vec2-xlsr-53-espeak-cv-ft
    (Meta, Apache-2.0). Cuenta las /θ/ reconocidas frente a las que pide la ortografía (z, ce, ci): una voz con
    seseo (acento latinoamericano o andaluz) da casi cero."""

    MODELO = 'facebook/wav2vec2-xlsr-53-espeak-cv-ft'

    def __init__(self, dispositivo: str):
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC
        self.torch, self.dispositivo = torch, dispositivo
        self.fe = Wav2Vec2FeatureExtractor.from_pretrained(self.MODELO)
        self.m = Wav2Vec2ForCTC.from_pretrained(self.MODELO).to(dispositivo).eval()
        vocab = json.loads(Path(hf_hub_download(self.MODELO, 'vocab.json')).read_text(encoding='utf-8'))
        self.ids = {v: k for k, v in vocab.items()}

    def fonemas(self, x16) -> list[str]:
        with self.torch.no_grad():
            ent = self.fe(x16, sampling_rate=16000, return_tensors='pt').input_values.to(self.dispositivo)
            ids = self.m(ent).logits.argmax(-1)[0].tolist()
        out, prev = [], None
        for i in ids:
            if i != prev and self.ids.get(i) not in ('<pad>', '<s>', '</s>', '<unk>', None):
                out.append(self.ids[i])
            prev = i
        return out

    @staticmethod
    def esperadas(dicho: str) -> dict:
        sys.path.insert(0, str(AQUI))
        from voz_texto import numeros_en_letras
        t = unicodedata.normalize('NFKD', numeros_en_letras(dicho).lower())
        t = ''.join(c for c in t if not unicodedata.combining(c))
        return {'theta': len(re.findall(r'z|c(?=[ei])', t)), 's': len(re.findall(r's', t))}


def medir_acento(acento: Acento, x16, meta: dict, frag: str, fr: dict) -> dict:
    fon = acento.fonemas(x16)
    esp = Acento.esperadas((meta.get('dicho') or {}).get(frag) or fr['texto'])
    return {'theta_rec': fon.count('θ'), 's_rec': sum(1 for f in fon if f.startswith('s')),
            'theta_esp': esp['theta'], 's_esp': esp['s']}


def medir(a: argparse.Namespace) -> None:
    import numpy as np
    import soundfile as sf
    import torch  # antes que faster_whisper: deja cargadas las DLL de CUDA y cuDNN
    from faster_whisper import WhisperModel
    carpeta = Path(a.carpeta)
    dispositivo = 'cuda' if torch.cuda.is_available() else 'cpu'
    asr = WhisperModel(a.modelo, device=dispositivo, compute_type='float16' if dispositivo == 'cuda' else 'int8')
    utmos = None
    if not a.sin_utmos:
        # Código de tarepan/SpeechMOS v1.2.0 (MIT) bajado de codeload.github.com a .herramientas/speechmos
        # (torch.hub consulta la API de GitHub, que limita las peticiones); pesos UTMOS22 strong (MIT).
        local = AQUI / '.herramientas' / 'speechmos' / 'SpeechMOS-1.2.0'
        utmos = (torch.hub.load(str(local), 'utmos22_strong', source='local') if local.exists()
                 else torch.hub.load('tarepan/SpeechMOS:v1.2.0', 'utmos22_strong', trust_repo=True)).to(dispositivo)
    acento = Acento(dispositivo) if a.acento else None
    previas = {}
    salida_json = carpeta / 'medidas.json'
    if salida_json.exists() and not a.forzar:
        previas = {(m['voz'], m['fragmento']): m for m in json.loads(salida_json.read_text(encoding='utf-8'))['muestras']}
    muestras = []
    for dir_voz in sorted(p for p in carpeta.iterdir() if p.is_dir() and (p / 'meta.json').exists()):
        if a.solo and dir_voz.name not in a.solo.split(','):
            for (vz, fr), m in previas.items():
                if vz == dir_voz.name:
                    muestras.append(m)
            continue
        meta = json.loads((dir_voz / 'meta.json').read_text(encoding='utf-8'))
        for wav in sorted(dir_voz.glob('*.wav')):
            fr = FRAGMENTOS.get(wav.stem)
            if not fr:
                continue
            clave = (dir_voz.name, wav.stem)
            mt = wav.stat().st_mtime
            import torchaudio
            if clave in previas and previas[clave].get('mtime') == mt:
                m = previas[clave]
                if acento is not None and 'theta_rec' not in m and fr['papel'] == 'narrador':
                    x, sr = sf.read(str(wav), dtype='float32')
                    x16 = torchaudio.functional.resample(torch.from_numpy(x if x.ndim == 1 else x.mean(axis=1)), sr, 16000).numpy()
                    m.update(medir_acento(acento, x16, meta, wav.stem, fr))
                muestras.append(m)
                continue
            x, sr = sf.read(str(wav), dtype='float32')
            if x.ndim > 1:
                x = x.mean(axis=1)
            x16 = torchaudio.functional.resample(torch.from_numpy(x), sr, 16000).numpy()  # sin PyAV
            segs, _ = asr.transcribe(x16, language='es', beam_size=5, condition_on_previous_text=False, vad_filter=False)
            hip = ' '.join(s.text.strip() for s in segs).strip()
            ref_n, hip_n = normalizar(fr['texto']), normalizar(hip)
            claves = fr['terminos']
            aciertos = {k: bool(re.search(BANCO['terminos'][k], hip_n)) for k in claves}
            w, err = wer(quitar_terminos(ref_n, claves).split(), quitar_terminos(hip_n, claves).split())
            m = {'voz': dir_voz.name, 'fragmento': wav.stem, 'papel': fr['papel'], 'mtime': mt,
                 'transcripcion': hip, 'wer': round(w, 3), 'errores': err, 'terminos': aciertos}
            m.update(analizar_audio(x, sr))
            palabras = len(ref_n.split())
            m['palabras_min'] = round(palabras / max(0.1, m.get('habla_s', 0.1)) * 60)
            seg = (meta.get('tiempos') or {}).get(wav.stem)
            if seg:
                m['sintesis_s'] = round(seg, 2)
                m['rtf'] = round(seg / max(0.1, m['duracion_s']), 3)
            if utmos is not None:
                with torch.no_grad():
                    onda = torch.from_numpy(x).unsqueeze(0).to(dispositivo)
                    m['utmos'] = round(float(utmos(onda, sr).item()), 3)
            if acento is not None and fr['papel'] == 'narrador':
                m.update(medir_acento(acento, x16, meta, wav.stem, fr))
            muestras.append(m)
            print(f"{dir_voz.name:34s} {wav.stem:9s} WER {m['wer']:.2f}  UTMOS {m.get('utmos', 0):.2f}  "
                  f"ton {m.get('entonacion_st')}  {m['palabras_min']} ppm  {hip[:90]}")
    salida_json.write_text(json.dumps({'modelo_asr': f'faster-whisper {a.modelo}', 'muestras': muestras}, ensure_ascii=False, indent=2), encoding='utf-8')
    tabla(carpeta, muestras)


def tabla(carpeta: Path, muestras: list[dict]) -> None:
    import numpy as np
    metas = {p.name: json.loads((p / 'meta.json').read_text(encoding='utf-8')) for p in carpeta.iterdir() if (p / 'meta.json').exists()}
    filas = []
    for voz in sorted({m['voz'] for m in muestras}):
        for papel in ('narrador', 'empleado'):
            ms = [m for m in muestras if m['voz'] == voz and m['papel'] == papel]
            if not ms:
                continue
            ter = [v for m in ms for v in m['terminos'].values()]
            errores = sum(m['errores'] for m in ms)
            palabras = sum(len(quitar_terminos(normalizar(FRAGMENTOS[m['fragmento']]['texto']), FRAGMENTOS[m['fragmento']]['terminos']).split()) for m in ms)
            media = lambda k: (round(float(np.nanmean([m[k] for m in ms if m.get(k) is not None])), 2) if any(m.get(k) is not None for m in ms) else None)  # noqa: E731
            filas.append({'voz': voz, 'papel': papel, 'motor': metas.get(voz, {}).get('motor', ''),
                          'wer': round(errores / max(1, palabras), 3), 'terminos': f'{sum(ter)}/{len(ter)}',
                          'utmos': media('utmos'), 'entonacion_st': media('entonacion_st'), 'palabras_min': media('palabras_min'),
                          'pausa_media_s': media('pausa_media_s'), 'silencios_largos': sum(m.get('silencios_largos', 0) for m in ms),
                          'final_cortado': sum(1 for m in ms if m.get('final_cortado')), 'rtf': media('rtf'),
                          'banda_hz': media('banda_995_hz'), 'frecuencia': ms[0].get('frecuencia'),
                          'distincion': (round(sum(m.get('theta_rec', 0) for m in ms) / max(1, sum(m.get('theta_esp', 0) for m in ms)), 2)
                                         if any('theta_rec' in m for m in ms) else None)})
    (carpeta / 'medidas-resumen.json').write_text(json.dumps(filas, ensure_ascii=False, indent=2), encoding='utf-8')
    lineas = ['| Voz | Papel | WER | Términos | UTMOS | Entonación (st) | Palabras/min | Pausa media (s) | Silencios > 1,2 s | Final cortado | RTF | /θ/ reconocidas | Banda (Hz) |',
              '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for f in sorted(filas, key=lambda f: (f['papel'], -(f['utmos'] or 0))):
        lineas.append(f"| {f['voz']} | {f['papel']} | {f['wer']:.3f} | {f['terminos']} | {f['utmos']} | {f['entonacion_st']} | {f['palabras_min']} | "
                      f"{f['pausa_media_s']} | {f['silencios_largos']} | {f['final_cortado']} | {f['rtf']} | {f['distincion']} | {f['banda_hz']} |")
    (carpeta / 'medidas.md').write_text('\n'.join(lineas) + '\n', encoding='utf-8')
    print('\n'.join(lineas))


def sintetizar(a: argparse.Namespace) -> None:
    """Sintetiza el banco con cada voz candidata, cada motor en su entorno (voz_motores.py)."""
    import subprocess
    import tempfile
    sys.path.insert(0, str(AQUI))
    from voz_motores import python_de
    from voz_texto import pronunciar
    candidatas = json.loads(Path(a.candidatas).read_text(encoding='utf-8'))['voces']
    salida = Path(a.salida)
    for c in candidatas:
        if a.solo and c['id'] not in a.solo.split(','):
            continue
        if not a.solo and c.get('omitir'):
            continue
        papeles = ('narrador', 'empleado') if c.get('papel', 'ambos') == 'ambos' else (c['papel'],)
        frs = [f for p in papeles for f in BANCO[p]]
        dir_voz = salida / c['id']
        dir_voz.mkdir(parents=True, exist_ok=True)
        items = []
        for f in frs:
            dicho = pronunciar(f['texto'], c['motor'])
            for patron, por in c.get('reemplazos', []):
                dicho = re.sub(patron, por, dicho)
            items.append({'id': f['id'], 'texto': dicho, 'salida': str(dir_voz / f'{f["id"]}.wav')})
        with tempfile.TemporaryDirectory() as tmp:
            lote = Path(tmp) / 'lote.json'
            res = Path(tmp) / 'resultado.json'
            # {voz}: carpeta de esta voz; {muestras}: carpeta del banco (para usar la voz diseñada de otra candidata).
            config = json.loads(json.dumps(c.get('config', {}), ensure_ascii=False)
                                .replace('{voz}', dir_voz.as_posix()).replace('{muestras}', salida.resolve().as_posix()))
            lote.write_text(json.dumps({'motor': c['motor'], 'config': config, 'por_frases': c.get('por_frases', False),
                                        'pausa_frase': c.get('pausa_frase', 0.32), 'items': items, 'resultado': str(res)},
                                       ensure_ascii=False), encoding='utf-8')
            print(f'== {c["id"]} ({c["motor"]})', flush=True)
            r = subprocess.run([str(python_de(c['motor'])), str(AQUI / 'voz_motores.py'), str(lote)], text=True,
                               encoding='utf-8', errors='replace', capture_output=True)
            if r.returncode != 0:
                print(r.stdout[-2000:], r.stderr[-4000:])
                continue
            resultado = json.loads(res.read_text(encoding='utf-8'))
        meta = {k: v for k, v in c.items() if k not in ('omitir',)}
        meta['carga_s'] = resultado['carga_s']
        meta['tiempos'] = {i['id']: i['segundos'] for i in resultado['items']}
        meta['dicho'] = {i['id']: i['texto'] for i in items}
        (dir_voz / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        for i in resultado['items']:
            print(f"   {i['id']:9s} {i['duracion_s']:6.1f} s de audio en {i['segundos']:6.1f} s")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='orden', required=True)
    s = sub.add_parser('sintetizar')
    s.add_argument('candidatas')
    s.add_argument('--salida', required=True)
    s.add_argument('--solo')
    s = sub.add_parser('medir')
    s.add_argument('carpeta')
    s.add_argument('--modelo', default='medium')
    s.add_argument('--solo', help='voces (subcarpetas) separadas por comas; el resto se toma de medidas.json')
    s.add_argument('--forzar', action='store_true')
    s.add_argument('--sin-utmos', action='store_true')
    s.add_argument('--acento', action='store_true', help='mide la distinción /θ/-/s/ con un reconocedor de fonemas (1,3 GB)')
    s = sub.add_parser('tabla')
    s.add_argument('carpeta')
    for s in sub.choices.values():
        s.add_argument('--banco', default='voz_banco.json', help='textos del banco (voz_banco_v2.json: los del guion v2)')
    a = ap.parse_args()
    usar_banco(a.banco)
    if a.orden == 'medir':
        medir(a)
    elif a.orden == 'sintetizar':
        sintetizar(a)
    else:
        c = Path(a.carpeta)
        tabla(c, json.loads((c / 'medidas.json').read_text(encoding='utf-8'))['muestras'])
