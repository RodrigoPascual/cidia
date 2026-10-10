"""Voz: transcripción de una pregunta grabada («mantén pulsado para hablar»)."""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from cidia.db import obtener_bd

from cidia.ficheros import nombre_seguro
from cidia.ia import asr
from cidia.modelos import Instruccion, Paso, Puesto, Tarea
from cidia.permisos import alcance_de, departamentos_visibles
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
    if _ALUCINACION.search(texto):
        return ""
    from cidia.servicios.aportaciones import transcripcion_util

    return transcripcion_util(texto) or ""


def vocabulario(bd: Session, actor: Actor, tarea_id: int | None = None) -> str:
    """Códigos y nombres de las tareas que la persona puede ver (y los pasos de la tarea en curso),
    como prompt inicial de Whisper: con ruido de planta mejora mucho los códigos y las cifras."""
    alcance = alcance_de(bd, actor)
    deps = departamentos_visibles(alcance)
    consulta = select(Tarea.id, Tarea.codigo, Tarea.nombre).join(Puesto, Puesto.id == Tarea.puesto_id).where(Tarea.activa.is_(True))
    if not alcance.todo:
        if not deps:
            return ""
        consulta = consulta.where(Puesto.departamento_id.in_(deps))
    tareas = bd.execute(consulta.order_by(Tarea.id).limit(30)).all()
    partes: list[str] = []
    if tarea_id and any(t.id == tarea_id for t in tareas):
        pasos = bd.scalars(select(Paso.titulo).join(Instruccion, Instruccion.id == Paso.instruccion_id)
                           .where(Instruccion.tarea_id == tarea_id, Instruccion.estado == "publicada")
                           .order_by(Paso.orden).limit(12)).all()
        partes.extend(pasos)
    partes.extend(f"{t.codigo} {t.nombre}" if t.codigo else t.nombre for t in tareas)
    texto = "Vocabulario de la planta: " + "; ".join(partes)
    return texto[:700]


@router.post("/transcribir")
def transcribir(audio: UploadFile = File(...), tarea_id: int | None = Form(None),
                actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Devuelve {texto, duracion}. Solo con sesión de usuario (los invitados no usan la voz).
    `tarea_id` (opcional) añade los pasos de esa tarea al vocabulario."""
    tipo = (audio.content_type or "").split(";")[0].strip().lower()
    if not (tipo.startswith("audio/") or tipo in _TIPOS_GENERICOS):
        raise HTTPException(400, "El fichero no es una grabación de audio.")
    datos = audio.file.read(MAX_AUDIO + 1)
    if len(datos) > MAX_AUDIO:
        raise HTTPException(413, "La grabación es demasiado larga. Prueba con una pregunta más corta.")
    if len(datos) < MIN_AUDIO:
        raise HTTPException(400, "La grabación está vacía. Mantén pulsado el botón mientras hablas.")
    try:
        try:
            prompt = vocabulario(bd, actor, tarea_id)
        except Exception:  # noqa: BLE001  (el vocabulario ayuda, pero no es imprescindible)
            log.warning("No se pudo preparar el vocabulario de la voz", exc_info=True)
            prompt = ""
        r = asr.transcribir(datos, nombre=nombre_seguro(audio.filename or "voz.webm"), prompt=prompt or None)
    except Exception as e:  # noqa: BLE001  (servicio caído o respuesta que no se entiende)
        log.warning("Fallo de transcripción: %s", e)
        raise HTTPException(503, "El servicio de voz no está disponible ahora mismo. "
                                 "Escribe tu pregunta o inténtalo más tarde.") from e
    return {"texto": limpiar_transcripcion(r.get("texto")), "duracion": r.get("duracion")}
