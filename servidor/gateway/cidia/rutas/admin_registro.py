"""Registro de actividad (sentencias xAPI) y auditoría de cambios de administración.

La lista xAPI se puede exportar completa en JSON para cargarla en un LRS externo.
Cada fila incluye un `texto` legible («Luis García completó Montaje de la brida B»).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from cidia.db import obtener_bd
from cidia.modelos import Auditoria, SentenciaXapi
from cidia.seguridad import Actor, requiere_admin
from cidia.xapi import VERBOS, auditar

router = APIRouter(prefix="/api/admin", tags=["administración"])

MAX_EXPORTAR = 100_000


def _zona() -> tzinfo:
    """Las fechas de los filtros se entienden en hora de la planta."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Europe/Madrid")
    except Exception:  # noqa: BLE001  (sin base de zonas horarias en el sistema)
        return timezone.utc


def _fecha(valor: str | None, fin: bool) -> datetime | None:
    """Acepta AAAA-MM-DD (día completo) o una fecha y hora ISO."""
    if not valor:
        return None
    try:
        if len(valor) == 10:
            d = date.fromisoformat(valor)
            momento = datetime.combine(d + timedelta(days=1) if fin else d, time(0), tzinfo=_zona())
            return momento
        momento = datetime.fromisoformat(valor)
        return momento if momento.tzinfo else momento.replace(tzinfo=_zona())
    except ValueError:
        raise HTTPException(400, f"La fecha «{valor}» no es válida. Usa el formato AAAA-MM-DD.")


def _es_id(valor: str) -> bool:
    """¿Es un id de persona? (solo cifras y dentro del rango de un entero de la base de datos)."""
    return valor.isdigit() and len(valor) <= 9


def _paginar(bd: Session, q: Select, pagina: int, por_pagina: int, orden: Any) -> tuple[int, list[Any]]:
    total = bd.scalar(select(func.count()).select_from(q.order_by(None).subquery())) or 0
    filas = bd.scalars(q.order_by(orden).offset((pagina - 1) * por_pagina).limit(por_pagina)).all()
    return total, list(filas)


# --------------------------------------------------------------------------- xAPI


def _verbo_texto(s: SentenciaXapi) -> str:
    try:
        return s.sentencia["verb"]["display"]["es-ES"]
    except (KeyError, TypeError):
        return VERBOS.get(s.verbo, ("", s.verbo))[1]


def sentencia_dict(s: SentenciaXapi) -> dict[str, Any]:
    verbo = _verbo_texto(s)
    objeto = s.objeto_nombre or s.objeto_tipo
    return {
        "id": s.id,
        "momento": s.momento.isoformat() if s.momento else None,
        "actor_id": s.actor_id,
        "actor_nombre": s.actor_nombre,
        "verbo": s.verbo,
        "verbo_texto": verbo,
        "objeto_tipo": s.objeto_tipo,
        "objeto_id": s.objeto_id,
        "objeto_nombre": s.objeto_nombre,
        "texto": f"{s.actor_nombre or 'Alguien'} {verbo} {objeto}",
        "resultado": s.resultado,
        "contexto": s.contexto,
        "sentencia": s.sentencia,
    }


def _consulta_xapi(actor: str | None, verbo: str | None, objeto: str | None, objeto_tipo: str | None,
                   desde: str | None, hasta: str | None) -> Select:
    q = select(SentenciaXapi)
    if actor and actor.strip():
        a = actor.strip()
        q = q.where(SentenciaXapi.actor_id == int(a)) if _es_id(a) else \
            q.where(func.lower(SentenciaXapi.actor_nombre).like(f"%{a.lower()}%"))
    if verbo:
        q = q.where(SentenciaXapi.verbo == verbo)
    if objeto_tipo:
        q = q.where(SentenciaXapi.objeto_tipo == objeto_tipo)
    if objeto and objeto.strip():
        o = objeto.strip().lower()
        q = q.where(or_(func.lower(SentenciaXapi.objeto_tipo) == o,
                        func.lower(func.coalesce(SentenciaXapi.objeto_nombre, "")).like(f"%{o}%")))
    ini, fin = _fecha(desde, False), _fecha(hasta, True)
    if ini:
        q = q.where(SentenciaXapi.momento >= ini)
    if fin:
        q = q.where(SentenciaXapi.momento < fin)
    return q


@router.get("/xapi")
def xapi(
    actor_filtro: str | None = Query(None, alias="actor"),
    verbo: str | None = None,
    objeto: str | None = None,
    objeto_tipo: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    _: Actor = Depends(requiere_admin),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    q = _consulta_xapi(actor_filtro, verbo, objeto, objeto_tipo, desde, hasta)
    total, filas = _paginar(bd, q, pagina, por_pagina, SentenciaXapi.momento.desc())
    usados = set(bd.scalars(select(SentenciaXapi.verbo).distinct()).all())
    verbos = [{"clave": k, "nombre": v[1]} for k, v in VERBOS.items()]
    verbos += [{"clave": k, "nombre": k} for k in sorted(usados - set(VERBOS))]
    tipos = sorted(bd.scalars(select(SentenciaXapi.objeto_tipo).distinct()).all())
    return {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": max(1, -(-total // por_pagina)),
        "sentencias": [sentencia_dict(s) for s in filas],
        "verbos": verbos,
        "tipos_objeto": tipos,
    }


@router.get("/xapi/exportar")
def exportar_xapi(
    actor_filtro: str | None = Query(None, alias="actor"),
    verbo: str | None = None,
    objeto: str | None = None,
    objeto_tipo: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    actor: Actor = Depends(requiere_admin),
    bd: Session = Depends(obtener_bd),
) -> JSONResponse:
    """Lista de sentencias xAPI completas (orden cronológico), lista para importar en un LRS."""
    q = _consulta_xapi(actor_filtro, verbo, objeto, objeto_tipo, desde, hasta)
    filas = bd.scalars(q.order_by(SentenciaXapi.momento).limit(MAX_EXPORTAR)).all()
    auditar(bd, actor, "exportar_xapi", "xapi", None,
            {"resumen": f"Exportó {len(filas)} sentencias xAPI",
             "filtros": {k: v for k, v in {"actor": actor_filtro, "verbo": verbo, "objeto": objeto,
                                          "objeto_tipo": objeto_tipo, "desde": desde, "hasta": hasta}.items() if v}})
    bd.commit()
    nombre = f"cidia-xapi-{datetime.now(timezone.utc):%Y%m%d-%H%M}.json"
    return JSONResponse([s.sentencia for s in filas],
                        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


# --------------------------------------------------------------------------- auditoría


def auditoria_dict(a: Auditoria) -> dict[str, Any]:
    detalle = a.detalle or {}
    resumen = detalle.get("resumen") if isinstance(detalle, dict) else None
    texto = resumen or " ".join(p for p in (a.accion.replace("_", " "), a.entidad or "",
                                            f"#{a.entidad_id}" if a.entidad_id else "") if p)
    return {
        "id": a.id,
        "momento": a.momento.isoformat() if a.momento else None,
        "usuario_id": a.usuario_id,
        "usuario_nombre": a.usuario_nombre,
        "accion": a.accion,
        "entidad": a.entidad,
        "entidad_id": a.entidad_id,
        "detalle": a.detalle,
        "texto": texto,
    }


@router.get("/auditoria")
def auditoria(
    usuario: str | None = None,
    accion: str | None = None,
    entidad: str | None = None,
    texto: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    _: Actor = Depends(requiere_admin),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    q = select(Auditoria)
    if usuario and usuario.strip():
        u = usuario.strip()
        q = q.where(Auditoria.usuario_id == int(u)) if _es_id(u) else \
            q.where(func.lower(Auditoria.usuario_nombre).like(f"%{u.lower()}%"))
    if accion:
        q = q.where(Auditoria.accion == accion)
    if entidad:
        q = q.where(Auditoria.entidad == entidad)
    if texto and texto.strip():
        q = q.where(func.lower(cast(Auditoria.detalle, Text)).like(f"%{texto.strip().lower()}%"))
    ini, fin = _fecha(desde, False), _fecha(hasta, True)
    if ini:
        q = q.where(Auditoria.momento >= ini)
    if fin:
        q = q.where(Auditoria.momento < fin)
    total, filas = _paginar(bd, q, pagina, por_pagina, Auditoria.momento.desc())
    return {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": max(1, -(-total // por_pagina)),
        "filas": [auditoria_dict(a) for a in filas],
        "acciones": sorted(bd.scalars(select(Auditoria.accion).distinct()).all()),
        "entidades": sorted(e for e in bd.scalars(select(Auditoria.entidad).distinct()).all() if e),
    }
