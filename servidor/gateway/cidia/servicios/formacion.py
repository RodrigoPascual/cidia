"""Formación: itinerario y micro-lecciones. PROVISIONAL: lo implementa el módulo de planta y formación."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from cidia.seguridad import Actor


def generar_microlecciones(bd: Session, instruccion_id: int) -> int:
    return 0


def encolar_generacion(instruccion_id: int) -> None:
    return None


def itinerario(bd: Session, actor: Actor) -> list[dict[str, Any]]:
    return []
