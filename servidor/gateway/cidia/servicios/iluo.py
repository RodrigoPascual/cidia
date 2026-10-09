"""Niveles ILUO. PROVISIONAL: lo implementa el módulo de evaluación y progreso."""

from __future__ import annotations

from sqlalchemy.orm import Session

from cidia.modelos import NivelIluo
from cidia.seguridad import Actor

LETRAS = ["", "I", "L", "U", "O"]


def nivel_letra(n: int) -> str:
    return LETRAS[n] if 0 <= n < len(LETRAS) else ""


def recalcular(bd: Session, usuario_id: int, tarea_id: int) -> NivelIluo | None:
    return None


def marcar_reevaluacion(bd: Session, tarea_id: int) -> int:
    return 0


def validar_formador(bd: Session, actor: Actor, usuario_id: int, tarea_id: int) -> NivelIluo | None:
    return None
