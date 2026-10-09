"""Reglas ILUO paso a paso, caducidad, reevaluación por versión nueva y validación de formadores."""

from datetime import timedelta

import pytest
from ayudas_evaluacion import (
    actor,
    ejecucion,
    hasta_l,
    intento,
    nivel_guardado,
    nueva_instruccion,
    nueva_tarea,
    observacion,
)
from fastapi import HTTPException
from sqlalchemy import func, select

from cidia.modelos import Formacion, NivelIluo, SentenciaXapi, ahora
from cidia.servicios import iluo

pytestmark = pytest.mark.usefixtures("app")  # crea las tablas aunque la prueba no use el cliente


def _certificados(bd, usuario_id, tarea_id):
    bd.expire_all()
    return bd.scalars(select(SentenciaXapi).where(SentenciaXapi.verbo == "certifico",
                                                  SentenciaXapi.actor_id == usuario_id,
                                                  SentenciaXapi.objeto_id == str(tarea_id))
                      .order_by(SentenciaXapi.momento)).all()


def _recalcular(bd, usuario, tarea):
    fila = iluo.recalcular(bd, usuario.id, tarea.id)
    bd.commit()
    return fila


def test_letras_y_configuracion(bd):
    assert [iluo.nivel_letra(n) for n in range(5)] == ["", "I", "L", "U", "O"]
    assert iluo.nivel_letra(9) == ""
    cfg = iluo.configuracion(bd)
    assert cfg["ejecuciones_para_L"] >= 1 and 0 < cfg["umbral_cuestionario"] <= 1 and cfg["meses_validez"] >= 1


def test_de_i_a_o_paso_a_paso(bd, planta):
    luis, ana = planta.personas["luis"], planta.personas["ana"]
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)

    # Sin ninguna evidencia: nivel 0 y no se guarda nada.
    fila = _recalcular(bd, luis, tarea)
    assert fila.nivel == 0 and nivel_guardado(bd, luis, tarea) is None

    # I: ha iniciado una ejecución.
    ejecucion(bd, luis, tarea, ins, estado="en_curso")
    fila = _recalcular(bd, luis, tarea)
    assert fila.nivel == 1 and fila.desde is not None and fila.caduca > ahora() + timedelta(days=300)
    assert fila.evidencias["actividad"]["tipo"] == "ejecucion"

    # Cuestionario aprobado pero sin las ejecuciones necesarias: sigue en I.
    intento(bd, luis, ins)
    assert _recalcular(bd, luis, tarea).nivel == 1

    # L: tres ejecuciones completadas (la última con una consulta en un paso crítico).
    ejecucion(bd, luis, tarea, ins)
    ejecucion(bd, luis, tarea, ins, consultas=3)
    ejecucion(bd, luis, tarea, ins, consultas=2, criticos=1)
    fila = _recalcular(bd, luis, tarea)
    assert fila.nivel == 2
    assert fila.evidencias["cuestionario"]["instruccion_id"] == ins.id
    assert fila.evidencias["ejecuciones"]["completadas"] == 3

    # Observación aprobada, pero la última ejecución tuvo consultas en críticos: sigue en L.
    observacion(bd, ana, luis, tarea, ins)
    assert _recalcular(bd, luis, tarea).nivel == 2

    # U: una ejecución sin consultas en pasos críticos.
    ejecucion(bd, luis, tarea, ins, consultas=1, criticos=0)
    fila = _recalcular(bd, luis, tarea)
    assert fila.nivel == 3 and fila.evidencias["observacion"]["evaluador"] == "Ana López"

    # O: validado como formador por la jefa de su departamento.
    fila = iluo.validar_formador(bd, actor(ana), luis.id, tarea.id)
    bd.commit()
    assert fila.nivel == 4 and fila.formador_validado and fila.evidencias["formador"]["por"] == "Ana López"

    # Cada subida dejó su sentencia «certifico» con la letra alcanzada.
    assert [s.resultado["nivel"] for s in _certificados(bd, luis.id, tarea.id)] == ["I", "L", "U", "O"]
    assert [h["tipo"] for h in fila.evidencias["historial"]].count("subida") == 4

    # Nunca baja solo: un suspenso y una ejecución con consultas en críticos no le quitan el nivel.
    intento(bd, luis, ins, aprobado=False)
    ejecucion(bd, luis, tarea, ins, consultas=5, criticos=2)
    assert _recalcular(bd, luis, tarea).nivel == 4


def test_formacion_activa_da_nivel_i(bd, planta):
    """Marta (Producción) tiene una formación activa en Oficina técnica: sus tareas cuentan como iniciadas."""
    marta = planta.personas["marta"]
    tarea = nueva_tarea(bd, planta, "ot")
    nueva_instruccion(bd, tarea)
    fila = _recalcular(bd, marta, tarea)
    assert fila.nivel == 1 and fila.evidencias["actividad"]["tipo"] == "formacion"
    # Pedro no se forma en Oficina técnica.
    assert _recalcular(bd, planta.personas["pedro"], tarea).nivel == 0


def test_validar_formador_permisos_y_requisitos(bd, planta):
    luis, ana = planta.personas["luis"], planta.personas["ana"]
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    hasta_l(bd, luis, tarea, ins)
    _recalcular(bd, luis, tarea)

    # Jefe y experta de otro departamento, o el propio interesado: no pueden.
    for quien in ("javier", "carmen", "luis", "pedro"):
        with pytest.raises(HTTPException) as e:
            iluo.validar_formador(bd, actor(planta.personas[quien]), luis.id, tarea.id)
        assert e.value.status_code == 403
    bd.rollback()

    # Con nivel L todavía no se puede validar como formador.
    with pytest.raises(HTTPException) as e:
        iluo.validar_formador(bd, actor(ana), luis.id, tarea.id)
    assert e.value.status_code == 400 and "nivel U" in e.value.detail
    bd.rollback()

    # La administración sí puede (una vez alcanzado U).
    observacion(bd, ana, luis, tarea, ins)
    assert _recalcular(bd, luis, tarea).nivel == 3
    fila = iluo.validar_formador(bd, actor(planta.personas["admin"]), luis.id, tarea.id)
    bd.commit()
    assert fila.nivel == 4


def test_caducidad_vuelve_a_calcular_con_evidencias_recientes(bd, planta):
    luis, ana = planta.personas["luis"], planta.personas["ana"]
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    hace_14_meses = ahora() - timedelta(days=425)
    intento(bd, luis, ins, cuando=hace_14_meses)
    for _ in range(3):
        ejecucion(bd, luis, tarea, ins, cuando=hace_14_meses)
    observacion(bd, ana, luis, tarea, ins, cuando=hace_14_meses)
    bd.add(NivelIluo(usuario_id=luis.id, tarea_id=tarea.id, nivel=3, desde=hace_14_meses,
                     caduca=ahora() - timedelta(days=60), evidencias={}))
    bd.commit()

    # Caducado y sin evidencias en los últimos 12 meses: baja a 0 y queda constancia.
    fila = _recalcular(bd, luis, tarea)
    assert fila.nivel == 0 and fila.caduca is None
    assert fila.evidencias["historial"][-1]["tipo"] == "caducidad"
    assert fila.evidencias["historial"][-1]["nivel_anterior"] == 3

    # Con evidencias recientes vuelve a subir.
    hasta_l(bd, luis, tarea, ins)
    assert _recalcular(bd, luis, tarea).nivel == 2


def test_caducidad_con_evidencias_vigentes_renueva(bd, planta):
    luis = planta.personas["luis"]
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    hasta_l(bd, luis, tarea, ins)
    bd.add(NivelIluo(usuario_id=luis.id, tarea_id=tarea.id, nivel=2, desde=ahora() - timedelta(days=400),
                     caduca=ahora() - timedelta(days=1), evidencias={}))
    bd.commit()
    fila = _recalcular(bd, luis, tarea)
    assert fila.nivel == 2 and fila.caduca > ahora() + timedelta(days=300)
    assert _certificados(bd, luis.id, tarea.id)[-1].contexto["motivo"] == "renovacion"


def test_sin_caducar_no_baja_aunque_falten_evidencias(bd, planta):
    luis = planta.personas["luis"]
    tarea = nueva_tarea(bd, planta, "ot")
    nueva_instruccion(bd, tarea)
    bd.add(NivelIluo(usuario_id=luis.id, tarea_id=tarea.id, nivel=3, desde=ahora(),
                     caduca=ahora() + timedelta(days=200), evidencias={}))
    bd.commit()
    assert _recalcular(bd, luis, tarea).nivel == 3


def test_reevaluacion_al_publicar_version_nueva(bd, planta):
    luis, marta = planta.personas["luis"], planta.personas["marta"]
    tarea = nueva_tarea(bd, planta, "ot")
    v1 = nueva_instruccion(bd, tarea)
    hasta_l(bd, luis, tarea, v1)
    assert _recalcular(bd, luis, tarea).nivel == 2
    assert _recalcular(bd, marta, tarea).nivel == 1  # en formación: no tiene nada que reevaluar

    # Se publica la versión 2: la anterior queda obsoleta y se marca a quien tiene L o más.
    v1.estado = "obsoleta"
    v2 = nueva_instruccion(bd, tarea, version=2)
    assert iluo.marcar_reevaluacion(bd, tarea.id) == 1
    bd.commit()
    fila = nivel_guardado(bd, luis, tarea)
    assert fila.requiere_reevaluacion and fila.nivel == 2
    assert not nivel_guardado(bd, marta, tarea).requiere_reevaluacion

    # Recalcular no le baja el nivel aunque su cuestionario era de la versión anterior.
    fila = _recalcular(bd, luis, tarea)
    assert fila.nivel == 2 and fila.requiere_reevaluacion

    # Aprueba el cuestionario de la versión 2: reevaluado.
    intento(bd, luis, v2)
    fila = _recalcular(bd, luis, tarea)
    assert fila.nivel == 2 and not fila.requiere_reevaluacion
    assert fila.evidencias["historial"][-1]["tipo"] == "reevaluado"


def test_ajuste_manual_baja_y_corta_evidencias(bd, planta):
    luis, ana = planta.personas["luis"], planta.personas["ana"]
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    hasta_l(bd, luis, tarea, ins)
    assert _recalcular(bd, luis, tarea).nivel == 2

    fila = iluo.ajustar(bd, actor(ana), luis.id, tarea.id, 1, "Ha cambiado el útil y tiene que repetir la formación")
    bd.commit()
    assert fila.nivel == 1 and fila.evidencias.get("corte")
    # Las evidencias anteriores al ajuste ya no lo vuelven a subir.
    assert _recalcular(bd, luis, tarea).nivel == 1
    n = bd.scalar(select(func.count()).select_from(SentenciaXapi).where(SentenciaXapi.verbo == "certifico",
                                                                         SentenciaXapi.actor_id == luis.id,
                                                                         SentenciaXapi.objeto_id == str(tarea.id)))
    assert n == 1  # solo la subida a L; el ajuste a la baja no certifica nada

    # Sin motivo, o desde otro departamento: no.
    with pytest.raises(HTTPException) as e:
        iluo.ajustar(bd, actor(ana), luis.id, tarea.id, 3, "")
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        iluo.ajustar(bd, actor(planta.personas["javier"]), luis.id, tarea.id, 3, "Motivo suficiente")
    assert e.value.status_code == 403
    bd.rollback()


def test_formacion_con_puesto_solo_incluye_ese_puesto(bd, planta):
    pedro = planta.personas["pedro"]
    tarea = nueva_tarea(bd, planta, "ot")
    f = Formacion(usuario_id=pedro.id, departamento_id=planta.deps["ot"].id, puesto_id=planta.puestos["ot"].id,
                  estado="activa")
    bd.add(f)
    bd.commit()
    try:
        assert _recalcular(bd, pedro, tarea).nivel == 1
    finally:
        f.estado = "cancelada"
        bd.commit()
