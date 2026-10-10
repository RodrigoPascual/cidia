"""Formación: itinerario de cada persona y micro-lecciones generadas desde las instrucciones.

El itinerario reúne las tareas de su puesto (si no tiene puesto, las de su departamento que su
nivel alcanza), las de los puestos de sus formaciones activas y las de su departamento en las
que ya tiene nivel. De cada una calcula el nivel ILUO, el avance y la siguiente acción.

Avance (camino hasta la autonomía, nivel U): micro-lecciones vistas 25 %, cuestionario
aprobado de la versión vigente 25 %, ejecuciones completadas 30 % y observación aprobada 20 %
(sin micro-lecciones: 0/35/40/25). Con nivel U u O el avance es 100 %.

Las micro-lecciones (entre 3 y 6) las escribe el LLM a partir de los pasos de la instrucción
publicada. Con modelos pequeños el JSON puede fallar, el modelo puede saltarse un paso crítico
o repetir la misma frase y la misma pregunta en todas las lecciones: entonces se quitan las
repeticiones y se completa con el propio texto de los pasos y con preguntas de control
construidas a partir de ellos (ver `generar_microlecciones`).
"""

from __future__ import annotations

import logging
import math
import random
import re
import unicodedata
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from cidia import trabajos, xapi
from cidia.ia import llm
from cidia.modelos import (
    Ejecucion,
    Empresa,
    Formacion,
    Instruccion,
    IntentoEval,
    Microleccion,
    MicroleccionVista,
    NivelIluo,
    Observacion,
    Paso,
    PreguntaEval,
    Puesto,
    SentenciaXapi,
    Tarea,
    Trabajo,
)
from cidia.seguridad import Actor, url_fichero
from cidia.servicios import iluo, planta

log = logging.getLogger("cidia.formacion")

CONFIG_ILUO = {"ejecuciones_para_L": 3, "umbral_cuestionario": 0.8, "meses_validez": 12}
MAX_LECCIONES = 6  # el encargo pide entre 3 y 6 micro-lecciones por instrucción


def config_iluo(bd: Session) -> dict[str, Any]:
    """Reglas ILUO de la empresa (la misma fila que lee servicios/iluo.py) sobre los valores por defecto."""
    c = dict(CONFIG_ILUO)
    e = bd.scalar(select(Empresa).order_by(Empresa.id).limit(1))
    if e and isinstance(e.config_iluo, dict):
        c.update({k: v for k, v in e.config_iluo.items() if v is not None})
    return c


def objetivo_ejecuciones(bd: Session) -> int:
    """Ejecuciones completadas que pide el nivel L. Un valor mal guardado no rompe el itinerario."""
    try:
        return max(1, int(config_iluo(bd).get("ejecuciones_para_L")))
    except (TypeError, ValueError):
        return CONFIG_ILUO["ejecuciones_para_L"]


# --------------------------------------------------------------------------- itinerario


def _tareas_itinerario(bd: Session, actor: Actor) -> list[tuple[Tarea, dict[str, Any]]]:
    """Tareas del itinerario con su origen: [(tarea, {"origen", "formacion_id"})]."""
    u = actor.usuario
    if u is None:
        return []
    acceso = planta.acceso_tareas(bd, actor)
    formaciones = bd.scalars(
        select(Formacion).where(Formacion.usuario_id == u.id, Formacion.estado == "activa")
    ).all()
    con_nivel = set(bd.scalars(select(NivelIluo.tarea_id).where(NivelIluo.usuario_id == u.id, NivelIluo.nivel > 0)))
    filas = bd.scalars(
        select(Tarea).where(Tarea.id.in_(list(acceso) or [0]))
        .options(selectinload(Tarea.puesto).selectinload(Puesto.departamento))
    ).all()
    salida: list[tuple[Tarea, dict[str, Any]]] = []
    for t in filas:
        info = acceso[t.id]
        de_su_puesto = t.puesto_id == u.puesto_id if u.puesto_id else (
            t.puesto is not None and t.puesto.departamento_id == u.departamento_id
        )
        if info["origen"] == "formacion":
            pass  # siempre: es lo que la persona está aprendiendo
        elif info["origen"] in ("puesto", "departamento", "admin") and de_su_puesto:
            info = {**info, "origen": "puesto"}
        else:
            # Otras tareas del departamento (o todas, para la administración) solo si ya tiene nivel,
            # salvo que una formación activa las cubra (la de ese puesto o, sin puesto, la del departamento).
            dep = t.puesto.departamento_id if t.puesto is not None else None
            form = next((f for f in formaciones
                         if (f.puesto_id == t.puesto_id if f.puesto_id else f.departamento_id == dep)), None)
            if form is not None:
                info = {"origen": "formacion", "formacion_id": form.id}
            elif t.id not in con_nivel:
                continue
        salida.append((t, info))
    return salida


def _avance(total_ml: int, vistas: int, cuestionario: bool, ejecuciones: int, objetivo: int,
            observada: bool, nivel: int, hay_instruccion: bool) -> int:
    if nivel >= 3:
        return 100
    if not hay_instruccion:
        return 0
    objetivo = max(1, objetivo)
    partes: list[tuple[float, float]] = []
    if total_ml:
        partes += [(0.25, vistas / total_ml), (0.25, float(cuestionario)), (0.30, min(ejecuciones, objetivo) / objetivo),
                   (0.20, float(observada))]
    else:
        partes += [(0.35, float(cuestionario)), (0.40, min(ejecuciones, objetivo) / objetivo), (0.25, float(observada))]
    return round(100 * sum(peso * valor for peso, valor in partes))


def _siguiente(tarea_id: int, ins: Instruccion | None, n: dict[str, Any], mls: list[Microleccion], vistas: set[int],
               cuestionario: bool, hay_preguntas: bool, ejecuciones: int, objetivo: int,
               observada: bool) -> dict[str, Any]:
    """Siguiente acción recomendada para avanzar en la tarea."""
    ruta = f"/formacion/tarea/{tarea_id}"
    nivel = n["nivel"]
    if ins is None:
        return {"accion": "esperar", "texto": "Aún no hay instrucción publicada. Aparecerá aquí cuando el experto la publique.",
                "ruta": ruta}
    if n["requiere_reevaluacion"]:
        return {"accion": "reevaluar", "ruta": ruta,
                "texto": f"Hay una versión nueva (v{ins.version}): repasa los cambios y vuelve a hacer el cuestionario."}
    if n["caducado"]:
        return {"accion": "renovar", "ruta": ruta, "texto": "Tu nivel ha caducado: repasa la tarea y vuelve a evaluarte."}
    pendiente = next((m for m in mls if m.id not in vistas), None)
    if pendiente is not None:
        return {"accion": "microleccion", "ruta": ruta, "microleccion_id": pendiente.id,
                "texto": f"Micro-lección {pendiente.orden}: {pendiente.titulo}"}
    if not cuestionario and hay_preguntas:
        return {"accion": "cuestionario", "ruta": f"/evaluacion?tarea={tarea_id}", "texto": "Haz el cuestionario de evaluación."}
    if ejecuciones < objetivo:
        return {"accion": "practicar", "ruta": ruta,
                "texto": f"Practica en modo planta: llevas {ejecuciones} de {objetivo} ejecuciones."}
    if not cuestionario:
        return {"accion": "esperar_cuestionario", "ruta": ruta,
                "texto": "El cuestionario está pendiente de aprobación por el experto."}
    if nivel < 3 and not observada:
        return {"accion": "observacion", "ruta": ruta, "texto": "Pide a tu supervisor la observación en el puesto."}
    if nivel < 3:
        return {"accion": "practicar", "ruta": ruta,
                "texto": "Haz una ejecución sin consultar al copiloto en los pasos críticos."}
    if nivel == 3:
        return {"accion": "formador", "ruta": ruta,
                "texto": "Ya eres autónomo. Pide a tu jefe o al experto la validación como formador."}
    return {"accion": "completo", "ruta": ruta, "texto": "Nivel máximo: puedes formar a otras personas."}


def _calcular(bd: Session, actor: Actor, tareas: list[tuple[Tarea, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Estado de formación de cada tarea (consultas agrupadas para no hacer una por tarea)."""
    if not tareas:
        return []
    uid = actor.id
    ids = [t.id for t, _ in tareas]
    vigentes = planta.instrucciones_vigentes(bd, ids)
    ins_ids = [i.id for i in vigentes.values()] or [0]
    niv = planta.niveles(bd, uid, ids)
    objetivo = objetivo_ejecuciones(bd)

    mls: dict[int, list[Microleccion]] = {}
    for m in bd.scalars(select(Microleccion).where(Microleccion.instruccion_id.in_(ins_ids)).order_by(Microleccion.orden)):
        mls.setdefault(m.instruccion_id, []).append(m)
    todas = [m.id for lista in mls.values() for m in lista] or [0]
    vistas = set(bd.scalars(select(MicroleccionVista.microleccion_id).where(
        MicroleccionVista.usuario_id == uid, MicroleccionVista.microleccion_id.in_(todas))))
    preguntas = dict(bd.execute(
        select(PreguntaEval.instruccion_id, func.count()).where(
            PreguntaEval.instruccion_id.in_(ins_ids), PreguntaEval.estado == "aprobada")
        .group_by(PreguntaEval.instruccion_id)).all())
    aprobados = set(bd.scalars(select(IntentoEval.instruccion_id).where(
        IntentoEval.usuario_id == uid, IntentoEval.instruccion_id.in_(ins_ids), IntentoEval.aprobado.is_(True))))
    ejecuciones = dict(bd.execute(
        select(Ejecucion.tarea_id, func.count()).where(
            Ejecucion.usuario_id == uid, Ejecucion.tarea_id.in_(ids), Ejecucion.estado == "completada")
        .group_by(Ejecucion.tarea_id)).all())
    observadas = set(bd.scalars(select(Observacion.tarea_id).where(
        Observacion.usuario_id == uid, Observacion.tarea_id.in_(ids), Observacion.aprobada.is_(True))))
    formaciones = {f.id: f for f in bd.scalars(select(Formacion).where(Formacion.usuario_id == uid))}

    salida: list[dict[str, Any]] = []
    for t, info in tareas:
        ins = vigentes.get(t.id)
        lista = mls.get(ins.id, []) if ins else []
        n = planta.nivel_dict(niv.get(t.id))
        vistas_t = sum(1 for m in lista if m.id in vistas)
        cuestionario = bool(ins and ins.id in aprobados)
        hay_preguntas = bool(ins and preguntas.get(ins.id))
        ejec = ejecuciones.get(t.id, 0)
        observada = t.id in observadas
        f = formaciones.get(info.get("formacion_id") or 0)
        salida.append({
            "tarea_id": t.id,
            "codigo": t.codigo,
            "nombre": t.nombre,
            "descripcion": t.descripcion,
            "criticidad": t.criticidad,
            "puesto": t.puesto.nombre if t.puesto else None,
            "departamento": t.puesto.departamento.nombre if t.puesto and t.puesto.departamento else None,
            "origen": info["origen"],
            "formacion": {
                "id": f.id, "departamento": f.departamento.nombre, "puesto": f.puesto.nombre if f.puesto else None,
                "inicio": f.inicio.isoformat() if f.inicio else None,
                "fin_previsto": f.fin_previsto.isoformat() if f.fin_previsto else None,
            } if f else None,
            **n,
            "tiene_instruccion": ins is not None,
            "instruccion": {"id": ins.id, "codigo": ins.codigo, "version": ins.version, "titulo": ins.titulo,
                            "pasos": len(ins.pasos), "pasos_criticos": sum(1 for p in ins.pasos if p.es_critico)}
            if ins else None,
            "microlecciones": {"total": len(lista), "vistas": vistas_t},
            "cuestionario": {"disponible": hay_preguntas, "aprobado": cuestionario},
            "ejecuciones": {"completadas": ejec, "objetivo": objetivo},
            "observacion_aprobada": observada,
            "avance": _avance(len(lista), vistas_t, cuestionario, ejec, objetivo, observada, n["nivel"], ins is not None),
            "siguiente": _siguiente(t.id, ins, n, lista, vistas, cuestionario, hay_preguntas, ejec, objetivo, observada),
        })
    return salida


def itinerario(bd: Session, actor: Actor) -> list[dict[str, Any]]:
    """Tareas del itinerario de la persona con nivel ILUO, avance y siguiente acción."""
    datos = _calcular(bd, actor, _tareas_itinerario(bd, actor))
    orden = {"puesto": 0, "formacion": 1, "departamento": 2, "admin": 3}
    datos.sort(key=lambda d: (orden.get(d["origen"], 9), not d["tiene_instruccion"], d["nivel"] >= 3,
                              (d["codigo"] or "~").lower(), d["nombre"].lower()))
    return datos


def formaciones_activas(bd: Session, actor: Actor, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Formaciones activas de la persona con el avance medio de sus tareas."""
    filas = bd.scalars(select(Formacion).where(Formacion.usuario_id == actor.id, Formacion.estado == "activa")
                       .order_by(Formacion.inicio)).all()
    salida = []
    for f in filas:
        suyas = [i for i in items if i["formacion"] and i["formacion"]["id"] == f.id]
        salida.append({
            "id": f.id,
            "departamento": f.departamento.nombre,
            "puesto": f.puesto.nombre if f.puesto else None,
            "otro_departamento": f.departamento_id != actor.departamento_id,
            "inicio": f.inicio.isoformat() if f.inicio else None,
            "fin_previsto": f.fin_previsto.isoformat() if f.fin_previsto else None,
            "tareas": len(suyas),
            "avance": round(sum(i["avance"] for i in suyas) / len(suyas)) if suyas else 0,
        })
    return salida


# --------------------------------------------------------------------------- detalle de una tarea


def _ultimo_trabajo(bd: Session, instruccion_id: int) -> Trabajo | None:
    return bd.scalar(select(Trabajo).where(
        Trabajo.tipo == "microlecciones", Trabajo.entidad == "instruccion", Trabajo.entidad_id == instruccion_id
    ).order_by(Trabajo.id.desc()).limit(1))


def puede_generar(bd: Session, actor: Actor, tarea: Tarea) -> bool:
    """Expertos y jefes del departamento de la tarea (y la administración)."""
    if not actor.es_experto:
        return False
    if actor.es_admin:
        return True
    puesto = bd.get(Puesto, tarea.puesto_id)
    return puesto is not None and puesto.departamento_id == actor.departamento_id


def detalle_tarea(bd: Session, actor: Actor, tarea_id: int) -> dict[str, Any]:
    """Formación de una tarea: instrucción resumida, micro-lecciones y estado de evaluación."""
    tarea, info = planta.exigir_acceso(bd, actor, tarea_id)
    origen = next((i for t, i in _tareas_itinerario(bd, actor) if t.id == tarea.id), info)
    item = _calcular(bd, actor, [(tarea, origen)])[0]
    ins = planta.instruccion_vigente(bd, tarea.id)

    lecciones: list[dict[str, Any]] = []
    generacion = None
    gestiona = puede_generar(bd, actor, tarea)
    evaluacion: dict[str, Any] = {**item["cuestionario"], "intentos": 0, "ultimo": None}
    if ins is not None:
        mls = bd.scalars(select(Microleccion).where(Microleccion.instruccion_id == ins.id)
                         .order_by(Microleccion.orden)).all()
        vistas = set(bd.scalars(select(MicroleccionVista.microleccion_id).where(
            MicroleccionVista.usuario_id == actor.id,
            MicroleccionVista.microleccion_id.in_([m.id for m in mls] or [0]))))
        lecciones = [{
            "id": m.id,
            "orden": m.orden,
            "titulo": m.titulo,
            "contenido": m.contenido,
            "punto_clave": m.punto_clave,
            # La respuesta correcta no sale del servidor: se comprueba con /responder.
            "pregunta": {"enunciado": q["enunciado"], "opciones": q["opciones"]}
            if (q := pregunta_guardada(m.pregunta)) else None,
            "vista": m.id in vistas,
        } for m in mls]
        t = _ultimo_trabajo(bd, ins.id)
        if t is not None:
            # El mensaje de un trabajo fallido es técnico (errores del modelo): solo para quien puede regenerar.
            generacion = {"trabajo_id": t.id, "estado": t.estado, "mensaje": t.mensaje if gestiona else None}
        intentos = bd.scalars(select(IntentoEval).where(
            IntentoEval.usuario_id == actor.id, IntentoEval.instruccion_id == ins.id
        ).order_by(IntentoEval.creado.desc())).all()
        evaluacion["intentos"] = len(intentos)
        if intentos:
            u = intentos[0]
            evaluacion["ultimo"] = {"puntuacion": u.puntuacion, "aprobado": u.aprobado, "aciertos": u.aciertos,
                                    "total": u.total, "creado": u.creado.isoformat()}

    return {
        **item,
        "riesgos_prl": tarea.riesgos_prl,
        "instruccion": {
            "id": ins.id,
            "codigo": ins.codigo,
            "version": ins.version,
            "titulo": ins.titulo,
            "resumen": ins.resumen,
            "riesgos": ins.riesgos,
            "epis": ins.epis,
            "herramientas": ins.herramientas,
            "publicada_en": ins.publicada_en.isoformat() if ins.publicada_en else None,
            "video_url": url_fichero(ins.video_ruta),
            "pasos": [{"id": p.id, "numero": i, "titulo": p.titulo, "es_critico": p.es_critico,
                       "es_seguridad": p.es_seguridad, "imagen_url": url_fichero(p.imagen_ruta)}
                      for i, p in enumerate(ins.pasos, start=1)],
        } if ins else None,
        "lecciones": lecciones,
        "evaluacion": evaluacion,
        "puede_generar": gestiona,
        "generacion": generacion,
    }


# --------------------------------------------------------------------------- uso de micro-lecciones


def pregunta_guardada(p: Any) -> dict[str, Any] | None:
    """Pregunta de control de una micro-lección leída con cuidado: {enunciado, opciones, correcta,
    explicacion}, o None si no tiene una utilizable. Una fila escrita a mano, por la semilla o por
    una versión anterior con otra forma no debe romper la página de la tarea (sería un error 500):
    se trata como una micro-lección sin pregunta."""
    if not isinstance(p, dict) or not isinstance(p.get("opciones"), list):
        return None
    opciones = [_texto(o.get("texto") if isinstance(o, dict) else o) for o in p["opciones"]]
    enunciado = _texto(p.get("enunciado"))
    correcta = _indice_correcta(p.get("correcta"), opciones)
    if not enunciado or len(opciones) < 2 or not all(opciones) or correcta is None or not 0 <= correcta < len(opciones):
        return None
    return {"enunciado": enunciado, "opciones": opciones, "correcta": correcta, "explicacion": _texto(p.get("explicacion"))}


def _microleccion_accesible(bd: Session, actor: Actor, microleccion_id: int) -> tuple[Microleccion, Instruccion]:
    """Micro-lección de una instrucción publicada (o ya obsoleta) de una tarea que la persona puede
    abrir. Las de un borrador no existen para nadie: 404 igual que si no existiera."""
    m = bd.get(Microleccion, microleccion_id) if planta.id_valido(microleccion_id) else None
    ins = bd.get(Instruccion, m.instruccion_id) if m else None
    if m is None or ins is None or ins.estado not in ("publicada", "obsoleta"):
        raise HTTPException(404, "No encontramos esa micro-lección.")
    if ins.tarea_id not in planta.acceso_tareas(bd, actor):
        raise HTTPException(404, "No encontramos esa micro-lección.")
    return m, ins


def marcar_vista(bd: Session, actor: Actor, microleccion_id: int) -> dict[str, Any]:
    """Registra que la persona ha visto la micro-lección (xAPI «vio») y recalcula su nivel."""
    m, ins = _microleccion_accesible(bd, actor, microleccion_id)
    ya = bd.scalar(select(MicroleccionVista).where(
        MicroleccionVista.usuario_id == actor.id, MicroleccionVista.microleccion_id == m.id))
    nueva = False
    if ya is None:
        try:
            # Punto de guardado: si llegan dos «vista» a la vez, la segunda choca con la restricción única.
            with bd.begin_nested():
                bd.add(MicroleccionVista(usuario_id=actor.id, microleccion_id=m.id))
                bd.flush()
            nueva = True
        except IntegrityError:
            nueva = False
    if nueva:
        xapi.registrar(bd, actor, "vio", "microleccion", m.id, m.titulo, resultado={"completion": True},
                       contexto={"tarea_id": ins.tarea_id, "instruccion_id": ins.id, "version": ins.version,
                                 "orden": m.orden})
        bd.flush()
        iluo.recalcular(bd, actor.id, ins.tarea_id)
    ids = list(bd.scalars(select(Microleccion.id).where(Microleccion.instruccion_id == ins.id)))
    vistas = bd.scalar(select(func.count()).select_from(MicroleccionVista).where(
        MicroleccionVista.usuario_id == actor.id, MicroleccionVista.microleccion_id.in_(ids or [0]))) or 0
    nivel = bd.scalar(select(NivelIluo).where(NivelIluo.usuario_id == actor.id, NivelIluo.tarea_id == ins.tarea_id))
    return {"vista": True, "vistas": vistas, "total": len(ids), **planta.nivel_dict(nivel)}


FALLOS_PARA_REVELAR = 2  # la respuesta correcta se enseña al acertar o tras el segundo fallo


def responder(bd: Session, actor: Actor, microleccion_id: int, opcion: int) -> dict[str, Any]:
    """Comprueba la pregunta de control de una micro-lección y devuelve el feedback.

    La respuesta correcta (y la explicación, que suele delatarla) solo sale del servidor al
    acertar o a partir del segundo fallo; después del primero solo se dice que no es esa, para
    que la persona vuelva a intentarlo. Los fallos se cuentan con las sentencias xAPI «respondio».
    """
    m, ins = _microleccion_accesible(bd, actor, microleccion_id)
    p = pregunta_guardada(m.pregunta)
    if p is None:
        raise HTTPException(400, "Esta micro-lección no tiene pregunta de control.")
    opciones = p["opciones"]
    if not 0 <= opcion < len(opciones):
        raise HTTPException(400, "Elige una de las opciones.")
    correcta = p["correcta"]
    acierto = opcion == correcta
    fallos = 0 if acierto else 1 + (bd.scalar(
        select(func.count()).select_from(SentenciaXapi).where(
            SentenciaXapi.actor_id == actor.id, SentenciaXapi.verbo == "respondio",
            SentenciaXapi.objeto_tipo == "microleccion", SentenciaXapi.objeto_id == str(m.id),
            SentenciaXapi.resultado["success"].astext == "false",
        )) or 0)
    xapi.registrar(bd, actor, "respondio", "microleccion", m.id, m.titulo,
                   resultado={"success": acierto, "response": opciones[opcion]},
                   contexto={"tarea_id": ins.tarea_id, "instruccion_id": ins.id, "pregunta": "control"})
    revelar = acierto or fallos >= FALLOS_PARA_REVELAR
    return {
        "correcta": acierto,
        "opcion_correcta": correcta if revelar else None,
        "explicacion": p["explicacion"] if revelar else "",
        "revelada": revelar,
    }


# --------------------------------------------------------------------------- generación de micro-lecciones

_SISTEMA = (
    "Eres formador de operarios en una planta industrial. Escribes en castellano de España, claro y directo, "
    "para personas que están aprendiendo un puesto. Usas solo la información que te dan. Respondes SOLO con JSON válido."
)

_FORMATO = (
    '{"microlecciones": [{"titulo": "...", "contenido": "...", "punto_clave": "...", '
    '"pregunta": {"enunciado": "...", "opciones": ["...", "...", "..."], "correcta": 0, "explicacion": "..."}}]}'
)


_PREFIJO_TITULO = re.compile(r"^\s*(micro-?\s*)?lecci[oó]n\s*\d+\s*[:.\-–]\s*", re.I)


def _texto(v: Any) -> str:
    return re.sub(r"[ \t]+", " ", str(v)).strip() if isinstance(v, (str, int, float)) else ""


def _recortar_palabras(texto: str, maximo: int) -> str:
    palabras = texto.split(" ")
    return texto if len(palabras) <= maximo else " ".join(palabras[:maximo]).rstrip(",;:") + "…"


def _texto_pasos(ins: Instruccion) -> str:
    lineas = []
    for i, p in enumerate(ins.pasos, start=1):
        linea = f"{i}. {p.titulo}"
        if p.es_critico:
            linea += " [PASO CRÍTICO]"
        if p.es_seguridad:
            linea += " [SEGURIDAD]"
        if p.texto:
            linea += f"\n   {p.texto.strip()[:600]}"
        if p.criterio_aceptacion:
            linea += f"\n   Criterio de aceptación: {p.criterio_aceptacion.strip()[:300]}"
        lineas.append(linea)
    return "\n".join(lineas)[:7000]


def _mensajes(ins: Instruccion) -> list[dict[str, Any]]:
    cabecera = f"Instrucción: {ins.codigo or ''} versión {ins.version} · {ins.titulo}".strip()
    extra = "".join(f"\n{k}: {v.strip()[:500]}" for k, v in (
        ("Resumen", ins.resumen), ("Riesgos", ins.riesgos), ("EPI", ins.epis), ("Herramientas", ins.herramientas)
    ) if v)
    texto = (
        "Crea entre 3 y 6 micro-lecciones para aprender esta instrucción de trabajo. "
        "Cada micro-lección se lee en un minuto.\n\n"
        f"{cabecera}{extra}\n\nPasos:\n{_texto_pasos(ins)}\n\n"
        "Reglas:\n"
        "- Cada micro-lección agrupa pasos seguidos y explica qué se hace y por qué.\n"
        '- "contenido": entre 80 y 150 palabras, en markdown sencillo (frases cortas, alguna lista).\n'
        '- "punto_clave": una frase con lo que no se puede olvidar; si hay un paso crítico, menciónalo.\n'
        '- "pregunta": pregunta de control con 3 opciones y una sola correcta; "correcta" es su posición (0, 1 o 2).\n'
        "- No inventes datos que no estén en la instrucción (pares, medidas, referencias).\n\n"
        f"Formato exacto:\n{_FORMATO}"
    )
    return [{"role": "system", "content": _SISTEMA}, {"role": "user", "content": texto}]


_NEGACIONES = {"no", "nunca", "ni", "jamas", "tampoco"}


def _afirma(explicacion: str, opcion: str) -> bool | None:
    """¿Cómo nombra la explicación esta opción? None: no la nombra; True: al menos una vez sin
    negarla; False: solo para negarla («no se aprietan en círculo»). Palabras completas, sin tildes."""
    texto, frase = _sin_tildes(explicacion), _sin_tildes(opcion).strip()
    menciones = list(re.finditer(rf"(?<!\w){re.escape(frase)}(?!\w)", texto)) if frase else []
    if not menciones:
        return None
    return any(not _NEGACIONES & set(re.findall(r"\w+", texto[:m.start()])[-3:]) for m in menciones)


def _corregir_por_explicacion(opciones: list[str], idx: int, explicacion: str) -> int:
    """Los modelos pequeños a veces marcan una posición y explican otra («correcta»: la pulsera;
    «explicacion»: la llave dinamométrica). Si la explicación afirma una sola opción y no habla de
    la marcada, manda la explicación: así la corrección y su explicación no se contradicen.

    Con cuidado de no estropear una pregunta buena: las opciones muy cortas («Sí», «No») no se
    pueden comprobar, y una opción nombrada para negarla («no en círculo») no cuenta.
    """
    if not explicacion or len(opciones[idx]) < 3:
        return idx
    afirmadas = [i for i, o in enumerate(opciones) if len(o) >= 3 and _afirma(explicacion, o)]
    if len(afirmadas) == 1 and afirmadas[0] != idx and not _afirma(explicacion, opciones[idx]):
        return afirmadas[0]
    return idx


LETRAS = "ABCDEF"
# «A) En cruz», «b. En círculo», «C: Da igual» o «1) Aflojar»: la interfaz ya pone su letra a cada
# opción. Con números no vale el guion («1 - 2 bar» es un dato, no una numeración).
_PREFIJO_OPCION = re.compile(r"^\s*(?:([A-Fa-f])\s*[).:\-]|([1-6])\s*[).:])\s+")


def _sin_prefijos(opciones: list[str]) -> list[str]:
    """Quita la numeración que ponen los modelos («A) ...»), solo si todas las opciones la llevan y en
    orden (A, B, C... o 1, 2, 3...): así no se toca una opción que empieza por «A mano»."""
    marcas = [_PREFIJO_OPCION.match(o) for o in opciones]
    if not all(marcas):
        return opciones
    vistas = [(m.group(1) or m.group(2) or "").upper() for m in marcas if m]
    if vistas not in (list(LETRAS[:len(opciones)]), [str(i) for i in range(1, len(opciones) + 1)]):
        return opciones
    limpias = [o[m.end():].strip() for o, m in zip(opciones, marcas) if m]
    return limpias if all(limpias) else opciones


def _indice_correcta(c: Any, opciones: list[str]) -> int | None:
    """Posición de la opción correcta tal como la escriba el modelo: 1, 1.0, «1», «B», «b)», «B) En
    círculo» o el propio texto de la opción."""
    if isinstance(c, bool):
        return None
    if isinstance(c, float) and c.is_integer():
        c = int(c)
    if isinstance(c, int):
        return c
    if not isinstance(c, str):
        return None
    s = c.strip()
    if s.isdigit():
        return int(s)
    if len(s) == 1 and s.upper() in LETRAS:
        return LETRAS.index(s.upper())
    exacta = next((i for i, o in enumerate(opciones) if _clave(o) == _clave(s)), None)
    if exacta is not None:
        return exacta
    m = re.match(r"^\s*([A-Fa-f])\s*[).:\-](?:\s|$)", s)
    return LETRAS.index(m.group(1).upper()) if m else None


def _normalizar_pregunta(p: Any) -> dict[str, Any] | None:
    """Pregunta de control válida con exactamente 3 opciones distintas, o None."""
    if not isinstance(p, dict) or not isinstance(p.get("opciones"), list):
        return None
    enunciado = _texto(p.get("enunciado") or p.get("pregunta"))
    # Los modelos pequeños a veces devuelven opciones como objetos: {"texto": ..., "correcta": true}.
    opciones: list[str] = []
    marcada: int | None = None
    for x in p["opciones"]:
        if isinstance(x, dict):
            if x.get("correcta") is True:
                marcada = len(opciones)
            x = x.get("texto") or x.get("opcion") or x.get("text")
        o = _texto(x)
        if o:
            opciones.append(o)
    if not enunciado or len(opciones) < 3:
        return None
    opciones = _sin_prefijos(opciones)
    idx = marcada if marcada is not None else _indice_correcta(p.get("correcta"), opciones)
    if idx is None or not 0 <= idx < len(opciones):
        return None
    explicacion = _texto(p.get("explicacion"))
    idx = _corregir_por_explicacion(opciones, idx, explicacion)
    correcta = opciones[idx]
    if len(opciones) > 3:  # quedarse con 3 opciones conservando la correcta en su sitio relativo
        otras = [o for i, o in enumerate(opciones) if i != idx][:2]
        pos = min(idx, 2)
        opciones = otras[:pos] + [correcta] + otras[pos:]
        idx = pos
    if len({o.lower() for o in opciones}) < 3:
        return None
    return {"enunciado": enunciado[:500], "opciones": [o[:300] for o in opciones], "correcta": idx,
            "explicacion": explicacion[:600]}


def _normalizar_lecciones(datos: Any) -> list[dict[str, Any]]:
    """Lecciones válidas del JSON del modelo (tolerante con claves y formatos parecidos)."""
    if isinstance(datos, dict) and "titulo" in datos and "contenido" in datos:
        datos = [datos]  # una sola lección, sin la lista alrededor
    elif isinstance(datos, dict):
        datos = datos.get("microlecciones") or datos.get("micro_lecciones") or datos.get("lecciones") or next(
            (v for v in datos.values() if isinstance(v, list)), None)
    if not isinstance(datos, list):
        return []
    salida = []
    for d in datos:
        if not isinstance(d, dict):
            continue
        titulo = _PREFIJO_TITULO.sub("", _texto(d.get("titulo")))[:300]
        bruto = d.get("contenido")
        if isinstance(bruto, list):  # a veces llega como lista de frases: se convierte en lista markdown
            bruto = "\n".join(f"- {_texto(x)}" for x in bruto if _texto(x))
        contenido = bruto.strip() if isinstance(bruto, str) else ""
        if not titulo or len(contenido.split()) < 8:
            continue
        salida.append({
            "titulo": titulo,
            "contenido": _recortar_palabras(contenido, 220),
            "punto_clave": _texto(d.get("punto_clave"))[:500] or None,
            "pregunta": _normalizar_pregunta(d.get("pregunta")),
        })
    return salida[:MAX_LECCIONES]


def _grupos(pasos: list[Paso]) -> list[list[tuple[int, Paso]]]:
    """Reparte los pasos (numerados desde 1) en 3-6 grupos seguidos del tamaño más parecido posible."""
    n = len(pasos)
    if n == 0:
        return []
    k = min(6, max(min(3, n), math.ceil(n / 3)))
    numerados = list(enumerate(pasos, start=1))
    grupos, i = [], 0
    for g in range(k):
        tam = n // k + (1 if g < n % k else 0)
        grupos.append(numerados[i:i + tam])
        i += tam
    return grupos


def _pregunta_de_pasos(pasos: list[Paso], grupo: list[tuple[int, Paso]], semilla: int) -> dict[str, Any] | None:
    """Pregunta de control sin LLM: qué paso es crítico o qué paso va después."""
    rng = random.Random(semilla)
    titulos = [(p.titulo or "").strip() for p in pasos]  # siempre sin espacios: opciones comparables
    if len(set(t.lower() for t in titulos)) < len(titulos) or len(pasos) < 3 or not all(titulos):
        return None

    def montar(enunciado: str, correcta: str, otras: list[str], explicacion: str) -> dict[str, Any]:
        opciones = [correcta] + rng.sample(otras, 2)
        rng.shuffle(opciones)
        return {"enunciado": enunciado, "opciones": opciones, "correcta": opciones.index(correcta),
                "explicacion": explicacion}

    critico = next((n for n, p in grupo if p.es_critico), None)
    normales = [titulos[i] for i, p in enumerate(pasos) if not p.es_critico]
    if critico is not None and len(normales) >= 2:
        t = titulos[critico - 1]
        return montar("¿Cuál de estos pasos es crítico?", t, normales,
                      f"«{t}» es un paso crítico: en el modo planta hay que confirmarlo antes de seguir.")
    num = grupo[0][0]
    actual = titulos[num - 1]

    def distractores(correcta: str) -> list[str]:
        otras = [t for t in titulos if t not in (actual, correcta)]
        return otras if len(otras) >= 2 else [t for t in titulos if t != correcta]

    if num < len(pasos):
        siguiente = titulos[num]  # los pasos se numeran desde 1: el siguiente está en el índice num
        return montar(f"¿Qué paso va justo después de «{actual}»?", siguiente, distractores(siguiente),
                      f"Después de «{actual}» viene «{siguiente}» (paso {num + 1}).")
    anterior = titulos[num - 2]
    return montar(f"¿Qué paso va justo antes de «{actual}»?", anterior, distractores(anterior),
                  f"Antes de «{actual}» va «{anterior}» (paso {num - 1}).")


def _leccion_de_grupo(pasos: list[Paso], grupo: list[tuple[int, Paso]], semilla: int) -> dict[str, Any]:
    """Lección hecha con el texto de unos pasos seguidos (numerados desde 1)."""
    a, b = grupo[0][0], grupo[-1][0]
    titulo = f"Paso {a}: {grupo[0][1].titulo}" if a == b else f"Pasos {a} a {b}: {grupo[0][1].titulo}"
    bloques = []
    for num, p in grupo:
        bloque = f"**{num}. {p.titulo}**"
        if p.texto:
            bloque += f"\n\n{p.texto.strip()}"
        if p.es_critico:
            bloque += f"\n\n> **Paso crítico.** {p.criterio_aceptacion or 'Compruébalo y confírmalo antes de seguir.'}"
        elif p.criterio_aceptacion:
            bloque += f"\n\n*Cómo saber que está bien:* {p.criterio_aceptacion}"
        if p.es_seguridad:
            bloque += "\n\n*Atención a tu seguridad en este paso.*"
        bloques.append(bloque)
    critico = next(((n, p) for n, p in grupo if p.es_critico), None)
    seguridad = next(((n, p) for n, p in grupo if p.es_seguridad), None)
    if critico:
        n, p = critico
        clave: str | None = f"El paso {n} es crítico: {(p.criterio_aceptacion or p.titulo).strip().rstrip('.')}."
    elif seguridad:
        n, p = seguridad
        clave = f"El paso {n} tiene riesgo para tu seguridad: {p.titulo}."
    elif len(grupo) > 1:
        clave = "Sigue el orden: " + ", después ".join(f"«{p.titulo}»" for _, p in grupo) + "."
    else:
        clave = None
    return {"titulo": titulo[:300], "contenido": "\n\n".join(bloques), "punto_clave": clave,
            "pregunta": _pregunta_de_pasos(pasos, grupo, semilla)}


def _lecciones_de_pasos(ins: Instruccion) -> list[dict[str, Any]]:
    """Plan B sin LLM: una lección por grupo de pasos con el texto de los propios pasos."""
    pasos = list(ins.pasos)
    return [_leccion_de_grupo(pasos, grupo, ins.id * 31 + gi) for gi, grupo in enumerate(_grupos(pasos))]


def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


def _menciona(texto: str, titulo: str) -> bool:
    """¿El texto habla de este paso? Título literal o la mayoría de sus palabras significativas."""
    t, frase = _sin_tildes(texto), _sin_tildes(titulo).strip()
    if frase and frase in t:
        return True
    palabras = [w for w in re.findall(r"\w+", frase) if len(w) >= 5]
    return bool(palabras) and sum(1 for w in palabras if w in t) >= max(1, math.ceil(len(palabras) * 2 / 3))


def _cubrir_criticos(ins: Instruccion, lecciones: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Los modelos pequeños a veces se saltan pasos: ningún paso crítico se queda sin lección.

    Añade una lección por cada paso crítico que el modelo no trata. Si con ellas se pasaría de
    MAX_LECCIONES devuelve None: entonces es mejor el plan B, que cubre todos los pasos en 3-6.
    """
    pasos = list(ins.pasos)
    texto = " ".join(f"{l['titulo']} {l['contenido']} {l['punto_clave'] or ''}" for l in lecciones)
    faltan = [(n, p) for n, p in enumerate(pasos, start=1) if p.es_critico and not _menciona(texto, p.titulo)]
    if len(lecciones) + len(faltan) > MAX_LECCIONES:
        return None
    for n, p in faltan:
        lecciones.append(_leccion_de_grupo(pasos, [(n, p)], ins.id * 31 + 100 + n))
    return lecciones


_FRASES = re.compile(r"(?<=[.!?…])\s+")


def _clave(texto: str) -> str:
    """Texto comparable: sin tildes, sin mayúsculas ni signos."""
    return re.sub(r"\W+", " ", _sin_tildes(texto or "")).strip()


def _quitar_repeticiones(lecciones: list[dict[str, Any]]) -> None:
    """Los modelos pequeños rellenan todas las lecciones con la misma frase, el mismo punto clave y
    hasta la misma pregunta (caso real con qwen3:0.6b). Cada cosa se queda solo en la primera
    lección en la que aparece; una pregunta repetida se descarta y la sustituye una hecha con los
    pasos (`_completar_preguntas`). Ninguna lección se queda con menos de 8 palabras."""
    frases_vistas: set[str] = set()
    puntos_vistos: set[str] = set()
    preguntas_vistas: set[str] = set()
    for l in lecciones:
        restantes = len(l["contenido"].split())
        lineas = []
        for linea in l["contenido"].split("\n"):
            frases = []
            for frase in _FRASES.split(linea):
                k, n = _clave(frase), len(frase.split())
                if len(k) > 20 and k in frases_vistas and restantes - n >= 8:
                    restantes -= n
                    continue
                if k:
                    frases_vistas.add(k)
                frases.append(frase)
            lineas.append(" ".join(frases))
        l["contenido"] = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()
        punto = _clave(l.get("punto_clave") or "")
        if punto and punto in puntos_vistos:
            l["punto_clave"] = None
        puntos_vistos.add(punto)
        p = l.get("pregunta")
        enunciado = _clave(p["enunciado"]) if p else ""
        if enunciado and enunciado in preguntas_vistas:
            l["pregunta"] = None
        preguntas_vistas.add(enunciado)


def _enriquecer(ins: Instruccion, lecciones: list[dict[str, Any]]) -> None:
    """Una lección corta (menos de las 80 palabras pedidas) dedicada a un paso concreto se completa
    con el texto y el criterio de aceptación de ese paso, tal como están en la instrucción, si la
    lección no los cuenta ya. Así lo que falta lo pone la instrucción, no el modelo."""
    pasos = list(ins.pasos)
    for l in lecciones:
        if len(l["contenido"].split()) >= 80:
            continue
        extra: list[str] = []
        titulo = _clave(l["titulo"])
        for n, p in enumerate(pasos, start=1):
            # El título de la lección contiene el del paso, palabra por palabra («Paso número 1» no
            # vale para «Paso número 10»): aquí no sirve el parecido aproximado de `_menciona`.
            frase = _clave(p.titulo)
            if not frase or not re.search(rf"(?<!\w){re.escape(frase)}(?!\w)", titulo):
                continue
            if p.texto and p.texto.strip() and not _menciona(l["contenido"], p.texto):
                extra.append(f"**Paso {n}. {p.titulo.strip()}.** {p.texto.strip()}")
            criterio = (p.criterio_aceptacion or "").strip()
            if criterio and not _menciona(l["contenido"], criterio):
                extra.append(f"> **Paso crítico.** {criterio}" if p.es_critico else f"*Cómo saber que está bien:* {criterio}")
        if extra:
            l["contenido"] = "\n\n".join([l["contenido"].rstrip(), *extra])


def _completar_preguntas(ins: Instruccion, lecciones: list[dict[str, Any]]) -> None:
    """Toda micro-lección lleva su pregunta de control: si la del modelo no vale (le faltan
    opciones, no marca la correcta, repite la de otra lección...), se pone una construida con los
    pasos, repartiendo las lecciones a lo largo de la instrucción y sin repetir enunciados."""
    pasos = list(ins.pasos)
    usadas = {_clave(l["pregunta"]["enunciado"]) for l in lecciones if l.get("pregunta")}
    for i, l in enumerate(lecciones):
        if l.get("pregunta") is not None or not pasos:
            continue
        j = min(len(pasos) - 1, round(i * len(pasos) / max(1, len(lecciones))))
        candidatas = [_pregunta_de_pasos(pasos, [(k + 1, pasos[k])], ins.id * 31 + 200 + i)
                      for k in [*range(j, len(pasos)), *range(0, j)]]
        validas = [c for c in candidatas if c is not None]
        nueva = next((c for c in validas if _clave(c["enunciado"]) not in usadas), validas[0] if validas else None)
        if nueva is not None:
            usadas.add(_clave(nueva["enunciado"]))
        l["pregunta"] = nueva


def generar_microlecciones(bd: Session, instruccion_id: int) -> int:
    """Crea (o rehace) las micro-lecciones de una instrucción. Devuelve cuántas hay. No hace commit."""
    ins = bd.scalar(select(Instruccion).where(Instruccion.id == instruccion_id)
                    .options(selectinload(Instruccion.pasos)))
    if ins is None or not ins.pasos:
        return 0
    lecciones: list[dict[str, Any]] = []
    try:
        lecciones = _normalizar_lecciones(llm.chat_json(_mensajes(ins), bd=bd, temperatura=0.3, max_tokens=4000))
    except Exception as e:  # noqa: BLE001  (modelo caído o JSON imposible de leer)
        log.warning("Micro-lecciones de la instrucción %s sin LLM: %s", instruccion_id, e)
    _quitar_repeticiones(lecciones)
    minimo = min(3, len(_grupos(list(ins.pasos))))
    completas = _cubrir_criticos(ins, lecciones) if len(lecciones) >= minimo else None
    if completas is None:
        log.info("Micro-lecciones de la instrucción %s generadas a partir de los pasos", instruccion_id)
        lecciones = _lecciones_de_pasos(ins)
    else:
        lecciones = completas
    _enriquecer(ins, lecciones)
    _completar_preguntas(ins, lecciones)
    bd.execute(delete(Microleccion).where(Microleccion.instruccion_id == ins.id))
    for orden, l in enumerate(lecciones, start=1):
        bd.add(Microleccion(instruccion_id=ins.id, orden=orden, titulo=l["titulo"], contenido=l["contenido"],
                            punto_clave=l["punto_clave"], pregunta=l["pregunta"]))
    bd.flush()
    return len(lecciones)


def _trabajo_generar(bd: Session, progreso: Any, instruccion_id: int) -> dict[str, Any]:
    progreso(10, "Escribiendo las micro-lecciones")
    return {"microlecciones": generar_microlecciones(bd, instruccion_id)}


def encolar_generacion(instruccion_id: int, usuario_id: int | None = None) -> int:
    """Genera las micro-lecciones en segundo plano. Llamar después del commit de la instrucción."""
    return trabajos.encolar("microlecciones", _trabajo_generar, instruccion_id,
                            entidad="instruccion", entidad_id=instruccion_id, usuario_id=usuario_id)
