"""Evaluación: generación y revisión de preguntas, cuestionario corregido en el servidor y observación."""

import json
from datetime import timedelta

import pytest
from ayudas_evaluacion import (
    ejecucion,
    hasta_l,
    intento,
    nivel_guardado,
    nueva_instruccion,
    nueva_tarea,
    preguntas_basicas,
)
from fabrica import cab
from sqlalchemy import select

from cidia.modelos import IntentoEval, Observacion, PreguntaEval, SentenciaXapi, ahora
from cidia.servicios import evaluacion, iluo

pytestmark = pytest.mark.usefixtures("app")


def _ultima_xapi(bd, verbo, actor_id=None):
    bd.expire_all()
    q = select(SentenciaXapi).where(SentenciaXapi.verbo == verbo)
    if actor_id is not None:
        q = q.where(SentenciaXapi.actor_id == actor_id)
    return bd.scalars(q.order_by(SentenciaXapi.momento.desc()).limit(1)).first()


# --------------------------------------------------------------------------- generación


def test_generar_preguntas_con_el_modelo(bd, planta, ia):
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    ia.json = {"preguntas": [
        {"enunciado": "¿A qué par se aprietan los tornillos de la brida?", "opciones": ["25 N·m", "10 N·m", "40 N·m"],
         "correcta": 0, "explicacion": "El paso 2 indica 25 N·m.", "paso": 2},
        {"enunciado": "¿Cuánto tiempo dura la prueba de estanqueidad?",
         "opciones": ["A) 5 segundos", "B) 30 segundos", "C) 10 minutos", "D) 1 hora", "E) 2 horas"],
         "correcta": "B", "explicacion": "Sin caída de presión en 30 segundos.", "paso": 3},
        {"enunciado": "Mal formada", "opciones": ["solo una"], "correcta": 0},
        {"enunciado": "¿Qué se hace al final con la pieza?", "opciones": ["Etiquetarla", "Tirarla", "Pintarla"],
         "correcta": "Etiquetarla", "paso": 4},
    ]}
    creadas = evaluacion.generar_preguntas(bd, ins.id, n=3)
    bd.commit()
    assert creadas == 3
    preguntas = bd.scalars(select(PreguntaEval).where(PreguntaEval.instruccion_id == ins.id)).all()
    assert all(p.estado == "propuesta" for p in preguntas)
    por_enunciado = {p.enunciado: p for p in preguntas}
    par = por_enunciado["¿A qué par se aprietan los tornillos de la brida?"]
    assert par.opciones[par.correcta] == "25 N·m" and par.paso_id == ins.pasos[1].id
    prueba = por_enunciado["¿Cuánto tiempo dura la prueba de estanqueidad?"]
    assert len(prueba.opciones) == 4 and prueba.opciones[prueba.correcta] == "30 segundos"
    assert "Mal formada" not in por_enunciado
    # El modelo recibió los pasos con los críticos marcados.
    texto = ia.llamadas[-1]["mensajes"][-1]["content"]
    assert "[CRÍTICO] Apretar los cuatro tornillos" in texto

    # Generar otra vez no repite enunciados (se completa con preguntas sencillas).
    evaluacion.generar_preguntas(bd, ins.id, n=3)
    bd.commit()
    enunciados = bd.scalars(select(PreguntaEval.enunciado).where(PreguntaEval.instruccion_id == ins.id)).all()
    assert len(enunciados) == len(set(enunciados)) == 6


def test_generar_preguntas_con_respuestas_raras_del_modelo(bd, planta, ia):
    """Formatos que devuelven los modelos pequeños: opciones repetidas (la correcta no se desplaza),
    opciones como diccionario, claves en inglés, «C) texto» como correcta y opciones marcadas."""
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    ia.json = {"questions": [
        {"enunciado": "¿Qué par hay que aplicar a los tornillos?", "opciones": ["10 N·m", "10 N·m", "25 N·m", "40 N·m"],
         "correcta": 2, "paso": "Paso 2"},
        {"question": "¿Cuánto dura la prueba de aire sin caída de presión?",
         "options": {"A": "5 segundos", "B": "30 segundos", "C": "2 minutos"}, "answer": "B",
         "explanation": "Son 30 segundos."},
        {"enunciado": "¿Qué se hace al final con la pieza?",
         "opciones": ["A) Pintarla", "B) Tirarla", "C) Etiquetarla"], "correcta": "C) Etiquetarla", "paso": 4},
        {"enunciado": "¿Qué se hace primero con la brida?", "opciones": [
            {"texto": "Colocarla en el útil", "correcta": True}, {"texto": "Pintarla"}, {"texto": "Pesarla"}]},
    ]}
    assert evaluacion.generar_preguntas(bd, ins.id, n=4) == 4
    bd.commit()
    por_enunciado = {p.enunciado: p for p in bd.scalars(select(PreguntaEval)
                                                        .where(PreguntaEval.instruccion_id == ins.id))}
    par = por_enunciado["¿Qué par hay que aplicar a los tornillos?"]
    assert par.opciones[par.correcta] == "25 N·m" and len(par.opciones) == 3 and par.paso_id == ins.pasos[1].id
    aire = por_enunciado["¿Cuánto dura la prueba de aire sin caída de presión?"]
    assert aire.opciones[aire.correcta] == "30 segundos" and aire.explicacion == "Son 30 segundos."
    final = por_enunciado["¿Qué se hace al final con la pieza?"]
    assert final.opciones[final.correcta] == "Etiquetarla" and "A) Pintarla" not in final.opciones
    primero = por_enunciado["¿Qué se hace primero con la brida?"]
    assert primero.opciones[primero.correcta] == "Colocarla en el útil"


def test_generar_preguntas_sin_modelo_usa_los_pasos(bd, planta, ia):
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)

    def falla(mensajes):
        raise RuntimeError("modelo caído")

    ia.json = falla
    creadas = evaluacion.generar_preguntas(bd, ins.id, n=4)
    bd.commit()
    assert creadas == 4
    preguntas = bd.scalars(select(PreguntaEval).where(PreguntaEval.instruccion_id == ins.id)
                           .order_by(PreguntaEval.id)).all()
    # Primero los pasos críticos (2 y 3), con distractores de otros pasos.
    assert preguntas[0].enunciado == "¿Qué hay que hacer en el paso 2?"
    assert preguntas[0].opciones[preguntas[0].correcta] == ins.pasos[1].titulo
    assert len(preguntas[0].opciones) == 4 and len(set(preguntas[0].opciones)) == 4
    assert all(p.explicacion for p in preguntas)


def test_generar_preguntas_por_api_y_permisos(cliente, bd, planta, ia):
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    ia.json = {}
    r = cliente.post(f"/api/evaluacion/instrucciones/{ins.id}/generar-preguntas", json={"n": 2},
                     headers=cab(cliente, "ana"))
    assert r.status_code == 200, r.text
    assert r.json()["trabajo_id"] > 0
    assert len(bd.scalars(select(PreguntaEval).where(PreguntaEval.instruccion_id == ins.id)).all()) == 2
    # Empleado sin ser experto, o experta de otro departamento: no.
    assert cliente.post(f"/api/evaluacion/instrucciones/{ins.id}/generar-preguntas",
                        headers=cab(cliente, "luis")).status_code == 403
    assert cliente.post(f"/api/evaluacion/instrucciones/{ins.id}/generar-preguntas",
                        headers=cab(cliente, "carmen")).status_code == 403
    # En una versión obsoleta no se generan preguntas.
    ins.estado = "obsoleta"
    bd.commit()
    r = cliente.post(f"/api/evaluacion/instrucciones/{ins.id}/generar-preguntas", headers=cab(cliente, "ana"))
    assert r.status_code == 400 and "obsoleta" in r.json()["detail"]


# --------------------------------------------------------------------------- revisión del experto


def test_revision_de_preguntas(cliente, bd, planta):
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    aprobada, _, propuesta, _ = preguntas_basicas(bd, ins)
    h = cab(cliente, "ana")

    r = cliente.get(f"/api/evaluacion/preguntas?instruccion_id={ins.id}", headers=h)
    assert r.status_code == 200
    datos = r.json()
    assert len(datos["preguntas"]) == 4 and len(datos["instruccion"]["pasos"]) == 4
    assert "correcta" in datos["preguntas"][0]

    # Aprobar.
    r = cliente.put(f"/api/evaluacion/preguntas/{propuesta.id}", json={"estado": "aprobada"}, headers=h)
    assert r.status_code == 200 and r.json()["estado"] == "aprobada"
    # Editar enunciado, opciones y correcta.
    r = cliente.put(f"/api/evaluacion/preguntas/{propuesta.id}",
                    json={"enunciado": "¿Qué se comprueba al final?", "opciones": ["La etiqueta", "El color", "El peso"],
                          "correcta": 0, "paso_id": ins.pasos[3].id}, headers=h)
    assert r.status_code == 200 and r.json()["paso"]["orden"] == 4
    # Ediciones no válidas.
    assert cliente.put(f"/api/evaluacion/preguntas/{propuesta.id}", json={"opciones": ["solo una"]},
                       headers=h).status_code == 400
    assert cliente.put(f"/api/evaluacion/preguntas/{propuesta.id}", json={"correcta": 7}, headers=h).status_code == 400
    assert cliente.put(f"/api/evaluacion/preguntas/{propuesta.id}", json={"estado": "rara"},
                       headers=h).status_code == 400
    # Descartar y borrar.
    assert cliente.put(f"/api/evaluacion/preguntas/{aprobada.id}", json={"estado": "descartada"},
                       headers=h).json()["estado"] == "descartada"
    id_borrada, ana_id = aprobada.id, planta.personas["ana"].id
    assert cliente.delete(f"/api/evaluacion/preguntas/{id_borrada}", headers=h).status_code == 200
    x = _ultima_xapi(bd, "rechazo", ana_id)  # deja constancia del borrado
    assert x.objeto_id == str(id_borrada) and x.resultado["borrada"] is True
    assert bd.scalar(select(PreguntaEval.id).where(PreguntaEval.id == id_borrada)) is None
    # Añadir a mano: nace aprobada.
    r = cliente.post("/api/evaluacion/preguntas", headers=h, json={
        "instruccion_id": ins.id, "enunciado": "¿Qué EPI hace falta?", "opciones": ["Guantes", "Ninguno"],
        "correcta": 0, "explicacion": "Guantes de corte.", "paso_id": None})
    assert r.status_code == 200 and r.json()["estado"] == "aprobada"

    # Permisos: empleado no experto, experta de otro departamento.
    assert cliente.get(f"/api/evaluacion/preguntas?instruccion_id={ins.id}",
                       headers=cab(cliente, "luis")).status_code == 403
    hc = cab(cliente, "carmen")
    assert cliente.get(f"/api/evaluacion/preguntas?instruccion_id={ins.id}", headers=hc).status_code == 403
    assert cliente.put(f"/api/evaluacion/preguntas/{propuesta.id}", json={"estado": "descartada"},
                       headers=hc).status_code == 403
    assert cliente.delete(f"/api/evaluacion/preguntas/{propuesta.id}", headers=hc).status_code == 403


# --------------------------------------------------------------------------- cuestionario


def test_cuestionario_no_filtra_la_respuesta(cliente, bd, planta):
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    preguntas_basicas(bd, ins)
    r = cliente.get(f"/api/evaluacion/cuestionario/{tarea.id}", headers=cab(cliente, "luis"))
    assert r.status_code == 200, r.text
    datos = r.json()
    assert len(datos["preguntas"]) == 2  # solo las aprobadas
    texto = json.dumps(datos)
    assert "correcta" not in texto and "explicacion" not in texto and "Porque es" not in texto
    assert datos["instruccion"]["version"] == 1
    assert all({"clave", "texto"} == set(o) for p in datos["preguntas"] for o in p["opciones"])


def test_cuestionario_con_claves_opacas(cliente, bd, planta):
    """Las opciones no llevan su posición original (en las preguntas escritas a mano la correcta
    suele ser la primera): se responde con una clave opaca que corrige el servidor."""
    luis = planta.personas["luis"]
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    p1, p2, _, _ = preguntas_basicas(bd, ins)
    h = cab(cliente, "luis")
    datos = cliente.get(f"/api/evaluacion/cuestionario/{tarea.id}", headers=h).json()
    claves = [o["clave"] for p in datos["preguntas"] for o in p["opciones"]]
    assert len(set(claves)) == len(claves) and not any(c in {"0", "1", "2"} for c in claves)
    # Otra petición da las mismas claves (no dependen del orden en que se muestran).
    otra = cliente.get(f"/api/evaluacion/cuestionario/{tarea.id}", headers=h).json()
    assert sorted(claves) == sorted(o["clave"] for p in otra["preguntas"] for o in p["opciones"])

    correctas = {p1.id: p1.opciones[p1.correcta], p2.id: p2.opciones[p2.correcta]}
    elegidas = {str(p["id"]): next(o["clave"] for o in p["opciones"] if o["texto"] == correctas[p["id"]])
                for p in datos["preguntas"]}
    r = cliente.post(f"/api/evaluacion/cuestionario/{tarea.id}/responder", headers=h,
                     json={"instruccion_id": ins.id, "respuestas": elegidas})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["aprobado"] and res["aciertos"] == 2
    assert {c["id"]: c["elegida"] for c in res["correccion"]} == {p1.id: p1.correcta, p2.id: p2.correcta}
    guardado = bd.scalars(select(IntentoEval).where(IntentoEval.usuario_id == luis.id,
                                                    IntentoEval.instruccion_id == ins.id)).one()
    assert guardado.respuestas == {str(p1.id): p1.correcta, str(p2.id): p2.correcta}

    # Una clave inventada cuenta como fallo (sin respuesta reconocida).
    r = cliente.post(f"/api/evaluacion/cuestionario/{tarea.id}/responder", headers=h,
                     json={"respuestas": {str(p1.id): "inventada", str(p2.id): elegidas[str(p2.id)]}})
    res = r.json()
    assert not res["aprobado"] and res["aciertos"] == 1
    assert next(c for c in res["correccion"] if c["id"] == p1.id)["elegida"] is None


def test_cuestionario_aprobado_y_suspendido(cliente, bd, planta):
    luis = planta.personas["luis"]
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    p1, p2, propuesta, _ = preguntas_basicas(bd, ins)
    h = cab(cliente, "luis")

    # Suspenso: una de dos (50 % < 80 %).
    r = cliente.post(f"/api/evaluacion/cuestionario/{tarea.id}/responder", headers=h,
                     json={"instruccion_id": ins.id, "respuestas": {str(p1.id): 1, str(p2.id): 2}})
    assert r.status_code == 200, r.text
    res = r.json()
    assert not res["aprobado"] and res["aciertos"] == 1 and res["total"] == 2
    fallo = next(c for c in res["correccion"] if not c["acierto"])
    assert fallo["id"] == p2.id and fallo["correcta"] == 0 and fallo["explicacion"]
    assert res["nivel"]["letra"] == "I" and res["siguiente"]
    x = _ultima_xapi(bd, "suspendio", luis.id)
    assert x.resultado["score"] == 0.5 and x.resultado["success"] is False

    # Aprobado: todas bien (una pregunta propuesta enviada no cuenta).
    r = cliente.post(f"/api/evaluacion/cuestionario/{tarea.id}/responder", headers=h,
                     json={"respuestas": {str(p1.id): 1, str(p2.id): 0, str(propuesta.id): 2}})
    res = r.json()
    assert res["aprobado"] and res["puntuacion"] == 1.0 and res["total"] == 2
    assert _ultima_xapi(bd, "aprobo", luis.id).resultado["success"] is True
    intentos = bd.scalars(select(IntentoEval).where(IntentoEval.usuario_id == luis.id,
                                                    IntentoEval.instruccion_id == ins.id)
                          .order_by(IntentoEval.id)).all()
    assert len(intentos) == 2 and str(propuesta.id) not in intentos[-1].respuestas
    assert nivel_guardado(bd, luis, tarea).evidencias["cuestionario"]["instruccion_id"] == ins.id

    # Versión cambiada mientras respondía: 409. Sin respuestas: 400.
    assert cliente.post(f"/api/evaluacion/cuestionario/{tarea.id}/responder", headers=h,
                        json={"instruccion_id": ins.id + 999, "respuestas": {str(p1.id): 1}}).status_code == 409
    assert cliente.post(f"/api/evaluacion/cuestionario/{tarea.id}/responder", headers=h,
                        json={"respuestas": {}}).status_code == 400


def test_cuestionario_permisos_y_sin_preparar(cliente, bd, planta):
    tarea = nueva_tarea(bd, planta, "ot")
    # Sin instrucción publicada.
    r = cliente.get(f"/api/evaluacion/cuestionario/{tarea.id}", headers=cab(cliente, "luis"))
    assert r.status_code == 404 and "instrucción publicada" in r.json()["detail"]
    ins = nueva_instruccion(bd, tarea)
    # Sin preguntas aprobadas.
    r = cliente.get(f"/api/evaluacion/cuestionario/{tarea.id}", headers=cab(cliente, "luis"))
    assert r.status_code == 404 and "preguntas aprobadas" in r.json()["detail"]
    preguntas_basicas(bd, ins)
    # Pedro (Producción, sin formación en Oficina técnica) no puede; Marta (en formación) sí.
    assert cliente.get(f"/api/evaluacion/cuestionario/{tarea.id}", headers=cab(cliente, "pedro")).status_code == 403
    assert cliente.post(f"/api/evaluacion/cuestionario/{tarea.id}/responder", headers=cab(cliente, "pedro"),
                        json={"respuestas": {"1": 0}}).status_code == 403
    assert cliente.get(f"/api/evaluacion/cuestionario/{tarea.id}", headers=cab(cliente, "marta")).status_code == 200
    assert cliente.get("/api/evaluacion/cuestionario/999999", headers=cab(cliente, "luis")).status_code == 404
    assert cliente.get(f"/api/evaluacion/cuestionario/{tarea.id}", headers=cab(cliente, "invitado")).status_code == 401


# --------------------------------------------------------------------------- observación


def _marcas(plantilla, ok=True, fallo_critico=False):
    marcas = []
    for p in plantilla["lista"]:
        marcas.append({"paso_id": p["paso_id"], "ok": not (fallo_critico and p["critico"]) and ok,
                       "nota": "Bien" if p["critico"] else None})
    return marcas


def test_observacion_por_el_jefe(cliente, bd, planta):
    luis, ana = planta.personas["luis"], planta.personas["ana"]
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    hasta_l(bd, luis, tarea, ins)
    iluo.recalcular(bd, luis.id, tarea.id)
    bd.commit()
    h = cab(cliente, "ana")

    r = cliente.get(f"/api/evaluacion/observacion/plantilla?usuario_id={luis.id}&tarea_id={tarea.id}", headers=h)
    assert r.status_code == 200, r.text
    plantilla = r.json()
    assert [p["orden"] for p in plantilla["lista"]] == [1, 2, 3, 4]
    assert [p["critico"] for p in plantilla["lista"]] == [False, True, True, False]
    assert plantilla["nivel"]["letra"] == "L"

    # Le sugiere observarle (tiene L y le falta la observación).
    pend = cliente.get("/api/evaluacion/pendientes", headers=h).json()
    assert any(s["usuario_id"] == luis.id and s["tarea_id"] == tarea.id for s in pend["observaciones"])

    # Faltan pasos por marcar, o aprobar con un crítico mal: 400.
    incompleta = {"usuario_id": luis.id, "tarea_id": tarea.id, "aprobada": True,
                  "lista": _marcas(plantilla)[:2]}
    assert cliente.post("/api/evaluacion/observaciones", json=incompleta, headers=h).status_code == 400
    mala = {"usuario_id": luis.id, "tarea_id": tarea.id, "aprobada": True,
            "lista": _marcas(plantilla, fallo_critico=True)}
    assert cliente.post("/api/evaluacion/observaciones", json=mala, headers=h).status_code == 400

    # No superada: queda guardada y no sube.
    r = cliente.post("/api/evaluacion/observaciones", headers=h, json={
        **mala, "aprobada": False, "comentario": "Repetir el apriete en cruz."})
    assert r.status_code == 200 and r.json()["nivel"]["letra"] == "L"
    assert r.json()["observacion"]["criticos_fallidos"] == 2

    # Aprobada: sube a U (la última ejecución no tuvo consultas en críticos).
    r = cliente.post("/api/evaluacion/observaciones", headers=h, json={
        "usuario_id": luis.id, "tarea_id": tarea.id, "instruccion_id": ins.id, "aprobada": True,
        "lista": _marcas(plantilla), "comentario": "Muy bien."})
    assert r.status_code == 200, r.text
    assert r.json()["nivel"] == {"nivel": 3, "letra": "U", "nombre": "Autónomo", "subio": True}
    obs = bd.scalars(select(Observacion).where(Observacion.usuario_id == luis.id, Observacion.tarea_id == tarea.id,
                                               Observacion.aprobada.is_(True))).one()
    assert obs.evaluador_id == ana.id and obs.lista[1]["critico"] and obs.lista[1]["texto"] == ins.pasos[1].titulo
    x = _ultima_xapi(bd, "observo", ana.id)
    assert x.objeto_nombre == f"Luis García · {tarea.nombre}" and x.contexto["usuario_id"] == luis.id


def test_observacion_permisos(cliente, bd, planta):
    luis, marta, pedro = planta.personas["luis"], planta.personas["marta"], planta.personas["pedro"]
    tarea_ot = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea_ot)
    tarea_prod = nueva_tarea(bd, planta, "prod")
    nueva_instruccion(bd, tarea_prod)
    ejecucion(bd, luis, tarea_ot, ins)
    cuerpo = {"usuario_id": luis.id, "tarea_id": tarea_ot.id, "aprobada": False, "lista": []}
    url = f"/api/evaluacion/observacion/plantilla?usuario_id={luis.id}&tarea_id={tarea_ot.id}"

    # Jefe de otro departamento: 403 (plantilla y registro).
    hj = cab(cliente, "javier")
    assert cliente.get(url, headers=hj).status_code == 403
    assert cliente.post("/api/evaluacion/observaciones", json=cuerpo, headers=hj).status_code == 403
    # Empleados (aunque sean expertos): 403.
    assert cliente.post("/api/evaluacion/observaciones", json=cuerpo, headers=cab(cliente, "luis")).status_code == 403
    assert cliente.get(url, headers=cab(cliente, "carmen")).status_code == 403
    # Ana no observa a Pedro en una tarea de Producción.
    ha = cab(cliente, "ana")
    assert cliente.get(f"/api/evaluacion/observacion/plantilla?usuario_id={pedro.id}&tarea_id={tarea_prod.id}",
                       headers=ha).status_code == 403
    # Ana sí observa a Marta, que se forma en Oficina técnica; y la administración a cualquiera.
    assert cliente.get(f"/api/evaluacion/observacion/plantilla?usuario_id={marta.id}&tarea_id={tarea_ot.id}",
                       headers=ha).status_code == 200
    assert cliente.get(url, headers=cab(cliente, "admin")).status_code == 200
    # Nadie se observa a sí mismo.
    ana = planta.personas["ana"]
    assert cliente.get(f"/api/evaluacion/observacion/plantilla?usuario_id={ana.id}&tarea_id={tarea_ot.id}",
                       headers=ha).status_code == 403


# --------------------------------------------------------------------------- pendientes


def test_pendientes_segun_rol(cliente, bd, planta):
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    preguntas_basicas(bd, ins)

    # Luis tiene la tarea en su itinerario (su puesto) y el cuestionario pendiente.
    d = cliente.get("/api/evaluacion/pendientes", headers=cab(cliente, "luis")).json()
    c = next(c for c in d["cuestionarios"] if c["tarea_id"] == tarea.id)
    assert c["pendiente"] and c["preguntas"] == 2 and not c["aprobado"]
    assert "preguntas" not in d and "observaciones" not in d

    # Ana (experta y jefa) ve las preguntas propuestas de su departamento.
    d = cliente.get("/api/evaluacion/pendientes", headers=cab(cliente, "ana")).json()
    i = next(i for i in d["preguntas"] if i["id"] == ins.id)
    assert i["propuestas"] == 1 and i["aprobadas"] == 2
    assert "observaciones" in d

    # Carmen (experta de Producción) no ve las de Oficina técnica; Pedro no tiene esta tarea.
    d = cliente.get("/api/evaluacion/pendientes", headers=cab(cliente, "carmen")).json()
    assert all(i["id"] != ins.id for i in d["preguntas"])
    d = cliente.get("/api/evaluacion/pendientes", headers=cab(cliente, "pedro")).json()
    assert all(c["tarea_id"] != tarea.id for c in d["cuestionarios"])
    assert cliente.get("/api/evaluacion/pendientes", headers=cab(cliente, "invitado")).status_code == 401


def test_pendientes_aprobado_fuera_de_validez(cliente, bd, planta):
    """Un cuestionario aprobado hace más de `meses_validez` meses vuelve a estar pendiente,
    igual que en el pasaporte (ya no respalda el nivel)."""
    luis = planta.personas["luis"]
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    preguntas_basicas(bd, ins)
    intento(bd, luis, ins, cuando=ahora() - timedelta(days=430))
    h = cab(cliente, "luis")
    c = next(c for c in cliente.get("/api/evaluacion/pendientes", headers=h).json()["cuestionarios"]
             if c["tarea_id"] == tarea.id)
    assert c["pendiente"] and not c["aprobado"] and c["aprobado_caducado"]
    intento(bd, luis, ins)
    c = next(c for c in cliente.get("/api/evaluacion/pendientes", headers=h).json()["cuestionarios"]
             if c["tarea_id"] == tarea.id)
    assert c["aprobado"] and not c["pendiente"] and not c["aprobado_caducado"]


@pytest.mark.ia_real
def test_generar_preguntas_con_modelo_real(cliente, bd, planta):
    """Con el modelo pequeño real: siempre salen preguntas válidas (del modelo o de respaldo)."""
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    creadas = evaluacion.generar_preguntas(bd, ins.id, n=3)
    bd.commit()
    assert creadas == 3
    for p in bd.scalars(select(PreguntaEval).where(PreguntaEval.instruccion_id == ins.id)).all():
        assert len(p.enunciado) >= 8 and 2 <= len(p.opciones) <= 4 and 0 <= p.correcta < len(p.opciones)
        assert p.estado == "propuesta"
