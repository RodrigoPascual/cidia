"""Registro de actividad en formato xAPI (IEEE 9274.1.1-2023) y auditoría de cambios."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from cidia.config import ajustes
from cidia.modelos import Auditoria, SentenciaXapi, ahora, nuevo_uuid
from cidia.seguridad import Actor

ADL = "http://adlnet.gov/expapi/verbs/"
CIDIA = "https://cidia.local/xapi/verbos/"

# verbo -> (IRI, nombre visible)
VERBOS: dict[str, tuple[str, str]] = {
    "pregunto": (ADL + "asked", "preguntó"),
    "respondio": (ADL + "answered", "respondió"),
    "inicio": (ADL + "launched", "inició"),
    "completo": (ADL + "completed", "completó"),
    "abandono": (ADL + "terminated", "abandonó"),
    "vio": (ADL + "experienced", "vio"),
    "intento": (ADL + "attempted", "intentó"),
    "aprobo": (ADL + "passed", "aprobó"),
    "suspendio": (ADL + "failed", "no superó"),
    "confirmo": (CIDIA + "confirmo-paso", "confirmó"),
    "aporto": (ADL + "shared", "aportó"),
    "valido": (CIDIA + "valido", "validó"),
    "rechazo": (CIDIA + "rechazo", "rechazó"),
    "publico": (CIDIA + "publico", "publicó"),
    "capturo": (CIDIA + "capturo", "capturó"),
    "observo": (CIDIA + "observo", "observó"),
    "certifico": (CIDIA + "nivel-iluo", "alcanzó el nivel"),
    "subio": (CIDIA + "subio", "subió"),
    "fotografio": (CIDIA + "fotografio", "fotografió"),
    "valoro": (CIDIA + "valoro", "valoró"),
    "configuro": (CIDIA + "configuro", "configuró"),
    "borro": (CIDIA + "borro", "borró"),
    "uso_modelo": (CIDIA + "uso-modelo", "usó el modelo"),
    "probo_busqueda": (CIDIA + "probo-busqueda", "probó la búsqueda"),
    "retiro": (CIDIA + "retiro", "retiró"),
    "asigno": (CIDIA + "asigno", "asignó"),
}


def registrar(
    bd: Session,
    actor: Actor | None,
    verbo: str,
    objeto_tipo: str,
    objeto_id: Any = None,
    objeto_nombre: str | None = None,
    resultado: dict[str, Any] | None = None,
    contexto: dict[str, Any] | None = None,
    actor_id: int | None = None,
    actor_nombre: str | None = None,
) -> SentenciaXapi:
    """Guarda una sentencia xAPI. No hace commit (lo hace quien llama)."""
    iri, visible = VERBOS.get(verbo, (CIDIA + verbo, verbo))
    aid = actor.id if actor else actor_id
    anombre = actor.nombre if actor else (actor_nombre or "Sistema")
    sid = nuevo_uuid()
    momento = ahora()
    base = ajustes().url_publica.rstrip("/")
    sentencia: dict[str, Any] = {
        "id": sid,
        "actor": {
            "objectType": "Agent",
            "name": anombre,
            "account": {"homePage": base, "name": str(aid) if aid else "invitado"},
        },
        "verb": {"id": iri, "display": {"es-ES": visible}},
        "object": {
            "objectType": "Activity",
            "id": f"{base}/xapi/{objeto_tipo}/{objeto_id}",
            "definition": {"name": {"es-ES": objeto_nombre or objeto_tipo}, "type": f"{base}/xapi/tipos/{objeto_tipo}"},
        },
        "timestamp": momento.isoformat(),
    }
    if resultado:
        sentencia["result"] = {"extensions": {f"{base}/xapi/ext/resultado": resultado}}
        for clave in ("success", "completion", "response"):
            if clave in resultado:
                sentencia["result"][clave] = resultado[clave]
        if "score" in resultado:
            sentencia["result"]["score"] = {"scaled": resultado["score"]}
    if contexto:
        sentencia["context"] = {"extensions": {f"{base}/xapi/ext/contexto": contexto}}
    fila = SentenciaXapi(
        id=sid,
        actor_id=aid,
        actor_nombre=anombre,
        verbo=verbo,
        verbo_iri=iri,
        objeto_tipo=objeto_tipo,
        objeto_id=str(objeto_id) if objeto_id is not None else None,
        objeto_nombre=objeto_nombre,
        resultado=resultado,
        contexto=contexto,
        sentencia=sentencia,
        momento=momento,
    )
    bd.add(fila)
    return fila


def auditar(
    bd: Session,
    actor: Actor | None,
    accion: str,
    entidad: str | None = None,
    entidad_id: Any = None,
    detalle: dict[str, Any] | None = None,
) -> None:
    """Deja constancia de un cambio de administración. No hace commit."""
    bd.add(
        Auditoria(
            usuario_id=actor.id if actor else None,
            usuario_nombre=actor.nombre if actor else "Sistema",
            accion=accion,
            entidad=entidad,
            entidad_id=str(entidad_id) if entidad_id is not None else None,
            detalle=detalle,
        )
    )
