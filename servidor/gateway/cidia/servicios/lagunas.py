"""Lagunas: preguntas sin respaldo. PROVISIONAL: lo implementa el módulo de consulta."""

from __future__ import annotations

from sqlalchemy.orm import Session

from cidia.modelos import Laguna


def registrar(bd: Session, pregunta: str, departamento_id: int | None, tarea_id: int | None = None) -> Laguna | None:
    return None


def resolver(bd: Session, laguna_id: int, aportacion_id: int) -> None:
    return None
