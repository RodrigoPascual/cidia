"""Modo planta: qué tareas puede ejecutar cada persona y ejecución guiada paso a paso.

Acceso (calculado siempre en el servidor a partir de la sesión):
  * tareas activas de su departamento cuyo nivel mínimo alcanza su nivel;
  * tareas de los puestos en los que tiene una formación activa (de todo el departamento si
    la formación no fija puesto);
  * la administración puede abrir cualquier tarea.

Una ejecución solo la modifica la persona que la hace (y mientras siga teniendo acceso a la
tarea); la ven además la administración, los jefes de su departamento y los del departamento de
la tarea cuando se forma en él (quien la observa y la evalúa). Si quien supervisa no puede abrir
la tarea (el jefe de alguien que se forma en otro departamento), ve el avance y las métricas,
pero no el contenido de la instrucción ni las respuestas del copiloto (`contenido_restringido`).
Cada ejecución guarda la instrucción publicada con la que se hizo, la confirmación de cada paso
y las consultas al copiloto por paso (curva de autonomía).
"""

from __future__ import annotations

import logging
import math
import mimetypes
import re
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from cidia import ficheros, trabajos, xapi
from cidia.db import sesion_bd
from cidia.ia import llm
from cidia.modelos import (
    Consulta,
    Documento,
    Ejecucion,
    EjecucionPaso,
    Formacion,
    Instruccion,
    NivelIluo,
    Paso,
    Puesto,
    Tarea,
    Usuario,
    ahora,
)
from cidia.permisos import Alcance, alcance_de, puede_ver
from cidia.seguridad import Actor, url_fichero
from cidia.servicios import consulta, iluo

log = logging.getLogger("cidia.planta")

MAX_FOTO = 25 * 1024 * 1024  # 25 MB: de sobra para una foto de móvil o de portátil
MAX_ID = 2**31 - 1  # las claves son INTEGER de PostgreSQL: un id mayor haría fallar la consulta
ORDEN_ORIGEN = {"puesto": 0, "departamento": 1, "formacion": 2, "admin": 3}


def id_valido(n: int | None) -> bool:
    """¿Puede existir una fila con este id? Fuera de rango se trata como «no existe» (404, no 500)."""
    return n is not None and 0 < n <= MAX_ID


# --------------------------------------------------------------------------- acceso a tareas


def acceso_tareas(bd: Session, actor: Actor) -> dict[int, dict[str, Any]]:
    """Tareas activas que la persona puede abrir: {tarea_id: {"origen", "formacion_id"}}.

    origen: "puesto" (de su propio puesto), "departamento" (otra de su departamento),
    "formacion" (de una formación activa) o "admin".
    """
    if actor.es_invitado or actor.usuario is None:
        return {}
    consulta = (
        select(Tarea.id, Tarea.puesto_id, Tarea.nivel_minimo, Puesto.departamento_id)
        .join(Puesto, Tarea.puesto_id == Puesto.id)
        .where(Tarea.activa.is_(True))
    )
    if actor.es_admin:
        return {f.id: {"origen": "admin", "formacion_id": None} for f in bd.execute(consulta)}

    formaciones = bd.scalars(
        select(Formacion).where(Formacion.usuario_id == actor.id, Formacion.estado == "activa")
    ).all()
    conds = []
    if actor.departamento_id:
        conds.append(and_(Puesto.departamento_id == actor.departamento_id, Tarea.nivel_minimo <= actor.nivel_orden))
    for f in formaciones:
        conds.append(Tarea.puesto_id == f.puesto_id if f.puesto_id else Puesto.departamento_id == f.departamento_id)
    if not conds:
        return {}

    def de_formacion(puesto_id: int, departamento_id: int) -> Formacion | None:
        for f in formaciones:
            if (f.puesto_id == puesto_id) if f.puesto_id else (f.departamento_id == departamento_id):
                return f
        return None

    acceso: dict[int, dict[str, Any]] = {}
    for f in bd.execute(consulta.where(or_(*conds))):
        if f.departamento_id == actor.departamento_id and f.nivel_minimo <= actor.nivel_orden:
            origen = "puesto" if f.puesto_id == actor.usuario.puesto_id else "departamento"
            acceso[f.id] = {"origen": origen, "formacion_id": None}
        else:
            form = de_formacion(f.puesto_id, f.departamento_id)
            acceso[f.id] = {"origen": "formacion", "formacion_id": form.id if form else None}
    return acceso


def exigir_acceso(bd: Session, actor: Actor, tarea_id: int) -> tuple[Tarea, dict[str, Any]]:
    """Devuelve la tarea si la persona puede abrirla; si no, 404 o 403."""
    tarea = bd.get(Tarea, tarea_id) if id_valido(tarea_id) else None
    if tarea is None or not tarea.activa:
        raise HTTPException(404, "No encontramos esa tarea.")
    info = acceso_tareas(bd, actor).get(tarea_id)
    if info is None:
        raise HTTPException(403, "Esta tarea no es de tu puesto ni de tus formaciones activas.")
    return tarea, info


def instrucciones_vigentes(bd: Session, tarea_ids: Iterable[int]) -> dict[int, Instruccion]:
    """Instrucción publicada de mayor versión de cada tarea (con sus pasos cargados)."""
    ids = list(tarea_ids)
    if not ids:
        return {}
    filas = bd.scalars(
        select(Instruccion)
        .where(Instruccion.tarea_id.in_(ids), Instruccion.estado == "publicada")
        .options(selectinload(Instruccion.pasos))
        .order_by(Instruccion.version)
    ).all()
    return {i.tarea_id: i for i in filas}  # la versión más alta queda la última


def instruccion_vigente(bd: Session, tarea_id: int) -> Instruccion | None:
    return instrucciones_vigentes(bd, [tarea_id]).get(tarea_id)


def niveles(bd: Session, usuario_id: int | None, tarea_ids: Iterable[int]) -> dict[int, NivelIluo]:
    ids = list(tarea_ids)
    if not ids or usuario_id is None:
        return {}
    filas = bd.scalars(select(NivelIluo).where(NivelIluo.usuario_id == usuario_id, NivelIluo.tarea_id.in_(ids)))
    return {n.tarea_id: n for n in filas}


def nivel_dict(n: NivelIluo | None) -> dict[str, Any]:
    """Nivel ILUO listo para la interfaz (0 sin iniciar ... 4 O)."""
    nivel = n.nivel if n else 0
    return {
        "nivel": nivel,
        "nivel_letra": iluo.nivel_letra(nivel),
        "requiere_reevaluacion": bool(n and n.requiere_reevaluacion),
        "caduca": n.caduca.isoformat() if n and n.caduca else None,
        "caducado": bool(n and n.caduca and n.caduca < ahora()),
    }


def _portada(ins: Instruccion) -> str | None:
    """Primera imagen de la instrucción, para la tarjeta de la tarea."""
    for p in ins.pasos:
        if p.imagen_ruta:
            return url_fichero(p.imagen_ruta)
    return None


# --------------------------------------------------------------------------- lista de tareas


def tareas(bd: Session, actor: Actor) -> list[dict[str, Any]]:
    """Tareas con instrucción publicada que la persona puede ejecutar en el modo planta."""
    acceso = acceso_tareas(bd, actor)
    vigentes = instrucciones_vigentes(bd, acceso.keys())
    if not vigentes:
        return []
    ids = list(vigentes)
    filas = bd.scalars(
        select(Tarea).where(Tarea.id.in_(ids)).options(selectinload(Tarea.puesto).selectinload(Puesto.departamento))
    ).all()
    niv = niveles(bd, actor.id, ids)
    mias = and_(Ejecucion.usuario_id == actor.id, Ejecucion.tarea_id.in_(ids))
    completadas = dict(bd.execute(
        select(Ejecucion.tarea_id, func.count()).where(mias, Ejecucion.estado == "completada").group_by(Ejecucion.tarea_id)
    ).all())
    ultimas = dict(bd.execute(
        select(Ejecucion.tarea_id, func.max(Ejecucion.fin)).where(mias, Ejecucion.estado == "completada")
        .group_by(Ejecucion.tarea_id)
    ).all())
    en_curso = {e.tarea_id: e for e in bd.scalars(
        select(Ejecucion).where(mias, Ejecucion.estado == "en_curso").order_by(Ejecucion.inicio)
    )}  # si hubiera varias, queda la más reciente
    confirmados = dict(bd.execute(
        select(EjecucionPaso.ejecucion_id, func.count())
        .where(EjecucionPaso.ejecucion_id.in_([e.id for e in en_curso.values()] or [0]),
               EjecucionPaso.confirmado_en.is_not(None))
        .group_by(EjecucionPaso.ejecucion_id)
    ).all())

    salida: list[dict[str, Any]] = []
    for t in filas:
        ins = vigentes[t.id]
        e = en_curso.get(t.id)
        ultima = ultimas.get(t.id)
        salida.append({
            "id": t.id,
            "codigo": t.codigo,
            "nombre": t.nombre,
            "descripcion": t.descripcion,
            "criticidad": t.criticidad,
            "riesgos_prl": t.riesgos_prl,
            "puesto": t.puesto.nombre if t.puesto else None,
            "departamento": t.puesto.departamento.nombre if t.puesto and t.puesto.departamento else None,
            "origen": acceso[t.id]["origen"],
            "instruccion": {
                "id": ins.id,
                "codigo": ins.codigo,
                "version": ins.version,
                "titulo": ins.titulo,
                "pasos": len(ins.pasos),
                "pasos_criticos": sum(1 for p in ins.pasos if p.es_critico),
                "portada_url": _portada(ins),
            },
            **nivel_dict(niv.get(t.id)),
            "ejecuciones_completadas": completadas.get(t.id, 0),
            "ultima_ejecucion": ultima.isoformat() if ultima else None,
            "ejecucion_en_curso": {
                "id": e.id,
                "inicio": e.inicio.isoformat(),
                "pasos_confirmados": confirmados.get(e.id, 0),
                "misma_version": e.instruccion_id == ins.id,
            } if e else None,
        })
    salida.sort(key=lambda d: (d["ejecucion_en_curso"] is None, ORDEN_ORIGEN.get(d["origen"], 9),
                               (d["codigo"] or "~").lower(), d["nombre"].lower()))
    return salida


# --------------------------------------------------------------------------- ejecuciones


def _supervisa(bd: Session, actor: Actor, ej: Ejecucion) -> bool:
    """¿Puede el actor ver (sin tocar) la ejecución de otra persona?

    La administración; los jefes del departamento de la persona; y los jefes del departamento de
    la tarea cuando la persona se forma en él, que son quienes la observan y la evalúan (la misma
    regla que servicios/iluo.py).
    """
    if actor.es_admin:
        return True
    if actor.rol != "jefe" or not actor.departamento_id:
        return False
    dueno = bd.get(Usuario, ej.usuario_id)
    if dueno is None:
        return False
    if dueno.departamento_id == actor.departamento_id:
        return True
    tarea = bd.get(Tarea, ej.tarea_id)
    dep = tarea.puesto.departamento_id if tarea is not None and tarea.puesto is not None else None
    if dep != actor.departamento_id:
        return False
    return bool(bd.scalar(select(func.count()).select_from(Formacion).where(
        Formacion.usuario_id == dueno.id, Formacion.departamento_id == dep, Formacion.estado == "activa")))


def obtener_ejecucion(bd: Session, actor: Actor, ejecucion_id: int, escribir: bool = False,
                      exigir_tarea: bool = True, bloquear: bool = False) -> Ejecucion:
    """Ejecución con control de acceso.

    Leer: la propia persona y quien la supervisa (ver `_supervisa`).
    Escribir: solo la propia persona y, salvo para abandonarla (`exigir_tarea=False`), mientras
    siga teniendo acceso a la tarea (si se le cancela la formación, no puede seguir sumando
    evidencias). A quien no puede verla se le responde 404 (no se revela que existe).
    Para escribir (o con `bloquear`, la revisión del jefe) se bloquea la fila hasta el commit: dos
    «Finalizar» seguidos (un reintento de la red) no cierran la ejecución dos veces, y la revisión
    no pisa el veredicto que la comparación en segundo plano guarde mientras tanto.
    """
    bloqueo = escribir or bloquear
    ej = bd.get(Ejecucion, ejecucion_id, with_for_update=bloqueo) if id_valido(ejecucion_id) else None
    if ej is None:
        raise HTTPException(404, "No encontramos esa ejecución.")
    if ej.usuario_id == actor.id:
        if escribir and exigir_tarea and ej.tarea_id not in acceso_tareas(bd, actor):
            raise HTTPException(403, "Ya no tienes acceso a esta tarea (puede que haya terminado tu formación). "
                                     "Sal del modo planta y abandona la ejecución.")
        return ej
    if not _supervisa(bd, actor, ej):
        raise HTTPException(404, "No encontramos esa ejecución.")
    if escribir:
        raise HTTPException(403, "Solo la persona que hace la tarea puede avanzar en su ejecución.")
    return ej


def _exigir_en_curso(ej: Ejecucion) -> None:
    if ej.estado != "en_curso":
        estado = "completada" if ej.estado == "completada" else "abandonada"
        raise HTTPException(409, f"Esta ejecución ya está {estado}. Empieza una nueva desde la lista de tareas.")


def _contexto(ej: Ejecucion, ins: Instruccion | None = None) -> dict[str, Any]:
    ctx: dict[str, Any] = {"ejecucion_id": ej.id, "tarea_id": ej.tarea_id, "instruccion_id": ej.instruccion_id}
    if ins is not None:
        ctx["version"] = ins.version
        ctx["codigo"] = ins.codigo
    return ctx


def iniciar(bd: Session, actor: Actor, tarea_id: int) -> tuple[Ejecucion, bool]:
    """Crea una ejecución con la instrucción publicada vigente. Devuelve (ejecución, reanudada).

    Si la persona ya tenía una ejecución en curso de esa tarea con la misma instrucción, la
    reanuda; si era de una versión anterior, la da por abandonada y empieza otra.
    """
    tarea, _ = exigir_acceso(bd, actor, tarea_id)
    ins = instruccion_vigente(bd, tarea.id)
    if ins is None:
        raise HTTPException(409, "Esta tarea todavía no tiene una instrucción publicada.")
    if not ins.pasos:
        raise HTTPException(409, "La instrucción publicada no tiene pasos. Avisa al experto de la tarea.")

    abiertas = bd.scalars(select(Ejecucion).where(
        Ejecucion.usuario_id == actor.id, Ejecucion.tarea_id == tarea.id, Ejecucion.estado == "en_curso"
    ).order_by(Ejecucion.inicio.desc())).all()
    for e in abiertas:
        if e.instruccion_id == ins.id:
            return e, True
        # Ejecución a medias de una versión anterior: se cierra y queda constancia del motivo.
        e.estado = "abandonada"
        e.fin = ahora()
        xapi.registrar(
            bd, actor, "abandono", "tarea", tarea.id, tarea.nombre,
            resultado={"completion": False, "motivo": "nueva_version", "consultas": e.consultas,
                       "duracion": _segundos(e)},
            contexto={**_contexto(e), "instruccion_nueva_id": ins.id},
        )

    ej = Ejecucion(usuario_id=actor.id, tarea_id=tarea.id, instruccion_id=ins.id, inicio=ahora())
    bd.add(ej)
    bd.flush()
    for p in ins.pasos:
        bd.add(EjecucionPaso(ejecucion_id=ej.id, paso_id=p.id))
    xapi.registrar(bd, actor, "inicio", "tarea", tarea.id, tarea.nombre, contexto=_contexto(ej, ins))
    bd.flush()
    iluo.recalcular(bd, actor.id, tarea.id)  # empezar a ejecutar ya cuenta para el nivel I
    return ej, False


def _ejecucion_paso(bd: Session, ej: Ejecucion, paso: Paso) -> EjecucionPaso:
    ep = bd.scalar(select(EjecucionPaso).where(EjecucionPaso.ejecucion_id == ej.id, EjecucionPaso.paso_id == paso.id))
    if ep is None:
        ep = EjecucionPaso(ejecucion_id=ej.id, paso_id=paso.id)
        bd.add(ep)
        bd.flush()
    return ep


def _paso_de(bd: Session, ej: Ejecucion, paso_id: int) -> Paso:
    paso = bd.get(Paso, paso_id) if id_valido(paso_id) else None
    if paso is None or paso.instruccion_id != ej.instruccion_id:
        raise HTTPException(404, "Ese paso no pertenece a la instrucción de esta ejecución.")
    return paso


def confirmar_paso(bd: Session, actor: Actor, ej: Ejecucion, paso_id: int, critico_confirmado: bool) -> EjecucionPaso:
    """Marca un paso como hecho. En los pasos críticos exige la confirmación expresa."""
    _exigir_en_curso(ej)
    paso = _paso_de(bd, ej, paso_id)
    if paso.es_critico and not critico_confirmado:
        raise HTTPException(400, "Es un paso crítico: marca la casilla de confirmación antes de continuar.")
    ep = _ejecucion_paso(bd, ej, paso)
    if ep.confirmado_en is None:
        ep.confirmado_en = ahora()
        ep.critico_confirmado = bool(paso.es_critico and critico_confirmado)
        xapi.registrar(
            bd, actor, "confirmo", "paso", paso.id, paso.titulo,
            resultado={"completion": True, "critico": paso.es_critico, "critico_confirmado": ep.critico_confirmado,
                       "consultas": ep.consultas},
            contexto={**_contexto(ej), "orden": paso.orden},
        )
    return ep


def validar_pregunta(bd: Session, ej: Ejecucion, paso_id: int | None) -> Paso | None:
    """Comprueba que se puede preguntar en esta ejecución y que el paso es de su instrucción."""
    _exigir_en_curso(ej)
    return _paso_de(bd, ej, paso_id) if paso_id is not None else None


def registrar_consulta(bd: Session, ej: Ejecucion, paso_id: int | None) -> Paso | None:
    """Cuenta una pregunta al copiloto en la ejecución y en su paso (curva de autonomía).

    La ruta del modo planta la llama ANTES de pedir la respuesta: preguntar ya es la evidencia, y
    así cuenta aunque el modelo falle o la persona cierre la pantalla a mitad de la respuesta.
    `consulta.responder_stream` no toca estos contadores (servicios/consulta.py), así que la
    pregunta se cuenta una sola vez.
    """
    paso = validar_pregunta(bd, ej, paso_id)
    critico = bool(paso is not None and paso.es_critico)
    # Incrementos en SQL (no «leer, sumar y escribir»): dos preguntas seguidas que se procesan a
    # la vez no pueden perder una consulta de la curva de autonomía.
    bd.execute(
        update(Ejecucion).where(Ejecucion.id == ej.id)
        .values(consultas=func.coalesce(Ejecucion.consultas, 0) + 1,
                consultas_criticos=func.coalesce(Ejecucion.consultas_criticos, 0) + (1 if critico else 0))
        .execution_options(synchronize_session=False)
    )
    bd.expire(ej, ["consultas", "consultas_criticos"])
    if paso is not None:
        ep = _ejecucion_paso(bd, ej, paso)
        bd.execute(
            update(EjecucionPaso).where(EjecucionPaso.id == ep.id)
            .values(consultas=func.coalesce(EjecucionPaso.consultas, 0) + 1)
            .execution_options(synchronize_session=False)
        )
        bd.expire(ep, ["consultas"])
    return paso


def _segundos(ej: Ejecucion) -> int:
    fin = ej.fin or ahora()
    return max(0, int((fin - ej.inicio).total_seconds())) if ej.inicio else 0


def finalizar(bd: Session, actor: Actor, ej: Ejecucion) -> dict[str, Any]:
    """Cierra la ejecución si todos los pasos están confirmados y recalcula el nivel ILUO."""
    _exigir_en_curso(ej)
    ins = bd.get(Instruccion, ej.instruccion_id)
    tarea = bd.get(Tarea, ej.tarea_id)
    assert ins is not None and tarea is not None
    hechos = {ep.paso_id for ep in ej.pasos if ep.confirmado_en is not None}
    faltan = [str(i) for i, p in enumerate(ins.pasos, start=1) if p.id not in hechos]
    if faltan:
        lista = ", ".join(faltan)
        raise HTTPException(400, f"Faltan pasos por confirmar ({lista}). Confírmalos antes de finalizar.")

    previo = bd.scalar(select(NivelIluo).where(NivelIluo.usuario_id == ej.usuario_id, NivelIluo.tarea_id == ej.tarea_id))
    nivel_antes = previo.nivel if previo else 0
    ej.estado = "completada"
    ej.fin = ahora()
    duracion = _segundos(ej)
    xapi.registrar(
        bd, actor, "completo", "tarea", tarea.id, tarea.nombre,
        resultado={"completion": True, "consultas": ej.consultas, "consultas_criticos": ej.consultas_criticos,
                   "duracion": duracion},
        contexto=_contexto(ej, ins),
    )
    bd.flush()
    nuevo = iluo.recalcular(bd, ej.usuario_id, ej.tarea_id)
    if nuevo is None:
        nuevo = bd.scalar(select(NivelIluo).where(NivelIluo.usuario_id == ej.usuario_id, NivelIluo.tarea_id == ej.tarea_id))
    completadas = bd.scalar(select(func.count()).select_from(Ejecucion).where(
        Ejecucion.usuario_id == ej.usuario_id, Ejecucion.tarea_id == ej.tarea_id, Ejecucion.estado == "completada"
    )) or 0
    return {
        "duracion_s": duracion,
        "consultas": ej.consultas,
        "consultas_criticos": ej.consultas_criticos,
        "pasos": len(ins.pasos),
        "pasos_criticos": sum(1 for p in ins.pasos if p.es_critico),
        "ejecuciones_completadas": completadas,
        "nivel_anterior": nivel_antes,
        **nivel_dict(nuevo),
    }


def abandonar(bd: Session, actor: Actor, ej: Ejecucion) -> None:
    _exigir_en_curso(ej)
    tarea = bd.get(Tarea, ej.tarea_id)
    ej.estado = "abandonada"
    ej.fin = ahora()
    hechos = sum(1 for ep in ej.pasos if ep.confirmado_en is not None)
    xapi.registrar(
        bd, actor, "abandono", "tarea", ej.tarea_id, tarea.nombre if tarea else None,
        resultado={"completion": False, "pasos_confirmados": hechos, "consultas": ej.consultas,
                   "duracion": _segundos(ej)},
        contexto=_contexto(ej),
    )


# --------------------------------------------------------------------------- foto del resultado


# Pasos finales de papeleo («Registrar y etiquetar el conjunto», «Registro el número de serie»): su
# imagen es un esquema del registro, no la pieza terminada, y no sirve para comparar la foto.
_RE_PASO_PAPELEO = re.compile(r"^\s*(registr|etiquet|anot|document|archiv|firm|rellen)", re.I)


def _paso_referencia(ins: Instruccion) -> Paso | None:
    """Imagen de referencia del resultado: la del último paso con imagen, saltando los pasos finales
    de papeleo si antes hay otro con imagen (en IT-023, la inspección visual final y no el registro)."""
    con_imagen = [p for p in ins.pasos if p.imagen_ruta]
    for p in reversed(con_imagen):
        if not _RE_PASO_PAPELEO.match(p.titulo or ""):
            return p
    return con_imagen[-1] if con_imagen else None


_SI = {"true", "si", "sí", "yes", "1", "coincide", "verdadero", "correcto", "cierto"}
_NO = {"false", "no", "0", "falso", "incorrecto"}


def _a_bool(v: Any) -> bool | None:
    """Sí/no del modelo. Como texto vale «Sí», «sí, coincide», «No» o «no coincide»; lo dudoso
    («no sé», «sí, pero no del todo», «puede») queda en None, y la foto la revisa una persona."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        palabras = re.findall(r"\w+", v.lower())
        if not palabras:
            return None
        if palabras[0] in _NO and (len(palabras) == 1 or palabras[1:] == ["coincide"]):
            return False
        if palabras[0] in _SI and not _NO & set(palabras[1:]):
            return True
    return None


# Confianza escrita con palabras: se traduce a la escala 0-1 (por debajo de UMBRAL_CONFIANZA,
# la foto la revisa una persona aunque el modelo diga que coincide).
_CONFIANZA_PALABRAS = {"muy baja": 0.1, "baja": 0.3, "poca": 0.3, "media": 0.5, "moderada": 0.5,
                       "alta": 0.85, "muy alta": 0.95}


def _a_confianza(v: Any) -> float | None:
    """Confianza entre 0 y 1. Los modelos pequeños la escriben de muchas formas: 0.85, 85, «85 %»,
    «0,85» (coma decimal) o «alta». Lo que no se entiende (o un NaN) queda en None."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, str):
        s = " ".join(re.findall(r"[\w.,%]+", v.lower())).rstrip(".")
        if s in _CONFIANZA_PALABRAS:
            return _CONFIANZA_PALABRAS[s]
        porcentaje = s.endswith("%")
        try:
            v = float(s.rstrip("%").strip().replace(",", ".")) / (100 if porcentaje else 1)
        except ValueError:
            return None
    if not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    v = float(v) / 100 if v > 1 else float(v)
    return max(0.0, min(1.0, v))


def _veredicto_modelo(r: Any) -> dict[str, Any]:
    """Normaliza el JSON del modelo de visión: {coincide, observaciones, confianza}.

    Tolerante con los modelos pequeños: una lista con el objeto dentro, el objeto anidado en
    otra clave ({"resultado": {...}}), el sí/no escrito como texto o la confianza en porcentaje,
    con coma decimal o con palabras.
    """
    if isinstance(r, list) and r:
        r = r[0]
    if isinstance(r, dict) and "coincide" not in r:
        r = next((v for v in r.values() if isinstance(v, dict) and "coincide" in v), r)
    if not isinstance(r, dict):
        raise ValueError("Respuesta sin objeto JSON")
    coincide = _a_bool(r.get("coincide"))
    if coincide is None:
        raise ValueError("Respuesta sin el campo «coincide»")
    observaciones = r.get("observaciones")
    if isinstance(observaciones, list):  # a veces llega como lista de frases
        observaciones = " ".join(str(x).strip() for x in observaciones if isinstance(x, (str, int, float)))
    observaciones = observaciones.strip()[:600] if isinstance(observaciones, str) else ""
    return {"coincide": coincide, "observaciones": observaciones, "confianza": _a_confianza(r.get("confianza"))}


UMBRAL_CONFIANZA = 0.7  # por debajo, el modelo «duda» y la foto la revisa el jefe aunque diga que coincide


def necesita_revision(v: dict[str, Any] | None) -> bool:
    """¿Tiene que mirar la foto una persona? Sí cuando no se pudo comparar (sin visión, sin imagen de
    referencia o error del modelo), cuando el modelo ve diferencias y cuando duda (poca confianza).
    Se calcula con los datos del veredicto, no con el indicador guardado, para valer también con
    las fotos guardadas antes de existir la revisión."""
    if not v:
        return False
    if v.get("estado") != "comparada" or v.get("coincide") is not True:
        return True
    confianza = v.get("confianza")
    return isinstance(confianza, (int, float)) and confianza < UMBRAL_CONFIANZA


COMPARANDO = "comparando"  # la foto está guardada y el modelo con visión la está comparando


@dataclass(frozen=True)
class Referencia:
    """Lo que hace falta del paso de referencia para comparar fuera de la sesión de la petición."""

    paso_id: int
    titulo: str
    criterio: str
    imagen_ruta: str


def _referencia(p: Paso) -> Referencia:
    return Referencia(p.id, p.titulo, (p.criterio_aceptacion or "").strip(), p.imagen_ruta or "")


def _base_veredicto(referencia: Paso | Referencia | None) -> dict[str, Any]:
    pid = referencia.paso_id if isinstance(referencia, Referencia) else (referencia.id if referencia else None)
    return {"revision_humana": True, "coincide": None, "observaciones": "", "confianza": None, "modelo": None,
            "referencia_paso_id": pid}


def comparar_foto(bd: Session, ruta_foto: str, referencia: Paso | None) -> dict[str, Any]:
    """Compara la foto con la imagen del experto si hay un modelo con visión permitido.

    El resultado es siempre orientativo. `revision_humana` indica que el jefe tiene que revisarla
    (ver `necesita_revision`); puede revisar también las demás desde la ejecución.
    """
    base = _base_veredicto(referencia)
    modelo = llm.modelo_vision(bd)
    if not modelo:
        return {**base, "estado": "sin_vision",
                "mensaje": "Este servidor no tiene un modelo con visión. La foto queda guardada y la revisará una persona."}
    if referencia is None or not referencia.imagen_ruta:
        return {**base, "estado": "sin_referencia",
                "mensaje": "La instrucción no tiene imagen de referencia del experto. La foto queda guardada y la "
                           "revisará una persona."}
    return _comparar(modelo, ruta_foto, _referencia(referencia))


def _comparar(modelo: str, ruta_foto: str, referencia: Referencia) -> dict[str, Any]:
    """La comparación con el modelo de visión (lenta con modelos pequeños: no usa la base de datos)."""
    base = _base_veredicto(referencia)
    try:
        ref = ficheros.ruta_absoluta(referencia.imagen_ruta)
        foto = ficheros.ruta_absoluta(ruta_foto)
        criterio = referencia.criterio
        texto = (
            "Compara dos fotos de una tarea industrial.\n"
            f"Imagen 1: referencia del experto (paso «{referencia.titulo}»).\n"
            "Imagen 2: foto del resultado que ha hecho el operario.\n"
            + (f"Criterio de aceptación: {criterio}\n" if criterio else "")
            + "¿El resultado de la imagen 2 coincide con la referencia? Fíjate en piezas que falten, posiciones, "
            "montajes incompletos o daños. Responde SOLO con JSON:\n"
            '{"coincide": true o false, "observaciones": "una o dos frases en castellano", '
            '"confianza": número entre 0 y 1}'
        )
        mensajes = [
            {"role": "system", "content": "Eres inspector de calidad en una planta industrial. Respondes solo con JSON."},
            {"role": "user", "content": [
                {"type": "text", "text": texto},
                llm.imagen_a_parte(ref, mimetypes.guess_type(ref.name)[0] or "image/jpeg"),
                llm.imagen_a_parte(foto, mimetypes.guess_type(foto.name)[0] or "image/jpeg"),
            ]},
        ]
        v = _veredicto_modelo(llm.chat_json(mensajes, modelo=modelo, bd=None, max_tokens=400))
    except Exception as e:  # noqa: BLE001  (modelo caído, JSON inválido o imagen ilegible)
        log.warning("No se pudo comparar la foto con visión: %s", e)
        return {**base, "estado": "error",
                "mensaje": "No se ha podido comparar la foto automáticamente. La revisará una persona."}
    mensaje = ("La foto se parece a la referencia del experto." if v["coincide"]
               else "El modelo ve diferencias con la referencia: revísalo antes de dar la tarea por buena.")
    veredicto = {**base, **v, "estado": "comparada", "modelo": modelo, "mensaje": mensaje}
    veredicto["revision_humana"] = necesita_revision(veredicto)
    if v["coincide"] and veredicto["revision_humana"]:
        veredicto["mensaje"] = "El modelo cree que se parece, pero no está seguro: la revisará tu responsable."
    return veredicto


def tipo_imagen(cabecera: bytes) -> str | None:
    """Extensión de una foto JPG, PNG o WEBP según sus primeros bytes, o None si no es una de ellas.

    No se fía del nombre ni del tipo que declara el navegador: un SVG (que puede llevar
    JavaScript) o un HTML disfrazado de imagen se serviría desde el mismo origen que la interfaz.
    """
    if cabecera.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if cabecera.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        return "webp"
    return None


def _en_hilo(funcion: Callable[[], None]) -> None:
    # Con la cola de trabajos en modo síncrono (las pruebas), también en el mismo hilo.
    if getattr(trabajos, "_sincrono", False):
        funcion()
        return
    threading.Thread(target=funcion, name="cidia-foto", daemon=True).start()


# Cómo se lanza la comparación de la foto.
lanzar_comparacion: Callable[[Callable[[], None]], None] = _en_hilo


def comparar_en_segundo_plano(ej: Ejecucion, ins: Instruccion) -> None:
    """Compara con el modelo de visión la foto que `guardar_foto` dejó «comparando» (después del
    commit). Con un modelo pequeño puede tardar minutos: la persona no espera, puede finalizar la
    tarea mientras tanto y la pantalla recoge el veredicto cuando llega. Si entretanto ha hecho otra
    foto, el resultado de la anterior se descarta; una revisión del jefe hecha mientras tanto se
    conserva. Si el servidor se reinicia a mitad, la foto queda «comparando», que cuenta como
    pendiente de revisar por una persona (ver `necesita_revision`)."""
    v = ej.foto_veredicto or {}
    referencia = _paso_referencia(ins)
    if v.get("estado") != COMPARANDO or not ej.foto_ruta or referencia is None or not v.get("modelo"):
        return
    ejecucion_id, ruta, modelo, datos_ref = ej.id, ej.foto_ruta, str(v["modelo"]), _referencia(referencia)

    def comparar() -> None:
        resultado = _comparar(modelo, ruta, datos_ref)
        try:
            with sesion_bd() as bd:
                fila = bd.get(Ejecucion, ejecucion_id, with_for_update=True)
                if fila is None or fila.foto_ruta != ruta:
                    return
                previo = fila.foto_veredicto or {}
                fila.foto_veredicto = {**resultado, "revision": previo.get("revision")}
        except Exception:  # noqa: BLE001  (sin veredicto, la foto sigue pendiente de una persona)
            log.exception("No se pudo guardar el veredicto de la foto de la ejecución %s", ejecucion_id)

    lanzar_comparacion(comparar)


def guardar_foto(bd: Session, actor: Actor, ej: Ejecucion, subida: UploadFile) -> dict[str, Any]:
    """Guarda la foto del resultado y devuelve su veredicto. Sin visión o sin imagen de referencia el
    veredicto es inmediato; con visión queda «comparando» y quien llama, tras el commit, lanza
    `comparar_en_segundo_plano`."""
    _exigir_en_curso(ej)
    datos = subida.file.read(MAX_FOTO + 1)  # como mucho 25 MB en memoria: no se escribe nada más grande
    if not datos:
        raise HTTPException(400, "La imagen está vacía. Vuelve a hacer la foto.")
    if len(datos) > MAX_FOTO:
        raise HTTPException(413, "La foto es demasiado grande (máximo 25 MB).")
    ext = tipo_imagen(datos[:16])
    if ext is None:
        raise HTTPException(400, "Sube una foto en JPG, PNG o WEBP.")
    # Nombre fijo: la extensión (y con ella el tipo con el que se sirve) la deciden los bytes.
    ruta = ficheros.guardar_bytes(datos, "planta/fotos", f"resultado.{ext}")
    ins = bd.get(Instruccion, ej.instruccion_id)
    tarea = bd.get(Tarea, ej.tarea_id)
    assert ins is not None
    referencia = _paso_referencia(ins)
    modelo = llm.modelo_vision(bd)
    if modelo and referencia is not None and referencia.imagen_ruta:
        veredicto = {**_base_veredicto(referencia), "estado": COMPARANDO, "modelo": modelo,
                     "mensaje": "Comparando la foto con la imagen del experto. Puedes finalizar mientras tanto."}
    else:
        veredicto = comparar_foto(bd, ruta, referencia)
    ej.foto_ruta = ruta
    ej.foto_veredicto = veredicto
    xapi.registrar(
        bd, actor, "fotografio", "ejecucion", ej.id, tarea.nombre if tarea else None,
        resultado={"estado": veredicto["estado"], "coincide": veredicto["coincide"],
                   "confianza": veredicto["confianza"]},
        contexto=_contexto(ej, ins),
    )
    return veredicto_dict(ej, ins)


def veredicto_dict(ej: Ejecucion, ins: Instruccion | None, restringido: bool = False) -> dict[str, Any] | None:
    """Veredicto guardado con las URLs firmadas de la foto y de la referencia.

    Con `restringido` (quien mira no puede abrir la tarea) no sale la imagen del experto."""
    if not ej.foto_ruta:
        return None
    v = dict(ej.foto_veredicto or {})
    ref = _paso_referencia(ins) if ins is not None and not restringido else None
    v["foto_url"] = url_fichero(ej.foto_ruta)
    v["referencia_url"] = url_fichero(ref.imagen_ruta) if ref else None
    v["necesita_revision"] = necesita_revision(v)
    v.setdefault("revision", None)
    v["pendiente_revision"] = v["necesita_revision"] and not v["revision"]
    return v


# --------------------------------------------------------------------------- revisión de la foto por el jefe

DECISIONES = ("aprobada", "rechazada")
MAX_COMENTARIO = 1000
ESTADOS_REVISABLES = ("en_curso", "completada")


def puede_revisar(bd: Session, actor: Actor, ej: Ejecucion) -> bool:
    """Revisa la foto del resultado el jefe del departamento de la tarea (cuando la persona es de ese
    departamento o se forma en él) o la administración, nunca quien hizo la tarea: la misma regla que
    la observación en el puesto (iluo.puede_evaluar)."""
    if actor.es_invitado or actor.usuario is None or ej.usuario_id == actor.id:
        return False
    persona = bd.get(Usuario, ej.usuario_id)
    tarea = bd.get(Tarea, ej.tarea_id)
    if persona is None or tarea is None:
        return False
    return iluo.puede_evaluar(bd, actor, persona, tarea)


def revisar_foto(bd: Session, actor: Actor, ej: Ejecucion, decision: str, comentario: str | None) -> dict[str, Any]:
    """El jefe da por buena la foto del resultado o la rechaza con un comentario para la persona.

    Queda en el veredicto (`revision`), con su sentencia xAPI («validó» o «rechazó»), y se recalcula
    el nivel ILUO si la ejecución ya está completada. Se puede cambiar de decisión; una foto nueva
    vuelve a quedar pendiente. No hace commit."""
    if not puede_revisar(bd, actor, ej):
        raise HTTPException(403, "Solo el jefe del departamento de la tarea puede revisar esta foto.")
    if not ej.foto_ruta:
        raise HTTPException(409, "Esta ejecución no tiene foto del resultado.")
    if ej.estado not in ESTADOS_REVISABLES:
        raise HTTPException(409, "La ejecución se abandonó: no hay resultado que revisar.")
    if decision not in DECISIONES:
        raise HTTPException(400, "Decisión no válida: da la foto por buena o recházala.")
    comentario = (comentario or "").strip()[:MAX_COMENTARIO]
    if decision == "rechazada" and len(comentario) < 3:
        raise HTTPException(400, "Explica qué hay que corregir: quien hizo la tarea verá tu comentario.")
    v = dict(ej.foto_veredicto or {})
    anterior = v.get("revision") or None
    v["revision"] = {"estado": decision, "comentario": comentario or None, "revisor_id": actor.id,
                     "revisor": actor.nombre, "fecha": ahora().isoformat()}
    ej.foto_veredicto = v  # un diccionario nuevo: así JSONB guarda el cambio
    tarea = bd.get(Tarea, ej.tarea_id)
    ins = bd.get(Instruccion, ej.instruccion_id)
    xapi.registrar(
        bd, actor, "valido" if decision == "aprobada" else "rechazo", "ejecucion", ej.id,
        tarea.nombre if tarea else None,
        resultado={"objeto": "foto_resultado", "decision": decision, "comentario": comentario or None,
                   "decision_anterior": anterior.get("estado") if isinstance(anterior, dict) else None,
                   "veredicto_modelo": v.get("estado"), "coincide": v.get("coincide")},
        contexto={**_contexto(ej, ins), "usuario_id": ej.usuario_id},
    )
    bd.flush()
    if ej.estado == "completada":
        iluo.recalcular(bd, ej.usuario_id, ej.tarea_id)
    return veredicto_dict(ej, ins, contenido_restringido(bd, actor, ej)) or {}


def revisiones(bd: Session, actor: Actor, estado: str = "pendientes", limite: int = 60) -> dict[str, Any]:
    """Fotos del resultado que puede revisar el actor (jefe o administración).

    estado: «pendientes» (sin visión, con diferencias o con dudas del modelo, y sin revisar),
    «revisadas» o «todas». Devuelve {elementos, pendientes} con el total de pendientes."""
    if actor.es_invitado or actor.usuario is None or not (actor.es_admin or actor.rol == "jefe"):
        raise HTTPException(403, "Solo los jefes de departamento y la administración revisan las fotos.")
    q = select(Ejecucion).where(Ejecucion.foto_ruta.is_not(None), Ejecucion.estado.in_(ESTADOS_REVISABLES),
                                Ejecucion.usuario_id != actor.id)
    if not actor.es_admin:
        if not actor.departamento_id:
            return {"elementos": [], "pendientes": 0}
        q = (q.join(Tarea, Tarea.id == Ejecucion.tarea_id).join(Puesto, Puesto.id == Tarea.puesto_id)
             .where(Puesto.departamento_id == actor.departamento_id))
    filas = bd.scalars(q.order_by(func.coalesce(Ejecucion.fin, Ejecucion.inicio).desc(), Ejecucion.id.desc())
                       .limit(400)).all()
    if not filas:
        return {"elementos": [], "pendientes": 0}
    personas = {u.id: u for u in bd.scalars(select(Usuario).where(Usuario.id.in_({e.usuario_id for e in filas})))}
    tareas_ = {t.id: t for t in bd.scalars(select(Tarea).where(Tarea.id.in_({e.tarea_id for e in filas})))}
    inss = {i.id: i for i in bd.scalars(select(Instruccion).where(Instruccion.id.in_({e.instruccion_id for e in filas}))
                                        .options(selectinload(Instruccion.pasos)))}
    permitido: dict[int, bool] = {}  # por persona: es de su departamento o se forma en él
    # La imagen del experto solo sale si quien revisa puede abrir la tarea (como en la ejecución):
    # un jefe de nivel 3 no ve la referencia de una tarea de nivel 4 de su departamento.
    abre = set() if actor.es_admin else set(acceso_tareas(bd, actor))

    def puede(e: Ejecucion) -> bool:
        if actor.es_admin:
            return True
        if e.usuario_id not in permitido:
            u = personas.get(e.usuario_id)
            permitido[e.usuario_id] = u is not None and (
                u.departamento_id == actor.departamento_id or iluo.en_formacion(bd, u.id, actor.departamento_id))
        return permitido[e.usuario_id]

    elementos: list[dict[str, Any]] = []
    pendientes = 0
    for e in filas:
        if not puede(e):
            continue
        v = e.foto_veredicto or {}
        pendiente = necesita_revision(v) and not v.get("revision")
        pendientes += pendiente
        if (estado == "pendientes" and not pendiente) or (estado == "revisadas" and not v.get("revision")):
            continue
        if len(elementos) >= limite:
            continue
        u, t, ins = personas.get(e.usuario_id), tareas_.get(e.tarea_id), inss.get(e.instruccion_id)
        elementos.append({
            "id": e.id,
            "estado": e.estado,
            "inicio": e.inicio.isoformat() if e.inicio else None,
            "fin": e.fin.isoformat() if e.fin else None,
            "persona": {"id": u.id, "nombre": u.nombre} if u else None,
            "tarea": {"id": t.id, "codigo": t.codigo, "nombre": t.nombre} if t else None,
            "instruccion": {"codigo": ins.codigo, "version": ins.version} if ins else None,
            "pendiente": pendiente,
            "foto": veredicto_dict(e, ins, restringido=not actor.es_admin and e.tarea_id not in abre),
        })
    return {"elementos": elementos, "pendientes": pendientes}


# --------------------------------------------------------------------------- representación


def _paso_dict(p: Paso, ep: EjecucionPaso | None, numero: int, restringido: bool = False) -> dict[str, Any]:
    """Un paso con su estado en la ejecución. Con `restringido` solo el título y las métricas."""
    return {
        "id": p.id,
        "orden": p.orden,
        "numero": numero,
        "titulo": p.titulo,
        "texto": None if restringido else p.texto,
        "es_critico": p.es_critico,
        "es_seguridad": p.es_seguridad,
        "criterio_aceptacion": None if restringido else p.criterio_aceptacion,
        "imagen_url": None if restringido else url_fichero(p.imagen_ruta),
        "clip_url": None if restringido else url_fichero(p.clip_ruta),
        "confirmado": bool(ep and ep.confirmado_en),
        "confirmado_en": ep.confirmado_en.isoformat() if ep and ep.confirmado_en else None,
        "critico_confirmado": bool(ep and ep.critico_confirmado),
        "consultas": ep.consultas if ep else 0,
    }


def _numero(f: dict[str, Any], posicion: int) -> int:
    """Número de cita de una fuente guardada ([n] en la respuesta); si falta, su posición."""
    return f["n"] if isinstance(f.get("n"), int) else posicion


def _fuentes_para(bd: Session, actor: Actor,
                  consultas: list[Consulta]) -> tuple[dict[int, list[dict[str, Any]]], dict[int, set[int]]]:
    """Fuentes guardadas de cada consulta, vistas por quien mira ahora la ejecución.

    Las URLs guardadas caducan (se firmaron al preguntar) y pueden ser de documentos que quien
    mira no puede abrir (el jefe que revisa la ejecución de alguien que se forma en otro
    departamento). Se vuelven a firmar solo las de documentos que el actor puede ver; las demás
    se vacían, como si no existieran (igual que en la búsqueda).

    Devuelve también, por consulta, los números de las fuentes «ajenas»: documentos que existen
    pero quedan fuera del alcance de quien mira (otro departamento o más nivel). Un documento
    borrado o retirado (versión obsoleta de una instrucción) también se vacía, pero no es ajeno:
    no hay ninguna barrera que proteger en la respuesta (ver `_cita_ajena`).
    """
    guardadas = {c.id: [f for f in (c.fuentes or []) if isinstance(f, dict)] for c in consultas}
    ids = {f.get("documento_id") for lista in guardadas.values() for f in lista if f.get("documento_id")}
    docs = {d.id: d for d in bd.scalars(select(Documento).where(Documento.id.in_(ids)))} if ids else {}
    alcance = alcance_de(bd, actor) if docs else None
    salida: dict[int, list[dict[str, Any]]] = {}
    ajenas: dict[int, set[int]] = {}
    for cid, lista in guardadas.items():
        salida[cid] = []
        for i, f in enumerate(lista, start=1):
            d = docs.get(f.get("documento_id"))
            if d is not None and alcance is not None and puede_ver(alcance, d):
                salida[cid].append({**f, "url": url_fichero(d.ruta_fichero) if d.ruta_fichero else None,
                                    "disponible": True})
                continue
            salida[cid].append(_fuente_no_disponible(f))
            if d is not None and alcance is not None and not _en_alcance(alcance, d):
                ajenas.setdefault(cid, set()).add(_numero(f, i))
    return salida, ajenas


def _en_alcance(alcance: Alcance, d: Documento) -> bool:
    """¿Lo vería quien mira si el documento estuviera disponible? La misma regla de permisos.puede_ver,
    sin mirar su estado (un documento retirado no es de otro departamento)."""
    return puede_ver(alcance, Documento(estado="listo", es_publico=d.es_publico, departamento_id=d.departamento_id,
                                        es_formacion=d.es_formacion, nivel_minimo=d.nivel_minimo))


def _fuente_no_disponible(f: dict[str, Any]) -> dict[str, Any]:
    return {"n": f.get("n"), "documento_id": None, "titulo": "Documento no disponible", "fragmento": "",
            "url": None, "disponible": False}


def _cita_ajena(c: Consulta, fuentes: list[dict[str, Any]], ajenas: set[int]) -> bool:
    """¿Se apoya la respuesta en una fuente que quien mira no puede abrir?

    Esas fuentes se vacían (`_fuentes_para`), pero el texto del copiloto contaría igualmente lo
    que dicen: la jefa de Oficina técnica no debe leer, en la respuesta que recibió quien se forma
    con ella, lo que pone un documento de Producción. Se oculta si la respuesta cita alguna de ellas
    o si, sin citar ninguna, se dio por respaldada (no se sabe en qué fragmento se apoyó)."""
    if not ajenas:
        return False
    total = max((_numero(f, i) for i, f in enumerate(fuentes, start=1)), default=0)
    citas = set(consulta.citadas(c.respuesta or "", total))
    return bool(citas & ajenas) or (not citas and bool(c.con_respaldo))


def contenido_restringido(bd: Session, actor: Actor, ej: Ejecucion) -> bool:
    """¿Mira la ejecución alguien que la supervisa pero no puede abrir su tarea?

    Es el jefe de una persona que se forma en otro departamento: ve su avance (pasos confirmados,
    consultas por paso, tiempo, foto), pero el contenido de la instrucción y lo que respondió el
    copiloto son material de ese otro departamento (docs/arquitectura.md §4), así que no salen.
    """
    if ej.usuario_id == actor.id or actor.es_admin:
        return False
    return ej.tarea_id not in acceso_tareas(bd, actor)


def a_dict(bd: Session, ej: Ejecucion, actor: Actor) -> dict[str, Any]:
    """Ejecución completa: tarea, instrucción con pasos (imágenes y clips firmados) e historial."""
    ins = bd.get(Instruccion, ej.instruccion_id)
    tarea = bd.get(Tarea, ej.tarea_id)
    persona = bd.get(Usuario, ej.usuario_id)
    assert ins is not None and tarea is not None
    restringido = contenido_restringido(bd, actor, ej)
    estados = {ep.paso_id: ep for ep in ej.pasos}
    pasos = [_paso_dict(p, estados.get(p.id), i, restringido) for i, p in enumerate(ins.pasos, start=1)]
    hechos = sum(1 for p in pasos if p["confirmado"])
    actual = next((i for i, p in enumerate(pasos) if not p["confirmado"]), max(0, len(pasos) - 1))
    historial = list(bd.scalars(select(Consulta).where(Consulta.ejecucion_id == ej.id).order_by(Consulta.creada)))
    fuentes, ajenas = ({}, {}) if restringido else _fuentes_para(bd, actor, historial)

    def oculto(valor: Any) -> Any:
        return None if restringido else valor

    def respuesta_oculta(c: Consulta) -> bool:
        # La propia persona ve siempre lo que se le respondió; quien supervisa, solo lo que puede abrir.
        if not c.respuesta or ej.usuario_id == actor.id:
            return False
        return restringido or _cita_ajena(c, fuentes.get(c.id, []), ajenas.get(c.id, set()))

    return {
        "id": ej.id,
        "estado": ej.estado,
        "inicio": ej.inicio.isoformat() if ej.inicio else None,
        "fin": ej.fin.isoformat() if ej.fin else None,
        "duracion_s": _segundos(ej),
        "consultas": ej.consultas,
        "consultas_criticos": ej.consultas_criticos,
        "es_mia": ej.usuario_id == actor.id,
        "contenido_restringido": restringido,
        "persona": {"id": persona.id, "nombre": persona.nombre} if persona else None,
        "tarea": {"id": tarea.id, "codigo": tarea.codigo, "nombre": tarea.nombre, "riesgos_prl": oculto(tarea.riesgos_prl)},
        "instruccion": {
            "id": ins.id,
            "codigo": ins.codigo,
            "version": ins.version,
            "titulo": ins.titulo,
            "resumen": oculto(ins.resumen),
            "riesgos": oculto(ins.riesgos),
            "epis": oculto(ins.epis),
            "herramientas": oculto(ins.herramientas),
            "video_url": oculto(url_fichero(ins.video_ruta)),
            # La imagen con la que se comparará la foto del resultado (la misma regla que el servidor).
            "referencia_url": oculto(url_fichero(ref.imagen_ruta) if (ref := _paso_referencia(ins)) else None),
        },
        "pasos": pasos,
        "total_pasos": len(pasos),
        "pasos_confirmados": hechos,
        "paso_actual": actual,
        "foto": veredicto_dict(ej, ins, restringido),
        "puede_revisar": bool(ej.foto_ruta) and ej.estado in ESTADOS_REVISABLES and puede_revisar(bd, actor, ej),
        "historial": [
            {"id": c.id, "paso_id": c.paso_id, "pregunta": c.pregunta,
             "respuesta": None if (oculta := respuesta_oculta(c)) else c.respuesta, "respuesta_oculta": oculta,
             "fuentes": fuentes.get(c.id, []), "con_respaldo": c.con_respaldo, "creada": c.creada.isoformat()}
            for c in historial
        ],
    }
