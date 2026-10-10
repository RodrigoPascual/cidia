"""Servicio de transcripción de CidIA (compatible con POST /v1/audio/transcriptions).

faster-whisper (MIT) + CTranslate2 (MIT). El audio se decodifica con ffmpeg LGPL llamado
como programa externo, así que no se usa PyAV (cuyas ruedas llevan códecs GPL): se sustituye
por un módulo vacío antes de importar faster-whisper.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import types

import numpy as np

# faster_whisper importa `av` al cargarse, aunque no lo usa si recibe un array de numpy.
sys.modules.setdefault("av", types.ModuleType("av"))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402

MODELO = os.environ.get("ASR_MODELO", "base")
DISPOSITIVO = os.environ.get("ASR_DISPOSITIVO", "cpu")
PRECISION = os.environ.get("ASR_PRECISION", "int8")
HILOS = int(os.environ.get("ASR_HILOS", "2"))
LIBERAR_TRAS = int(os.environ.get("ASR_LIBERAR_TRAS_S", "600"))  # descarga el modelo si no se usa

app = FastAPI(title="CidIA ASR")
_modelo: WhisperModel | None = None
_ultimo_uso = 0.0
_cerrojo = threading.Lock()


def modelo() -> WhisperModel:
    global _modelo, _ultimo_uso
    with _cerrojo:
        if _modelo is None:
            _modelo = WhisperModel(MODELO, device=DISPOSITIVO, compute_type=PRECISION, cpu_threads=HILOS,
                                   download_root=os.environ.get("ASR_DIR_MODELOS", "/modelos"))
        _ultimo_uso = time.time()
        return _modelo


def _liberador() -> None:
    global _modelo
    while True:
        time.sleep(30)
        with _cerrojo:
            if _modelo is not None and LIBERAR_TRAS > 0 and time.time() - _ultimo_uso > LIBERAR_TRAS:
                _modelo = None


threading.Thread(target=_liberador, daemon=True).start()


def a_pcm(datos: bytes) -> np.ndarray:
    r = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", "16000", "pipe:1"],
        input=datos, capture_output=True,
    )
    if r.returncode != 0:
        raise HTTPException(400, f"No se puede leer el audio: {r.stderr.decode(errors='ignore')[:200]}")
    return np.frombuffer(r.stdout, np.float32)


@app.get("/health")
def salud() -> dict:
    return {"estado": "ok", "modelo": MODELO, "cargado": _modelo is not None}


@app.post("/v1/audio/transcriptions")
def transcribir(
    file: UploadFile = File(...),
    model: str = Form("whisper"),
    language: str | None = Form("es"),
    response_format: str = Form("json"),
    temperature: float = Form(0.0),
    prompt: str | None = Form(None),
) -> dict:
    audio = a_pcm(file.file.read())
    if audio.size == 0:
        return {"text": "", "segments": [], "duration": 0.0}
    # Con temperatura 0 se permiten reintentos a temperaturas mayores si la salida se repite
    # o es poco probable (prueba de ruido: docs/prueba-audio-ruido.md).
    temperaturas = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0) if temperature == 0 else temperature
    segmentos, info = modelo().transcribe(
        audio, language=language or None, vad_filter=True, beam_size=5, temperature=temperaturas,
        initial_prompt=prompt or None, condition_on_previous_text=False,
    )
    segs = [{"id": i, "start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
            for i, s in enumerate(segmentos)]
    texto = " ".join(s["text"] for s in segs).strip()
    if response_format == "verbose_json":
        return {"text": texto, "language": info.language, "duration": info.duration, "segments": segs}
    if response_format == "text":
        return {"text": texto}
    return {"text": texto}
