"""Instrucciones de trabajo versionadas. PROVISIONAL: lo implementa el módulo de captura."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from cidia.modelos import Instruccion
from cidia.seguridad import Actor


def publicar(bd: Session, actor: Actor, instruccion_id: int) -> Instruccion:
    raise NotImplementedError


def a_dict(bd: Session, ins: Instruccion, con_pasos: bool = True) -> dict[str, Any]:
    raise NotImplementedError
