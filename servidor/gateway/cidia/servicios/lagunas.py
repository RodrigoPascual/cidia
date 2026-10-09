"""Lagunas: preguntas que el copiloto no supo responder con respaldo.

Las preguntas parecidas del mismo departamento se agrupan (similitud de embeddings >= 0.85)
para que el jefe vea «¿Qué presión lleva el cilindro de la prensa 2? · 3 veces» y no tres
filas sueltas. Ninguna función hace commit (lo hace quien llama).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cidia.ia import llm
from cidia.modelos import Laguna, ahora

log = logging.getLogger("cidia.lagunas")

UMBRAL_AGRUPAR = 0.85
MAX_EJEMPLOS = 5


def _normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni signos: para comparar preguntas cuando no hay embeddings."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", t).strip()


def _filtro_departamento(departamento_id: int | None) -> Any:
    if departamento_id is None:
        return Laguna.departamento_id.is_(None)
    return Laguna.departamento_id == departamento_id


def _parecida(bd: Session, pregunta: str, departamento_id: int | None,
              vector: list[float] | None) -> Laguna | None:
    """Laguna abierta (o descartada) del mismo departamento que pregunta lo mismo."""
    estados = Laguna.estado.in_(["abierta", "descartada"])
    if vector:
        dist = Laguna.embedding.cosine_distance(vector)
        fila = bd.execute(
            select(Laguna, (1 - dist).label("sim"))
            .where(estados, _filtro_departamento(departamento_id), Laguna.embedding.is_not(None),
                   func.vector_dims(Laguna.embedding) == len(vector))
            .order_by(dist)
            .limit(1)
        ).first()
        if fila and float(fila.sim) >= UMBRAL_AGRUPAR:
            return fila[0]
    # Sin vector (modelo caído) o sin parecidas por significado: misma pregunta escrita igual.
    clave = _normalizar(pregunta)
    candidatas = bd.scalars(
        select(Laguna).where(estados, _filtro_departamento(departamento_id)).order_by(Laguna.ultima_vez.desc()).limit(200)
    ).all()
    for lg in candidatas:
        if _normalizar(lg.pregunta) == clave or any(_normalizar(e) == clave for e in lg.ejemplos or []):
            return lg
    return None


def registrar(bd: Session, pregunta: str, departamento_id: int | None, tarea_id: int | None = None) -> Laguna:
    """Apunta una pregunta sin respaldo; si ya hay una parecida, aumenta su frecuencia."""
    pregunta = (pregunta or "").strip()[:2000]
    try:
        vector: list[float] | None = llm.embeddings([pregunta])[0]
    except Exception as e:  # noqa: BLE001  (sin modelo de embeddings se agrupa por texto)
        log.warning("Sin embedding para la laguna: %s", e)
        vector = None
    lg = _parecida(bd, pregunta, departamento_id, vector)
    if lg is None:
        lg = Laguna(pregunta=pregunta, departamento_id=departamento_id, tarea_id=tarea_id, frecuencia=1,
                    embedding=vector, estado="abierta", ejemplos=[pregunta])
        bd.add(lg)
        bd.flush()
        return lg
    lg.frecuencia = (lg.frecuencia or 0) + 1
    lg.ultima_vez = ahora()
    if tarea_id and not lg.tarea_id:
        lg.tarea_id = tarea_id
    ejemplos = list(lg.ejemplos or [])
    if _normalizar(pregunta) not in {_normalizar(e) for e in ejemplos}:
        ejemplos.append(pregunta)
        lg.ejemplos = ejemplos[-MAX_EJEMPLOS:]  # lista nueva: JSONB detecta el cambio
    bd.flush()
    return lg


def resolver(bd: Session, laguna_id: int, aportacion_id: int) -> None:
    """Marca la laguna como resuelta por una aportación validada."""
    lg = bd.get(Laguna, laguna_id)
    if lg is None:
        return
    lg.estado = "resuelta"
    lg.aportacion_id = aportacion_id
    bd.flush()


def a_dict(lg: Laguna) -> dict[str, Any]:
    """Representación JSON de una laguna (para las pantallas de jefes y administración)."""
    return {
        "id": lg.id,
        "pregunta": lg.pregunta,
        "departamento_id": lg.departamento_id,
        "tarea_id": lg.tarea_id,
        "frecuencia": lg.frecuencia,
        "estado": lg.estado,
        "aportacion_id": lg.aportacion_id,
        "ejemplos": list(lg.ejemplos or []),
        "primera_vez": lg.primera_vez.isoformat() if lg.primera_vez else None,
        "ultima_vez": lg.ultima_vez.isoformat() if lg.ultima_vez else None,
    }
