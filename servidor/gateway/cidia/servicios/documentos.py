"""Alta, indexado y baja de documentos de conocimiento.

Es la puerta única hacia el motor de conocimiento: instrucciones publicadas, aportaciones
validadas, fichas y ficheros subidos entran siempre por aquí.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from cidia import trabajos
from cidia.config import ajustes
from cidia.conocimiento import motor
from cidia.conocimiento.extraccion import tipo_por_extension
from cidia.ficheros import guardar_subida
from cidia.ia import asr, llm
from cidia.modelos import Documento, Fragmento
from cidia.seguridad import Actor
from cidia.xapi import registrar

log = logging.getLogger("cidia.documentos")


def crear_desde_subida(
    bd: Session,
    actor: Actor,
    subida: UploadFile,
    titulo: str | None,
    departamento_id: int | None,
    nivel_minimo: int = 1,
    es_formacion: bool = False,
    es_publico: bool = False,
    descripcion: str | None = None,
) -> Documento:
    """Guarda el fichero, crea el documento en estado «procesando» y encola su indexado."""
    ruta, nombre, tam = guardar_subida(subida, "documentos")
    tipo = tipo_por_extension(nombre)
    if tipo == "otro":
        tipo = "texto"
    doc = Documento(
        titulo=((titulo or "").strip() or Path(nombre).stem).strip()[:300],
        descripcion=descripcion,
        tipo=tipo,
        departamento_id=departamento_id,
        nivel_minimo=nivel_minimo,
        es_formacion=es_formacion,
        es_publico=es_publico,
        estado="procesando",
        ruta_fichero=ruta,
        nombre_fichero=nombre,
        mime=subida.content_type,
        tamano=tam,
        autor_id=actor.id,
        subido_por_id=actor.id,
        origen="subida",
    )
    bd.add(doc)
    bd.flush()
    registrar(bd, actor, "subio", "documento", doc.id, doc.titulo,
              contexto={"departamento_id": departamento_id, "nivel_minimo": nivel_minimo})
    bd.commit()
    trabajos.encolar("indexar_documento", indexar_trabajo, doc.id, entidad="documento", entidad_id=doc.id,
                     usuario_id=actor.id)
    return doc


def crear_desde_texto(
    bd: Session,
    titulo: str,
    texto: str,
    tipo: str = "texto",
    departamento_id: int | None = None,
    nivel_minimo: int = 1,
    es_formacion: bool = False,
    es_publico: bool = False,
    autor_id: int | None = None,
    validador_id: int | None = None,
    subido_por_id: int | None = None,
    origen: str = "subida",
    origen_id: int | None = None,
    version: int = 1,
    partes: list[tuple[str, dict[str, Any]]] | None = None,
    en_segundo_plano: bool = True,
    descripcion: str | None = None,
) -> Documento:
    """Crea un documento a partir de texto (instrucción, FAQ, ficha...) y lo indexa."""
    doc = Documento(
        titulo=titulo[:300],
        descripcion=descripcion,
        tipo=tipo,
        departamento_id=departamento_id,
        nivel_minimo=nivel_minimo,
        es_formacion=es_formacion,
        es_publico=es_publico,
        estado="procesando",
        contenido_texto=texto,
        autor_id=autor_id,
        validador_id=validador_id,
        subido_por_id=subido_por_id,
        origen=origen,
        origen_id=origen_id,
        version=version,
    )
    bd.add(doc)
    bd.flush()
    if en_segundo_plano:
        bd.commit()
        trabajos.encolar("indexar_documento", indexar_trabajo, doc.id, partes, entidad="documento", entidad_id=doc.id)
    else:
        indexar(bd, doc, partes=partes)
    return doc


def indexar(bd: Session, doc: Documento, partes: list[tuple[str, dict[str, Any]]] | None = None) -> None:
    """Indexa en el motor. Transcribe audio y describe imágenes antes si hace falta."""
    try:
        texto: str | None = None
        if partes is None and doc.ruta_fichero and doc.tipo in ("audio", "imagen"):
            ruta = ajustes().dir_datos / doc.ruta_fichero
            if doc.tipo == "audio":
                texto = asr.transcribir(ruta)["texto"]
            else:
                vision = llm.modelo_vision(bd)
                if not vision:
                    raise RuntimeError("No hay un modelo con visión permitido para describir imágenes.")
                texto = llm.chat(
                    [{"role": "user", "content": [
                        {"type": "text", "text": "Describe con detalle esta imagen de un entorno industrial, en castellano. "
                                                 "Transcribe cualquier texto visible."},
                        llm.imagen_a_parte(ruta, doc.mime or "image/jpeg"),
                    ]}],
                    modelo=vision,
                )
            doc.contenido_texto = texto
        elif partes is None and not doc.ruta_fichero:
            texto = doc.contenido_texto or ""
        n = motor().indexar(bd, doc, texto=texto, partes=partes)
        doc.fragmentos_n = n
        doc.estado = "listo" if n > 0 else "error"
        doc.mensaje_estado = None if n > 0 else "No se ha encontrado texto en el documento."
    except Exception as e:  # noqa: BLE001
        log.exception("Error indexando el documento %s", doc.id)
        doc.estado = "error"
        doc.mensaje_estado = str(e)[:1000]
    bd.flush()


def indexar_trabajo(bd: Session, progreso: Any, documento_id: int,
                    partes: list[tuple[str, dict[str, Any]]] | None = None) -> dict[str, Any]:
    doc = bd.get(Documento, documento_id)
    if doc is None:
        return {"error": "documento no encontrado"}
    progreso(20, "Indexando")
    indexar(bd, doc, partes=partes)
    return {"estado": doc.estado, "fragmentos": doc.fragmentos_n}


def partes_guardadas(bd: Session, doc: Documento) -> list[tuple[str, dict[str, Any]]] | None:
    """Partes con metadatos propios (p. ej. los pasos de una instrucción) a partir de los
    fragmentos actuales, para no perderlos al reindexar un documento sin fichero."""
    frags = bd.scalars(select(Fragmento).where(Fragmento.documento_id == doc.id).order_by(Fragmento.orden)).all()
    partes = [(f.texto, {k: v for k, v in (f.metadatos or {}).items() if not k.startswith("wk_")}) for f in frags]
    return partes if any(meta for _, meta in partes) else None


def reindexar(bd: Session, doc: Documento) -> None:
    """Vuelve a indexar un documento conservando los metadatos por parte si no tiene fichero."""
    partes = None if doc.ruta_fichero else partes_guardadas(bd, doc)
    doc.estado = "procesando"
    doc.mensaje_estado = None
    bd.commit()
    trabajos.encolar("indexar_documento", indexar_trabajo, doc.id, partes, entidad="documento", entidad_id=doc.id)


def marcar_interrumpidos(bd: Session) -> None:
    """Al arrancar: los documentos que se quedaron indexando pasan a error para poder reintentarlos."""
    bd.execute(update(Documento).where(Documento.estado == "procesando")
               .values(estado="error", mensaje_estado="Indexado interrumpido al reiniciar el servidor. Reindexa el documento."))


def borrar(bd: Session, doc: Documento) -> None:
    try:
        motor().borrar(bd, doc)
    except Exception:  # noqa: BLE001
        log.exception("No se pudo borrar del motor el documento %s", doc.id)
    if doc.ruta_fichero:
        try:
            (ajustes().dir_datos / doc.ruta_fichero).unlink(missing_ok=True)
        except OSError:
            pass
    bd.delete(doc)


def a_dict(bd: Session, d: Documento) -> dict[str, Any]:
    from cidia.seguridad import url_fichero

    return {
        "id": d.id,
        "titulo": d.titulo,
        "descripcion": d.descripcion,
        "tipo": d.tipo,
        "departamento_id": d.departamento_id,
        "departamento": d.departamento.nombre if d.departamento else None,
        "nivel_minimo": d.nivel_minimo,
        "es_formacion": d.es_formacion,
        "es_publico": d.es_publico,
        "estado": d.estado,
        "mensaje_estado": d.mensaje_estado,
        "nombre_fichero": d.nombre_fichero,
        "tamano": d.tamano,
        "url": url_fichero(d.ruta_fichero),
        "autor": d.autor.nombre if d.autor else None,
        "validador": d.validador.nombre if d.validador else None,
        "origen": d.origen,
        "origen_id": d.origen_id,
        "version": d.version,
        "fragmentos": d.fragmentos_n,
        "creado": d.creado.isoformat() if d.creado else None,
    }
