"""Lagunas: preguntas que el copiloto no supo responder con respaldo.

Las registra y las resuelve el módulo de consulta (servicios/lagunas.py); aquí se listan y se
gestionan:
  · jefes (su departamento) y administración (todas): GET /api/lagunas, descartar y reabrir;
  · cualquier empleado: GET /api/lagunas/abiertas-de-mi-departamento, las «preguntas pendientes»
    de su departamento para que quien sepa la respuesta la aporte (sin datos personales).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import false, func, select, true
from sqlalchemy.orm import Session

from cidia.db import obtener_bd
from cidia.modelos import Aportacion, Departamento, Laguna, Tarea
from cidia.seguridad import Actor, requiere_jefe, usuario_actual
from cidia.xapi import auditar

router = APIRouter(prefix="/api/lagunas", tags=["lagunas"])

ESTADOS = ("abierta", "resuelta", "descartada")


def _alcance(actor: Actor):
    """Condición SQL: lagunas que el actor puede gestionar."""
    if actor.es_admin:
        return true()
    if actor.departamento_id is None:
        return false()
    return Laguna.departamento_id == actor.departamento_id


def _ejemplos(lag: Laguna, maximo: int = 5) -> list[dict[str, Any]]:
    """Formas en que se ha hecho la pregunta, solo texto y fecha (nunca quién la hizo).

    Acepta cadenas o diccionarios ({pregunta|texto|consulta, fecha|momento|creada})."""
    salida: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for e in reversed(lag.ejemplos or []):
        if isinstance(e, str):
            texto, fecha = e, None
        elif isinstance(e, dict):
            texto = e.get("pregunta") or e.get("texto") or e.get("consulta")
            fecha = e.get("fecha") or e.get("momento") or e.get("creada")
        else:
            continue
        texto = str(texto or "").strip()
        if not texto or texto.lower() in vistos:
            continue
        vistos.add(texto.lower())
        salida.append({"pregunta": texto[:500], "fecha": fecha if isinstance(fecha, str) else None})
        if len(salida) >= maximo:
            break
    return salida


def _en_revision(bd: Session, ids: list[int]) -> dict[int, int]:
    """Respuestas aportadas y aún sin revisar, por laguna."""
    if not ids:
        return {}
    return dict(bd.execute(
        select(Aportacion.laguna_id, func.count())
        .where(Aportacion.laguna_id.in_(ids), Aportacion.estado.in_(("procesando", "pendiente")))
        .group_by(Aportacion.laguna_id)
    ).all())


def _tareas(bd: Session, lags: list[Laguna]) -> dict[int, Tarea]:
    ids = {g.tarea_id for g in lags if g.tarea_id}
    return {t.id: t for t in bd.scalars(select(Tarea).where(Tarea.id.in_(ids)))} if ids else {}


def _tarea_dict(t: Tarea | None) -> dict[str, Any] | None:
    return {"id": t.id, "codigo": t.codigo, "nombre": t.nombre} if t else None


def _cargar(bd: Session, actor: Actor, laguna_id: int) -> Laguna:
    lag = bd.get(Laguna, laguna_id)
    if lag is None or not (actor.es_admin or (lag.departamento_id is not None
                                                 and lag.departamento_id == actor.departamento_id)):
        raise HTTPException(404, "Laguna no encontrada.")
    return lag


def _a_dicts(bd: Session, lags: list[Laguna]) -> list[dict[str, Any]]:
    tareas = _tareas(bd, lags)
    revision = _en_revision(bd, [g.id for g in lags])
    deps = {d.id: d.nombre for d in bd.scalars(select(Departamento))}
    aps_ids = {g.aportacion_id for g in lags if g.aportacion_id}
    aps = {a.id: a for a in bd.scalars(select(Aportacion).where(Aportacion.id.in_(aps_ids)))} if aps_ids else {}
    salida = []
    for g in lags:
        ap = aps.get(g.aportacion_id) if g.aportacion_id else None
        salida.append({
            "id": g.id,
            "pregunta": g.pregunta,
            "frecuencia": g.frecuencia,
            "estado": g.estado,
            "departamento": {"id": g.departamento_id, "nombre": deps.get(g.departamento_id)} if g.departamento_id else None,
            "tarea": _tarea_dict(tareas.get(g.tarea_id) if g.tarea_id else None),
            "ejemplos": _ejemplos(g),
            "primera_vez": g.primera_vez.isoformat() if g.primera_vez else None,
            "ultima_vez": g.ultima_vez.isoformat() if g.ultima_vez else None,
            "respuestas_en_revision": revision.get(g.id, 0),
            "aportacion": {"id": ap.id, "titulo": ap.titulo, "estado": ap.estado, "documento_id": ap.documento_id}
            if ap else None,
        })
    return salida


@router.get("")
def listar(
    estado: str = Query("abierta", description="abierta | resuelta | descartada | todas"),
    orden: str = Query("frecuencia", description="frecuencia | reciente"),
    departamento_id: int | None = Query(None, description="solo administración"),
    limite: int = Query(100, ge=1, le=500),
    actor: Actor = Depends(requiere_jefe),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    """Lagunas del departamento del jefe (la administración ve todas), las más preguntadas primero."""
    if estado not in (*ESTADOS, "todas"):
        raise HTTPException(400, "Estado no válido: usa abierta, resuelta, descartada o todas.")
    if orden not in ("frecuencia", "reciente"):
        raise HTTPException(400, "Orden no válido: usa frecuencia o reciente.")
    filtro = _alcance(actor)
    if departamento_id is not None and actor.es_admin:
        filtro = Laguna.departamento_id == departamento_id
    q = select(Laguna).where(filtro)
    if estado != "todas":
        q = q.where(Laguna.estado == estado)
    if orden == "reciente":
        q = q.order_by(Laguna.ultima_vez.desc(), Laguna.id.desc())
    else:
        q = q.order_by(Laguna.frecuencia.desc(), Laguna.ultima_vez.desc(), Laguna.id.desc())
    lags = list(bd.scalars(q.limit(limite)))
    conteo = {e: 0 for e in ESTADOS}
    for e, n in bd.execute(select(Laguna.estado, func.count()).where(filtro).group_by(Laguna.estado)).all():
        conteo[e] = n
    return {"lagunas": _a_dicts(bd, lags), "contadores": conteo}


@router.get("/abiertas-de-mi-departamento")
def abiertas_de_mi_departamento(actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """«Preguntas pendientes» del departamento de quien pregunta, para que quien lo sepa responda.

    Sin datos personales: ni quién preguntó ni cómo se formuló cada vez."""
    if actor.departamento_id is None and not actor.es_admin:
        return {"lagunas": []}
    q = select(Laguna).where(Laguna.estado == "abierta")
    if actor.departamento_id is not None:
        q = q.where(Laguna.departamento_id == actor.departamento_id)
    lags = list(bd.scalars(q.order_by(Laguna.frecuencia.desc(), Laguna.ultima_vez.desc()).limit(30)))
    tareas = _tareas(bd, lags)
    revision = _en_revision(bd, [g.id for g in lags])
    mias = {
        a.laguna_id: a for a in bd.scalars(select(Aportacion).where(
            Aportacion.autor_id == actor.id, Aportacion.laguna_id.in_([g.id for g in lags]),
            Aportacion.estado.in_(("procesando", "pendiente"))))
    } if lags else {}
    return {"lagunas": [
        {
            "id": g.id,
            "pregunta": g.pregunta,
            "frecuencia": g.frecuencia,
            "ultima_vez": g.ultima_vez.isoformat() if g.ultima_vez else None,
            "tarea": _tarea_dict(tareas.get(g.tarea_id) if g.tarea_id else None),
            "respuestas_en_revision": revision.get(g.id, 0),
            "mi_respuesta": {"id": mias[g.id].id, "estado": mias[g.id].estado} if g.id in mias else None,
        }
        for g in lags
    ]}


@router.post("/{laguna_id}/descartar")
def descartar(laguna_id: int, actor: Actor = Depends(requiere_jefe), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """La pregunta no procede (fuera de ámbito, repetida, mal planteada...)."""
    lag = _cargar(bd, actor, laguna_id)
    if lag.estado == "descartada":
        raise HTTPException(409, "Esta laguna ya está descartada.")
    anterior = lag.estado
    lag.estado = "descartada"
    auditar(bd, actor, "descartar_laguna", "laguna", lag.id, {"anterior": anterior, "pregunta": lag.pregunta[:200]})
    bd.commit()
    return _a_dicts(bd, [lag])[0]


@router.post("/{laguna_id}/reabrir")
def reabrir(laguna_id: int, actor: Actor = Depends(requiere_jefe), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Vuelve a ponerla como pregunta pendiente (p. ej. si la respuesta publicada no bastaba)."""
    lag = _cargar(bd, actor, laguna_id)
    if lag.estado == "abierta":
        raise HTTPException(409, "Esta laguna ya está abierta.")
    anterior = lag.estado
    lag.estado = "abierta"
    auditar(bd, actor, "reabrir_laguna", "laguna", lag.id, {"anterior": anterior, "pregunta": lag.pregunta[:200]})
    bd.commit()
    return _a_dicts(bd, [lag])[0]
