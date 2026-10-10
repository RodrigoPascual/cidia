"""Progreso: pasaporte, matriz del equipo, planta, validación de formador y ajuste manual (con permisos)."""

from datetime import timedelta

import pytest
from ayudas_evaluacion import (
    ejecucion,
    hasta_l,
    nivel_guardado,
    nueva_instruccion,
    nueva_tarea,
    observacion,
    preguntas_basicas,
)
from fabrica import cab
from sqlalchemy import event, select

from cidia.db import motor_bd
from cidia.modelos import Auditoria, NivelIluo, SentenciaXapi, ahora
from cidia.servicios import iluo

pytestmark = pytest.mark.usefixtures("app")


def _fila(datos, tarea_id):
    return next(t for t in datos["tareas"] if t["tarea"]["id"] == tarea_id)


def test_mi_progreso_pasaporte(cliente, bd, planta):
    luis, ana = planta.personas["luis"], planta.personas["ana"]
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    preguntas_basicas(bd, ins)
    hasta_l(bd, luis, tarea, ins)
    ejecucion(bd, luis, tarea, ins, consultas=4, criticos=2)  # la última con consultas en críticos
    observacion(bd, ana, luis, tarea, ins)

    r = cliente.get("/api/progreso/yo", headers=cab(cliente, "luis"))
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["persona"]["nombre"] == "Luis García"
    # La cabecera del pasaporte dice el departamento, como en la maqueta del plan.
    assert datos["persona"]["departamento"] == planta.deps["ot"].nombre
    t = _fila(datos, tarea.id)
    assert t["letra"] == "L" and t["nombre_nivel"] == "Ejecuta con apoyo"
    assert t["siguiente"]["letra"] == "U"
    assert t["siguiente"]["texto"] == "Falta una ejecución completa sin consultas en los pasos críticos."
    assert 75 <= t["porcentaje"] < 100 and t["caduca"] and not t["caducado"]
    assert t["cuestionario_disponible"] and t["cuestionario_aprobado"]
    # Curva de autonomía: ejecuciones completadas en orden con sus consultas.
    assert [p["consultas"] for p in t["curva"]] == [0, 0, 0, 4]
    assert t["curva"][-1]["consultas_criticos"] == 2
    ev = t["evidencias"]
    assert len(ev["cuestionarios"]) == 1 and ev["cuestionarios"][0]["vigente"]
    assert len(ev["ejecuciones"]) == 4 and ev["observaciones"][0]["evaluador"] == "Ana López"
    assert {r["clave"] for r in t["requisitos"] if r["cumplido"]} == {"inicio", "cuestionario", "ejecuciones",
                                                                      "observacion"}
    assert datos["resumen"]["por_nivel"]["L"] >= 1
    # Sin sesión no hay pasaporte.
    assert cliente.get("/api/progreso/yo", headers=cab(cliente, "invitado")).status_code == 401


def test_progreso_de_otra_persona(cliente, bd, planta):
    luis, marta = planta.personas["luis"], planta.personas["marta"]
    tarea_ot = nueva_tarea(bd, planta, "ot")
    nueva_instruccion(bd, tarea_ot)

    # La jefa de Oficina técnica ve a Luis; la administración también; él mismo también.
    for quien in ("ana", "admin", "luis"):
        r = cliente.get(f"/api/progreso/persona/{luis.id}", headers=cab(cliente, quien))
        assert r.status_code == 200, (quien, r.text)
        assert any(t["tarea"]["id"] == tarea_ot.id for t in r.json()["tareas"])
    # Un jefe de otro departamento o un compañero: no.
    for quien in ("javier", "pedro", "marta"):
        assert cliente.get(f"/api/progreso/persona/{luis.id}", headers=cab(cliente, quien)).status_code == 403
    # Marta se forma en Oficina técnica: Ana solo ve sus tareas de Oficina técnica; Javier, su jefe, todas.
    datos = cliente.get(f"/api/progreso/persona/{marta.id}", headers=cab(cliente, "ana")).json()
    deps = {t["tarea"]["puesto"] for t in datos["tareas"]}
    assert deps == {planta.puestos["ot"].nombre}
    datos = cliente.get(f"/api/progreso/persona/{marta.id}", headers=cab(cliente, "javier")).json()
    assert {planta.puestos["ot"].nombre, planta.puestos["prod"].nombre} <= {t["tarea"]["puesto"] for t in datos["tareas"]}
    assert cliente.get("/api/progreso/persona/999999", headers=cab(cliente, "admin")).status_code == 404

    # Detalle de una celda: Ana puede actuar sobre Luis en su tarea; Javier no puede verlo.
    r = cliente.get(f"/api/progreso/iluo/{luis.id}/{tarea_ot.id}", headers=cab(cliente, "ana"))
    assert r.status_code == 200 and r.json()["acciones"]["observar"] and r.json()["acciones"]["ajustar"]
    assert cliente.get(f"/api/progreso/iluo/{luis.id}/{tarea_ot.id}", headers=cab(cliente, "javier")).status_code == 403


def test_matriz_del_equipo(cliente, bd, planta):
    luis, ana, marta = planta.personas["luis"], planta.personas["ana"], planta.personas["marta"]
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    hasta_l(bd, luis, tarea, ins)
    iluo.recalcular(bd, luis.id, tarea.id)
    iluo.recalcular(bd, marta.id, tarea.id)
    # Otra persona con un nivel que caduca pronto y pendiente de reevaluación.
    bd.add(NivelIluo(usuario_id=ana.id, tarea_id=tarea.id, nivel=3, desde=ahora() - timedelta(days=330),
                     caduca=ahora() + timedelta(days=30), requiere_reevaluacion=True, evidencias={}))
    bd.commit()

    r = cliente.get("/api/progreso/equipo", headers=cab(cliente, "ana"))
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["departamento"]["id"] == planta.deps["ot"].id and m["departamentos"] == []
    personas = {p["id"]: p for p in m["personas"]}
    assert luis.id in personas and personas[marta.id]["en_formacion"] and planta.personas["pedro"].id not in personas
    celdas = {(c["usuario_id"], c["tarea_id"]): c for c in m["celdas"]}
    assert celdas[(luis.id, tarea.id)]["letra"] == "L" and celdas[(marta.id, tarea.id)]["letra"] == "I"
    ind = m["indicadores"]
    por_tarea = next(p for p in ind["personas_por_tarea"] if p["tarea_id"] == tarea.id)
    assert por_tarea["l_o_mas"] == 2 and por_tarea["u_o_mas"] == 1 and por_tarea["i"] == 1
    assert any(c["usuario_id"] == ana.id and c["tarea_id"] == tarea.id and 28 <= c["dias"] <= 30
               for c in ind["caducidades_proximas"])
    assert any(x["usuario_id"] == ana.id and x["tarea_id"] == tarea.id for x in ind["reevaluaciones_pendientes"])
    assert ind["tiempo_medio_primera_correcta"]["muestras"] >= 1

    # Permisos: empleados no; jefe de otro departamento no puede pedir este.
    assert cliente.get("/api/progreso/equipo", headers=cab(cliente, "luis")).status_code == 403
    assert cliente.get(f"/api/progreso/equipo?departamento_id={planta.deps['ot'].id}",
                       headers=cab(cliente, "javier")).status_code == 403
    mj = cliente.get("/api/progreso/equipo", headers=cab(cliente, "javier")).json()
    assert all(c["tarea_id"] != tarea.id for c in mj["celdas"])
    # La administración elige el departamento.
    ma = cliente.get(f"/api/progreso/equipo?departamento_id={planta.deps['ot'].id}", headers=cab(cliente, "admin"))
    assert ma.status_code == 200 and len(ma.json()["departamentos"]) >= 2
    assert cliente.get("/api/progreso/equipo?departamento_id=999999", headers=cab(cliente, "admin")).status_code == 404


def test_planta_solo_administracion(cliente, bd, planta):
    r = cliente.get("/api/progreso/planta", headers=cab(cliente, "admin"))
    assert r.status_code == 200, r.text
    datos = r.json()
    assert {d["nombre"] for d in datos["departamentos"]} >= {"Producción", "Oficina técnica"}
    assert "personas_por_tarea" in datos["indicadores"]
    for quien in ("ana", "luis"):
        assert cliente.get("/api/progreso/planta", headers=cab(cliente, quien)).status_code == 403


def test_validar_formador_por_api(cliente, bd, planta):
    luis, ana = planta.personas["luis"], planta.personas["ana"]
    tarea = nueva_tarea(bd, planta, "ot")
    ins = nueva_instruccion(bd, tarea)
    hasta_l(bd, luis, tarea, ins)
    observacion(bd, ana, luis, tarea, ins)
    url = f"/api/progreso/iluo/{luis.id}/{tarea.id}/formador"
    assert cliente.post(url, headers=cab(cliente, "javier")).status_code == 403
    assert cliente.post(url, headers=cab(cliente, "luis")).status_code == 403
    r = cliente.post(url, headers=cab(cliente, "ana"))
    assert r.status_code == 200, r.text
    assert r.json()["letra"] == "O" and r.json()["formador_validado"]
    assert r.json()["evidencias"]["formador"]["por"] == "Ana López"


def test_experto_valida_formador_por_api(cliente, bd, planta):
    """Un experto (sin ser jefe) del departamento de la tarea valida al formador y el cambio se guarda."""
    pedro, javier = planta.personas["pedro"], planta.personas["javier"]
    tarea = nueva_tarea(bd, planta, "prod")
    ins = nueva_instruccion(bd, tarea)
    hasta_l(bd, pedro, tarea, ins)
    observacion(bd, javier, pedro, tarea, ins)
    hc = cab(cliente, "carmen")  # experta de Producción

    # Ve esa celda (para decidir) con la acción de validar, pero no el pasaporte completo ni puede observar.
    r = cliente.get(f"/api/progreso/iluo/{pedro.id}/{tarea.id}", headers=hc)
    assert r.status_code == 200, r.text
    assert r.json()["letra"] == "U" and r.json()["acciones"] == {"observar": False, "ajustar": False,
                                                                 "validar_formador": True}
    assert cliente.get(f"/api/progreso/persona/{pedro.id}", headers=hc).status_code == 403

    r = cliente.post(f"/api/progreso/iluo/{pedro.id}/{tarea.id}/formador", headers=hc)
    assert r.status_code == 200, r.text
    assert r.json()["letra"] == "O" and r.json()["evidencias"]["formador"]["por"] == "Carmen Díaz"
    fila = nivel_guardado(bd, pedro, tarea)
    assert fila.nivel == 4 and fila.formador_validado

    # Una experta de otro departamento no ve ni valida.
    tarea_ot = nueva_tarea(bd, planta, "ot")
    assert cliente.get(f"/api/progreso/iluo/{planta.personas['luis'].id}/{tarea_ot.id}", headers=hc).status_code == 403


def test_formador_tras_ajuste_manual_a_u(cliente, bd, planta):
    """Si la U se puso a mano (sin evidencias), validar como formador también lleva a O."""
    luis = planta.personas["luis"]
    tarea = nueva_tarea(bd, planta, "ot")
    nueva_instruccion(bd, tarea)
    h = cab(cliente, "ana")
    assert cliente.put(f"/api/progreso/iluo/{luis.id}/{tarea.id}", headers=h,
                       json={"nivel": 3, "motivo": "Viene formado de la otra planta"}).status_code == 200
    r = cliente.post(f"/api/progreso/iluo/{luis.id}/{tarea.id}/formador", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["letra"] == "O" and r.json()["formador_validado"]
    assert nivel_guardado(bd, luis, tarea).nivel == 4
    bd.expire_all()
    ultima = bd.scalars(select(SentenciaXapi).where(SentenciaXapi.verbo == "certifico",
                                                    SentenciaXapi.actor_id == luis.id,
                                                    SentenciaXapi.objeto_id == str(tarea.id))
                        .order_by(SentenciaXapi.momento.desc()).limit(1)).one()
    assert ultima.resultado["nivel"] == "O"


def test_detalle_propio_solo_en_su_alcance(cliente, bd, planta):
    """Cada persona ve su detalle en las tareas de su alcance, no en las de otros departamentos."""
    pedro, luis = planta.personas["pedro"], planta.personas["luis"]
    tarea_ot = nueva_tarea(bd, planta, "ot")
    nueva_instruccion(bd, tarea_ot)
    assert cliente.get(f"/api/progreso/iluo/{pedro.id}/{tarea_ot.id}", headers=cab(cliente, "pedro")).status_code == 403
    r = cliente.get(f"/api/progreso/iluo/{luis.id}/{tarea_ot.id}", headers=cab(cliente, "luis"))
    assert r.status_code == 200 and not any(r.json()["acciones"].values())


def test_ajuste_manual_por_api(cliente, bd, planta):
    luis = planta.personas["luis"]
    tarea = nueva_tarea(bd, planta, "ot")
    nueva_instruccion(bd, tarea)
    url = f"/api/progreso/iluo/{luis.id}/{tarea.id}"
    h = cab(cliente, "ana")
    assert cliente.put(url, json={"nivel": 3, "motivo": ""}, headers=h).status_code == 400
    assert cliente.put(url, json={"nivel": 7, "motivo": "Motivo válido"}, headers=h).status_code == 400
    assert cliente.put(url, json={"nivel": 3, "motivo": "Lleva años haciéndolo"},
                       headers=cab(cliente, "javier")).status_code == 403
    assert cliente.put(url, json={"nivel": 3, "motivo": "Me lo pongo yo"}, headers=cab(cliente, "luis")).status_code == 403
    r = cliente.put(url, json={"nivel": 3, "motivo": "Lleva años haciéndolo en la otra planta"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["letra"] == "U"
    assert nivel_guardado(bd, luis, tarea).nivel == 3
    aud = bd.scalars(select(Auditoria).where(Auditoria.accion == "ajustar_nivel_iluo",
                                             Auditoria.entidad_id == f"{luis.id}-{tarea.id}")).all()
    assert len(aud) == 1 and aud[0].detalle["a"] == "U" and aud[0].detalle["motivo"].startswith("Lleva años")
    # El recálculo automático no se lo quita (nunca baja salvo caducidad).
    assert cliente.get("/api/progreso/yo", headers=cab(cliente, "luis")).status_code == 200
    assert nivel_guardado(bd, luis, tarea).nivel == 3


def test_itinerario_respeta_el_nivel_de_la_tarea(cliente, bd, planta):
    """Una tarea de su puesto que exige más nivel no entra en su pasaporte (igual que en el modo planta)."""
    normal = nueva_tarea(bd, planta, "ot")
    alta = nueva_tarea(bd, planta, "ot")
    alta.nivel_minimo = 3
    bd.commit()
    ids = {t["tarea"]["id"] for t in cliente.get("/api/progreso/yo", headers=cab(cliente, "luis")).json()["tareas"]}
    assert normal.id in ids and alta.id not in ids  # Luis es de nivel 1
    ids = {t["tarea"]["id"] for t in cliente.get("/api/progreso/yo", headers=cab(cliente, "ana")).json()["tareas"]}
    assert alta.id in ids  # Ana es de nivel 3


def test_pasaporte_sin_reescrituras_y_con_pocas_consultas(cliente, bd, planta):
    """Ver el pasaporte otra vez no reescribe los niveles y no hace una tanda de consultas por tarea."""
    luis = planta.personas["luis"]
    for _ in range(4):
        t = nueva_tarea(bd, planta, "ot")
        hasta_l(bd, luis, t, nueva_instruccion(bd, t))
    h = cab(cliente, "luis")
    primera = cliente.get("/api/progreso/yo", headers=h)  # primera visita: guarda los niveles nuevos
    assert primera.status_code == 200
    n_tareas = len(primera.json()["tareas"])
    assert n_tareas >= 5

    def guardadas() -> dict:
        bd.expire_all()
        return {f.tarea_id: f.evidencias.get("actualizado")
                for f in bd.scalars(select(NivelIluo).where(NivelIluo.usuario_id == luis.id))}

    antes = guardadas()
    consultas: list[str] = []

    def apuntar(conn, cursor, sentencia, *args):  # noqa: ANN001
        consultas.append(sentencia)

    event.listen(motor_bd(), "before_cursor_execute", apuntar)
    try:
        r = cliente.get("/api/progreso/yo", headers=h)
    finally:
        event.remove(motor_bd(), "before_cursor_execute", apuntar)
    assert r.status_code == 200
    assert guardadas() == antes
    assert not [c for c in consultas if c.lstrip().lower().startswith("update iluo")]
    # Antes eran unas veinte consultas por tarea; ahora un número fijo (más la sesión).
    assert len(consultas) <= 40, (n_tareas, len(consultas))


def test_siguiente_paso_con_nivel_puesto_a_mano(cliente, bd, planta):
    """Si el nivel se puso a mano y no hay evidencias, el siguiente paso lo explica."""
    luis = planta.personas["luis"]
    tarea = nueva_tarea(bd, planta, "ot")
    nueva_instruccion(bd, tarea)
    assert cliente.put(f"/api/progreso/iluo/{luis.id}/{tarea.id}", headers=cab(cliente, "ana"),
                       json={"nivel": 2, "motivo": "Viene de la matriz en papel"}).status_code == 200
    t = _fila(cliente.get("/api/progreso/yo", headers=cab(cliente, "luis")).json(), tarea.id)
    assert t["letra"] == "L" and t["siguiente"]["letra"] == "U"
    assert t["siguiente"]["texto"].startswith("Falta empezar la formación")
    assert "se asignó a mano" in t["siguiente"]["texto"]
