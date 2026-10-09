"""Progreso: pasaporte de habilidades, matriz ILUO del equipo e indicadores de planta.

* `mi_progreso`: por cada tarea del itinerario, nivel, avance, caducidad, reevaluación,
  siguiente requisito en lenguaje claro, evidencias con fechas y curva de autonomía
  (consultas por ejecución completada).
* `equipo`: matriz personas × tareas del departamento del jefe (la administración elige
  departamento) con indicadores: personas en L o más por tarea, caducidades próximas,
  reevaluaciones pendientes y tiempo medio hasta la primera ejecución correcta.
* `planta`: lo mismo resumido para toda la planta (administración).

Ver a una persona exige ser ella, su jefe (o el del departamento en el que se forma, solo
para las tareas de ese departamento) o la administración.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cidia.modelos import (
    Aportacion,
    Departamento,
    Ejecucion,
    Formacion,
    Instruccion,
    IntentoEval,
    Microleccion,
    MicroleccionVista,
    NivelIluo,
    Observacion,
    PreguntaEval,
    Puesto,
    Tarea,
    Usuario,
    ahora,
)
from cidia.seguridad import Actor
from cidia.servicios import iluo

DIAS_AVISO_CADUCIDAD = 60
PISO_PORCENTAJE = {0: 0, 1: 25, 2: 75, 3: 100, 4: 100}


def iniciales(nombre: str) -> str:
    partes = [p for p in (nombre or "").split() if p]
    return ("".join(p[0] for p in partes[:2]) or "?").upper()


def _tarea_dict(t: Tarea, con_departamento: bool = False) -> dict[str, Any]:
    datos = {"id": t.id, "codigo": t.codigo, "nombre": t.nombre, "criticidad": t.criticidad,
             "puesto": t.puesto.nombre if t.puesto else None}
    if con_departamento:
        datos["departamento"] = t.puesto.departamento.nombre if t.puesto and t.puesto.departamento else None
    return datos


# --------------------------------------------------------------------------- itinerario


def tareas_de(bd: Session, usuario: Usuario) -> list[Tarea]:
    """Tareas del itinerario: las de su puesto, las de sus formaciones activas (el puesto de la
    formación o, si no tiene, todo el departamento) y las que ya ha empezado o certificado."""
    puestos: set[int] = set()
    deps: set[int] = set()
    if usuario.puesto_id:
        puestos.add(usuario.puesto_id)
    for f in bd.scalars(select(Formacion).where(Formacion.usuario_id == usuario.id, Formacion.estado == "activa")):
        if f.puesto_id:
            puestos.add(f.puesto_id)
        else:
            deps.add(f.departamento_id)
    conds = [
        Tarea.id.in_(select(NivelIluo.tarea_id).where(NivelIluo.usuario_id == usuario.id, NivelIluo.nivel > 0)),
        Tarea.id.in_(select(Ejecucion.tarea_id).where(Ejecucion.usuario_id == usuario.id)),
    ]
    if puestos:
        conds.append(Tarea.puesto_id.in_(puestos))
    if deps:
        conds.append(Puesto.departamento_id.in_(deps))
    q = (select(Tarea).join(Puesto, Puesto.id == Tarea.puesto_id)
         .where(Tarea.activa.is_(True), or_(*conds))
         .order_by(Puesto.departamento_id, Puesto.nombre, Tarea.codigo, Tarea.nombre))
    return list(bd.scalars(q).all())


# --------------------------------------------------------------------------- detalle de una tarea


def _evidencias(bd: Session, usuario: Usuario, tarea: Tarea, fila: NivelIluo,
                vigente: Instruccion | None) -> dict[str, Any]:
    versiones = dict(bd.execute(select(Instruccion.id, Instruccion.version)
                                .where(Instruccion.tarea_id == tarea.id)).all())
    intentos = bd.scalars(select(IntentoEval).where(IntentoEval.usuario_id == usuario.id,
                                                    IntentoEval.instruccion_id.in_(list(versiones)))
                          .order_by(IntentoEval.creado.desc()).limit(20)).all() if versiones else []
    ejecuciones = bd.scalars(select(Ejecucion).where(Ejecucion.usuario_id == usuario.id, Ejecucion.tarea_id == tarea.id)
                             .order_by(Ejecucion.inicio.desc()).limit(30)).all()
    observaciones = bd.scalars(select(Observacion).where(Observacion.usuario_id == usuario.id,
                                                         Observacion.tarea_id == tarea.id)
                               .order_by(Observacion.creada.desc()).limit(10)).all()
    aportaciones = bd.scalars(select(Aportacion).where(Aportacion.autor_id == usuario.id, Aportacion.tarea_id == tarea.id,
                                                       Aportacion.estado == "validada")
                              .order_by(Aportacion.creada.desc()).limit(20)).all()
    micro_total = micro_vistas = 0
    if vigente is not None:
        micro_total = bd.scalar(select(func.count(Microleccion.id)).where(Microleccion.instruccion_id == vigente.id)) or 0
        micro_vistas = bd.scalar(
            select(func.count(MicroleccionVista.id)).join(Microleccion, Microleccion.id == MicroleccionVista.microleccion_id)
            .where(Microleccion.instruccion_id == vigente.id, MicroleccionVista.usuario_id == usuario.id)) or 0
    ids_evaluadores = sorted({o.evaluador_id for o in observaciones if o.evaluador_id})
    evaluadores = {u.id: u.nombre for u in bd.scalars(select(Usuario).where(Usuario.id.in_(ids_evaluadores)))} \
        if ids_evaluadores else {}
    formador = (fila.evidencias or {}).get("formador") if fila.formador_validado else None
    return {
        "cuestionarios": [{"id": i.id, "fecha": iluo.iso(i.creado), "puntuacion": round(i.puntuacion, 4),
                           "aciertos": i.aciertos, "total": i.total, "aprobado": i.aprobado,
                           "version": versiones.get(i.instruccion_id),
                           "vigente": bool(vigente and i.instruccion_id == vigente.id)} for i in intentos],
        "ejecuciones": [{"id": e.id, "inicio": iluo.iso(e.inicio), "fin": iluo.iso(e.fin), "estado": e.estado,
                         "consultas": e.consultas or 0, "consultas_criticos": e.consultas_criticos or 0}
                        for e in ejecuciones],
        "observaciones": [{"id": o.id, "fecha": iluo.iso(o.creada), "aprobada": o.aprobada,
                           "evaluador": evaluadores.get(o.evaluador_id), "comentario": o.comentario,
                           "pasos": len(o.lista or []), "pasos_ok": sum(1 for x in (o.lista or []) if x.get("ok"))}
                          for o in observaciones],
        "aportaciones": [{"id": a.id, "titulo": a.titulo or (a.problema or "Aportación")[:120],
                          "fecha": iluo.iso(a.validada_en or a.creada)} for a in aportaciones],
        "microlecciones": {"vistas": micro_vistas, "total": micro_total},
        "formador": formador,
    }


def _curva(bd: Session, usuario_id: int, tarea_id: int) -> list[dict[str, Any]]:
    """Curva de autonomía: consultas en cada ejecución completada, en orden."""
    filas = bd.execute(
        select(Ejecucion.id, Ejecucion.inicio, Ejecucion.fin, Ejecucion.consultas, Ejecucion.consultas_criticos)
        .where(Ejecucion.usuario_id == usuario_id, Ejecucion.tarea_id == tarea_id, Ejecucion.estado == "completada")
        .order_by(func.coalesce(Ejecucion.fin, Ejecucion.inicio), Ejecucion.id)
    ).all()
    return [{"n": i, "ejecucion_id": e.id, "fecha": iluo.iso(e.fin or e.inicio), "consultas": e.consultas or 0,
             "consultas_criticos": e.consultas_criticos or 0} for i, e in enumerate(filas, start=1)]


def detalle_tarea(bd: Session, usuario: Usuario, tarea: Tarea, fila: NivelIluo, ev: iluo.Evidencias,
                  momento: datetime | None = None, con_departamento: bool = False) -> dict[str, Any]:
    """Una fila del pasaporte: nivel, avance, caducidad, siguiente requisito, evidencias y curva."""
    from cidia.servicios.evaluacion import siguiente_paso  # import tardío: evaluacion usa este módulo

    momento = momento or ahora()
    nivel = fila.nivel or 0
    dias = (fila.caduca - momento).days if fila.caduca and nivel > 0 else None
    if fila.requiere_reevaluacion:
        porcentaje = ev.porcentaje()
    else:
        porcentaje = max(PISO_PORCENTAJE.get(nivel, 0), ev.porcentaje())
    vigente = ev.instruccion
    preguntas = 0
    if vigente is not None:
        preguntas = bd.scalar(select(func.count(PreguntaEval.id)).where(PreguntaEval.instruccion_id == vigente.id,
                                                                        PreguntaEval.estado == "aprobada")) or 0
    texto_siguiente = siguiente_paso(fila, ev)
    historial = list(reversed((fila.evidencias or {}).get("historial") or []))
    return {
        "tarea": _tarea_dict(tarea, con_departamento),
        "nivel": nivel,
        "letra": iluo.nivel_letra(nivel),
        "nombre_nivel": iluo.nivel_nombre(nivel),
        "porcentaje": min(100, porcentaje),
        "desde": iluo.iso(fila.desde),
        "caduca": iluo.iso(fila.caduca),
        "dias_para_caducar": dias,
        "caducado": iluo.caducado(fila, momento),
        "caduca_pronto": dias is not None and dias <= DIAS_AVISO_CADUCIDAD,
        "requiere_reevaluacion": bool(fila.requiere_reevaluacion),
        "formador_validado": bool(fila.formador_validado),
        "instruccion": {"id": vigente.id, "codigo": vigente.codigo, "titulo": vigente.titulo,
                        "version": vigente.version} if vigente else None,
        "cuestionario_disponible": preguntas > 0,
        "cuestionario_aprobado": bool(ev.cuestionario),
        "siguiente": {"nivel": nivel + 1, "letra": iluo.nivel_letra(nivel + 1), "texto": texto_siguiente}
        if nivel < 4 else None,
        "requisitos": ev.requisitos(),
        "evidencias": _evidencias(bd, usuario, tarea, fila, vigente),
        "historial": historial,
        "curva": _curva(bd, usuario.id, tarea.id),
    }


# --------------------------------------------------------------------------- pasaporte de una persona


def _persona_dict(bd: Session, usuario: Usuario, con_departamento: bool) -> dict[str, Any]:
    formaciones = bd.scalars(select(Formacion).where(Formacion.usuario_id == usuario.id,
                                                     Formacion.estado == "activa")).all()
    datos: dict[str, Any] = {
        "id": usuario.id, "nombre": usuario.nombre, "iniciales": iniciales(usuario.nombre),
        "puesto": usuario.puesto.nombre if usuario.puesto else None,
        "formaciones": [{"departamento": f.departamento.nombre, "puesto": f.puesto.nombre if f.puesto else None}
                        for f in formaciones],
    }
    if con_departamento:
        datos["departamento"] = usuario.departamento.nombre if usuario.departamento else None
    return datos


def progreso_de(bd: Session, usuario: Usuario, con_departamento: bool = False,
                tareas: list[Tarea] | None = None) -> dict[str, Any]:
    """Pasaporte de una persona. Recalcula antes cada tarea (idempotente: aplica caducidades
    y evidencias que otros módulos no hayan notificado)."""
    momento = ahora()
    filas = []
    for t in tareas if tareas is not None else tareas_de(bd, usuario):
        fila, ev = iluo.recalcular_con_evidencias(bd, usuario.id, t.id)
        filas.append(detalle_tarea(bd, usuario, t, fila, ev, momento, con_departamento))
    por_nivel = {letra: sum(1 for f in filas if f["letra"] == letra) for letra in ("I", "L", "U", "O")}
    return {
        "persona": _persona_dict(bd, usuario, con_departamento),
        "resumen": {
            "tareas": len(filas),
            "por_nivel": por_nivel,
            "sin_iniciar": sum(1 for f in filas if f["nivel"] == 0),
            "autonomas": por_nivel["U"] + por_nivel["O"],
            "reevaluaciones": sum(1 for f in filas if f["requiere_reevaluacion"]),
            "caducan_pronto": sum(1 for f in filas if f["caduca_pronto"]),
        },
        "tareas": filas,
    }


def mi_progreso(bd: Session, actor: Actor) -> dict[str, Any]:
    assert actor.usuario is not None
    return progreso_de(bd, actor.usuario, con_departamento=actor.es_jefe)


def _en_su_alcance(bd: Session, usuario: Usuario, tarea: Tarea) -> bool:
    """¿Es una tarea en la que la persona se forma o ya tiene actividad? (su departamento,
    una formación activa en el de la tarea, o un nivel o una ejecución en ella)."""
    from cidia.servicios.evaluacion import puede_formarse  # import tardío: evaluacion usa este módulo

    if puede_formarse(bd, usuario, tarea) or iluo.fila_de(bd, usuario.id, tarea.id) is not None:
        return True
    return bool(bd.scalar(select(func.count(Ejecucion.id)).where(Ejecucion.usuario_id == usuario.id,
                                                                 Ejecucion.tarea_id == tarea.id)))


def _visible(bd: Session, actor: Actor, usuario: Usuario, tarea: Tarea | None = None) -> None:
    """Comprueba que el actor puede ver el progreso de la persona (y de esa tarea). Lanza 403.

    La persona se ve a sí misma (en las tareas de su alcance); su jefe o el del departamento en el
    que se forma la ven; y quien puede validarla como formadora en una tarea (jefe o experto de ese
    departamento) ve esa tarea concreta.
    """
    if actor.es_admin:
        return
    if usuario.id == actor.id:
        if tarea is not None and not _en_su_alcance(bd, usuario, tarea):
            raise HTTPException(403, "Esa tarea no está en tu itinerario.")
        return
    if tarea is not None and iluo.puede_evaluar(bd, actor, usuario, tarea, expertos=True):
        return
    if not iluo.gestiona_persona(bd, actor, usuario):
        raise HTTPException(403, "Solo puedes ver el progreso de las personas de tu departamento.")
    if tarea is not None and usuario.departamento_id != actor.departamento_id \
            and iluo.departamento_de_tarea(tarea) != actor.departamento_id:
        raise HTTPException(403, "Esa tarea no es de tu departamento.")


def progreso_persona(bd: Session, actor: Actor, usuario_id: int) -> dict[str, Any]:
    usuario = bd.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "No existe esa persona.")
    if usuario.id == actor.id:
        return mi_progreso(bd, actor)
    _visible(bd, actor, usuario)
    tareas = tareas_de(bd, usuario)
    if not actor.es_admin and usuario.departamento_id != actor.departamento_id:
        # Se forma en el departamento del jefe: solo ve las tareas de su departamento.
        tareas = [t for t in tareas if iluo.departamento_de_tarea(t) == actor.departamento_id]
    return progreso_de(bd, usuario, con_departamento=True, tareas=tareas)


def detalle(bd: Session, actor: Actor, usuario_id: int, tarea_id: int) -> dict[str, Any]:
    """Una persona en una tarea (celda de la matriz) con las acciones que el actor puede hacer."""
    usuario = bd.get(Usuario, usuario_id)
    tarea = bd.get(Tarea, tarea_id)
    if usuario is None or tarea is None:
        raise HTTPException(404, "No existe esa persona o esa tarea.")
    _visible(bd, actor, usuario, tarea)
    fila, ev = iluo.recalcular_con_evidencias(bd, usuario.id, tarea.id)
    datos = detalle_tarea(bd, usuario, tarea, fila, ev, con_departamento=actor.es_jefe)
    jefe = actor.es_admin or actor.rol == "jefe"
    evalua = iluo.puede_evaluar(bd, actor, usuario, tarea)
    datos["persona"] = _persona_dict(bd, usuario, actor.es_jefe)
    datos["acciones"] = {
        "observar": jefe and evalua,
        "ajustar": jefe and evalua,
        "validar_formador": iluo.puede_evaluar(bd, actor, usuario, tarea, expertos=True)
        and fila.nivel == 3 and not fila.requiere_reevaluacion,
    }
    return datos


# --------------------------------------------------------------------------- matriz e indicadores


def _tiempo_medio(bd: Session, usuarios: list[int], tareas: list[int]) -> dict[str, Any]:
    """Días medios desde que alguien empieza una tarea hasta su primera ejecución correcta
    (completada y sin consultas en pasos críticos)."""
    if not usuarios or not tareas:
        return {"dias": None, "muestras": 0}
    inicio: dict[tuple[int, int], datetime] = {}
    correcta: dict[tuple[int, int], datetime] = {}
    for e in bd.execute(select(Ejecucion.usuario_id, Ejecucion.tarea_id, Ejecucion.inicio, Ejecucion.fin,
                               Ejecucion.estado, Ejecucion.consultas_criticos)
                        .where(Ejecucion.usuario_id.in_(usuarios), Ejecucion.tarea_id.in_(tareas))).all():
        k = (e.usuario_id, e.tarea_id)
        if e.inicio and (k not in inicio or e.inicio < inicio[k]):
            inicio[k] = e.inicio
        if e.estado == "completada" and not e.consultas_criticos:
            fin = e.fin or e.inicio
            if fin and (k not in correcta or fin < correcta[k]):
                correcta[k] = fin
    vistas = bd.execute(
        select(MicroleccionVista.usuario_id, Instruccion.tarea_id, func.min(MicroleccionVista.completada_en))
        .join(Microleccion, Microleccion.id == MicroleccionVista.microleccion_id)
        .join(Instruccion, Instruccion.id == Microleccion.instruccion_id)
        .where(MicroleccionVista.usuario_id.in_(usuarios), Instruccion.tarea_id.in_(tareas))
        .group_by(MicroleccionVista.usuario_id, Instruccion.tarea_id)
    ).all()
    for u, t, primera in vistas:
        if primera and ((u, t) not in inicio or primera < inicio[(u, t)]):
            inicio[(u, t)] = primera
    dias = [max(0.0, (fin - inicio[k]).total_seconds() / 86400) for k, fin in correcta.items() if k in inicio]
    return {"dias": round(sum(dias) / len(dias), 1) if dias else None, "muestras": len(dias)}


def _matriz(bd: Session, dep_ids: list[int]) -> dict[str, Any]:
    """Personas × tareas de unos departamentos, con sus niveles e indicadores."""
    momento = ahora()
    tareas = list(bd.scalars(
        select(Tarea).join(Puesto, Puesto.id == Tarea.puesto_id)
        .where(Puesto.departamento_id.in_(dep_ids or [0]), Tarea.activa.is_(True))
        .order_by(Puesto.departamento_id, Puesto.nombre, Tarea.codigo, Tarea.nombre)).all())
    propios = list(bd.scalars(select(Usuario).where(Usuario.departamento_id.in_(dep_ids or [0]),
                                                    Usuario.activo.is_(True)).order_by(Usuario.nombre)).all())
    ids_propios = {u.id for u in propios}
    externos = [u for u in bd.scalars(
        select(Usuario).join(Formacion, Formacion.usuario_id == Usuario.id)
        .where(Formacion.departamento_id.in_(dep_ids or [0]), Formacion.estado == "activa", Usuario.activo.is_(True))
        .order_by(Usuario.nombre)).unique().all() if u.id not in ids_propios]
    personas = propios + list({u.id: u for u in externos}.values())
    ids_personas = [u.id for u in personas]
    ids_tareas = [t.id for t in tareas]
    tareas_por_id = {t.id: t for t in tareas}
    personas_por_id = {u.id: u for u in personas}
    filas = list(bd.scalars(select(NivelIluo).where(NivelIluo.usuario_id.in_(ids_personas or [0]),
                                                    NivelIluo.tarea_id.in_(ids_tareas or [0]))).all())

    celdas = []
    por_tarea: dict[int, dict[str, int]] = defaultdict(lambda: {"i": 0, "l_o_mas": 0, "u_o_mas": 0, "o": 0})
    caducidades, reevaluaciones = [], []
    limite = momento + timedelta(days=DIAS_AVISO_CADUCIDAD)
    for f in filas:
        cad = iluo.caducado(f, momento)
        celdas.append({"usuario_id": f.usuario_id, "tarea_id": f.tarea_id, "nivel": f.nivel,
                       "letra": iluo.nivel_letra(f.nivel), "caduca": iluo.iso(f.caduca), "caducado": cad,
                       "requiere_reevaluacion": bool(f.requiere_reevaluacion),
                       "formador_validado": bool(f.formador_validado)})
        u, t = personas_por_id[f.usuario_id], tareas_por_id[f.tarea_id]
        base = {"usuario_id": u.id, "nombre": u.nombre, "tarea_id": t.id, "codigo": t.codigo, "tarea": t.nombre,
                "nivel": f.nivel, "letra": iluo.nivel_letra(f.nivel)}
        if not cad:
            c = por_tarea[f.tarea_id]
            c["i"] += f.nivel == 1
            c["l_o_mas"] += f.nivel >= 2
            c["u_o_mas"] += f.nivel >= 3
            c["o"] += f.nivel >= 4
        if f.nivel > 0 and f.caduca and f.caduca <= limite:
            caducidades.append({**base, "caduca": iluo.iso(f.caduca), "caducado": cad,
                                "dias": (f.caduca - momento).days})
        if f.requiere_reevaluacion and f.nivel > 0:
            reevaluaciones.append(base)
    caducidades.sort(key=lambda c: c["caduca"])
    reevaluaciones.sort(key=lambda r: (r["tarea"], r["nombre"]))

    personas_por_tarea = [{"tarea_id": t.id, "codigo": t.codigo, "tarea": t.nombre, "criticidad": t.criticidad,
                           **por_tarea[t.id]} for t in tareas]
    celdas_l = sum(c["l_o_mas"] for c in por_tarea.values())
    return {
        "tareas": [_tarea_dict(t, con_departamento=len(dep_ids) > 1) for t in tareas],
        "personas": [{"id": u.id, "nombre": u.nombre, "iniciales": iniciales(u.nombre),
                      "puesto": u.puesto.nombre if u.puesto else None, "rol": u.rol,
                      "en_formacion": u.id not in ids_propios} for u in personas],
        "celdas": celdas,
        "indicadores": {
            "personas": len(personas),
            "tareas": len(tareas),
            "celdas_l_o_mas": celdas_l,
            "polivalencia": round(celdas_l / len(personas), 1) if personas else 0,
            "tareas_con_riesgo": sum(1 for p in personas_por_tarea if p["u_o_mas"] < 2),
            "personas_por_tarea": personas_por_tarea,
            "caducidades_proximas": caducidades,
            "reevaluaciones_pendientes": reevaluaciones,
            "tiempo_medio_primera_correcta": _tiempo_medio(bd, ids_personas, ids_tareas),
        },
    }


def equipo(bd: Session, actor: Actor, departamento_id: int | None = None) -> dict[str, Any]:
    """Matriz del departamento del jefe; la administración puede elegir cualquier departamento."""
    if not actor.es_jefe:
        raise HTTPException(403, "Solo jefes y administradores pueden ver la matriz del equipo.")
    deps = list(bd.scalars(select(Departamento).order_by(Departamento.nombre)).all())
    if actor.es_admin:
        dep = next((d for d in deps if d.id == departamento_id), None) if departamento_id else (deps[0] if deps else None)
        if departamento_id and dep is None:
            raise HTTPException(404, "No existe ese departamento.")
    else:
        if not actor.departamento_id:
            raise HTTPException(400, "No tienes un departamento asignado. Pide a la administración que te asigne uno.")
        if departamento_id and departamento_id != actor.departamento_id:
            raise HTTPException(403, "Solo puedes ver la matriz de tu departamento.")
        dep = next((d for d in deps if d.id == actor.departamento_id), None)
    if dep is None:
        return {"departamento": None, "departamentos": [], "tareas": [], "personas": [], "celdas": [],
                "indicadores": None, "puede_evaluar": False}
    datos = _matriz(bd, [dep.id])
    datos["departamento"] = {"id": dep.id, "nombre": dep.nombre}
    datos["departamentos"] = [{"id": d.id, "nombre": d.nombre} for d in deps] if actor.es_admin else []
    datos["puede_evaluar"] = actor.es_admin or actor.departamento_id == dep.id
    return datos


def planta(bd: Session, actor: Actor) -> dict[str, Any]:
    """Indicadores de toda la planta y resumen por departamento (administración)."""
    if not actor.es_admin:
        raise HTTPException(403, "Solo la administración puede ver el progreso de toda la planta.")
    deps = list(bd.scalars(select(Departamento).order_by(Departamento.nombre)).all())
    resumen = []
    for d in deps:
        m = _matriz(bd, [d.id])["indicadores"]
        resumen.append({"id": d.id, "nombre": d.nombre, "personas": m["personas"], "tareas": m["tareas"],
                        "celdas_l_o_mas": m["celdas_l_o_mas"], "polivalencia": m["polivalencia"],
                        "tareas_con_riesgo": m["tareas_con_riesgo"],
                        "reevaluaciones": len(m["reevaluaciones_pendientes"]),
                        "caducidades": len(m["caducidades_proximas"]),
                        "tiempo_medio_dias": m["tiempo_medio_primera_correcta"]["dias"]})
    total = _matriz(bd, [d.id for d in deps])["indicadores"]
    return {"indicadores": total, "departamentos": resumen}
