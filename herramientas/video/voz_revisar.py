"""Revisa con Whisper (en local) la voz ya sintetizada y rehace lo que salga mal.

    <python de .herramientas/tts/medida> herramientas/video/voz_revisar.py narracion <carpeta de voces> [--rehacer 4]
    <python de .herramientas/tts/medida> herramientas/video/voz_revisar.py frase <wav> "<texto esperado>" [--modelos base,medium]
    <python de .herramientas/tts/medida> herramientas/video/voz_revisar.py comparar <voces nuevas> <voces de referencia>

`narracion` transcribe cada fragmento de <carpeta>/<id>.json (los que deja voz.py narrar) con faster-whisper
(medium, castellano, sin texto de ayuda), lo compara con lo que se quería decir (el «dicho», tras
pronunciacion.json) y marca los fragmentos con errores de lectura (WER alto), un ritmo raro o silencios internos
largos. Con --rehacer N, cada fragmento marcado se vuelve a sintetizar con hasta N semillas distintas y se queda la
toma que mejor se entiende; el índice apunta la semilla y la revisión. Deja <carpeta>/revision.json.

`frase` comprueba un WAV del micrófono con los modelos de Whisper que se indiquen (el servidor de pruebas usa
base con int8 en CPU): la pregunta tiene que transcribirse tal cual para que la escena funcione.

`comparar` suma la duración de la voz por pieza en las dos carpetas y avisa de las piezas que se alargan mucho.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

LETRAS = {'ele': 'l', 'eme': 'm', 'ese': 's', 'erre': 'r', 'efe': 'f', 'equis': 'x', 'jota': 'j', 'pe': 'p', 'be': 'b',
          'ce': 'c', 'ge': 'g', 'zeta': 'z', 'hache': 'h'}
SEMILLAS = [101, 202, 303, 404, 505, 606, 707, 808]


def normal(t: str) -> list[str]:
    """Texto comparable: el de voz_banco (números en letras, sin tildes ni signos) con siglas deletreadas juntas y
    sin diferencias que no se oyen («12,000», «micro-lecciones» o «porqué» frente a «por qué»)."""
    from voz_banco import normalizar
    t = re.sub(r'(\d),(\d{3})\b', r'\1\2', t)
    t = normalizar(t)
    t = re.sub(r'\b[csz][iy] ?d ?[iy] ?a\b', 'cidia', t)
    t = re.sub(r'\bmicro ', 'micro', t)
    t = re.sub(r'\bpor que\b', 'porque', t)
    out: list[str] = []
    letras = False
    for w in (LETRAS.get(w, w) for w in t.split()):  # letras sueltas seguidas, juntas: «i l u o» -> «iluo»
        if len(w) == 1 and letras:
            out[-1] += w
        else:
            out.append(w)
        letras = len(w) == 1 or (letras and len(w) == 1)
    return out


def wer(ref: list[str], hip: list[str]) -> tuple[float, int]:
    from voz_banco import wer as _wer
    return _wer(ref, hip)


class Oido:
    """faster-whisper con los mismos ajustes que voz_banco.py (sin VAD, sin texto previo, castellano)."""

    def __init__(self):
        self.modelos = {}

    def transcribir(self, wav: Path, modelo: str = 'medium', cpu_int8: bool = False, servidor: bool = False,
                    prompt: str | None = None, kbps: int = 32) -> str:
        """Con `servidor`, como lo hace el servicio de voz de CidIA (servidor/asr/app.py): el audio pasa antes por Opus
        en WebM (lo que graba el navegador), VAD activado, reintentos a más temperatura y, si se da, el vocabulario de la
        planta como texto inicial (el servidor lo saca de las tareas que ve la persona y de los pasos de la tarea en curso)."""
        import numpy as np
        import soundfile as sf
        import torch
        import torchaudio
        from faster_whisper import WhisperModel
        clave = (modelo, cpu_int8)
        if clave not in self.modelos:
            if cpu_int8 or not torch.cuda.is_available():
                self.modelos[clave] = WhisperModel(modelo, device='cpu', compute_type='int8')
            else:
                self.modelos[clave] = WhisperModel(modelo, device='cuda', compute_type='float16')
        if servidor:
            from comun import correr, ffmpeg
            with tempfile.TemporaryDirectory() as tmp:
                webm, pcm = Path(tmp) / 'voz.webm', Path(tmp) / 'voz.wav'
                correr([ffmpeg(), '-y', '-hide_banner', '-loglevel', 'error', '-i', str(wav), '-c:a', 'libopus', '-b:a', f'{kbps}k',
                        '-ac', '1', '-ar', '48000', str(webm)])
                correr([ffmpeg(), '-y', '-hide_banner', '-loglevel', 'error', '-i', str(webm), '-ac', '1', '-ar', '16000', str(pcm)])
                x16, _ = sf.read(str(pcm), dtype='float32')
            segs, _ = self.modelos[clave].transcribe(x16, language='es', vad_filter=True, beam_size=5,
                                                     temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0), condition_on_previous_text=False,
                                                     initial_prompt=prompt or None)
            return ' '.join(s.text.strip() for s in segs).strip()
        x, sr = sf.read(str(wav), dtype='float32')
        if x.ndim > 1:
            x = x.mean(axis=1)
        x16 = torchaudio.functional.resample(torch.from_numpy(np.ascontiguousarray(x)), sr, 16000).numpy()
        segs, _ = self.modelos[clave].transcribe(x16, language='es', beam_size=5, condition_on_previous_text=False, vad_filter=False)
        return ' '.join(s.text.strip() for s in segs).strip()


def analizar(wav: Path) -> dict:
    import soundfile as sf
    from voz_banco import analizar_audio
    x, sr = sf.read(str(wav), dtype='float32')
    return analizar_audio(x, sr)


def silabas(t: str) -> int:
    """Sílabas aproximadas (grupos de vocales del texto normalizado): en castellano, el ritmo se mide mejor en sílabas
    por segundo que en palabras por minuto, que se disparan con frases de monosílabos («Y ve qué le falta...»)."""
    from voz_banco import normalizar
    return len(re.findall(r'[aeiou]+', normalizar(t).replace('y ', 'i ')))


def tasa(fr: dict, audio: dict) -> float:
    return silabas(fr.get('dicho') or fr['texto']) / max(0.1, audio.get('habla_s', 0.1))


def juzgar(fr: dict, hip: str, audio: dict, a: argparse.Namespace) -> tuple[float, list[str]]:
    ref = normal(fr.get('dicho') or fr['texto'])
    w, _ = wer(ref, normal(hip))
    w = round(w, 3)
    motivos = []
    if w > a.umbral:
        motivos.append(f'WER {w:.2f}')
    s, t = silabas(fr.get('dicho') or fr['texto']), tasa(fr, audio)
    if s >= 4 and t > a.max_tasa:
        motivos.append(f'rápido {t:.1f} sílabas/s')
    elif s >= 8 and t < a.min_tasa:
        motivos.append(f'lento {t:.1f} sílabas/s')
    if audio.get('silencios_largos'):
        motivos.append(f"silencio interno de {audio.get('pausa_max_s')} s")
    if audio.get('final_cortado'):
        motivos.append('final cortado')
    return w, motivos


def narracion(a: argparse.Namespace) -> None:
    carpeta = Path(a.carpeta).resolve()
    oido = Oido()
    previa = {}
    rev_json = carpeta / 'revision.json'
    if rev_json.exists() and not a.forzar:
        previa = {(r['id'], r['n']): r for r in json.loads(rev_json.read_text(encoding='utf-8'))['fragmentos']}
    filas, malos = [], []
    indices = sorted(p for p in carpeta.glob('*.json') if p.name not in ('revision.json',))
    for ind in indices:
        datos = json.loads(ind.read_text(encoding='utf-8'))
        if 'fragmentos' not in datos or 'id' not in datos or (a.solo and datos['id'] not in a.solo.split(',')):
            continue
        for fr in datos['fragmentos']:
            wav = carpeta / datos['id'] / Path(fr['wav']).name
            clave = (datos['id'], fr['n'])
            mt = wav.stat().st_mtime
            if clave in previa and previa[clave].get('mtime') == mt and previa[clave].get('hash') == fr['hash'] and not a.rejuzgar:
                fila = previa[clave]
            else:
                if clave in previa and previa[clave].get('mtime') == mt and previa[clave].get('hash') == fr['hash']:
                    hip = previa[clave]['transcripcion']  # --rejuzgar: misma transcripción, criterios nuevos
                else:
                    hip = oido.transcribir(wav, a.modelo)
                audio = analizar(wav)
                w, motivos = juzgar(fr, hip, audio, a)
                fila = {'id': datos['id'], 'n': fr['n'], 'hash': fr['hash'], 'mtime': mt, 'texto': fr['texto'], 'dicho': fr.get('dicho'),
                        'transcripcion': hip, 'wer': w, 'duracion': round(audio['duracion_s'], 2),
                        'silabas_s': round(tasa(fr, audio), 2), 'pausa_max_s': audio.get('pausa_max_s'), 'motivos': motivos,
                        'semilla': fr.get('semilla'), 'velocidad': fr.get('velocidad')}
            filas.append(fila)
            if fila['motivos']:
                malos.append((ind, datos['voz'], float(datos.get('velocidad', 1.0)), fr, wav, fila))
            print(f"{'!!' if fila['motivos'] else '  '} {datos['id']} {fr['n']:02d} WER {fila['wer']:.2f} {', '.join(fila['motivos'])}\n     {fila['transcripcion'][:150]}")
    print(f'\n{len(filas)} fragmentos, {len(malos)} marcados.')
    if a.rehacer and malos:
        rehacer(a, oido, malos)
    rev_json.write_text(json.dumps({'modelo_asr': f'faster-whisper {a.modelo}', 'umbral_wer': a.umbral,
                                    'tasa_silabas_s': [a.min_tasa, a.max_tasa],
                                    'marcados': sum(1 for f in filas if f['motivos']), 'fragmentos': filas},
                                   ensure_ascii=False, indent=2), encoding='utf-8')


def rehacer(a: argparse.Namespace, oido: Oido, malos: list) -> None:
    """Vuelve a sintetizar los fragmentos marcados. Si van rápidos, más despacio (velocidad × objetivo / tasa, sin bajar
    de 0,8) y, en el primer intento, con su misma semilla; si se entienden mal, con otras semillas. Se queda la mejor toma."""
    from voz import duracion, sintetizar_externo
    pendientes = list(malos)
    for intento in range(a.rehacer):
        if not pendientes:
            break
        grupos: dict = {}
        for m in pendientes:
            _, spec, vel, fr, _, fila = m
            rapido = next((x for x in fila['motivos'] if x.startswith('rápido')), None)
            solo_ritmo = all(x.startswith(('rápido', 'lento')) for x in fila['motivos'])
            factor = 1.0
            if rapido:
                factor = max(0.8, min(1.0, a.objetivo_tasa / float(rapido.split()[1])))
                factor = round(max(0.75, factor * float(fr.get('velocidad') or vel) / vel), 3)  # sobre la toma que ya hay
            elif any(x.startswith('lento') for x in fila['motivos']):
                factor = round(min(1.2, a.objetivo_tasa / max(1.0, float(fila.get('silabas_s') or a.objetivo_tasa))), 3)
            semilla = (fr.get('semilla') or a.semilla) if (intento == 0 and solo_ritmo) else SEMILLAS[intento]
            grupos.setdefault((spec, round(vel * factor, 3), semilla), []).append(m)
        siguen = []
        for (spec, vel_f, semilla), lista in grupos.items():
            with tempfile.TemporaryDirectory() as tmp:
                trabajos = [{'dicho': m[3].get('dicho') or m[3]['texto'], 'wav': str(Path(tmp) / f'{k}.wav')} for k, m in enumerate(lista)]
                print(f'  {spec}: {len(trabajos)} fragmentos con la semilla {semilla} y velocidad {vel_f}...', flush=True)
                sintetizar_externo(spec, trabajos, vel_f, semilla)
                for t, m in zip(trabajos, lista):
                    ind, _, vel, fr, wav, fila = m
                    hip = oido.transcribir(Path(t['wav']), a.modelo)
                    audio = analizar(Path(t['wav']))
                    w, motivos = juzgar(fr, hip, audio, a)
                    mejor = (len(motivos), w) < (len(fila['motivos']), fila['wer'])
                    print(f"     {fila['id']} {fila['n']:02d}: WER {w:.2f} {tasa(fr, audio):.1f} sílabas/s {motivos} {'(mejor)' if mejor else ''}")
                    if mejor:
                        shutil.copyfile(t['wav'], wav)
                        fila.update(transcripcion=hip, wer=w, duracion=round(audio['duracion_s'], 2), motivos=motivos,
                                    silabas_s=round(tasa(fr, audio), 2), semilla=semilla,
                                    velocidad=vel_f if vel_f != vel else None, pausa_max_s=audio.get('pausa_max_s'),
                                    mtime=wav.stat().st_mtime)
                        datos = json.loads(ind.read_text(encoding='utf-8'))
                        for f2 in datos['fragmentos']:
                            if f2['n'] == fr['n']:
                                f2['duracion'] = round(duracion(wav), 3)
                                f2['semilla'] = semilla
                                if vel_f != vel:
                                    f2['velocidad'] = vel_f
                                else:
                                    f2.pop('velocidad', None)
                                fr.update({k: f2[k] for k in ('semilla',)})
                                if 'velocidad' in f2:
                                    fr['velocidad'] = f2['velocidad']
                                else:
                                    fr.pop('velocidad', None)
                        ind.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
                    if fila['motivos']:
                        siguen.append(m)
        pendientes = siguen
    for m in pendientes:
        print(f"  sigue marcado: {m[5]['id']} {m[5]['n']:02d} {m[5]['motivos']}  {m[5]['transcripcion'][:120]}")


def frase(a: argparse.Namespace) -> None:
    oido = Oido()
    ref = normal(a.texto)
    ok = True
    for modelo in a.modelos.split(','):
        cpu = modelo in ('base', 'small') and not a.gpu
        for servidor in ((False, True) if a.servidor else (False,)):
            for kbps in ((24, 32, 64, 128) if servidor and a.robustez else (32,)):
                for prompt in ((None, a.prompt) if servidor and a.prompt else (None,)):
                    hip = oido.transcribir(Path(a.wav), modelo, cpu_int8=cpu, servidor=servidor, prompt=prompt, kbps=kbps)
                    w, _ = wer(ref, normal(hip))
                    ok &= w == 0
                    print(json.dumps({'modelo': modelo + (' (cpu int8)' if cpu else '') + (f' como el servidor, Opus {kbps} kbit/s' if servidor else '')
                                      + (', con vocabulario' if prompt else ''), 'transcripcion': hip, 'wer': round(w, 3)}, ensure_ascii=False))
    sys.exit(0 if ok else 1)


def comparar(a: argparse.Namespace) -> None:
    nueva, ref = Path(a.nueva), Path(a.referencia)
    filas, tn, tr = [], 0.0, 0.0
    for ind in sorted(nueva.glob('*.json')):
        d = json.loads(ind.read_text(encoding='utf-8'))
        if 'fragmentos' not in d or 'id' not in d:  # revision.json
            continue
        dn = sum(f['duracion'] for f in d['fragmentos'])
        r = ref / ind.name
        dr = sum(f['duracion'] for f in json.loads(r.read_text(encoding='utf-8'))['fragmentos']) if r.exists() else None
        filas.append({'id': d['id'], 'nueva_s': round(dn, 2), 'referencia_s': round(dr, 2) if dr is not None else None,
                      'diferencia_s': round(dn - dr, 2) if dr is not None else None,
                      'diferencia_pct': round(100 * (dn - dr) / dr, 1) if dr else None})
        if dr is not None:
            tn, tr = tn + dn, tr + dr
    for f in sorted(filas, key=lambda f: -(f['diferencia_s'] or 0)):
        aviso = ' <<' if (f['diferencia_s'] or 0) >= a.aviso_s else ''
        print(f"{f['id']:32s} {f['referencia_s']!s:>7} s -> {f['nueva_s']:>6} s  {f['diferencia_s']!s:>6} s  {f['diferencia_pct']!s:>6} %{aviso}")
    print(f'TOTAL {tr:.1f} s -> {tn:.1f} s ({tn - tr:+.1f} s, {100 * (tn - tr) / max(tr, 1):+.1f} %)')
    if a.salida:
        Path(a.salida).write_text(json.dumps({'referencia_s': round(tr, 2), 'nueva_s': round(tn, 2), 'piezas': filas},
                                             ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='orden', required=True)
    s = sub.add_parser('narracion')
    s.add_argument('carpeta')
    s.add_argument('--modelo', default='medium')
    s.add_argument('--umbral', type=float, default=0.12, help='WER a partir del cual se marca un fragmento')
    s.add_argument('--rehacer', type=int, default=0, help='intentos (semillas o velocidad) con cada fragmento marcado')
    s.add_argument('--semilla', type=int, default=1234, help='la de voz.py narrar (primer intento de los que solo van rápidos)')
    s.add_argument('--max-tasa', type=float, default=6.3, help='sílabas por segundo a partir de las que se marca «rápido»')
    s.add_argument('--min-tasa', type=float, default=3.6, help='sílabas por segundo por debajo de las que se marca «lento»')
    s.add_argument('--objetivo-tasa', type=float, default=5.6, help='ritmo al que se lleva un fragmento rápido (mediana: 5,4)')
    s.add_argument('--solo')
    s.add_argument('--forzar', action='store_true')
    s.add_argument('--rejuzgar', action='store_true', help='vuelve a aplicar los criterios sin volver a transcribir')
    s = sub.add_parser('frase')
    s.add_argument('wav')
    s.add_argument('texto')
    s.add_argument('--modelos', default='base,medium')
    s.add_argument('--gpu', action='store_true')
    s.add_argument('--servidor', action='store_true', help='prueba además como el servidor: Opus, VAD y reintentos')
    s.add_argument('--prompt', help='vocabulario de la planta que el servidor pasa a Whisper (se prueba con y sin él)')
    s.add_argument('--robustez', action='store_true', help='como el servidor, con Opus a 24, 32, 64 y 128 kbit/s')
    s = sub.add_parser('comparar')
    s.add_argument('nueva')
    s.add_argument('referencia')
    s.add_argument('--aviso-s', type=float, default=2.0)
    s.add_argument('--salida')
    a = ap.parse_args()
    {'narracion': narracion, 'frase': frase, 'comparar': comparar}[a.orden](a)
