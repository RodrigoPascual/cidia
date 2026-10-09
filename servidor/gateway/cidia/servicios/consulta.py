"""Consulta al copiloto con citas (RAG), lagunas y memoria. PROVISIONAL: lo implementa el módulo de consulta."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from cidia.config import ajustes
from cidia.conocimiento import Encontrado, motor
from cidia.permisos import alcance_de
from cidia.seguridad import Actor


def buscar(bd: Session, actor: Actor, pregunta: str, k: int | None = None) -> list[Encontrado]:
    return motor().buscar(bd, pregunta, alcance_de(bd, actor), k or ajustes().fragmentos_por_consulta)


async def responder_stream(bd: Session, actor: Actor, pregunta: str, modo: str = "normal",
                           contexto: dict[str, Any] | None = None,
                           historial: list[dict[str, str]] | None = None) -> AsyncIterator[dict[str, Any]]:
    raise NotImplementedError
    yield {}


def responder(bd: Session, actor: Actor, pregunta: str, modo: str = "normal", contexto: dict[str, Any] | None = None,
              historial: list[dict[str, str]] | None = None) -> dict[str, Any]:
    raise NotImplementedError
