"""Transcripción de voz a través de un servicio compatible con /v1/audio/transcriptions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from cidia.config import ajustes


class ErrorVoz(RuntimeError):
    pass


def transcribir(
    audio: bytes | Path | str,
    nombre: str = "audio.webm",
    con_marcas: bool = False,
    idioma: str | None = None,
) -> dict[str, Any]:
    """Devuelve {"texto": str, "segmentos": [{"inicio", "fin", "texto"}], "duracion": float|None}."""
    a = ajustes()
    datos = Path(audio).read_bytes() if isinstance(audio, (Path, str)) else audio
    if isinstance(audio, (Path, str)):
        nombre = Path(audio).name
    campos: dict[str, Any] = {
        "model": a.asr_modelo,
        "language": idioma or a.asr_idioma,
        "response_format": "verbose_json" if con_marcas else "json",
        "temperature": "0",
    }
    if con_marcas:
        campos["timestamp_granularities[]"] = "segment"
    try:
        r = httpx.post(
            a.asr_base_url.rstrip("/") + "/audio/transcriptions",
            data=campos,
            files={"file": (nombre, datos)},
            timeout=max(120.0, a.llm_timeout),
        )
    except httpx.HTTPError as e:
        raise ErrorVoz(f"No se puede contactar con el servicio de voz: {e}") from e
    if r.status_code != 200:
        raise ErrorVoz(f"El servicio de voz respondió {r.status_code}: {r.text[:300]}")
    j = r.json()
    segmentos = [
        {"inicio": float(s.get("start", 0)), "fin": float(s.get("end", 0)), "texto": (s.get("text") or "").strip()}
        for s in j.get("segments", []) or []
    ]
    return {"texto": (j.get("text") or "").strip(), "segmentos": segmentos, "duracion": j.get("duration")}


def salud() -> dict[str, Any]:
    try:
        r = httpx.get(ajustes().asr_base_url.rstrip("/").removesuffix("/v1") + "/health", timeout=5)
        return {"ok": r.status_code == 200}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
