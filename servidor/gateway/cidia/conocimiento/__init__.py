"""Motores de conocimiento: propio (PostgreSQL + pgvector) o WeKnora."""

from __future__ import annotations

from functools import lru_cache

from cidia.config import ajustes
from cidia.conocimiento.base import Encontrado, MotorConocimiento, fusion_rrf


@lru_cache
def motor() -> MotorConocimiento:
    if ajustes().motor_conocimiento == "weknora":
        from cidia.conocimiento.weknora import MotorWeKnora

        return MotorWeKnora()
    from cidia.conocimiento.pgvector import MotorPgvector

    return MotorPgvector()


__all__ = ["Encontrado", "MotorConocimiento", "fusion_rrf", "motor"]
