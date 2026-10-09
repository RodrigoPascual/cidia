"""Qué conocimiento puede encontrar cada persona.

La regla (ver docs/arquitectura.md, sección 4):
  1. documentos públicos;
  2. de su departamento con nivel_minimo <= su nivel;
  3. material de formación de los departamentos en los que tiene una formación activa;
  4. la administración lo ve todo.
El alcance se calcula SIEMPRE en el servidor a partir de la sesión.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from cidia.modelos import Documento, Formacion
from cidia.seguridad import Actor


@dataclass(frozen=True)
class ElementoAlcance:
    departamento_id: int
    nivel_max: int  # niveles 1..nivel_max (0 si solo formación)
    solo_formacion: bool = False


@dataclass
class Alcance:
    publico: bool = True
    todo: bool = False
    elementos: list[ElementoAlcance] = field(default_factory=list)

    def describir(self) -> dict:
        return {
            "publico": self.publico,
            "todo": self.todo,
            "elementos": [e.__dict__ for e in self.elementos],
        }


def alcance_de(bd: Session, actor: Actor) -> Alcance:
    if actor.es_invitado:
        return Alcance(publico=True)
    if actor.es_admin:
        return Alcance(publico=True, todo=True)
    elementos: list[ElementoAlcance] = []
    if actor.departamento_id:
        elementos.append(ElementoAlcance(actor.departamento_id, actor.nivel_orden))
    activas = bd.scalars(
        select(Formacion.departamento_id).where(Formacion.usuario_id == actor.id, Formacion.estado == "activa")
    ).all()
    for dep in set(activas):
        if dep != actor.departamento_id:
            elementos.append(ElementoAlcance(dep, 0, solo_formacion=True))
    return Alcance(publico=True, elementos=elementos)


def filtro_documentos(alcance: Alcance) -> ColumnElement[bool]:
    """Condición SQL sobre Documento que aplica el alcance (solo documentos listos)."""
    listo = Documento.estado == "listo"
    if alcance.todo:
        return listo
    conds: list[ColumnElement[bool]] = []
    if alcance.publico:
        conds.append(Documento.es_publico.is_(True))
    for e in alcance.elementos:
        if e.solo_formacion:
            conds.append(and_(Documento.departamento_id == e.departamento_id, Documento.es_formacion.is_(True)))
        else:
            conds.append(and_(Documento.departamento_id == e.departamento_id, Documento.nivel_minimo <= e.nivel_max))
    if not conds:
        return false()
    return and_(listo, or_(*conds))


def puede_ver(alcance: Alcance, doc: Documento) -> bool:
    if doc.estado != "listo":
        return False
    if alcance.todo:
        return True
    if alcance.publico and doc.es_publico:
        return True
    for e in alcance.elementos:
        if doc.departamento_id != e.departamento_id:
            continue
        if e.solo_formacion and doc.es_formacion:
            return True
        if not e.solo_formacion and doc.nivel_minimo <= e.nivel_max:
            return True
    return False


def departamentos_visibles(alcance: Alcance) -> set[int]:
    return {e.departamento_id for e in alcance.elementos}
