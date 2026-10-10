"""Información pública del servidor y estado de los servicios."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from cidia import __version__
from cidia.config import ajustes
from cidia.conocimiento import motor
from cidia.db import obtener_bd
from cidia.ia import asr, llm
from cidia.modelos import Documento, Empresa, Fragmento, Trabajo, ahora
from cidia.seguridad import Actor, actor_actual, requiere_admin
from cidia.servicios import espacio

router = APIRouter(tags=["sistema"])


@router.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok"}


@router.get("/api/sistema/info")
def info(bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Datos públicos que la app muestra antes de iniciar sesión."""
    empresa = bd.scalar(select(Empresa))
    return {
        "producto": "CidIA",
        "version": __version__,
        "servidor": ajustes().nombre_servidor,
        "empresa": empresa.nombre if empresa else None,
        "invitado": True,
    }


def _medido(funcion: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Ejecuta una comprobación y anota cuánto ha tardado (ms). Nunca lanza."""
    t = time.monotonic()
    try:
        r = dict(funcion())
    except Exception as e:  # noqa: BLE001
        r = {"ok": False, "error": str(e)}
    r["ms"] = int((time.monotonic() - t) * 1000)
    return r


def _descargado(ref: str, descargados: set[str]) -> bool:
    return ref in descargados or f"{ref}:latest" in descargados or ref.removesuffix(":latest") in descargados


def _modelos_en_uso(bd: Session, salud: dict[str, Any]) -> dict[str, Any]:
    """Cruza los modelos que CidIA usa de verdad (los predeterminados permitidos) con los
    descargados en el servidor. Sin el de chat o el de búsqueda, CidIA no puede responder."""
    if not salud.get("ok"):
        return salud
    descargados = set(salud.get("modelos") or [])
    en_uso: dict[str, str | None] = {}
    for tipo in ("chat", "embeddings", "vision"):
        try:
            en_uso[tipo] = llm.modelo_permitido(bd, tipo)
        except Exception:  # noqa: BLE001  (ninguno permitido de ese tipo)
            en_uso[tipo] = None
    faltan = {tipo: ref for tipo, ref in en_uso.items() if ref and not _descargado(ref, descargados)}
    sin_permitir = [tipo for tipo, ref in en_uso.items() if ref is None and tipo in ("chat", "embeddings")]
    criticos = [t for t in faltan if t in ("chat", "embeddings")] + sin_permitir
    return {**salud, "ok": not criticos, "en_uso": en_uso, "faltan": faltan,
            "error": ("Faltan modelos imprescindibles: " + ", ".join(
                [f"{t} ({faltan[t]})" for t in faltan if t in ("chat", "embeddings")] +
                [f"{t} (ninguno permitido)" for t in sin_permitir])) if criticos else None}


def _conocimiento(bd: Session) -> dict[str, Any]:
    """Motor propio: comprueba la extensión pgvector y cuenta lo indexado. Externo: su salud."""
    m = motor()
    if m.externo:
        return m.salud()
    version = bd.scalar(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
    fragmentos = bd.scalar(select(func.count(Fragmento.id))) or 0
    return {"ok": version is not None, "motor": m.nombre, "pgvector": version, "fragmentos": fragmentos,
            "error": None if version else "La extensión pgvector no está instalada en la base de datos."}


def _espacio() -> dict[str, Any]:
    """Ejecutor del espacio de trabajo (contenedores sin red). Es opcional: sin configurar no es un fallo."""
    if not espacio.configurado():
        return {"ok": True, "configurado": False}
    e = espacio.estado_ejecutor()
    return {"ok": bool(e.get("disponible")), "configurado": True,
            "error": None if e.get("disponible") else "El ejecutor no responde."}


@router.get("/api/sistema/estado")
def estado(_: Actor = Depends(requiere_admin), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Estado real de cada servicio, con lo que tarda en responder. Las comprobaciones por red
    (modelos, voz, espacio de trabajo) van en paralelo para que la página no espere a la más lenta."""
    with ThreadPoolExecutor(max_workers=3) as hilos:
        f_modelos = hilos.submit(_medido, llm.salud)
        f_voz = hilos.submit(_medido, asr.salud)
        f_espacio = hilos.submit(_medido, _espacio)

        def base_datos() -> dict[str, Any]:
            bd.execute(text("SELECT 1"))
            return {"ok": True}

        bd_ok = _medido(base_datos)
        conocimiento = _medido(lambda: _conocimiento(bd)) if bd_ok["ok"] else {"ok": False, "error": "Sin base de datos."}
        modelos = f_modelos.result()
        if bd_ok["ok"]:
            ms = modelos.get("ms")
            modelos = _modelos_en_uso(bd, modelos)
            modelos["ms"] = ms
        voz = f_voz.result()
        espacio_trabajo = f_espacio.result()
    if not bd_ok["ok"]:
        bd.rollback()
        return {"version": __version__, "motor_conocimiento": ajustes().motor_conocimiento,
                "servicios": {"base_datos": bd_ok, "modelos": modelos, "voz": voz, "conocimiento": conocimiento,
                              "espacio": espacio_trabajo},
                "documentos": {}, "trabajos": [], "cola": {}}
    docs = dict(bd.execute(select(Documento.estado, func.count()).group_by(Documento.estado)).all())
    ultimos = bd.scalars(select(Trabajo).order_by(Trabajo.id.desc()).limit(15)).all()
    hace_un_dia = ahora() - timedelta(days=1)
    cola = dict(bd.execute(select(Trabajo.estado, func.count()).where(
        (Trabajo.estado.in_(("pendiente", "en_curso"))) | ((Trabajo.estado == "error") & (Trabajo.creado >= hace_un_dia)))
        .group_by(Trabajo.estado)).all())
    return {
        "version": __version__,
        "motor_conocimiento": ajustes().motor_conocimiento,
        "servicios": {
            "base_datos": bd_ok,
            "modelos": modelos,
            "voz": voz,
            "conocimiento": conocimiento,
            "espacio": espacio_trabajo,
        },
        "documentos": docs,
        "cola": {"pendientes": cola.get("pendiente", 0), "en_curso": cola.get("en_curso", 0),
                 "errores_24h": cola.get("error", 0)},
        "trabajos": [
            {"id": t.id, "tipo": t.tipo, "estado": t.estado, "progreso": t.progreso, "mensaje": t.mensaje,
             "creado": t.creado.isoformat(), "actualizado": t.actualizado.isoformat() if t.actualizado else None}
            for t in ultimos
        ],
    }


@router.get("/api/trabajos/{trabajo_id}")
def trabajo(trabajo_id: int, actor: Actor = Depends(actor_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Estado de un trabajo en segundo plano. Solo lo ve quien lo lanzó (o la administración);
    los detalles técnicos de un error (direcciones internas, trazas) solo se muestran a la
    administración: al resto se le da un mensaje genérico."""
    t = bd.get(Trabajo, trabajo_id)
    if t is None or actor.es_invitado or (not actor.es_admin and t.usuario_id != actor.id):
        return {"id": trabajo_id, "estado": "desconocido"}
    mensaje = t.mensaje
    if t.estado == "error" and not actor.es_admin:
        mensaje = "No se ha podido completar. Inténtalo de nuevo o avisa a la administración."
    return {"id": t.id, "tipo": t.tipo, "estado": t.estado, "progreso": t.progreso, "mensaje": mensaje,
            "resultado": t.resultado if (actor.es_admin or t.usuario_id == actor.id) else None}
