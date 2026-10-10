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
from cidia.rutas.admin import columna_sin_tildes, sin_tildes
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


# Verbos que algún módulo registra sin estar en xapi.VERBOS: así no se muestran «creo» o «uso_modelo».
VERBOS_LEGIBLES = {"creo": "creó", "edito": "editó", "movio": "movió", "descargo": "descargó", "ejecuto": "ejecutó",
                   "renombro": "renombró", "subio": "subió", "borro": "borró"}


def nombre_verbo(clave: str, texto: str | None = None) -> str:
    """Texto legible de un verbo: el de la sentencia salvo que sea la clave en bruto."""
    if texto and texto != clave:
        return texto
    if clave in VERBOS:
        return VERBOS[clave][1]
    return VERBOS_LEGIBLES.get(clave, clave.replace("_", " "))


def _verbo_texto(s: SentenciaXapi) -> str:
    try:
        texto = s.sentencia["verb"]["display"]["es-ES"]
    except (KeyError, TypeError):
        texto = None
    return nombre_verbo(s.verbo, texto)


def frase_sentencia(s: SentenciaXapi, verbo: str) -> str:
    """«Luis García completó Montaje de la brida B», con dos casos que en bruto se leían mal:
    «inició Inicio de sesión» y «alcanzó el nivel Montaje…» (sin decir qué nivel)."""
    quien = s.actor_nombre or "Alguien"
    objeto = s.objeto_nombre or s.objeto_tipo
    if s.objeto_tipo == "sesion":
        return f"{quien} {verbo} sesión"
    nivel = (s.resultado or {}).get("nivel") if isinstance(s.resultado, dict) else None
    if s.verbo == "certifico" and nivel:
        return f"{quien} {verbo} {nivel} en {objeto}"
    return f"{quien} {verbo} {objeto}"


def sentencia_dict(s: SentenciaXapi) -> dict[str, Any]:
    verbo = _verbo_texto(s)
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
        "texto": frase_sentencia(s, verbo),
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
            q.where(columna_sin_tildes(SentenciaXapi.actor_nombre).like(f"%{sin_tildes(a)}%"))
    if verbo:
        q = q.where(SentenciaXapi.verbo == verbo)
    if objeto_tipo:
        q = q.where(SentenciaXapi.objeto_tipo == objeto_tipo)
    if objeto and objeto.strip():
        o = sin_tildes(objeto)
        q = q.where(or_(func.lower(SentenciaXapi.objeto_tipo) == o,
                        columna_sin_tildes(func.coalesce(SentenciaXapi.objeto_nombre, "")).like(f"%{o}%")))
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
    verbos += [{"clave": k, "nombre": nombre_verbo(k)} for k in sorted(usados - set(VERBOS))]
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


# Frases de los cambios que algunos módulos auditan sin «resumen» propio. Sin ellas, la
# auditoría mostraba la clave en bruto («publicar instruccion instruccion #12»).
FRASES_ACCION = {
    "publicar_instruccion": "Publicó la instrucción",
    "borrar_borrador": "Borró el borrador de la instrucción",
    "regenerar_microlecciones": "Regeneró las micro-lecciones de la instrucción",
    "validar_aportacion": "Validó la aportación",
    "rechazar_aportacion": "Rechazó la aportación",
    "editar_aportacion": "Editó la aportación",
    "descartar_laguna": "Descartó la laguna",
    "reabrir_laguna": "Reabrió la laguna",
    "borrar_captura": "Borró la captura",
    "ajustar_nivel_iluo": "Ajustó el nivel ILUO",
    "documento.editar": "Editó el documento",
    "documento.reindexar": "Reindexó el documento",
    "documento.borrar": "Borró el documento",
    "documentos.probar_busqueda_como": "Probó la búsqueda como otra persona",
    "exportar_xapi": "Exportó el registro xAPI",
    "sembrar_demo": "Cargó los datos de demostración",
}
_SUJETO = ("titulo", "nombre", "pregunta", "codigo", "consulta")


def texto_auditoria(a: Auditoria) -> str:
    """Frase legible de un cambio: su resumen o, si no lo trae, una construida con su acción y
    lo que identifique al objeto (título, nombre, pregunta…)."""
    detalle = a.detalle if isinstance(a.detalle, dict) else {}
    if detalle.get("resumen"):
        return str(detalle["resumen"])
    frase = FRASES_ACCION.get(a.accion) or a.accion.replace(".", " ").replace("_", " ").capitalize()
    if a.accion == "ajustar_nivel_iluo" and detalle.get("usuario"):
        return (f"{frase} de {detalle['usuario']} en «{detalle.get('tarea') or 'una tarea'}»: "
                f"{detalle.get('de') or '-'} → {detalle.get('a') or '-'}")
    sujeto = next((detalle[k] for k in _SUJETO if detalle.get(k)), None)
    if sujeto:
        texto = f"{frase} «{str(sujeto)[:140]}»"
    elif a.entidad_id:
        texto = f"{frase} #{a.entidad_id}"
    else:
        texto = frase
    if a.entidad == "instruccion" and detalle.get("version"):
        texto += f" (versión {detalle['version']})"
    if a.accion == "rechazar_aportacion" and detalle.get("motivo"):
        texto += f". Motivo: {str(detalle['motivo'])[:200]}"
    return texto


def auditoria_dict(a: Auditoria) -> dict[str, Any]:
    texto = texto_auditoria(a)
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
            q.where(columna_sin_tildes(Auditoria.usuario_nombre).like(f"%{sin_tildes(u)}%"))
    if accion:
        q = q.where(Auditoria.accion == accion)
    if entidad:
        q = q.where(Auditoria.entidad == entidad)
    if texto and texto.strip():
        q = q.where(columna_sin_tildes(cast(Auditoria.detalle, Text)).like(f"%{sin_tildes(texto)}%"))
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
