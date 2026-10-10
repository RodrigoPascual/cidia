"""Panel de inicio y contadores de la barra lateral.

Lo que ve cada persona depende de su rol:
* todos: saludo, accesos rápidos, «continúa donde lo dejaste», sus tareas con nivel ILUO,
  sus cifras y sus aportaciones recientes;
* expertos: borradores de instrucciones y preguntas de evaluación por revisar;
* jefes: bandejas de su departamento (aportaciones por validar, lagunas abiertas,
  reevaluaciones y observaciones sugeridas);
* administración: lo mismo para toda la planta y las cifras generales.

Todo se calcula en el servidor a partir de la sesión y consultando las tablas directamente.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import Select

from cidia.db import obtener_bd
from cidia.modelos import (
    Aportacion,
    Consulta,
    Departamento,
    Documento,
    Ejecucion,
    EjecucionPaso,
    Formacion,
    Instruccion,
    IntentoEval,
    Laguna,
    Microleccion,
    MicroleccionVista,
    NivelIluo,
    Observacion,
    Paso,
    PreguntaEval,
    Puesto,
    Tarea,
    Usuario,
)
from cidia.rutas.auth import servicios
from cidia.seguridad import Actor, usuario_actual
from cidia.servicios.iluo import nivel_letra

router = APIRouter(prefix="/api/inicio", tags=["inicio"])

# Accesos rápidos grandes del panel (se muestran los que permite el perfil).
ACCESOS = [
    {"clave": "planta", "titulo": "Modo planta", "descripcion": "Sigue una instrucción paso a paso, con voz.", "ruta": "/planta"},
    {"clave": "chat", "titulo": "Copiloto", "descripcion": "Pregunta y obtén respuestas con sus fuentes.", "ruta": "/copiloto"},
    {"clave": "formacion", "titulo": "Formación", "descripcion": "Micro-lecciones de tus tareas.", "ruta": "/formacion"},
    {"clave": "aportaciones", "titulo": "Aportaciones", "descripcion": "Comparte un truco o una solución.", "ruta": "/aportaciones"},
]
DIAS_AVISO_CADUCIDAD = 30


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _saludo(nombre_corto: str) -> str:
    try:
        from zoneinfo import ZoneInfo

        hora = datetime.now(ZoneInfo("Europe/Madrid")).hour
    except Exception:  # noqa: BLE001
        hora = _ahora().hour + 1
    parte = "Buenos días" if 6 <= hora < 14 else "Buenas tardes" if 14 <= hora < 21 else "Buenas noches"
    return f"{parte}, {nombre_corto}"


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


# --------------------------------------------------------------------------- tareas de cada persona


def tareas_de_persona(bd: Session, u: Usuario) -> dict[int, str]:
    """Tareas que le tocan a una persona y por qué: {tarea_id: 'puesto' | 'formacion' | 'historial'}.

    Mismas reglas que el itinerario de servicios/progreso.py (`tareas_de`), para que Inicio,
    «Mi progreso» y el contador de Evaluación cuenten lo mismo. Solo tareas activas:
    * las de su puesto;
    * las de sus formaciones activas (el puesto de la formación o, sin puesto, todo el departamento);
    * las que ya ha empezado o certificado (nivel ILUO o alguna ejecución).
    """
    origen: dict[int, str] = {}
    activa = Tarea.activa.is_(True)
    if u.puesto_id:
        for tid in bd.scalars(select(Tarea.id).where(Tarea.puesto_id == u.puesto_id, activa)).all():
            origen[tid] = "puesto"
    for f in bd.scalars(select(Formacion).where(Formacion.usuario_id == u.id, Formacion.estado == "activa")).all():
        q = select(Tarea.id).join(Puesto).where(Puesto.departamento_id == f.departamento_id, activa)
        if f.puesto_id:
            q = q.where(Tarea.puesto_id == f.puesto_id)
        for tid in bd.scalars(q).all():
            origen.setdefault(tid, "formacion")
    empezadas = select(Tarea.id).where(activa, or_(
        Tarea.id.in_(select(NivelIluo.tarea_id).where(NivelIluo.usuario_id == u.id, NivelIluo.nivel > 0)),
        Tarea.id.in_(select(Ejecucion.tarea_id).where(Ejecucion.usuario_id == u.id))))
    for tid in bd.scalars(empezadas).all():
        origen.setdefault(tid, "historial")
    return origen


def _mis_tareas(bd: Session, u: Usuario, origen: dict[int, str]) -> list[dict[str, Any]]:
    if not origen:
        return []
    ahora = _ahora()
    tareas = bd.execute(select(Tarea, Puesto.nombre).join(Puesto).where(Tarea.id.in_(list(origen)))).all()
    niveles = {n.tarea_id: n for n in bd.scalars(select(NivelIluo).where(
        NivelIluo.usuario_id == u.id, NivelIluo.tarea_id.in_(list(origen)))).all()}
    publicadas = dict(bd.execute(select(Instruccion.tarea_id, func.max(Instruccion.id)).where(
        Instruccion.tarea_id.in_(list(origen)), Instruccion.estado == "publicada").group_by(Instruccion.tarea_id)).all())
    salida = []
    for t, puesto in tareas:
        n = niveles.get(t.id)
        nivel = n.nivel if n else 0
        caducado = bool(n and n.caduca and n.caduca < ahora)
        salida.append({
            "id": t.id, "codigo": t.codigo, "nombre": t.nombre, "puesto": puesto, "criticidad": t.criticidad,
            "origen": origen[t.id], "nivel": nivel, "letra": nivel_letra(nivel),
            "caduca": _iso(n.caduca) if n else None, "caducado": caducado,
            "requiere_reevaluacion": bool(n and n.requiere_reevaluacion),
            "instruccion_id": publicadas.get(t.id),
        })
    # Primero lo que pide atención, luego lo que está en marcha, luego el resto.
    salida.sort(key=lambda x: (not (x["caducado"] or x["requiere_reevaluacion"]),
                               {1: 0, 2: 0, 3: 1, 0: 2, 4: 3}.get(x["nivel"], 2), x["codigo"] or "", x["nombre"]))
    return salida


# --------------------------------------------------------------------------- «continúa donde lo dejaste»


def _continuar(bd: Session, u: Usuario) -> dict[str, Any] | None:
    """La ejecución en curso o la formación a medias más reciente."""
    opciones: list[tuple[datetime, dict[str, Any]]] = []
    ej = bd.scalar(select(Ejecucion).where(Ejecucion.usuario_id == u.id, Ejecucion.estado == "en_curso")
                   .order_by(Ejecucion.inicio.desc()).limit(1))
    if ej is not None:
        tarea = bd.get(Tarea, ej.tarea_id)
        total = bd.scalar(select(func.count(Paso.id)).where(Paso.instruccion_id == ej.instruccion_id)) or 0
        hechos = bd.scalar(select(func.count(EjecucionPaso.id)).where(
            EjecucionPaso.ejecucion_id == ej.id, EjecucionPaso.confirmado_en.is_not(None))) or 0
        ultimo = bd.scalar(select(func.max(EjecucionPaso.confirmado_en)).where(EjecucionPaso.ejecucion_id == ej.id))
        momento = ultimo or ej.inicio
        opciones.append((momento, {
            "tipo": "ejecucion", "id": ej.id, "titulo": tarea.nombre if tarea else "Ejecución en curso",
            "codigo": tarea.codigo if tarea else None,
            "detalle": f"Paso {min(hechos + 1, total)} de {total}" if total else "Ejecución en curso",
            "progreso": round(100 * hechos / total) if total else 0,
            "ruta": f"/planta/ejecucion/{ej.id}", "momento": _iso(momento),
        }))
    vista = bd.execute(select(MicroleccionVista.completada_en, Microleccion.instruccion_id)
                       .join(Microleccion, Microleccion.id == MicroleccionVista.microleccion_id)
                       .where(MicroleccionVista.usuario_id == u.id)
                       .order_by(MicroleccionVista.completada_en.desc()).limit(1)).first()
    if vista is not None:
        momento, instruccion_id = vista
        ins = bd.get(Instruccion, instruccion_id)
        total = bd.scalar(select(func.count(Microleccion.id)).where(Microleccion.instruccion_id == instruccion_id)) or 0
        vistas = bd.scalar(select(func.count(MicroleccionVista.id)).join(
            Microleccion, Microleccion.id == MicroleccionVista.microleccion_id).where(
            MicroleccionVista.usuario_id == u.id, Microleccion.instruccion_id == instruccion_id)) or 0
        if ins is not None:
            tarea = bd.get(Tarea, ins.tarea_id)
            completa = total and vistas >= total
            opciones.append((momento, {
                "tipo": "evaluacion" if completa else "microleccion", "id": ins.id,
                "titulo": tarea.nombre if tarea else ins.titulo, "codigo": tarea.codigo if tarea else None,
                "detalle": ("Has visto todas las micro-lecciones: ya puedes hacer el cuestionario" if completa
                            else f"{vistas} de {total} micro-lecciones vistas"),
                "progreso": round(100 * vistas / total) if total else 0,
                "ruta": "/evaluacion" if completa else f"/formacion/tarea/{ins.tarea_id}",
                "momento": _iso(momento),
            }))
    if not opciones:
        return None
    # La ejecución en curso tiene prioridad si es igual de reciente: hay una pieza a medio montar.
    opciones.sort(key=lambda o: (o[0], o[1]["tipo"] == "ejecucion"), reverse=True)
    return opciones[0][1]


# --------------------------------------------------------------------------- bandejas del jefe


def _en_alcance(q: Select, columna_dep: Any, actor: Actor) -> Select:
    """Filtra por el departamento del jefe; la administración ve toda la planta."""
    if actor.es_admin:
        return q
    return q.where(columna_dep == actor.departamento_id)


def _bandejas(bd: Session, actor: Actor) -> dict[str, Any]:
    ahora = _ahora()
    if not actor.es_admin and actor.departamento_id is None:
        return {"ambito": None, "pendientes_validar": 0, "aportaciones": [], "lagunas_abiertas": 0, "lagunas": [],
                "reevaluaciones_total": 0, "reevaluaciones": [], "observaciones_sugeridas": [], "personas": 0}

    limite = ahora + timedelta(days=DIAS_AVISO_CADUCIDAD)
    q_ap = _en_alcance(select(Aportacion).where(Aportacion.estado == "pendiente"), Aportacion.departamento_id, actor)
    q_la = _en_alcance(select(Laguna).where(Laguna.estado == "abierta"), Laguna.departamento_id, actor)
    # Niveles ILUO del equipo que piden reevaluación (nueva versión) o caducan pronto.
    q_re = _en_alcance(
        select(NivelIluo, Usuario.nombre, Tarea.nombre).join(Usuario, Usuario.id == NivelIluo.usuario_id)
        .join(Tarea, Tarea.id == NivelIluo.tarea_id)
        .where(Usuario.activo.is_(True), NivelIluo.nivel > 0,
               (NivelIluo.requiere_reevaluacion.is_(True)) | (NivelIluo.caduca < limite)),
        Usuario.departamento_id, actor)
    cuenta = _contar(
        bd,
        pendientes=select(func.count()).select_from(q_ap.subquery()),
        lagunas=select(func.count()).select_from(q_la.subquery()),
        reevaluaciones=select(func.count()).select_from(q_re.subquery()),
        personas=_en_alcance(select(func.count(Usuario.id)).where(Usuario.activo.is_(True)), Usuario.departamento_id, actor),
    )
    aportaciones = [
        {"id": a.id, "titulo": a.titulo or (a.problema or a.texto_original or "Aportación")[:90],
         "autor": a.autor.nombre if a.autor else None, "creada": _iso(a.creada), "nota_de_voz": bool(a.audio_ruta)}
        for a in bd.scalars(q_ap.options(joinedload(Aportacion.autor)).order_by(Aportacion.creada).limit(5)).all()
    ]
    lagunas = [{"id": la.id, "pregunta": la.pregunta, "frecuencia": la.frecuencia, "ultima_vez": _iso(la.ultima_vez)}
               for la in bd.scalars(q_la.order_by(Laguna.frecuencia.desc(), Laguna.ultima_vez.desc()).limit(5)).all()]

    reevaluaciones = []
    for n, persona, tarea in bd.execute(q_re.order_by(NivelIluo.requiere_reevaluacion.desc(),
                                                      NivelIluo.caduca.nulls_last()).limit(8)).all():
        if n.requiere_reevaluacion:
            motivo = "Nueva versión de la instrucción"
        elif n.caduca and n.caduca < ahora:
            motivo = "Nivel caducado"
        else:
            motivo = "Caduca pronto"
        reevaluaciones.append({"usuario_id": n.usuario_id, "persona": persona, "tarea_id": n.tarea_id, "tarea": tarea,
                               "nivel": n.nivel, "letra": nivel_letra(n.nivel), "motivo": motivo, "caduca": _iso(n.caduca)})

    # Personas en L (ejecutan con apoyo) sin observación aprobada: candidatas a observar en el puesto.
    observada = select(Observacion.id).where(Observacion.usuario_id == NivelIluo.usuario_id,
                                             Observacion.tarea_id == NivelIluo.tarea_id,
                                             Observacion.aprobada.is_(True)).exists()
    q_ob = _en_alcance(
        select(NivelIluo.usuario_id, Usuario.nombre, NivelIluo.tarea_id, Tarea.nombre, Tarea.codigo)
        .join(Usuario, Usuario.id == NivelIluo.usuario_id).join(Tarea, Tarea.id == NivelIluo.tarea_id)
        .where(Usuario.activo.is_(True), NivelIluo.nivel == 2, ~observada),
        Usuario.departamento_id, actor)
    observaciones = [{"usuario_id": uid, "persona": persona, "tarea_id": tid, "tarea": tarea, "codigo": codigo}
                     for uid, persona, tid, tarea, codigo in bd.execute(q_ob.order_by(Usuario.nombre).limit(8)).all()]

    ambito = "Toda la planta"
    if not actor.es_admin:
        dep = bd.get(Departamento, actor.departamento_id)
        ambito = dep.nombre if dep else None
    return {
        "ambito": ambito,
        "personas": cuenta["personas"],
        "pendientes_validar": cuenta["pendientes"],
        "aportaciones": aportaciones,
        "lagunas_abiertas": cuenta["lagunas"],
        "lagunas": lagunas,
        "reevaluaciones_total": cuenta["reevaluaciones"],
        "reevaluaciones": reevaluaciones,
        "observaciones_sugeridas": observaciones,
    }


# --------------------------------------------------------------------------- cifras


def _contar(bd: Session, **consultas: Select) -> dict[str, int]:
    """Varios recuentos en una sola ida y vuelta a la base de datos (SELECT de subconsultas)."""
    fila = bd.execute(select(*(c.scalar_subquery().label(k) for k, c in consultas.items()))).one()
    return {k: int(v or 0) for k, v in fila._mapping.items()}


def _cifras_planta(bd: Session) -> dict[str, Any]:
    semana = _ahora() - timedelta(days=7)
    n = _contar(
        bd,
        personas=select(func.count(Usuario.id)).where(Usuario.activo.is_(True)),
        departamentos=select(func.count(Departamento.id)),
        documentos=select(func.count(Documento.id)).where(Documento.estado == "listo"),
        documentos_procesando=select(func.count(Documento.id)).where(Documento.estado.in_(["procesando", "error"])),
        instrucciones_publicadas=select(func.count(Instruccion.id)).where(Instruccion.estado == "publicada"),
        consultas=select(func.count(Consulta.id)).where(Consulta.creada >= semana),
        con_respaldo=select(func.count(Consulta.id)).where(Consulta.creada >= semana, Consulta.con_respaldo.is_(True)),
        lagunas_abiertas=select(func.count(Laguna.id)).where(Laguna.estado == "abierta"),
    )
    return {
        "personas": n["personas"],
        "departamentos": n["departamentos"],
        "documentos": n["documentos"],
        "documentos_procesando": n["documentos_procesando"],
        "instrucciones_publicadas": n["instrucciones_publicadas"],
        "consultas_semana": n["consultas"],
        "pct_con_respaldo": round(100 * n["con_respaldo"] / n["consultas"]) if n["consultas"] else None,
        "lagunas_abiertas": n["lagunas_abiertas"],
    }


def _cifras_personales(bd: Session, u: Usuario) -> dict[str, Any]:
    semana = _ahora() - timedelta(days=7)
    return _contar(
        bd,
        tareas_autonomas=select(func.count(NivelIluo.id)).where(NivelIluo.usuario_id == u.id, NivelIluo.nivel >= 3),
        tareas_en_formacion=select(func.count(NivelIluo.id)).where(
            NivelIluo.usuario_id == u.id, NivelIluo.nivel.in_([1, 2])),
        ejecuciones=select(func.count(Ejecucion.id)).where(Ejecucion.usuario_id == u.id, Ejecucion.estado == "completada"),
        consultas_semana=select(func.count(Consulta.id)).where(Consulta.usuario_id == u.id, Consulta.creada >= semana),
        aportaciones_validadas=select(func.count(Aportacion.id)).where(
            Aportacion.autor_id == u.id, Aportacion.estado == "validada"),
    )


# --------------------------------------------------------------------------- contadores compartidos


def _borradores(bd: Session, actor: Actor) -> int:
    return bd.scalar(select(func.count(Instruccion.id)).where(
        Instruccion.autor_id == actor.id, Instruccion.estado == "borrador")) or 0


def _preguntas_por_revisar(bd: Session, actor: Actor) -> int:
    """Preguntas de evaluación propuestas por la IA que esperan a un experto de su departamento."""
    if not actor.es_experto:
        return 0
    q = (select(func.count(PreguntaEval.id)).join(Instruccion, Instruccion.id == PreguntaEval.instruccion_id)
         .join(Tarea, Tarea.id == Instruccion.tarea_id).join(Puesto, Puesto.id == Tarea.puesto_id)
         .where(PreguntaEval.estado == "propuesta", Instruccion.estado != "obsoleta"))
    if not actor.es_admin:
        if actor.departamento_id is None:
            return 0
        q = q.where(Puesto.departamento_id == actor.departamento_id)
    return bd.scalar(q) or 0


def _cuestionarios_disponibles(bd: Session, u: Usuario, origen: dict[int, str]) -> int:
    """Cuestionarios pendientes con el mismo criterio que la página de Evaluación.

    De cada tarea suya se toma la versión vigente (la publicada más reciente); cuenta si tiene
    preguntas aprobadas y la persona aún no la ha superado, o si su nivel pide reevaluación.
    """
    if not origen:
        return 0
    tareas = list(origen)
    ultima = (select(Instruccion.tarea_id, func.max(Instruccion.version).label("version"))
              .where(Instruccion.tarea_id.in_(tareas), Instruccion.estado == "publicada")
              .group_by(Instruccion.tarea_id).subquery())
    vigentes = bd.execute(select(Instruccion.id, Instruccion.tarea_id).join(
        ultima, and_(Instruccion.tarea_id == ultima.c.tarea_id, Instruccion.version == ultima.c.version))).all()
    if not vigentes:
        return 0
    ids = [iid for iid, _ in vigentes]
    con_preguntas = set(bd.scalars(select(PreguntaEval.instruccion_id).where(
        PreguntaEval.instruccion_id.in_(ids), PreguntaEval.estado == "aprobada").distinct()).all())
    superadas = set(bd.scalars(select(IntentoEval.instruccion_id).where(
        IntentoEval.usuario_id == u.id, IntentoEval.instruccion_id.in_(ids), IntentoEval.aprobado.is_(True))
        .distinct()).all())
    reevaluar = set(bd.scalars(select(NivelIluo.tarea_id).where(
        NivelIluo.usuario_id == u.id, NivelIluo.tarea_id.in_(tareas), NivelIluo.requiere_reevaluacion.is_(True))).all())
    return sum(1 for iid, tid in vigentes if iid in con_preguntas and (iid not in superadas or tid in reevaluar))


# --------------------------------------------------------------------------- rutas


@router.get("")
def inicio(actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    u = actor.usuario
    assert u is not None
    nombre_corto = u.nombre.split()[0] if u.nombre.strip() else u.usuario
    permitidos = set(servicios(actor))
    origen = tareas_de_persona(bd, u)
    tareas = _mis_tareas(bd, u, origen)
    aportaciones = [
        {"id": a.id, "titulo": a.titulo or (a.problema or a.texto_original or "Aportación")[:90], "estado": a.estado,
         "creada": _iso(a.creada)}
        for a in bd.scalars(select(Aportacion).where(Aportacion.autor_id == u.id)
                            .order_by(Aportacion.creada.desc()).limit(5)).all()
    ]
    datos: dict[str, Any] = {
        "nombre": u.nombre,
        "nombre_corto": nombre_corto,
        "saludo": _saludo(nombre_corto),
        "rol": u.rol,
        "es_experto": actor.es_experto,
        "puesto": u.puesto.nombre if u.puesto else None,
        "accesos": [a for a in ACCESOS if a["clave"] in permitidos],
        "continuar": _continuar(bd, u),
        "cifras": _cifras_personales(bd, u),
        "mis_tareas": tareas[:12],
        "mis_tareas_total": len(tareas),
        "mis_aportaciones": aportaciones,
        "cuestionarios_disponibles": _cuestionarios_disponibles(bd, u, origen),
        "experto": None,
        "equipo": None,
        "planta": None,
    }
    if actor.es_experto:
        datos["experto"] = {"borradores": _borradores(bd, actor), "preguntas_por_revisar": _preguntas_por_revisar(bd, actor)}
    if actor.es_jefe:
        datos["equipo"] = _bandejas(bd, actor)
    if actor.es_admin:
        datos["planta"] = _cifras_planta(bd)
    return datos


@router.get("/contadores")
def contadores(actor: Actor = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> dict[str, int]:
    """Números de la barra lateral: claves 'aportaciones', 'lagunas', 'borradores' y 'evaluacion'."""
    u = actor.usuario
    assert u is not None
    salida = {"aportaciones": 0, "lagunas": 0, "borradores": 0, "evaluacion": 0}
    if actor.es_jefe and (actor.es_admin or actor.departamento_id is not None):
        salida.update(_contar(
            bd,
            aportaciones=_en_alcance(select(func.count(Aportacion.id)).where(Aportacion.estado == "pendiente"),
                                     Aportacion.departamento_id, actor),
            lagunas=_en_alcance(select(func.count(Laguna.id)).where(Laguna.estado == "abierta"),
                                Laguna.departamento_id, actor),
        ))
    if actor.es_experto:
        from cidia.servicios.instrucciones import contar_borradores

        salida["borradores"] = contar_borradores(bd, actor)
    from cidia.servicios.evaluacion import contar_pendientes

    salida["evaluacion"] = contar_pendientes(bd, actor)
    return salida
