"""Documentos de conocimiento (jefes y administración) y consola de depuración de la búsqueda.

Permisos (siempre en el servidor):
* La administración ve y gestiona todos los documentos.
* Un jefe ve los documentos de su departamento y los públicos, y solo gestiona (sube, etiqueta,
  reindexa, borra) los de su departamento. Un documento que no puede ver responde 404, como si
  no existiera.

El alta, el indexado y el borrado pasan siempre por `servicios.documentos`.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Iterable
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from cidia import trabajos
from cidia.config import ajustes
from cidia.conocimiento import motor
from cidia.conocimiento.extraccion import tipo_por_extension
from cidia.conocimiento.weknora import ErrorWeKnora
from cidia.db import obtener_bd
from cidia.ia.llm import ErrorModelo
from cidia.modelos import Departamento, Documento, Fragmento, Nivel, Trabajo, Usuario
from cidia.permisos import Alcance, alcance_de
from cidia.seguridad import Actor, requiere_jefe, url_fichero
from cidia.servicios import documentos
from cidia.xapi import auditar, registrar

log = logging.getLogger("cidia.rutas.documentos")

router = APIRouter(prefix="/api/documentos", tags=["documentos"])

# Tipos que se pueden subir desde la consola (el vídeo entra por Captura).
TIPOS_SUBIDA = ("pdf", "office", "texto", "audio", "imagen")
NOMBRE_TIPO = {
    "pdf": "PDF", "office": "Office", "texto": "Texto", "audio": "Audio", "imagen": "Imagen",
    "instruccion": "Instrucción", "faq": "Pregunta frecuente", "ficha": "Ficha",
}
NOMBRE_ESTADO = {"procesando": "Procesando", "listo": "Listo", "error": "Con error", "borrador": "Borrador",
                 "obsoleto": "Sustituido"}
CAMPOS_PERMISO = ("departamento_id", "nivel_minimo", "es_formacion", "es_publico")
TRABAJO_ACTIVO = ("pendiente", "en_curso")


# --------------------------------------------------------------------------- permisos


def _puede_ver(actor: Actor, d: Documento) -> bool:
    if actor.es_admin or d.es_publico:
        return True
    return actor.departamento_id is not None and d.departamento_id == actor.departamento_id


def _puede_gestionar(actor: Actor, d: Documento) -> bool:
    if actor.es_admin:
        return True
    return actor.departamento_id is not None and d.departamento_id == actor.departamento_id


def _filtro_visibles(actor: Actor) -> ColumnElement[bool]:
    if actor.es_admin:
        return true()
    conds: list[ColumnElement[bool]] = [Documento.es_publico.is_(True)]
    if actor.departamento_id is not None:
        conds.append(Documento.departamento_id == actor.departamento_id)
    return or_(*conds)


def _cargar(bd: Session, actor: Actor, documento_id: int, gestionar: bool = False) -> Documento:
    d = bd.get(Documento, documento_id)
    if d is None or not _puede_ver(actor, d):
        raise HTTPException(404, "No se encuentra el documento.")
    if gestionar and not _puede_gestionar(actor, d):
        raise HTTPException(403, "Solo puedes modificar los documentos de tu departamento.")
    return d


# --------------------------------------------------------------------------- validaciones


def _niveles(bd: Session) -> dict[int, str]:
    return {n.orden: n.nombre for n in bd.scalars(select(Nivel).order_by(Nivel.orden)).all()}


def _validar_nivel(bd: Session, nivel: int | None) -> int:
    niveles = _niveles(bd) or {1: "", 2: "", 3: "", 4: ""}
    if nivel is None or nivel not in niveles:
        raise HTTPException(400, f"El nivel mínimo tiene que ser uno de estos: {', '.join(map(str, sorted(niveles)))}.")
    return nivel


def _entero_opcional(valor: str | None, campo: str) -> int | None:
    """Los formularios multipart envían «» o «null» para «sin valor»."""
    if valor is None or valor.strip().lower() in ("", "null", "none"):
        return None
    try:
        return int(valor)
    except ValueError:
        raise HTTPException(400, f"El campo «{campo}» no es válido.")


def _departamento_para_subida(bd: Session, actor: Actor, dep_id: int | None, es_publico: bool) -> int | None:
    if not actor.es_admin:
        if actor.departamento_id is None:
            raise HTTPException(400, "No tienes un departamento asignado. Pide a la administración que te asigne uno.")
        if dep_id is None:
            return actor.departamento_id
        if dep_id != actor.departamento_id:
            raise HTTPException(403, "Solo puedes subir documentos a tu departamento.")
        return dep_id
    if dep_id is not None and bd.get(Departamento, dep_id) is None:
        raise HTTPException(400, "El departamento elegido no existe.")
    if dep_id is None and not es_publico:
        raise HTTPException(400, "Elige un departamento o marca el documento como público.")
    return dep_id


# --------------------------------------------------------------------------- respuesta


def _ids_indexando(bd: Session, ids: Iterable[int]) -> set[int]:
    """Documentos de `ids` con un indexado pendiente o en curso en la cola de trabajos."""
    ids = list(ids)
    if not ids:
        return set()
    return set(bd.scalars(select(Trabajo.entidad_id).where(
        Trabajo.entidad == "documento", Trabajo.entidad_id.in_(ids), Trabajo.estado.in_(TRABAJO_ACTIVO),
    )).all())


def _a_dict(bd: Session, actor: Actor, d: Documento, niveles: dict[int, str] | None = None,
            indexando: bool | None = None) -> dict[str, Any]:
    datos = documentos.a_dict(bd, d)
    niveles = niveles if niveles is not None else _niveles(bd)
    if indexando is None:
        indexando = d.id in _ids_indexando(bd, [d.id])
    subido = bd.get(Usuario, d.subido_por_id) if d.subido_por_id else None
    datos.update({
        "tipo_nombre": NOMBRE_TIPO.get(d.tipo, d.tipo),
        "nivel_nombre": niveles.get(d.nivel_minimo),
        "subido_por": subido.nombre if subido else None,
        "actualizado": d.actualizado.isoformat() if d.actualizado else None,
        "url_descarga": f"{datos['url']}&descargar=1" if datos.get("url") else None,
        "mime": d.mime,
        "motor_id": d.motor_id,
        "puede_editar": _puede_gestionar(actor, d),
        # Un documento «procesando» sin trabajo en la cola se quedó a medias (p. ej. se reinició
        # el servidor mientras se indexaba): no avanzará solo y hay que reindexarlo.
        "indexando": indexando,
        "interrumpido": d.estado == "procesando" and not indexando,
    })
    return datos


def _partes_guardadas(bd: Session, d: Documento) -> list[tuple[str, dict[str, Any]]] | None:
    """Partes con metadatos propios (p. ej. los pasos de una instrucción) a partir de los
    fragmentos actuales, para no perder esos metadatos al reindexar un documento sin fichero."""
    frags = bd.scalars(select(Fragmento).where(Fragmento.documento_id == d.id).order_by(Fragmento.orden)).all()
    partes = [(f.texto, {k: v for k, v in (f.metadatos or {}).items() if not k.startswith("wk_")}) for f in frags]
    return partes if any(meta for _, meta in partes) else None


def _encolar_reindexado(bd: Session, d: Documento) -> None:
    partes = None if d.ruta_fichero else _partes_guardadas(bd, d)
    d.mensaje_estado = None
    if partes:
        d.estado = "procesando"
        bd.commit()
        trabajos.encolar("indexar_documento", documentos.indexar_trabajo, d.id, partes,
                         entidad="documento", entidad_id=d.id)
    else:
        documentos.reindexar(bd, d)


def _indexado_en_curso(bd: Session, d: Documento) -> bool:
    return d.id in _ids_indexando(bd, [d.id])


# --------------------------------------------------------------------------- listado y opciones


@router.get("")
def listar(
    departamento_id: int | None = Query(None, description="0 = sin departamento"),
    tipo: str | None = None,
    estado: str | None = None,
    texto: str | None = None,
    es_formacion: bool | None = None,
    es_publico: bool | None = None,
    origen: str | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(25, ge=1, le=100),
    actor: Actor = Depends(requiere_jefe),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    visibles = _filtro_visibles(actor)
    conds: list[ColumnElement[bool]] = [visibles]
    if departamento_id is not None:
        conds.append(Documento.departamento_id.is_(None) if departamento_id == 0
                     else Documento.departamento_id == departamento_id)
    if tipo:
        conds.append(Documento.tipo == tipo)
    if estado:
        conds.append(Documento.estado == estado)
    if es_formacion is not None:
        conds.append(Documento.es_formacion.is_(es_formacion))
    if es_publico is not None:
        conds.append(Documento.es_publico.is_(es_publico))
    if origen:
        conds.append(Documento.origen == origen)
    if texto and texto.strip():
        patron = f"%{texto.strip()}%"
        conds.append(or_(Documento.titulo.ilike(patron), Documento.descripcion.ilike(patron),
                         Documento.nombre_fichero.ilike(patron)))
    total = bd.scalar(select(func.count(Documento.id)).where(*conds)) or 0
    filas = bd.scalars(
        select(Documento)
        .where(*conds)
        .options(selectinload(Documento.departamento), selectinload(Documento.autor),
                 selectinload(Documento.validador))
        .order_by(Documento.creado.desc(), Documento.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    # Resumen de todo lo visible (sin filtros): alimenta las cifras y la recarga automática.
    por_estado = dict(bd.execute(
        select(Documento.estado, func.count(Documento.id)).where(visibles).group_by(Documento.estado)
    ).all())
    # «indexando» cuenta solo lo que tiene un trabajo vivo: la interfaz se recarga sola mientras
    # haya alguno, y no se queda sondeando para siempre por un documento interrumpido.
    activos = select(Trabajo.entidad_id).where(Trabajo.entidad == "documento", Trabajo.estado.in_(TRABAJO_ACTIVO))
    indexando = bd.scalar(select(func.count(Documento.id)).where(visibles, Documento.id.in_(activos))) or 0
    en_cola = _ids_indexando(bd, [d.id for d in filas])
    niveles = _niveles(bd)
    return {
        "documentos": [_a_dict(bd, actor, d, niveles, d.id in en_cola) for d in filas],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": max(1, math.ceil(total / por_pagina)),
        "resumen": {
            "total": sum(por_estado.values()),
            "listo": por_estado.get("listo", 0),
            "procesando": por_estado.get("procesando", 0),
            "error": por_estado.get("error", 0),
            "indexando": indexando,
        },
        "motor": ajustes().motor_conocimiento,
    }


@router.get("/opciones")
def opciones(actor: Actor = Depends(requiere_jefe), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Departamentos, niveles, tipos y estados para los selectores de la consola."""
    deps = bd.scalars(select(Departamento).order_by(Departamento.nombre)).all()
    niveles = bd.scalars(select(Nivel).order_by(Nivel.orden)).all()
    datos: dict[str, Any] = {
        "departamentos": [
            {"id": d.id, "nombre": d.nombre, "codigo": d.codigo, "color": d.color,
             "gestionable": actor.es_admin or d.id == actor.departamento_id}
            for d in deps
        ],
        "niveles": [{"orden": n.orden, "nombre": n.nombre, "descripcion": n.descripcion} for n in niveles],
        "tipos": [{"valor": t, "texto": NOMBRE_TIPO[t]} for t in NOMBRE_TIPO],
        "tipos_subida": list(TIPOS_SUBIDA),
        "estados": [{"valor": e, "texto": t} for e, t in NOMBRE_ESTADO.items()],
        "es_admin": actor.es_admin,
        "departamento_propio": actor.departamento_id,
        "motor": ajustes().motor_conocimiento,
        "umbral_respaldo": ajustes().umbral_respaldo,
        "fragmentos_por_consulta": ajustes().fragmentos_por_consulta,
    }
    # Para «buscar como...» en la consola de depuración: la administración, como cualquiera; un jefe,
    # como las personas de su departamento (para comprobar qué encuentra cada una de su equipo).
    if actor.es_admin or actor.departamento_id is not None:
        q = select(Usuario).where(Usuario.activo.is_(True))
        if not actor.es_admin:
            q = q.where(Usuario.departamento_id == actor.departamento_id, Usuario.id != actor.id)
        personas = bd.scalars(
            q.options(selectinload(Usuario.departamento), selectinload(Usuario.nivel)).order_by(Usuario.nombre)
        ).all()
        datos["personas"] = [
            {"id": u.id, "nombre": u.nombre, "usuario": u.usuario, "rol": u.rol,
             "departamento": u.departamento.nombre if u.departamento else None,
             "nivel": u.nivel.nombre if u.nivel else None}
            for u in personas
        ]
    return datos


# --------------------------------------------------------------------------- consola de búsqueda


class PruebaBusqueda(BaseModel):
    consulta: str
    como_usuario_id: int | None = None  # administración (cualquiera) o jefe (personas de su departamento)
    como_invitado: bool = False  # solo administración: alcance de alguien sin sesión
    k: int | None = None


def _describir_alcance(bd: Session, alcance: Alcance) -> list[dict[str, str]]:
    if alcance.todo:
        return [{"tipo": "todo", "texto": "Todo el conocimiento (administración)"}]
    niveles = _niveles(bd)
    salida = [{"tipo": "publico", "texto": "Documentos públicos"}] if alcance.publico else []
    for e in alcance.elementos:
        dep = bd.get(Departamento, e.departamento_id)
        nombre = dep.nombre if dep else f"Departamento {e.departamento_id}"
        if e.solo_formacion:
            salida.append({"tipo": "formacion", "texto": f"{nombre} · material de formación"})
        else:
            nivel = niveles.get(e.nivel_max)
            salida.append({"tipo": "departamento",
                           "texto": f"{nombre} · hasta nivel {e.nivel_max}" + (f" ({nivel})" if nivel else "")})
    return salida


@router.post("/probar-busqueda")
def probar_busqueda(datos: PruebaBusqueda, actor: Actor = Depends(requiere_jefe),
                    bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Consola de depuración: qué fragmentos encuentra una pregunta y con qué puntuación.

    Busca con el alcance de quien pregunta (calculado en el servidor). La administración puede
    buscar además como cualquier persona o como invitado; un jefe, como las personas de su
    departamento, y entonces solo ve lo que encuentran entre lo que él mismo puede ver (una
    persona que se forma en otro departamento encuentra material que su jefe no tiene por qué ver).
    """
    consulta = (datos.consulta or "").strip()
    if not consulta:
        raise HTTPException(400, "Escribe una pregunta para probar la búsqueda.")
    if len(consulta) > 2000:
        raise HTTPException(400, "La pregunta es demasiado larga (máximo 2000 caracteres).")
    k = min(max(datos.k or ajustes().fragmentos_por_consulta, 1), 20)
    como = actor
    if datos.como_invitado:
        if not actor.es_admin:
            raise HTTPException(403, "Solo la administración puede probar la búsqueda como invitado.")
        como = Actor(sesion=actor.sesion, usuario=None)
    elif datos.como_usuario_id is not None:
        u = bd.get(Usuario, datos.como_usuario_id)
        if not actor.es_admin and (u is None or actor.departamento_id is None
                                   or u.departamento_id != actor.departamento_id):
            raise HTTPException(403, "Solo puedes probar la búsqueda como personas de tu departamento.")
        if u is None:
            raise HTTPException(404, "No existe esa persona.")
        como = Actor(sesion=actor.sesion, usuario=u)
    alcance = alcance_de(bd, como)
    m = motor()
    inicio = time.perf_counter()
    try:
        encontrados = m.buscar(bd, consulta, alcance, k)
        if como is not actor and not actor.es_admin:  # solo lo que también puede ver quien prueba
            visibles = {d.id for d in bd.scalars(select(Documento).where(
                Documento.id.in_({r.documento_id for r in encontrados}), _filtro_visibles(actor)))} if encontrados else set()
            encontrados = [r for r in encontrados if r.documento_id in visibles]
        ambitos = [a.__dict__ for a in (m.ambitos(bd, alcance) or [])] if m.externo else None
    except (ErrorModelo, ErrorWeKnora) as e:  # mensajes pensados para mostrarse (modelo o WeKnora caídos)
        log.warning("Fallo en la prueba de búsqueda: %s", e)
        raise HTTPException(502, f"La búsqueda ha fallado: {e}")
    except Exception:  # noqa: BLE001  (lo demás no se enseña: puede llevar detalles internos)
        log.exception("Fallo en la prueba de búsqueda")
        raise HTTPException(500, "La búsqueda ha fallado por un error interno. Revisa el registro del servidor.")
    duracion = int((time.perf_counter() - inicio) * 1000)
    umbral = ajustes().umbral_respaldo
    docs = {d.id: d for d in bd.scalars(
        select(Documento).where(Documento.id.in_({r.documento_id for r in encontrados}))
        .options(selectinload(Documento.departamento))
    ).all()} if encontrados else {}
    niveles = _niveles(bd)
    resultados = []
    for i, r in enumerate(encontrados, start=1):
        d = docs.get(r.documento_id)
        resultados.append({
            "posicion": i,
            "documento_id": r.documento_id,
            "titulo": r.titulo,
            "texto": r.texto,
            "puntuacion": round(r.puntuacion, 6),
            "similitud": round(r.similitud, 4) if r.similitud is not None else None,
            "supera_umbral": r.similitud is not None and r.similitud >= umbral,
            "fragmento_id": r.fragmento_id,
            "metadatos": r.metadatos,
            "departamento": d.departamento.nombre if d and d.departamento else None,
            "nivel_minimo": d.nivel_minimo if d else None,
            "nivel_nombre": niveles.get(d.nivel_minimo) if d else None,
            "es_publico": d.es_publico if d else None,
            "es_formacion": d.es_formacion if d else None,
            "puede_abrir": bool(d and _puede_ver(actor, d)),
        })
    registrar(bd, actor, "probo_busqueda", "busqueda", None, consulta[:300],
              resultado={"fragmentos": len(resultados), "duracion_ms": duracion},
              contexto={"motor": m.nombre, "como_usuario_id": como.id if como is not actor else None})
    if como is not actor:
        auditar(bd, actor, "documentos.probar_busqueda_como", "usuario", como.id,
                {"consulta": consulta[:300], "invitado": como.es_invitado})
    bd.commit()
    u = como.usuario
    return {
        "consulta": consulta,
        "motor": m.nombre,
        "k": k,
        "duracion_ms": duracion,
        "umbral_respaldo": umbral,
        "con_respaldo": any(r["supera_umbral"] for r in resultados),
        "como": {
            "id": como.id,
            "nombre": como.nombre,
            "rol": como.rol,
            "departamento": u.departamento.nombre if u and u.departamento else None,
            "nivel": u.nivel.nombre if u and u.nivel else None,
        },
        "alcance": _describir_alcance(bd, alcance),
        "ambitos": ambitos,
        "resultados": resultados,
    }


# --------------------------------------------------------------------------- alta


@router.post("", status_code=201)
def subir(
    fichero: UploadFile = File(...),
    titulo: str | None = Form(None),
    departamento_id: str | None = Form(None),
    nivel_minimo: str | None = Form(None),
    es_formacion: bool = Form(False),
    es_publico: bool = Form(False),
    descripcion: str | None = Form(None),
    actor: Actor = Depends(requiere_jefe),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    nombre = fichero.filename or ""
    if tipo_por_extension(nombre) not in TIPOS_SUBIDA:
        raise HTTPException(400, f"El formato de «{nombre or 'el fichero'}» no se admite. "
                                 "Sube PDF, Word, Excel, PowerPoint, texto, audio o imagen.")
    if fichero.size == 0:
        raise HTTPException(400, f"«{nombre}» está vacío.")
    dep = _departamento_para_subida(bd, actor, _entero_opcional(departamento_id, "departamento"), es_publico)
    n = _entero_opcional(nivel_minimo, "nivel mínimo")
    nivel = _validar_nivel(bd, 1 if n is None else n)
    doc = documentos.crear_desde_subida(
        bd, actor, fichero, (titulo or "").strip() or None, dep, nivel, es_formacion, es_publico,
        (descripcion or "").strip() or None,
    )
    bd.refresh(doc)  # el indexado puede haber terminado ya en otra sesión
    return _a_dict(bd, actor, doc)


# --------------------------------------------------------------------------- un documento


@router.get("/{documento_id}")
def detalle(documento_id: int, fragmentos: int = Query(12, ge=0, le=200),
            actor: Actor = Depends(requiere_jefe), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Ficha del documento con sus primeros fragmentos y metadatos (para depurar el indexado)."""
    d = _cargar(bd, actor, documento_id)
    total = bd.scalar(select(func.count(Fragmento.id)).where(Fragmento.documento_id == d.id)) or 0
    frags = bd.execute(
        select(Fragmento.id, Fragmento.orden, Fragmento.texto, Fragmento.metadatos,
               Fragmento.embedding.is_not(None).label("con_vector"))
        .where(Fragmento.documento_id == d.id)
        .order_by(Fragmento.orden)
        .limit(fragmentos)
    ).all()
    tareas = bd.scalars(
        select(Trabajo).where(Trabajo.entidad == "documento", Trabajo.entidad_id == d.id)
        .order_by(Trabajo.id.desc()).limit(5)
    ).all()
    texto = d.contenido_texto or ""
    datos = _a_dict(bd, actor, d)
    datos.update({
        "texto_extraido": texto[:4000] or None,
        "texto_extraido_recortado": len(texto) > 4000,
        "fragmentos_total": total,
        "fragmentos_muestra": [
            {"id": f.id, "orden": f.orden, "texto": f.texto, "metadatos": f.metadatos or {},
             "caracteres": len(f.texto), "con_vector": bool(f.con_vector)}
            for f in frags
        ],
        "trabajos": [
            {"id": t.id, "estado": t.estado, "progreso": t.progreso, "mensaje": t.mensaje,
             "creado": t.creado.isoformat() if t.creado else None,
             "actualizado": t.actualizado.isoformat() if t.actualizado else None}
            for t in tareas
        ],
        "motor": ajustes().motor_conocimiento,
    })
    return datos


@router.get("/{documento_id}/descarga")
def descarga(documento_id: int, actor: Actor = Depends(requiere_jefe),
             bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """URL firmada para descargar el fichero original."""
    d = _cargar(bd, actor, documento_id)
    if not d.ruta_fichero:
        raise HTTPException(404, "Este documento no tiene fichero original: se creó desde texto.")
    registrar(bd, actor, "vio", "documento", d.id, d.titulo, contexto={"descarga": True})
    bd.commit()
    return {"url": f"{url_fichero(d.ruta_fichero)}&descargar=1", "nombre_fichero": d.nombre_fichero}


class CambiosDocumento(BaseModel):
    titulo: str | None = None
    descripcion: str | None = None
    departamento_id: int | None = None
    nivel_minimo: int | None = None
    es_formacion: bool | None = None
    es_publico: bool | None = None


@router.patch("/{documento_id}")
def editar(documento_id: int, datos: CambiosDocumento, actor: Actor = Depends(requiere_jefe),
           bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Cambia el título y las etiquetas (departamento, nivel mínimo, formación, público).

    Con el motor propio basta con actualizar la fila: los permisos se aplican en el SQL de
    cada búsqueda. Con WeKnora se reetiqueta el documento y, si cambia de base, se reindexa.
    """
    d = _cargar(bd, actor, documento_id, gestionar=True)
    campos = datos.model_fields_set
    antes = {c: getattr(d, c) for c in ("titulo", "descripcion", *CAMPOS_PERMISO)}
    if "titulo" in campos:
        t = (datos.titulo or "").strip()
        if not t:
            raise HTTPException(400, "El título no puede quedar vacío.")
        d.titulo = t[:300]
    if "descripcion" in campos:
        d.descripcion = (datos.descripcion or "").strip() or None
    if "nivel_minimo" in campos:
        d.nivel_minimo = _validar_nivel(bd, datos.nivel_minimo)
    if "es_formacion" in campos and datos.es_formacion is not None:
        d.es_formacion = datos.es_formacion
    if "es_publico" in campos and datos.es_publico is not None:
        d.es_publico = datos.es_publico
    if "departamento_id" in campos and datos.departamento_id != d.departamento_id:
        nuevo = datos.departamento_id
        if not actor.es_admin:
            raise HTTPException(403, "Solo la administración puede mover un documento a otro departamento.")
        if nuevo is not None and bd.get(Departamento, nuevo) is None:
            raise HTTPException(400, "El departamento elegido no existe.")
        d.departamento_id = nuevo
    if d.departamento_id is None and not d.es_publico:
        raise HTTPException(400, "Un documento sin departamento tiene que ser público.")
    cambios = {c: [antes[c], getattr(d, c)] for c in antes if antes[c] != getattr(d, c)}
    if not cambios:
        return _a_dict(bd, actor, d)
    reetiquetar = motor().reetiquetar if motor().externo else None
    cambia_permiso = any(c in cambios for c in CAMPOS_PERMISO)
    if cambia_permiso and reetiquetar is not None and _indexado_en_curso(bd, d):
        # Con un motor externo, el indexado en curso pondría las etiquetas antiguas.
        raise HTTPException(409, "El documento se está indexando. Espera a que termine para cambiar quién lo encuentra.")
    reindexar = False
    if cambia_permiso and d.motor_id:
        if reetiquetar is not None:
            try:
                reindexar = not reetiquetar(bd, d)
            except Exception as e:  # noqa: BLE001
                bd.rollback()
                log.exception("No se ha podido reetiquetar el documento %s", d.id)
                motivo = str(e) if isinstance(e, ErrorWeKnora) else "error interno (revisa el registro del servidor)"
                raise HTTPException(502, f"No se han podido actualizar las etiquetas en el motor de conocimiento: {motivo}")
    auditar(bd, actor, "documento.editar", "documento", d.id, {"titulo": d.titulo, "cambios": cambios})
    bd.commit()
    if reindexar:
        _encolar_reindexado(bd, d)
    bd.refresh(d)
    return _a_dict(bd, actor, d)


@router.post("/{documento_id}/reindexar")
def reindexar(documento_id: int, actor: Actor = Depends(requiere_jefe),
              bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    d = _cargar(bd, actor, documento_id, gestionar=True)
    if d.estado == "obsoleto":
        raise HTTPException(400, "Es una versión sustituida de una instrucción: se conserva solo para la trazabilidad de las citas y no se vuelve a indexar.")
    if d.estado == "borrador":
        # Reindexarla la pondría al alcance del copiloto sin que nadie la haya validado.
        raise HTTPException(409, "Es una ficha en borrador: el copiloto la encontrará cuando su autor la publique desde Captura.")
    if _indexado_en_curso(bd, d):
        raise HTTPException(409, "El documento ya se está procesando. Espera a que termine.")
    auditar(bd, actor, "documento.reindexar", "documento", d.id, {"titulo": d.titulo})
    bd.commit()
    _encolar_reindexado(bd, d)
    bd.refresh(d)
    return _a_dict(bd, actor, d)


@router.delete("/{documento_id}")
def borrar(documento_id: int, actor: Actor = Depends(requiere_jefe),
           bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    d = _cargar(bd, actor, documento_id, gestionar=True)
    if d.origen == "instruccion":
        # La instrucción seguiría publicada (en el modo planta y la formación) pero el copiloto no la
        # citaría, y no hay forma de volver a indexarla sin publicar otra versión. Las versiones
        # sustituidas se conservan para que las citas antiguas sigan llevando a su origen.
        raise HTTPException(409, "Este documento es una instrucción de trabajo y se gestiona desde Instrucciones: "
                                 "para cambiarla, crea y publica una versión nueva.")
    if motor().externo and _indexado_en_curso(bd, d):
        # Con un motor externo, el indexado en curso dejaría el documento huérfano allí.
        raise HTTPException(409, "El documento se está indexando. Espera a que termine para borrarlo.")
    info = {"titulo": d.titulo, "departamento_id": d.departamento_id, "origen": d.origen,
            "nombre_fichero": d.nombre_fichero}
    documentos.borrar(bd, d)
    auditar(bd, actor, "documento.borrar", "documento", documento_id, info)
    bd.commit()
    return {"ok": True}

