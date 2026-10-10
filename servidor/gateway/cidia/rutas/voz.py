"""Voz: transcripción de una pregunta grabada («mantén pulsado para hablar»)."""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from cidia.ficheros import nombre_seguro
from cidia.ia import asr
from cidia.seguridad import Actor, usuario_actual

log = logging.getLogger("cidia.voz")

router = APIRouter(prefix="/api/voz", tags=["voz"])

MAX_AUDIO = 25 * 1024 * 1024  # unos minutos de voz comprimida sobran para una pregunta
MIN_AUDIO = 200  # menos que esto es una grabación vacía
# Lo que envían los navegadores y la app al grabar (Chrome a veces etiqueta el webm como vídeo) y los
# clientes que no indican el tipo. Una imagen o un documento no se manda al servicio de voz.
_TIPOS_GENERICOS = {"", "application/octet-stream", "video/webm", "video/mp4", "video/ogg"}
# Lo que Whisper «oye» en una grabación casi en silencio (pulsar y soltar sin hablar, ruido de la
# nave): créditos de subtítulos, despedidas de vídeo o etiquetas de sonido. No es una pregunta, y
# enviarla tal cual haría responder al copiloto a algo que nadie ha dicho.
_ALUCINACION = re.compile(
    r"amara\.org|subt[ií]tulos? (?:realizados? )?por|gracias por (?:ver|mirar)|suscr[ií]bete|dale (?:a )?like"
    r"|^\W*[\[(][^\])]{1,30}[\])]\W*$",
    re.I,
)


def limpiar_transcripcion(texto: str | None) -> str:
    """Texto transcrito listo para enviar al copiloto, o «» si es una alucinación típica del silencio."""
    texto = " ".join((texto or "").split())
    return "" if _ALUCINACION.search(texto) else texto


@router.post("/transcribir")
def transcribir(audio: UploadFile = File(...), actor: Actor = Depends(usuario_actual)) -> dict[str, Any]:
    """Devuelve {texto, duracion}. Solo con sesión de usuario (los invitados no usan la voz)."""
    tipo = (audio.content_type or "").split(";")[0].strip().lower()
    if not (tipo.startswith("audio/") or tipo in _TIPOS_GENERICOS):
        raise HTTPException(400, "El fichero no es una grabación de audio.")
    datos = audio.file.read(MAX_AUDIO + 1)
    if len(datos) > MAX_AUDIO:
        raise HTTPException(413, "La grabación es demasiado larga. Prueba con una pregunta más corta.")
    if len(datos) < MIN_AUDIO:
        raise HTTPException(400, "La grabación está vacía. Mantén pulsado el botón mientras hablas.")
    try:
        r = asr.transcribir(datos, nombre=nombre_seguro(audio.filename or "voz.webm"))
    except Exception as e:  # noqa: BLE001  (servicio caído o respuesta que no se entiende)
        log.warning("Fallo de transcripción: %s", e)
        raise HTTPException(503, "El servicio de voz no está disponible ahora mismo. "
                                 "Escribe tu pregunta o inténtalo más tarde.") from e
    return {"texto": limpiar_transcripcion(r.get("texto")), "duracion": r.get("duracion")}
