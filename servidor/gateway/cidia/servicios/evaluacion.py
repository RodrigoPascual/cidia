"""Evaluación: cuestionarios y observaciones. PROVISIONAL: lo implementa el módulo de evaluación."""

from __future__ import annotations

from sqlalchemy.orm import Session


def generar_preguntas(bd: Session, instruccion_id: int, n: int = 6) -> int:
    return 0


def encolar_generacion(instruccion_id: int) -> None:
    return None
