"""Modelos permitidos: la lista que el gateway consulta antes de cada petición a un modelo.

* Solo la administración la ve y la cambia; cada cambio queda en la auditoría.
* Se cruza con lo que hay de verdad en el servidor (Ollama) para marcar si cada modelo
  local está descargado.
* Los modelos en la nube no se pueden permitir mientras la política del servidor
  (CIDIA_PERMITIR_MODELOS_NUBE) lo impida.
* Hay como mucho un predeterminado por tipo, y siempre queda al menos un modelo de chat y
  uno de búsqueda (embeddings) permitidos para que CidIA siga funcionando.
* El modelo de búsqueda con el que están indexados los documentos lo fija el servidor
  (CIDIA_LLM_MODELO_EMBEDDINGS): cambiarlo obliga a reindexar todo, así que desde aquí no se
  puede desactivar ni sustituir como predeterminado.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cidia.config import ajustes
from cidia.db import obtener_bd
from cidia.ia import llm
from cidia.modelos import ModeloIA
from cidia.rutas.admin import cambios, obtener, texto_limpio
from cidia.seguridad import Actor, requiere_admin
from cidia.xapi import auditar

router = APIRouter(prefix="/api/admin", tags=["administración"])

TIPOS = {"chat": "Chat", "embeddings": "Búsqueda por significado", "vision": "Visión", "asr": "Voz"}
# Tipos de los que siempre debe quedar al menos uno permitido.
IMPRESCINDIBLES = {"chat": "de chat", "embeddings": "de búsqueda (embeddings)"}
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/\-]{0,149}$")

MENSAJE_BUSQUEDA = ("Los documentos están indexados con «{ref}», el modelo de búsqueda que fija la configuración "
                    "del servidor (CIDIA_LLM_MODELO_EMBEDDINGS). Cambiarlo obliga a volver a indexar todos los "
                    "documentos, así que se hace en el servidor y no desde aquí.")

MENSAJE_NUBE = ("La política de la empresa no permite modelos en la nube: los datos saldrían del servidor. "
                "Solo se pueden habilitar si el servidor se configura con CIDIA_PERMITIR_MODELOS_NUBE=true.")


# --------------------------------------------------------------------------- utilidades


def _disponibles() -> dict[str, Any]:
    """Modelos descargados en el servidor de modelos (o el error si no responde)."""
    s = llm.salud()
    return {"ok": bool(s.get("ok")), "modelos": list(s.get("modelos") or []), "error": s.get("error")}


def _descargado(m: ModeloIA, servidor: dict[str, Any]) -> bool | None:
    """True/False para modelos locales si el servidor respondió; None si no se sabe o es de nube."""
    if m.ubicacion != "local" or not servidor["ok"]:
        return None
    ids = set(servidor["modelos"])
    return m.ref in ids or f"{m.ref}:latest" in ids or m.ref.removesuffix(":latest") in ids


def _sin_latest(ref: str) -> str:
    return ref.removesuffix(":latest")


def _indexa_documentos(m: ModeloIA) -> bool:
    """¿Es el modelo de búsqueda con el que el servidor indexa y consulta los documentos?"""
    return m.tipo == "embeddings" and m.ubicacion == "local" and         _sin_latest(m.ref) == _sin_latest(ajustes().llm_modelo_embeddings)


def _bloqueado(m: ModeloIA) -> bool:
    return m.ubicacion == "nube" and not ajustes().permitir_modelos_nube


def _uso(m: ModeloIA) -> str:
    """Texto de la columna «Quién lo usa»."""
    if not m.permitido or _bloqueado(m):
        return "Nadie"
    if m.tipo == "embeddings":
        return "Búsqueda de documentos" if _indexa_documentos(m) else "Reserva (la búsqueda usa el modelo del servidor)"
    if m.tipo == "vision":
        return "Fotos del modo planta" if m.predeterminado else "Reserva para fotos"
    if m.tipo == "asr":
        return "Notas de voz"
    if m.predeterminado:
        return "Todos (predeterminado)"
    return "Quien lo elija en el chat" + (" · también fotos" if m.soporta_vision else "")


def modelo_dict(m: ModeloIA, servidor: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": m.id,
        "nombre": m.nombre,
        "ref": m.ref,
        "tipo": m.tipo,
        "tipo_texto": TIPOS.get(m.tipo, m.tipo),
        "ubicacion": m.ubicacion,
        "donde": "En el servidor de la empresa" if m.ubicacion == "local" else "En la nube, fuera de la empresa",
        "proveedor": m.proveedor,
        "permitido": m.permitido and not _bloqueado(m),
        "predeterminado": m.predeterminado,
        "soporta_vision": m.soporta_vision,
        "descripcion": m.descripcion,
        "descargado": _descargado(m, servidor),
        "bloqueado": _bloqueado(m),
        "indexa_documentos": _indexa_documentos(m),
        "uso": _uso(m),
    }


def _respuesta(bd: Session, servidor: dict[str, Any] | None = None) -> dict[str, Any]:
    servidor = servidor or _disponibles()
    filas = bd.scalars(select(ModeloIA).order_by(ModeloIA.ubicacion, ModeloIA.tipo, ModeloIA.nombre)).all()
    registrados = {m.ref for m in filas} | {f"{m.ref}:latest" for m in filas}
    return {
        "modelos": [modelo_dict(m, servidor) for m in filas],
        "servidor": {
            "ok": servidor["ok"],
            "error": servidor["error"],
            "descargados": servidor["modelos"],
            # Descargados en el servidor pero aún sin registrar: se pueden añadir con un clic.
            "sin_registrar": [r for r in servidor["modelos"] if r not in registrados],
        },
        "permitir_nube": ajustes().permitir_modelos_nube,
    }


def _quedan_permitidos(bd: Session, tipo: str, salvo: int) -> int:
    """Otros modelos del mismo tipo que seguirían en uso (los de nube solo si la política lo permite)."""
    q = select(func.count(ModeloIA.id)).where(ModeloIA.tipo == tipo, ModeloIA.permitido.is_(True), ModeloIA.id != salvo)
    if not ajustes().permitir_modelos_nube:
        q = q.where(ModeloIA.ubicacion == "local")
    return bd.scalar(q) or 0


def _promover_otro(bd: Session, tipo: str, salvo: int) -> ModeloIA | None:
    """Si el predeterminado deja de estarlo, pasa a serlo otro permitido del mismo tipo."""
    otro = bd.scalar(select(ModeloIA).where(ModeloIA.tipo == tipo, ModeloIA.permitido.is_(True),
                                            ModeloIA.id != salvo).order_by(ModeloIA.ubicacion, ModeloIA.id))
    if otro is not None and not _bloqueado(otro):
        otro.predeterminado = True
        return otro
    return None


# --------------------------------------------------------------------------- rutas


@router.get("/modelos")
def listar(_: Actor = Depends(requiere_admin), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return _respuesta(bd)


class CambioModelo(BaseModel):
    permitido: bool | None = None
    predeterminado: bool | None = None
    nombre: str | None = None
    descripcion: str | None = None
    soporta_vision: bool | None = None


@router.put("/modelos/{modelo_id}")
def cambiar(modelo_id: int, datos: CambioModelo, actor: Actor = Depends(requiere_admin),
            bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    m = obtener(bd, ModeloIA, modelo_id, "ese modelo")
    entrada = datos.model_dump(exclude_unset=True)
    servidor = _disponibles()
    limpio: dict[str, Any] = {}
    if "nombre" in entrada:
        limpio["nombre"] = texto_limpio(entrada["nombre"], "el nombre del modelo", 150, obligatorio=True)
    if "descripcion" in entrada:
        limpio["descripcion"] = texto_limpio(entrada["descripcion"], "la descripción", 1000)
    if entrada.get("soporta_vision") is not None:
        limpio["soporta_vision"] = bool(entrada["soporta_vision"])

    permitido = entrada.get("permitido")
    predeterminado = entrada.get("predeterminado")
    if predeterminado:
        permitido = True  # el predeterminado siempre está permitido
    if permitido and _bloqueado(m):
        raise HTTPException(400, MENSAJE_NUBE)
    if predeterminado and _descargado(m, servidor) is False:
        raise HTTPException(400, f"«{m.ref}» no está descargado en el servidor. Descárgalo antes de hacerlo "
                                 "predeterminado.")
    if permitido is False and m.permitido and m.tipo in IMPRESCINDIBLES and not _quedan_permitidos(bd, m.tipo, m.id):
        raise HTTPException(400, f"Debe quedar al menos un modelo {IMPRESCINDIBLES[m.tipo]} permitido. "
                                 "Permite otro antes de desactivar este.")
    if m.tipo == "embeddings":
        busqueda = MENSAJE_BUSQUEDA.format(ref=ajustes().llm_modelo_embeddings)
        if predeterminado and not _indexa_documentos(m):
            raise HTTPException(400, f"«{m.nombre}» no puede ser el modelo de búsqueda predeterminado. {busqueda}")
        if _indexa_documentos(m) and ((permitido is False and m.permitido) or (predeterminado is False and m.predeterminado)):
            raise HTTPException(400, f"«{m.nombre}» no se puede desactivar. {busqueda}")
    if permitido is not None:
        limpio["permitido"] = permitido
        if not permitido:
            limpio["predeterminado"] = False
    if predeterminado is not None:
        limpio["predeterminado"] = predeterminado

    era_predeterminado = m.predeterminado
    hechos = cambios(m, limpio)
    promovido = None
    if m.predeterminado and "predeterminado" in hechos:
        # Un solo predeterminado por tipo.
        for otro in bd.scalars(select(ModeloIA).where(ModeloIA.tipo == m.tipo, ModeloIA.id != m.id,
                                                      ModeloIA.predeterminado.is_(True))).all():
            otro.predeterminado = False
    elif era_predeterminado and not m.predeterminado:
        promovido = _promover_otro(bd, m.tipo, m.id)
    if hechos:
        if set(hechos) <= {"permitido", "predeterminado"}:
            if m.predeterminado and "predeterminado" in hechos:
                resumen = f"Hizo predeterminado el modelo «{m.nombre}»"
            else:
                resumen = f"{'Permitió' if m.permitido else 'Desactivó'} el modelo «{m.nombre}»"
        else:
            resumen = f"Editó el modelo «{m.nombre}»"
        if promovido is not None:
            resumen += f"; ahora el predeterminado es «{promovido.nombre}»"
        auditar(bd, actor, "cambiar_modelo", "modelo", m.id, {"resumen": resumen, "cambios": hechos, "ref": m.ref})
    bd.commit()
    return _respuesta(bd, servidor)


class NuevoModelo(BaseModel):
    ref: str
    nombre: str | None = None
    tipo: str = "chat"
    soporta_vision: bool = False
    descripcion: str | None = None
    permitido: bool = False


@router.post("/modelos")
def anadir(datos: NuevoModelo, actor: Actor = Depends(requiere_admin), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Añade un modelo LOCAL (Ollama) por su referencia, p. ej. «qwen3.5:9b»."""
    ref = datos.ref.strip()
    if not _REF.match(ref):
        raise HTTPException(400, "La referencia del modelo no es válida. Usa el nombre de Ollama, p. ej. qwen3.5:9b.")
    if datos.tipo not in ("chat", "embeddings", "vision"):
        raise HTTPException(400, "El tipo debe ser chat, embeddings o vision.")
    if bd.scalar(select(ModeloIA).where(ModeloIA.ref == ref, ModeloIA.tipo == datos.tipo)) is not None:
        raise HTTPException(409, f"«{ref}» ya está en la lista como modelo de tipo {TIPOS[datos.tipo].lower()}.")
    m = ModeloIA(
        nombre=texto_limpio(datos.nombre, "el nombre", 150) or ref,
        ref=ref,
        tipo=datos.tipo,
        ubicacion="local",
        proveedor="ollama",
        permitido=datos.permitido,
        predeterminado=False,
        soporta_vision=datos.soporta_vision or datos.tipo == "vision",
        descripcion=texto_limpio(datos.descripcion, "la descripción", 1000),
    )
    bd.add(m)
    bd.flush()
    servidor = _disponibles()
    auditar(bd, actor, "anadir_modelo", "modelo", m.id,
            {"resumen": f"Añadió el modelo local «{m.nombre}» ({TIPOS[m.tipo].lower()})", "ref": ref,
             "descargado": _descargado(m, servidor)})
    bd.commit()
    respuesta = _respuesta(bd, servidor)
    respuesta["creado"] = modelo_dict(m, servidor)
    return respuesta


@router.delete("/modelos/{modelo_id}")
def quitar(modelo_id: int, actor: Actor = Depends(requiere_admin), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Quita de la lista un modelo local que no esté permitido (no lo borra del servidor)."""
    m = obtener(bd, ModeloIA, modelo_id, "ese modelo")
    if m.ubicacion != "local":
        raise HTTPException(400, "Los proveedores en la nube no se quitan de la lista: quedan bloqueados.")
    if m.permitido:
        raise HTTPException(400, "Desactiva el modelo antes de quitarlo de la lista.")
    nombre = m.nombre
    bd.delete(m)
    auditar(bd, actor, "quitar_modelo", "modelo", modelo_id, {"resumen": f"Quitó de la lista el modelo «{nombre}»"})
    bd.commit()
    return _respuesta(bd)
