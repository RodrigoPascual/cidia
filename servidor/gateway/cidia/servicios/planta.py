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
import mimetypes
from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from cidia import ficheros, xapi
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
from cidia.permisos import alcance_de, puede_ver
from cidia.seguridad import Actor, url_fichero
from cidia.servicios import iluo

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
                      exigir_tarea: bool = True) -> Ejecucion:
    """Ejecución con control de acceso.

    Leer: la propia persona y quien la supervisa (ver `_supervisa`).
    Escribir: solo la propia persona y, salvo para abandonarla (`exigir_tarea=False`), mientras
    siga teniendo acceso a la tarea (si se le cancela la formación, no puede seguir sumando
    evidencias). A quien no puede verla se le responde 404 (no se revela que existe).
    """
    ej = bd.get(Ejecucion, ejecucion_id) if id_valido(ejecucion_id) else None
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


def _paso_referencia(ins: Instruccion) -> Paso | None:
    """Imagen de referencia del resultado: la del último paso (o la última que haya)."""
    for p in reversed(ins.pasos):
        if p.imagen_ruta:
            return p
    return None


def _a_bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower().rstrip(".")
        if s in ("true", "si", "sí", "yes", "1", "coincide", "verdadero", "correcto"):
            return True
        if s in ("false", "no", "0", "no coincide", "falso", "incorrecto"):
            return False
    return None


def _veredicto_modelo(r: Any) -> dict[str, Any]:
    """Normaliza el JSON del modelo de visión: {coincide, observaciones, confianza}.

    Tolerante con los modelos pequeños: una lista con el objeto dentro, el objeto anidado en
    otra clave ({"resultado": {...}}) o el sí/no escrito como texto.
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
    try:
        confianza: float | None = float(r.get("confianza"))
        if confianza is not None and confianza > 1:
            confianza = confianza / 100
        confianza = max(0.0, min(1.0, confianza)) if confianza is not None else None
    except (TypeError, ValueError):
        confianza = None
    observaciones = str(r.get("observaciones") or "").strip()[:600]
    return {"coincide": coincide, "observaciones": observaciones, "confianza": confianza}


def comparar_foto(bd: Session, ruta_foto: str, referencia: Paso | None) -> dict[str, Any]:
    """Compara la foto con la imagen del experto si hay un modelo con visión permitido.

    El resultado es siempre orientativo: decide una persona (revision_humana = True).
    """
    base: dict[str, Any] = {"revision_humana": True, "coincide": None, "observaciones": "", "confianza": None,
                            "modelo": None, "referencia_paso_id": referencia.id if referencia else None}
    modelo = llm.modelo_vision(bd)
    if not modelo:
        return {**base, "estado": "sin_vision",
                "mensaje": "Este servidor no tiene un modelo con visión. La foto queda guardada y la revisará una persona."}
    if referencia is None or not referencia.imagen_ruta:
        return {**base, "estado": "sin_referencia",
                "mensaje": "La instrucción no tiene imagen de referencia del experto. La foto queda guardada y la "
                           "revisará una persona."}
    try:
        ref = ficheros.ruta_absoluta(referencia.imagen_ruta)
        foto = ficheros.ruta_absoluta(ruta_foto)
        criterio = (referencia.criterio_aceptacion or "").strip()
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
    return {**base, **v, "estado": "comparada", "modelo": modelo, "mensaje": mensaje}


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


def guardar_foto(bd: Session, actor: Actor, ej: Ejecucion, subida: UploadFile) -> dict[str, Any]:
    """Guarda la foto del resultado y la compara con la referencia. Devuelve el veredicto."""
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
    veredicto = comparar_foto(bd, ruta, _paso_referencia(ins))
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
    return v


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


def _fuentes_para(bd: Session, actor: Actor, consultas: list[Consulta]) -> dict[int, list[dict[str, Any]]]:
    """Fuentes guardadas de cada consulta, vistas por quien mira ahora la ejecución.

    Las URLs guardadas caducan (se firmaron al preguntar) y pueden ser de documentos que quien
    mira no puede abrir (el jefe que revisa la ejecución de alguien que se forma en otro
    departamento). Se vuelven a firmar solo las de documentos que el actor puede ver; las demás
    se vacían, como si no existieran (igual que en la búsqueda).
    """
    guardadas = {c.id: [f for f in (c.fuentes or []) if isinstance(f, dict)] for c in consultas}
    ids = {f.get("documento_id") for lista in guardadas.values() for f in lista if f.get("documento_id")}
    docs = {d.id: d for d in bd.scalars(select(Documento).where(Documento.id.in_(ids)))} if ids else {}
    alcance = alcance_de(bd, actor) if docs else None
    salida: dict[int, list[dict[str, Any]]] = {}
    for cid, lista in guardadas.items():
        salida[cid] = []
        for f in lista:
            d = docs.get(f.get("documento_id"))
            if d is not None and alcance is not None and puede_ver(alcance, d):
                salida[cid].append({**f, "url": url_fichero(d.ruta_fichero) if d.ruta_fichero else None,
                                    "disponible": True})
            else:
                salida[cid].append(_fuente_no_disponible(f))
    return salida


def _fuente_no_disponible(f: dict[str, Any]) -> dict[str, Any]:
    return {"n": f.get("n"), "documento_id": None, "titulo": "Documento no disponible", "fragmento": "",
            "url": None, "disponible": False}


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
    fuentes = {} if restringido else _fuentes_para(bd, actor, historial)

    def oculto(valor: Any) -> Any:
        return None if restringido else valor

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
        },
        "pasos": pasos,
        "total_pasos": len(pasos),
        "pasos_confirmados": hechos,
        "paso_actual": actual,
        "foto": veredicto_dict(ej, ins, restringido),
        "historial": [
            {"id": c.id, "paso_id": c.paso_id, "pregunta": c.pregunta, "respuesta": oculto(c.respuesta),
             "fuentes": fuentes.get(c.id, []), "con_respaldo": c.con_respaldo, "creada": c.creada.isoformat()}
            for c in historial
        ],
    }
