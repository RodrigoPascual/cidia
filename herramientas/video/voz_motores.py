"""Motores de voz de CidIA: un proceso por motor, cada uno en su entorno de .herramientas/.

    <python del motor> herramientas/video/voz_motores.py <lote.json>

voz.py y voz_banco.py escriben el lote y lanzan este script con el Python del entorno del motor
(ver ENTORNOS). El modelo se carga una vez y se sintetizan todos los textos del lote:

    {"motor": "chatterbox", "config": {...}, "por_frases": true, "pausa_frase": 0.32,
     "items": [{"id": "apertura", "texto": "texto ya adaptado con pronunciacion.json", "salida": "x.wav"}],
     "resultado": "x-resultado.json"}

Cada WAV sale mono, PCM de 16 bits, en la frecuencia propia del motor y sin silencio en los extremos.
Con "por_frases" el texto se parte en frases (como voz.py) y se unen con su pausa; si no, el motor
recibe el fragmento entero y pone él las pausas. El resultado apunta los segundos de cálculo de cada texto.
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
HERR = AQUI / '.herramientas'
TTS = HERR / 'tts'
os.environ.setdefault('HF_HOME', str(HERR / 'hf'))
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('TORCH_HOME', str(HERR / 'torch'))
os.environ.setdefault('SUPERTONIC_CACHE_DIR', str(HERR / 'supertonic'))

# Python de cada motor (entornos separados: cada uno fija versiones distintas de transformers).
# Tras la comparación de voces (04_VIDEO/v2/muestras-voz/indice.md) solo quedan instalados kokoro (.venv) y
# supertonic; los entornos y modelos de chatterbox, voxcpm y qwen3tts se borraron para liberar disco (omnivoice
# no llegó a instalarse). Sus clases se quedan como registro de cómo se probaron.
ENTORNOS = {
    'kokoro': HERR / '.venv',
    'chatterbox': TTS / 'chatterbox',
    'supertonic': TTS / 'supertonic',
    'voxcpm': TTS / 'voxcpm',
    'qwen3tts': TTS / 'qwen3tts',
    'omnivoice': TTS / 'omnivoice',
}


def python_de(motor: str) -> Path:
    base = ENTORNOS[motor]
    return base / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')


def trocear(texto: str, pausa_frase: float) -> list[tuple[str, float]]:
    """Frases con el silencio que va detrás (igual que voz.py)."""
    partes: list[tuple[str, float]] = []
    for bloque in re.split(r'(\[pausa \d+\])', texto):
        m = re.fullmatch(r'\[pausa (\d+)\]', bloque)
        if m:
            if partes:
                partes[-1] = (partes[-1][0], partes[-1][1] + int(m.group(1)) / 1000)
            continue
        for frase in re.split(r'(?<=[.!?…:;])\s+', bloque.strip()):
            if frase.strip():
                partes.append((frase.strip(), pausa_frase if frase.rstrip()[-1:] in '.!?…' else pausa_frase / 2))
    if partes:
        partes[-1] = (partes[-1][0], 0.0)
    return partes


def recortar(x, sr, umbral_db: float = -45.0, margen_s: float = 0.03):
    """Quita el silencio del principio y del final (umbral relativo al pico)."""
    import numpy as np
    if len(x) == 0:
        return x
    marco = max(1, int(0.01 * sr))
    n = len(x) // marco
    if n == 0:
        return x
    rms = np.sqrt(np.mean(x[:n * marco].reshape(n, marco) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms / (np.max(np.abs(x)) + 1e-9))
    voz = np.where(db > umbral_db)[0]
    if len(voz) == 0:
        return x
    a = max(0, voz[0] * marco - int(margen_s * sr))
    b = min(len(x), (voz[-1] + 1) * marco + int(2 * margen_s * sr))
    return x[a:b]


# ---------------------------------------------------------------- motores
class Motor:
    sr = 24000

    def __init__(self, config: dict):
        self.config = config

    def decir(self, texto: str):  # -> np.ndarray float32
        raise NotImplementedError


def semilla(n: int | None) -> None:
    if n is None:
        return
    random.seed(n)
    try:
        import numpy as np
        np.random.seed(n)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(n)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(n)
    except ImportError:
        pass


class Kokoro(Motor):
    """Kokoro-82M (Apache-2.0) con kokoro-onnx (MIT). config: voz (nombre o {nombre: peso}), velocidad, fonemas."""

    def __init__(self, config):
        super().__init__(config)
        from kokoro_onnx import Kokoro as K
        self.k = K(str(HERR / 'kokoro' / 'kokoro-v1.0.onnx'), str(HERR / 'kokoro' / 'voices-v1.0.bin'))
        voz = config.get('voz', 'em_alex')
        if isinstance(voz, dict):
            import numpy as np
            total = sum(voz.values())
            self.voz = sum(np.asarray(self.k.get_voice_style(n)) * (p / total) for n, p in voz.items())
        else:
            self.voz = voz
        self.fonemas = config.get('fonemas') or {}

    def decir(self, texto):
        import numpy as np
        vel = float(self.config.get('velocidad', 1.0))
        if self.fonemas:
            # Las palabras de «fonemas» se sustituyen por sus fonemas IPA después de fonetizar el resto.
            marcas = {}
            for i, (pal, fon) in enumerate(self.fonemas.items()):
                marca = f'Equis{"abcdefghij"[i]}'
                if pal in texto:
                    texto = texto.replace(pal, marca)
                    marcas[self.k.tokenizer.phonemize(marca, 'es').strip(' .')] = fon
            ph = self.k.tokenizer.phonemize(texto, 'es')
            for m, fon in marcas.items():
                ph = ph.replace(m, fon)
            x, self.sr = self.k.create(ph, voice=self.voz, speed=vel, lang='es', is_phonemes=True)
        else:
            x, self.sr = self.k.create(texto, voice=self.voz, speed=vel, lang='es')
        return np.asarray(x, dtype='float32')


class Chatterbox(Motor):
    """Chatterbox Multilingual V3, ajuste fino de castellano de España (Resemble AI, MIT).
    config: referencia (WAV de la voz; sin ella, la voz incorporada conds.pt), exageracion, cfg, temperatura, semilla."""

    def __init__(self, config):
        super().__init__(config)
        sys.path.insert(0, str(TTS / 'chatterbox-es-codigo' / 'chatterbox' / 'src'))
        import torch
        from chatterbox.tts import ChatterboxTTS
        self.torch = torch
        self.m = ChatterboxTTS.from_pretrained('cuda' if torch.cuda.is_available() else 'cpu')
        self.sr = self.m.sr
        ref = config.get('referencia')
        if ref:
            self.m.prepare_conditionals(str(ref), exaggeration=float(config.get('exageracion', 0.5)))

    def decir(self, texto):
        semilla(self.config.get('semilla', 1234))
        wav = self.m.generate(texto, exaggeration=float(self.config.get('exageracion', 0.5)), cfg_weight=float(self.config.get('cfg', 0.5)),
                              temperature=float(self.config.get('temperatura', 0.8)), language_id='es')
        return wav.squeeze(0).numpy().astype('float32')


class Supertonic(Motor):
    """Supertonic 3 (Supertone; código MIT, pesos BigScience OpenRAIL-M). config: voz (M1-M5, F1-F5), velocidad, pasos,
    semilla (el ruido de partida sale de numpy: con semilla, la misma frase sale siempre igual; otra semilla da otra toma)."""

    def __init__(self, config):
        super().__init__(config)
        from supertonic import TTS as ST
        # Sin descargas: el modelo ya está en .herramientas/supertonic (SUPERTONIC_CACHE_DIR).
        self.t = ST(auto_download=not (HERR / 'supertonic' / 'onnx' / 'tts.json').exists())
        self.estilo = self.t.get_voice_style(voice_name=config.get('voz', 'M1'))
        self.sr = getattr(self.t, 'sample_rate', 44100)

    def decir(self, texto):
        import numpy as np
        semilla(self.config.get('semilla'))
        kw = {}
        if 'velocidad' in self.config:
            kw['speed'] = float(self.config['velocidad'])
        if 'pasos' in self.config:
            kw['total_steps'] = int(self.config['pasos'])
        wav, _ = self.t.synthesize(texto, voice_style=self.estilo, lang='es', **kw)
        return np.asarray(wav, dtype='float32').reshape(-1)


class VoxCPM(Motor):
    """VoxCPM2 (OpenBMB, Apache-2.0), 48 kHz. config: diseno (descripción de la voz), referencia (+ texto_referencia),
    estilo, cfg, pasos, semilla. Con diseno y texto_diseno, la voz se diseña una vez (o se toma de referencia si ese
    WAV ya existe) y todos los fragmentos se dicen con ella como referencia: así el timbre no cambia de uno a otro."""

    def __init__(self, config):
        super().__init__(config)
        from voxcpm import VoxCPM as V
        self.m = V.from_pretrained('openbmb/VoxCPM2', load_denoiser=False, optimize=False)
        self.sr = self.m.tts_model.sample_rate
        c = self.config
        if c.get('diseno') and c.get('texto_diseno') and c.get('referencia'):
            ref = Path(c['referencia'])
            if not ref.exists():
                import numpy as np
                import soundfile as sf
                semilla(c.get('semilla_diseno', c.get('semilla', 1234)))
                x = self.m.generate(text=f"({c['diseno']}){c['texto_diseno']}", cfg_value=float(c.get('cfg', 2.0)),
                                    inference_timesteps=int(c.get('pasos', 10)))
                ref.parent.mkdir(parents=True, exist_ok=True)
                sf.write(str(ref), recortar(np.asarray(x, dtype='float32'), self.sr), self.sr, subtype='PCM_16')
            c['texto_referencia'] = c['texto_diseno']

    def decir(self, texto):
        import numpy as np
        semilla(self.config.get('semilla', 1234))
        c = self.config
        kw = {'cfg_value': float(c.get('cfg', 2.0)), 'inference_timesteps': int(c.get('pasos', 10))}
        if c.get('referencia'):
            kw['reference_wav_path'] = str(c['referencia'])
            if c.get('texto_referencia'):
                kw['prompt_wav_path'] = str(c['referencia'])
                kw['prompt_text'] = c['texto_referencia']
            if c.get('estilo'):
                texto = f"({c['estilo']}){texto}"
        elif c.get('diseno'):
            texto = f"({c['diseno']}){texto}"
        return np.asarray(self.m.generate(text=texto, **kw), dtype='float32')


class Qwen3TTS(Motor):
    """Qwen3-TTS 12 Hz (Apache-2.0). config: modelo (VoiceDesign, CustomVoice o Base), diseno / hablante + instruccion /
    referencia + texto_referencia, semilla."""

    def __init__(self, config):
        super().__init__(config)
        import torch
        from qwen_tts import Qwen3TTSModel
        nombre = config.get('modelo', 'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign')
        self.m = Qwen3TTSModel.from_pretrained(nombre, device_map='cuda:0', dtype=torch.bfloat16, attn_implementation='sdpa')
        self.tipo = 'diseno' if 'VoiceDesign' in nombre else ('hablante' if 'CustomVoice' in nombre else 'clon')
        self.clon = None
        if self.tipo == 'clon':
            self.clon = self.m.create_voice_clone_prompt(ref_audio=str(config['referencia']), ref_text=config['texto_referencia'])

    def decir(self, texto):
        import numpy as np
        semilla(self.config.get('semilla', 1234))
        c = self.config
        if self.tipo == 'diseno':
            wavs, self.sr = self.m.generate_voice_design(text=texto, language='Spanish', instruct=c['diseno'])
        elif self.tipo == 'hablante':
            wavs, self.sr = self.m.generate_custom_voice(text=texto, language='Spanish', speaker=c.get('hablante', 'Ryan'), instruct=c.get('instruccion', ''))
        else:
            wavs, self.sr = self.m.generate_voice_clone(text=texto, language='Spanish', voice_clone_prompt=self.clon)
        return np.asarray(wavs[0], dtype='float32')


class OmniVoice(Motor):
    """OmniVoice (k2-fsa, Apache-2.0). config: referencia + texto_referencia o diseno (atributos), pasos, velocidad, semilla."""

    def __init__(self, config):
        super().__init__(config)
        import torch
        from omnivoice import OmniVoice as O
        self.m = O.from_pretrained('k2-fsa/OmniVoice', device_map='cuda:0', dtype=torch.float16)
        self.sr = 24000

    def decir(self, texto):
        import numpy as np
        semilla(self.config.get('semilla', 1234))
        c = self.config
        kw = {'num_step': int(c.get('pasos', 32))}
        if 'velocidad' in c:
            kw['speed'] = float(c['velocidad'])
        if c.get('referencia'):
            kw.update(ref_audio=str(c['referencia']), ref_text=c.get('texto_referencia'))
        elif c.get('diseno'):
            kw['instruct'] = c['diseno']
        return np.asarray(self.m.generate(text=texto, **kw)[0], dtype='float32')


MOTORES = {'kokoro': Kokoro, 'chatterbox': Chatterbox, 'supertonic': Supertonic, 'voxcpm': VoxCPM, 'qwen3tts': Qwen3TTS, 'omnivoice': OmniVoice}


def main(lote_json: str) -> None:
    import numpy as np
    import soundfile as sf
    lote = json.loads(Path(lote_json).read_text(encoding='utf-8'))
    t0 = time.time()
    motor = MOTORES[lote['motor']](lote.get('config') or {})
    carga = time.time() - t0
    resultado = {'motor': lote['motor'], 'carga_s': round(carga, 2), 'items': []}
    for it in lote['items']:
        t = time.time()
        if lote.get('por_frases'):
            trozos = []
            for frase, pausa in trocear(it['texto'], float(lote.get('pausa_frase', 0.32))):
                if frase:
                    trozos.append(recortar(motor.decir(frase), motor.sr))
                trozos.append(np.zeros(int(round(pausa * motor.sr)), dtype='float32'))
            x = np.concatenate(trozos) if trozos else np.zeros(1, dtype='float32')
        else:
            x = recortar(motor.decir(it['texto']), motor.sr)
        seg = time.time() - t
        pico = float(np.max(np.abs(x))) if len(x) else 0.0
        if pico > 0.999:
            x = x / pico * 0.98
        Path(it['salida']).parent.mkdir(parents=True, exist_ok=True)
        sf.write(it['salida'], x, motor.sr, subtype='PCM_16')
        resultado['items'].append({'id': it.get('id'), 'salida': it['salida'], 'segundos': round(seg, 3),
                                   'duracion_s': round(len(x) / motor.sr, 3), 'sr': motor.sr})
        print(json.dumps(resultado['items'][-1], ensure_ascii=False), flush=True)
    if lote.get('resultado'):
        Path(lote['resultado']).write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main(sys.argv[1])
