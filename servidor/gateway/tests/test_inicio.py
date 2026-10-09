"""Pruebas del panel de inicio y de los contadores de la barra lateral.

Cada prueba crea su propio departamento (con nombre único) para que las cifras no dependan
de lo que hayan dejado otras pruebas en la misma base de datos.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

import pytest
from fabrica import CONTRASENA, cab
from sqlalchemy import func, select

from cidia.modelos import (
    Aportacion,
    Consulta,
    Departamento,
    Ejecucion,
    EjecucionPaso,
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
    ahora,
)
from cidia.seguridad import Actor, hash_contrasena
from cidia.servicios import evaluacion


@dataclass
class Taller:
    s: str
    dep: Departamento
    puesto: Puesto
    tareas: list[Tarea]
    jefa: Usuario
    operario: Usuario
    experto: Usuario
    otro: Usuario


_HASH: dict[str, str] = {}


def _taller(bd, planta) -> Taller:
    """Departamento nuevo con un puesto, dos tareas, una jefa, un operario y un experto."""
    if "h" not in _HASH:
        _HASH["h"] = hash_contrasena(CONTRASENA)
    s = uuid.uuid4().hex[:6]
    dep = Departamento(nombre=f"Taller {s}", codigo=f"T{s}")
    bd.add(dep)
    bd.flush()
    puesto = Puesto(departamento_id=dep.id, nombre="Prensas")
    bd.add(puesto)
    bd.flush()
    tareas = [Tarea(puesto_id=puesto.id, codigo=f"PR-{s}-{i}", nombre=f"Cambio de molde {i}", criticidad=3)
              for i in (1, 2)]
    bd.add_all(tareas)
    personas = []
    for nombre, rol, experto in (("Jefa", "jefe", False), ("Operario", "empleado", False),
                                 ("Experta", "empleado", True), ("Otro", "empleado", False)):
        u = Usuario(usuario=f"{nombre.lower()}.{s}", nombre=f"{nombre} {s}", hash_contrasena=_HASH["h"],
                    departamento_id=dep.id, puesto_id=puesto.id, nivel_id=planta.niveles[2].id, rol=rol,
                    es_experto=experto)
        bd.add(u)
        personas.append(u)
    bd.commit()
    return Taller(s, dep, puesto, tareas, *personas)


def _publicar(bd, tarea: Tarea, n_pasos: int = 3, estado: str = "publicada", autor_id: int | None = None) -> Instruccion:
    version = (bd.scalar(select(func.max(Instruccion.version)).where(Instruccion.tarea_id == tarea.id)) or 0) + 1
    ins = Instruccion(tarea_id=tarea.id, titulo=f"IT {tarea.nombre}", estado=estado, autor_id=autor_id,
                      version=version)
    bd.add(ins)
    bd.flush()
    for i in range(1, n_pasos + 1):
        bd.add(Paso(instruccion_id=ins.id, orden=i, titulo=f"Paso {i}", es_critico=i == 2))
    bd.commit()
    return ins


@pytest.fixture
def taller(cliente, bd, planta) -> Taller:
    return _taller(bd, planta)


def test_inicio_y_contadores_piden_sesion(cliente):
    h = cab(cliente, "invitado")
    assert cliente.get("/api/inicio", headers=h).status_code == 401
    assert cliente.get("/api/inicio/contadores", headers=h).status_code == 401
    assert cliente.get("/api/inicio").status_code == 401


def test_inicio_empleado(cliente, bd, taller):
    t1, t2 = taller.tareas
    op = taller.operario
    ins = _publicar(bd, t1)
    bd.add(NivelIluo(usuario_id=op.id, tarea_id=t1.id, nivel=2, requiere_reevaluacion=True))
    # Ejecución a medias: dos de tres pasos confirmados.
    ej = Ejecucion(usuario_id=op.id, tarea_id=t1.id, instruccion_id=ins.id, estado="en_curso")
    bd.add(ej)
    bd.flush()
    for p in ins.pasos[:2]:
        bd.add(EjecucionPaso(ejecucion_id=ej.id, paso_id=p.id, confirmado_en=ahora()))
    bd.add(Aportacion(autor_id=op.id, departamento_id=taller.dep.id, titulo="Atasco en la prensa", estado="pendiente"))
    bd.add(Consulta(usuario_id=op.id, pregunta="¿Qué par de apriete?", con_respaldo=True))
    bd.commit()

    r = cliente.get("/api/inicio", headers=cab(cliente, op.usuario))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["nombre_corto"] == "Operario" and d["saludo"].endswith(", Operario")
    assert [a["clave"] for a in d["accesos"]] == ["planta", "chat", "formacion", "aportaciones"]
    assert d["equipo"] is None and d["planta"] is None and d["experto"] is None
    # Continúa donde lo dejaste: la ejecución en curso.
    assert d["continuar"]["tipo"] == "ejecucion"
    assert d["continuar"]["ruta"] == f"/planta/ejecucion/{ej.id}"
    assert d["continuar"]["detalle"] == "Paso 3 de 3" and d["continuar"]["progreso"] == 67
    # Mis tareas: las dos del puesto, primero la que pide reevaluación.
    assert [t["id"] for t in d["mis_tareas"]] == [t1.id, t2.id]
    primera = d["mis_tareas"][0]
    assert primera["letra"] == "L" and primera["requiere_reevaluacion"] and primera["instruccion_id"] == ins.id
    assert d["mis_tareas"][1]["nivel"] == 0 and d["mis_tareas"][1]["instruccion_id"] is None
    assert d["mis_aportaciones"][0]["titulo"] == "Atasco en la prensa"
    assert d["cifras"]["consultas_semana"] == 1 and d["cifras"]["tareas_en_formacion"] == 1
    # Las etiquetas de departamento y nivel no se muestran al empleado.
    assert "departamento" not in d and "nivel" not in d


def test_continuar_con_microlecciones(cliente, bd, taller):
    t1 = taller.tareas[0]
    op = taller.otro
    ins = _publicar(bd, t1)
    micros = [Microleccion(instruccion_id=ins.id, orden=i, titulo=f"Lección {i}", contenido="...") for i in (1, 2, 3)]
    bd.add_all(micros)
    bd.flush()
    bd.add(MicroleccionVista(usuario_id=op.id, microleccion_id=micros[0].id))
    bd.commit()
    d = cliente.get("/api/inicio", headers=cab(cliente, op.usuario)).json()
    assert d["continuar"]["tipo"] == "microleccion"
    assert d["continuar"]["ruta"] == f"/formacion/tarea/{t1.id}"
    assert d["continuar"]["detalle"] == "1 de 3 micro-lecciones vistas"
    for m in micros[1:]:
        bd.add(MicroleccionVista(usuario_id=op.id, microleccion_id=m.id))
    bd.commit()
    d = cliente.get("/api/inicio", headers=cab(cliente, op.usuario)).json()
    assert d["continuar"]["tipo"] == "evaluacion" and d["continuar"]["ruta"] == "/evaluacion"


def test_inicio_jefe_ve_solo_su_departamento(cliente, bd, planta, taller):
    t1, t2 = taller.tareas
    op, exp = taller.operario, taller.experto
    otro_taller = _taller(bd, planta)
    bd.add_all([
        Aportacion(autor_id=op.id, departamento_id=taller.dep.id, titulo="Truco del molde", estado="pendiente"),
        Aportacion(autor_id=op.id, departamento_id=taller.dep.id, titulo="Ya validada", estado="validada"),
        Aportacion(autor_id=otro_taller.operario.id, departamento_id=otro_taller.dep.id, titulo="De otro taller",
                   estado="pendiente"),
        Laguna(pregunta="¿Qué presión lleva el cilindro?", departamento_id=taller.dep.id, frecuencia=3),
        Laguna(pregunta="¿Cómo se purga?", departamento_id=otro_taller.dep.id, frecuencia=9),
        NivelIluo(usuario_id=op.id, tarea_id=t1.id, nivel=3, requiere_reevaluacion=True),
        NivelIluo(usuario_id=exp.id, tarea_id=t2.id, nivel=3, caduca=ahora() - timedelta(days=1)),
        NivelIluo(usuario_id=exp.id, tarea_id=t1.id, nivel=2),  # en L sin observar: sugerida
        NivelIluo(usuario_id=op.id, tarea_id=t2.id, nivel=2),  # en L ya observado: no se sugiere
        Observacion(usuario_id=op.id, tarea_id=t2.id, aprobada=True),
        NivelIluo(usuario_id=otro_taller.operario.id, tarea_id=otro_taller.tareas[0].id, nivel=2),
    ])
    bd.commit()

    h = cab(cliente, taller.jefa.usuario)
    d = cliente.get("/api/inicio", headers=h).json()
    eq = d["equipo"]
    assert eq["ambito"] == taller.dep.nombre and eq["personas"] == 4
    assert eq["pendientes_validar"] == 1 and [a["titulo"] for a in eq["aportaciones"]] == ["Truco del molde"]
    assert eq["lagunas_abiertas"] == 1 and eq["lagunas"][0]["frecuencia"] == 3
    assert eq["reevaluaciones_total"] == 2
    motivos = {(r["persona"], r["motivo"]) for r in eq["reevaluaciones"]}
    assert motivos == {(op.nombre, "Nueva versión de la instrucción"), (exp.nombre, "Nivel caducado")}
    assert [(o["persona"], o["tarea_id"]) for o in eq["observaciones_sugeridas"]] == [(exp.nombre, t1.id)]
    assert d["planta"] is None and d["experto"] is not None

    c = cliente.get("/api/inicio/contadores", headers=h).json()
    assert c["aportaciones"] == 1 and c["lagunas"] == 1


def test_inicio_admin_cifras_de_planta(cliente, bd, taller):
    antes = cliente.get("/api/inicio", headers=cab(cliente, "admin")).json()["planta"]
    bd.add_all([
        Consulta(usuario_id=taller.operario.id, pregunta="a", con_respaldo=True),
        Consulta(usuario_id=taller.operario.id, pregunta="b", con_respaldo=False),
        Consulta(usuario_id=taller.operario.id, pregunta="vieja", con_respaldo=True, creada=ahora() - timedelta(days=9)),
    ])
    _publicar(bd, taller.tareas[0])
    bd.commit()
    d = cliente.get("/api/inicio", headers=cab(cliente, "admin")).json()
    p = d["planta"]
    assert p["consultas_semana"] == antes["consultas_semana"] + 2
    assert p["instrucciones_publicadas"] == antes["instrucciones_publicadas"] + 1
    assert p["personas"] >= 4 and p["departamentos"] >= 1
    assert 0 <= p["pct_con_respaldo"] <= 100
    # La administración ve las bandejas de toda la planta.
    assert d["equipo"]["ambito"] == "Toda la planta"


def test_contadores_por_rol(cliente, bd, taller):
    t1, t2 = taller.tareas
    op, exp, jefa = taller.operario, taller.experto, taller.jefa
    ins = _publicar(bd, t1)
    borrador = _publicar(bd, t2, estado="borrador", autor_id=exp.id)
    bd.add_all([
        PreguntaEval(instruccion_id=ins.id, enunciado="¿Qué EPI?", opciones=["a", "b"], estado="aprobada"),
        PreguntaEval(instruccion_id=ins.id, enunciado="¿Qué par?", opciones=["a", "b"], estado="propuesta"),
        PreguntaEval(instruccion_id=borrador.id, enunciado="¿Orden?", opciones=["a", "b"], estado="propuesta"),
        Aportacion(autor_id=op.id, departamento_id=taller.dep.id, titulo="Pendiente", estado="pendiente"),
        Laguna(pregunta="¿Dónde está la llave?", departamento_id=taller.dep.id),
    ])
    bd.commit()

    # Empleado: solo su cuestionario disponible.
    c = cliente.get("/api/inicio/contadores", headers=cab(cliente, op.usuario)).json()
    assert c == {"aportaciones": 0, "lagunas": 0, "borradores": 0, "evaluacion": 1}
    # Al aprobarlo deja de contar.
    bd.add(IntentoEval(usuario_id=op.id, instruccion_id=ins.id, aprobado=True, aciertos=1, total=1, puntuacion=1.0))
    bd.commit()
    assert cliente.get("/api/inicio/contadores", headers=cab(cliente, op.usuario)).json()["evaluacion"] == 0

    # Experta: su borrador, su cuestionario y las preguntas propuestas de su departamento.
    c = cliente.get("/api/inicio/contadores", headers=cab(cliente, exp.usuario)).json()
    assert c["borradores"] == 1 and c["evaluacion"] == 1 + 2
    assert c["aportaciones"] == 0 and c["lagunas"] == 0
    d = cliente.get("/api/inicio", headers=cab(cliente, exp.usuario)).json()
    assert d["experto"] == {"borradores": 1, "preguntas_por_revisar": 2} and d["equipo"] is None

    # Jefa: bandejas de su departamento (y también es experta a efectos de preguntas). Los
    # borradores cuentan los de su departamento, y Evaluación suma además las observaciones
    # sugeridas: el número coincide con la página (evaluacion.contar_pendientes).
    c = cliente.get("/api/inicio/contadores", headers=cab(cliente, jefa.usuario)).json()
    assert c["aportaciones"] == 1 and c["lagunas"] == 1 and c["borradores"] == 1
    assert c["evaluacion"] == evaluacion.contar_pendientes(bd, Actor(sesion=None, usuario=jefa))  # type: ignore[arg-type]
    assert c["evaluacion"] >= 1 + 2

    # Un jefe de otro departamento no ve nada de este.
    c = cliente.get("/api/inicio/contadores", headers=cab(cliente, "ana")).json()
    otro = cliente.get("/api/inicio", headers=cab(cliente, "ana")).json()["equipo"]
    assert "Pendiente" not in [a["titulo"] for a in otro["aportaciones"]]
    assert "¿Dónde está la llave?" not in [la["pregunta"] for la in otro["lagunas"]]


def test_formacion_activa_suma_tareas(cliente, bd, planta, taller):
    """Una formación en otro departamento añade sus tareas a «mis tareas»."""
    from cidia.modelos import Formacion

    op = taller.operario
    bd.add(Formacion(usuario_id=op.id, departamento_id=planta.deps["ot"].id, puesto_id=planta.puestos["ot"].id))
    bd.commit()
    d = cliente.get("/api/inicio", headers=cab(cliente, op.usuario)).json()
    origenes = {t["id"]: t["origen"] for t in d["mis_tareas"]}
    assert origenes[planta.tareas["ot"].id] == "formacion"
    assert origenes[taller.tareas[0].id] == "puesto"


def test_inicio_coincide_con_progreso_y_evaluacion(cliente, bd, planta, taller):
    """«Mis tareas» y el contador de Evaluación usan las mismas reglas que «Mi progreso» y la
    página de Evaluación (si no, la barra lateral anunciaría cuestionarios que luego no aparecen)."""
    from cidia.modelos import Formacion
    from cidia.rutas.inicio import tareas_de_persona
    from cidia.seguridad import Actor
    from cidia.servicios import evaluacion, progreso

    t1, t2 = taller.tareas
    op, otro = taller.operario, taller.otro
    ins = _publicar(bd, t1)
    bd.add(PreguntaEval(instruccion_id=ins.id, enunciado="¿Qué EPI?", opciones=["a", "b"], estado="aprobada"))
    # Sin puesto: solo cuenta lo que ya ha empezado (aquí, una ejecución de t1).
    sin_puesto = Usuario(usuario=f"sinpuesto.{taller.s}", nombre="Sin Puesto", hash_contrasena=hash_contrasena(CONTRASENA),
                         departamento_id=taller.dep.id, nivel_id=planta.niveles[3].id)
    bd.add(sin_puesto)
    bd.flush()
    bd.add(Ejecucion(usuario_id=sin_puesto.id, tarea_id=t1.id, instruccion_id=ins.id, estado="abandonada"))
    # Formación sin puesto: todas las tareas activas del otro departamento.
    bd.add(Formacion(usuario_id=otro.id, departamento_id=planta.deps["ot"].id))
    # Ya aprobó el cuestionario, pero la nueva versión pide reevaluación: sigue pendiente.
    bd.add(IntentoEval(usuario_id=op.id, instruccion_id=ins.id, aprobado=True, aciertos=1, total=1, puntuacion=1.0))
    bd.add(NivelIluo(usuario_id=op.id, tarea_id=t1.id, nivel=2, requiere_reevaluacion=True))
    # Una tarea desactivada no aparece en ningún sitio.
    bd.add(NivelIluo(usuario_id=op.id, tarea_id=t2.id, nivel=1))
    t2.activa = False
    bd.commit()

    for u in (op, otro, sin_puesto, taller.jefa):
        bd.expire_all()
        u = bd.get(Usuario, u.id)
        assert set(tareas_de_persona(bd, u)) == {t.id for t in progreso.tareas_de(bd, u)}, u.usuario
        h = cab(cliente, u.usuario)
        c = cliente.get("/api/inicio/contadores", headers=h).json()
        if u.rol == "empleado" and not u.es_experto:
            assert c["evaluacion"] == evaluacion.contar_pendientes(bd, Actor(sesion=None, usuario=u)), u.usuario  # type: ignore[arg-type]
        d = cliente.get("/api/inicio", headers=h).json()
        assert d["mis_tareas_total"] == len(progreso.tareas_de(bd, u))
        if u.rol == "empleado":
            assert d["cuestionarios_disponibles"] == c["evaluacion"] - (d["experto"] or {}).get("preguntas_por_revisar", 0)
        else:  # a un jefe el contador le suma además las observaciones sugeridas
            assert c["evaluacion"] == evaluacion.contar_pendientes(bd, Actor(sesion=None, usuario=u))  # type: ignore[arg-type]

    d = cliente.get("/api/inicio", headers=cab(cliente, op.usuario)).json()
    assert [t["id"] for t in d["mis_tareas"]] == [t1.id] and d["cuestionarios_disponibles"] == 1
    d = cliente.get("/api/inicio", headers=cab(cliente, sin_puesto.usuario)).json()
    assert [(t["id"], t["origen"]) for t in d["mis_tareas"]] == [(t1.id, "historial")]
