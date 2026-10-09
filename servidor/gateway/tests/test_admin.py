"""Pruebas de administración: organización, empresa, empleados, formaciones, modelos y registro."""

from __future__ import annotations

import uuid

import pytest
from fabrica import CONTRASENA, cab
from sqlalchemy import select

from cidia.modelos import Auditoria, Formacion, Instruccion, Nivel, Observacion, Sesion, Tarea, Usuario
from cidia.permisos import alcance_de
from cidia.seguridad import Actor, hash_contrasena


def _sufijo() -> str:
    return uuid.uuid4().hex[:6]


def _auditado(bd, accion: str, entidad_id) -> Auditoria | None:
    bd.expire_all()
    return bd.scalar(select(Auditoria).where(Auditoria.accion == accion, Auditoria.entidad_id == str(entidad_id))
                     .order_by(Auditoria.id.desc()))


@pytest.fixture
def h_admin(cliente, planta):
    return cab(cliente, "admin")


# --------------------------------------------------------------------------- permisos de acceso


def test_jefe_y_empleado_no_administran(cliente, planta):
    """Un jefe no puede administrar (403), un empleado tampoco y un invitado ni siquiera entra (401)."""
    rutas = [
        ("get", "/api/admin/organizacion", None),
        ("post", "/api/admin/departamentos", {"nombre": "Intrusos"}),
        ("put", f"/api/admin/departamentos/{planta.deps['prod'].id}", {"nombre": "Otro"}),
        ("post", "/api/admin/niveles", {"nombre": "Becario"}),
        ("post", "/api/admin/puestos", {"departamento_id": planta.deps["prod"].id, "nombre": "X"}),
        ("post", "/api/admin/tareas", {"puesto_id": planta.puestos["prod"].id, "nombre": "X"}),
        ("get", "/api/admin/empresa", None),
        ("put", "/api/admin/empresa", {"nombre": "Hackeada"}),
        ("post", "/api/admin/empleados", {"usuario": "nuevo", "nombre": "Nuevo"}),
        ("put", f"/api/admin/empleados/{planta.personas['pedro'].id}", {"rol": "admin"}),
        ("post", f"/api/admin/empleados/{planta.personas['pedro'].id}/contrasena", None),
        ("post", f"/api/admin/empleados/{planta.personas['pedro'].id}/desactivar", None),
        ("post", f"/api/admin/empleados/{planta.personas['pedro'].id}/formaciones",
         {"departamento_id": planta.deps["ot"].id}),
        ("get", "/api/admin/modelos", None),
        ("post", "/api/admin/modelos", {"ref": "malo:1b"}),
        ("get", "/api/admin/xapi", None),
        ("get", "/api/admin/xapi/exportar", None),
        ("get", "/api/admin/auditoria", None),
        ("delete", f"/api/admin/departamentos/{planta.deps['prod'].id}", None),
        ("delete", f"/api/admin/puestos/{planta.puestos['prod'].id}", None),
        ("put", f"/api/admin/tareas/{planta.tareas['prod'].id}", {"activa": False}),
        ("delete", f"/api/admin/tareas/{planta.tareas['prod'].id}", None),
        ("get", "/api/admin/niveles", None),
        ("put", "/api/admin/niveles/orden", {"ids": [n.id for n in planta.niveles.values()]}),
        ("delete", f"/api/admin/niveles/{planta.niveles[4].id}", None),
        ("post", f"/api/admin/empleados/{planta.personas['pedro'].id}/activar", None),
        ("post", "/api/admin/formaciones/1/completar", None),
        ("post", "/api/admin/formaciones/1/cancelar", None),
        ("put", "/api/admin/modelos/1", {"permitido": False}),
        ("delete", "/api/admin/modelos/1", None),
    ]
    for usuario, codigo in (("javier", 403), ("luis", 403), ("invitado", 401)):
        h = cab(cliente, usuario)
        for metodo, ruta, cuerpo in rutas:
            kw = {"json": cuerpo} if cuerpo is not None else {}
            if metodo in ("post", "put") and cuerpo is None:
                kw = {"json": {}}
            r = getattr(cliente, metodo)(ruta, headers=h, **kw)
            assert r.status_code == codigo, (usuario, metodo, ruta, r.status_code, r.text)
            assert isinstance(r.json()["detail"], str)
    # Un empleado tampoco puede leer fichas ni formaciones de nadie (ni de su departamento ni la suya).
    h = cab(cliente, "pedro")
    for ruta in (f"/api/admin/empleados/{planta.personas['marta'].id}",
                 f"/api/admin/empleados/{planta.personas['pedro'].id}",
                 f"/api/admin/empleados/{planta.personas['marta'].id}/formaciones"):
        assert cliente.get(ruta, headers=h).status_code == 403, ruta


# --------------------------------------------------------------------------- organización


def test_crud_organizacion_con_auditoria(cliente, bd, h_admin):
    s = _sufijo()
    r = cliente.post("/api/admin/departamentos", headers=h_admin,
                     json={"nombre": f"Calidad {s}", "codigo": f"cal{s}", "descripcion": "Control de calidad"})
    assert r.status_code == 200, r.text
    dep = r.json()
    assert dep["codigo"] == f"CAL{s}".upper() and dep["color"].startswith("#")
    assert _auditado(bd, "crear_departamento", dep["id"]).detalle["resumen"] == f"Creó el departamento «Calidad {s}»"

    # Duplicados y datos no válidos, con mensajes en castellano.
    r = cliente.post("/api/admin/departamentos", headers=h_admin, json={"nombre": f"calidad {s}"})
    assert r.status_code == 409 and "Ya hay un departamento" in r.json()["detail"]
    r = cliente.put(f"/api/admin/departamentos/{dep['id']}", headers=h_admin, json={"color": "rojo"})
    assert r.status_code == 400 and "#RRGGBB" in r.json()["detail"]
    r = cliente.post("/api/admin/departamentos", headers=h_admin, json={"nombre": "  "})
    assert r.status_code == 400

    r = cliente.put(f"/api/admin/departamentos/{dep['id']}", headers=h_admin, json={"color": "#aa3300"})
    assert r.json()["color"] == "#AA3300"
    assert _auditado(bd, "editar_departamento", dep["id"]).detalle["cambios"]["color"][1] == "#AA3300"

    r = cliente.post("/api/admin/puestos", headers=h_admin, json={"departamento_id": dep["id"], "nombre": "Laboratorio"})
    assert r.status_code == 200, r.text
    puesto = r.json()
    assert cliente.post("/api/admin/puestos", headers=h_admin,
                        json={"departamento_id": dep["id"], "nombre": "laboratorio"}).status_code == 409

    tarea_json = {"puesto_id": puesto["id"], "codigo": f"it-{s}", "nombre": "Medición de rugosidad",
                  "criticidad": 3, "riesgos_prl": "Cortes", "nivel_minimo": 2}
    r = cliente.post("/api/admin/tareas", headers=h_admin, json=tarea_json)
    assert r.status_code == 200, r.text
    tarea = r.json()
    assert tarea["codigo"] == f"IT-{s}".upper() and tarea["departamento_id"] == dep["id"] and tarea["activa"]
    assert cliente.post("/api/admin/tareas", headers=h_admin, json=tarea_json).status_code == 409
    assert cliente.post("/api/admin/tareas", headers=h_admin,
                        json={**tarea_json, "codigo": None, "criticidad": 5}).status_code == 400
    assert cliente.post("/api/admin/tareas", headers=h_admin,
                        json={**tarea_json, "codigo": None, "nivel_minimo": 99}).status_code == 400

    r = cliente.put(f"/api/admin/tareas/{tarea['id']}", headers=h_admin, json={"activa": False})
    assert r.json()["activa"] is False
    assert _auditado(bd, "editar_tarea", tarea["id"]).detalle["resumen"].startswith("Desactivó la tarea")

    # El árbol completo refleja la estructura.
    arbol = cliente.get("/api/admin/organizacion", headers=h_admin).json()
    d = next(x for x in arbol["departamentos"] if x["id"] == dep["id"])
    assert d["puestos"][0]["nombre"] == "Laboratorio"
    assert d["puestos"][0]["tareas"][0]["nombre"] == "Medición de rugosidad"
    assert [n["orden"] for n in arbol["niveles"]] == sorted(n["orden"] for n in arbol["niveles"])

    # Una tarea con instrucciones no se borra: se desactiva.
    bd.add(Instruccion(tarea_id=tarea["id"], titulo="IT rugosidad", estado="borrador"))
    bd.commit()
    r = cliente.delete(f"/api/admin/tareas/{tarea['id']}", headers=h_admin)
    assert r.status_code == 409 and "Desactívala" in r.json()["detail"]
    r = cliente.delete(f"/api/admin/departamentos/{dep['id']}", headers=h_admin)
    assert r.status_code == 409 and "tarea con instrucciones" in r.json()["detail"]
    bd.execute(Instruccion.__table__.delete().where(Instruccion.tarea_id == tarea["id"]))
    bd.commit()

    assert cliente.delete(f"/api/admin/tareas/{tarea['id']}", headers=h_admin).status_code == 200
    assert _auditado(bd, "borrar_tarea", tarea["id"]) is not None
    assert cliente.delete(f"/api/admin/puestos/{puesto['id']}", headers=h_admin).status_code == 200
    assert cliente.delete(f"/api/admin/departamentos/{dep['id']}", headers=h_admin).status_code == 200
    assert _auditado(bd, "borrar_departamento", dep["id"]) is not None
    assert cliente.put(f"/api/admin/departamentos/{dep['id']}", headers=h_admin, json={"nombre": "x"}).status_code == 404


def test_no_se_borra_un_departamento_con_personas(cliente, planta, h_admin):
    r = cliente.delete(f"/api/admin/departamentos/{planta.deps['prod'].id}", headers=h_admin)
    assert r.status_code == 409
    assert "personas" in r.json()["detail"]
    r = cliente.delete(f"/api/admin/puestos/{planta.puestos['prod'].id}", headers=h_admin)
    assert r.status_code == 409


def test_niveles_orden_y_borrado(cliente, bd, planta, h_admin):
    s = _sufijo()
    r = cliente.post("/api/admin/niveles", headers=h_admin, json={"nombre": f"Becario {s}", "descripcion": "Prácticas"})
    assert r.status_code == 200, r.text
    nuevo = r.json()
    assert cliente.post("/api/admin/niveles", headers=h_admin, json={"nombre": f"becario {s}"}).status_code == 409
    r = cliente.put(f"/api/admin/niveles/{nuevo['id']}", headers=h_admin, json={"nombre": f"Aprendiz {s}"})
    assert r.json()["nombre"] == f"Aprendiz {s}"

    # Un nivel en uso no se borra.
    operario = planta.niveles[1]
    r = cliente.delete(f"/api/admin/niveles/{operario.id}", headers=h_admin)
    assert r.status_code == 409 and "en uso" in r.json()["detail"]

    # Reordenar traduce el nivel mínimo de las tareas para que sigan apuntando al mismo nivel.
    tarea = planta.tareas["prod"]
    bd.execute(Tarea.__table__.update().where(Tarea.id == tarea.id).values(nivel_minimo=operario.orden))
    bd.commit()
    niveles = cliente.get("/api/admin/niveles", headers=h_admin).json()
    ids = [n["id"] for n in niveles]
    invertido = [ids[1], ids[0]] + ids[2:]
    r = cliente.put("/api/admin/niveles/orden", headers=h_admin, json={"ids": invertido})
    assert r.status_code == 200, r.text
    assert [n["id"] for n in r.json()] == invertido and [n["orden"] for n in r.json()] == list(range(1, len(ids) + 1))
    bd.expire_all()
    assert bd.get(Tarea, tarea.id).nivel_minimo == bd.get(Nivel, operario.id).orden == 2
    assert bd.scalar(select(Auditoria).where(Auditoria.accion == "ordenar_niveles")) is not None
    assert cliente.put("/api/admin/niveles/orden", headers=h_admin, json={"ids": ids[:-1]}).status_code == 400
    # Se deja como estaba para el resto de pruebas.
    assert cliente.put("/api/admin/niveles/orden", headers=h_admin, json={"ids": ids}).status_code == 200
    bd.expire_all()
    assert bd.get(Tarea, tarea.id).nivel_minimo == 1

    assert cliente.delete(f"/api/admin/niveles/{nuevo['id']}", headers=h_admin).status_code == 200
    assert _auditado(bd, "borrar_nivel", nuevo["id"]) is not None


def test_empresa_y_reglas_iluo(cliente, bd, h_admin):
    e = cliente.get("/api/admin/empresa", headers=h_admin).json()
    assert {"ejecuciones_para_L", "umbral_cuestionario", "meses_validez"} <= set(e["config_iluo"])
    r = cliente.put("/api/admin/empresa", headers=h_admin,
                    json={"nombre": "Metalúrgica del Arlanzón", "sector": "Metal",
                          "config_iluo": {"ejecuciones_para_L": 5, "umbral_cuestionario": 0.9, "meses_validez": 24}})
    assert r.status_code == 200, r.text
    assert r.json()["config_iluo"]["ejecuciones_para_L"] == 5 and r.json()["nombre"] == "Metalúrgica del Arlanzón"
    assert cliente.get("/api/sistema/info").json()["empresa"] == "Metalúrgica del Arlanzón"
    for malo in ({"umbral_cuestionario": 1.5}, {"umbral_cuestionario": 0.2}, {"meses_validez": 0},
                 {"ejecuciones_para_L": 2.5}, {"ejecuciones_para_L": True}, {"inventada": 3}, {"meses_validez": "doce"}):
        r = cliente.put("/api/admin/empresa", headers=h_admin, json={"config_iluo": malo})
        assert r.status_code == 400, malo
    assert cliente.get("/api/admin/empresa", headers=h_admin).json()["config_iluo"]["meses_validez"] == 24
    fila = bd.scalar(select(Auditoria).where(Auditoria.accion == "editar_empresa").order_by(Auditoria.id.desc()))
    assert fila is not None and "config_iluo" in fila.detalle["cambios"]


# --------------------------------------------------------------------------- empleados


def test_alta_contrasena_una_vez_y_sin_hash(cliente, bd, planta, h_admin):
    s = _sufijo()
    datos = {"usuario": f"Elena.{s}", "nombre": "Elena Gómez", "email": "elena@ejemplo.es",
             "departamento_id": planta.deps["prod"].id, "puesto_id": planta.puestos["prod"].id,
             "nivel_id": planta.niveles[2].id, "rol": "empleado", "es_experto": True}
    r = cliente.post("/api/admin/empleados", headers=h_admin, json=datos)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    clave = cuerpo["contrasena_inicial"]
    assert clave and len(clave) >= 12
    emp = cuerpo["empleado"]
    assert emp["usuario"] == f"elena.{s}" and emp["origen_identidad"] == "local" and emp["es_experto"]
    assert "hash_contrasena" not in r.text and "$argon2" not in r.text
    assert _auditado(bd, "crear_empleado", emp["id"]) is not None
    assert clave not in str(_auditado(bd, "crear_empleado", emp["id"]).detalle)

    # Duplicado (sin distinguir mayúsculas) y validaciones.
    assert cliente.post("/api/admin/empleados", headers=h_admin, json=datos).status_code == 409
    assert cliente.post("/api/admin/empleados", headers=h_admin,
                        json={**datos, "usuario": "con espacio"}).status_code == 400
    r = cliente.post("/api/admin/empleados", headers=h_admin,
                     json={**datos, "usuario": f"otra.{s}", "puesto_id": planta.puestos["ot"].id})
    assert r.status_code == 400 and "no pertenece" in r.json()["detail"]
    assert cliente.post("/api/admin/empleados", headers=h_admin,
                        json={"usuario": f"jefe.{s}", "nombre": "Sin dep", "rol": "jefe"}).status_code == 400

    # La contraseña inicial sirve para entrar y no vuelve a aparecer.
    login = cliente.post("/api/auth/login", json={"usuario": f"elena.{s}", "contrasena": clave})
    assert login.status_code == 200
    h_elena = {"Authorization": f"Bearer {login.json()['token']}"}
    detalle = cliente.get(f"/api/admin/empleados/{emp['id']}", headers=h_admin)
    assert clave not in detalle.text and "contrasena_inicial" not in detalle.text and "$argon2" not in detalle.text
    lista = cliente.get("/api/admin/empleados", headers=h_admin, params={"texto": "elena gó"}).json()
    assert [e["id"] for e in lista["empleados"]] == [emp["id"]]

    # Edición: cambiar de departamento quita el puesto que ya no vale.
    r = cliente.put(f"/api/admin/empleados/{emp['id']}", headers=h_admin,
                    json={"departamento_id": planta.deps["ot"].id, "nombre": "Elena Gómez Ruiz"})
    assert r.status_code == 200, r.text
    assert r.json()["departamento"]["id"] == planta.deps["ot"].id and r.json()["puesto"] is None
    assert _auditado(bd, "editar_empleado", emp["id"]).detalle["cambios"]["nombre"][1] == "Elena Gómez Ruiz"

    # Restablecer: la temporal se devuelve una vez, la anterior deja de valer y se cierran sus sesiones.
    r = cliente.post(f"/api/admin/empleados/{emp['id']}/contrasena", headers=h_admin)
    temporal = r.json()["contrasena_temporal"]
    assert temporal != clave and "$argon2" not in r.text
    otra_vez = cliente.get(f"/api/admin/empleados/{emp['id']}", headers=h_admin).text
    assert temporal not in otra_vez and "contrasena_temporal" not in otra_vez
    assert temporal not in str(_auditado(bd, "restablecer_contrasena", emp["id"]).detalle)
    assert cliente.get("/api/auth/yo", headers=h_elena).status_code == 401
    assert cliente.post("/api/auth/login", json={"usuario": f"elena.{s}", "contrasena": clave}).status_code == 401
    login = cliente.post("/api/auth/login", json={"usuario": f"elena.{s}", "contrasena": temporal})
    assert login.status_code == 200
    h_elena = {"Authorization": f"Bearer {login.json()['token']}"}

    # Desactivar cierra la sesión e impide entrar; activar lo devuelve.
    r = cliente.post(f"/api/admin/empleados/{emp['id']}/desactivar", headers=h_admin)
    assert r.json()["activo"] is False
    assert cliente.get("/api/auth/yo", headers=h_elena).status_code == 401
    assert cliente.post("/api/auth/login", json={"usuario": f"elena.{s}", "contrasena": temporal}).status_code == 401
    assert bd.scalar(select(Sesion).where(Sesion.usuario_id == emp["id"], Sesion.revocada.is_(False))) is None
    inactivos = cliente.get("/api/admin/empleados", headers=h_admin, params={"activo": False}).json()["empleados"]
    assert emp["id"] in [e["id"] for e in inactivos]
    assert cliente.post(f"/api/admin/empleados/{emp['id']}/activar", headers=h_admin).json()["activo"] is True
    assert cliente.post("/api/auth/login", json={"usuario": f"elena.{s}", "contrasena": temporal}).status_code == 200
    assert _auditado(bd, "desactivar_empleado", emp["id"]) and _auditado(bd, "activar_empleado", emp["id"])


def test_cuenta_externa_sin_contrasena(cliente, planta, h_admin):
    s = _sufijo()
    r = cliente.post("/api/admin/empleados", headers=h_admin,
                     json={"usuario": f"ldap.{s}", "nombre": "Cuenta LDAP", "origen_identidad": "ldap",
                           "departamento_id": planta.deps["ot"].id})
    assert r.status_code == 200
    assert r.json()["contrasena_inicial"] is None
    emp = r.json()["empleado"]
    assert emp["origen_identidad"] == "ldap" and emp["contrasena_gestionable"] is False
    r = cliente.post(f"/api/admin/empleados/{emp['id']}/contrasena", headers=h_admin)
    assert r.status_code == 400 and "directorio" in r.json()["detail"].lower()


def test_admin_no_se_bloquea_a_si_mismo(cliente, bd, planta, h_admin):
    yo = planta.personas["admin"]
    r = cliente.put(f"/api/admin/empleados/{yo.id}", headers=h_admin, json={"rol": "empleado"})
    assert r.status_code == 400
    assert cliente.post(f"/api/admin/empleados/{yo.id}/desactivar", headers=h_admin).status_code == 400
    # Su propia contraseña sí puede restablecerla sin perder la sesión actual.
    try:
        r = cliente.post(f"/api/admin/empleados/{yo.id}/contrasena", headers=h_admin)
        assert r.status_code == 200
        assert cliente.get("/api/auth/yo", headers=h_admin).status_code == 200
    finally:
        # Se deja la contraseña de pruebas para el resto de pruebas.
        bd.execute(Usuario.__table__.update().where(Usuario.id == yo.id)
                   .values(hash_contrasena=hash_contrasena(CONTRASENA)))
        bd.commit()


def test_jefe_ve_solo_su_departamento_en_lectura(cliente, planta):
    h = cab(cliente, "javier")
    r = cliente.get("/api/admin/empleados", headers=h)
    assert r.status_code == 200
    datos = r.json()
    assert datos["solo_lectura"] is True
    deps = {e["departamento"]["id"] for e in datos["empleados"] if e["departamento"]}
    assert deps == {planta.deps["prod"].id}
    assert "hash_contrasena" not in r.text
    assert cliente.get("/api/admin/empleados", headers=h,
                       params={"departamento_id": planta.deps["ot"].id}).status_code == 403
    assert cliente.get(f"/api/admin/empleados/{planta.personas['luis'].id}", headers=h).status_code == 403
    assert cliente.get(f"/api/admin/empleados/{planta.personas['pedro'].id}", headers=h).status_code == 200
    assert cliente.get(f"/api/admin/empleados/{planta.personas['marta'].id}/formaciones", headers=h).status_code == 200
    # Un empleado no ve la lista.
    assert cliente.get("/api/admin/empleados", headers=cab(cliente, "pedro")).status_code == 403


def test_formaciones_cambian_el_alcance(cliente, bd, planta, h_admin, monkeypatch):
    from cidia.servicios import iluo

    recalculos: list[tuple[int, int]] = []
    monkeypatch.setattr(iluo, "recalcular", lambda bd_, u, t: recalculos.append((u, t)))

    s = _sufijo()
    r = cliente.post("/api/admin/empleados", headers=h_admin,
                     json={"usuario": f"rafa.{s}", "nombre": "Rafa Pérez", "departamento_id": planta.deps["prod"].id})
    uid = r.json()["empleado"]["id"]
    ot = planta.deps["ot"]

    def alcance() -> set[int]:
        bd.expire_all()
        u = bd.get(Usuario, uid)
        return {e.departamento_id for e in alcance_de(bd, Actor(sesion=None, usuario=u)).elementos  # type: ignore[arg-type]
                if e.solo_formacion}

    assert alcance() == set()
    r = cliente.post(f"/api/admin/empleados/{uid}/formaciones", headers=h_admin,
                     json={"departamento_id": ot.id, "puesto_id": planta.puestos["ot"].id, "fin_previsto": "2099-12-31"})
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["estado"] == "activa" and f["fin_previsto"] == "2099-12-31" and f["puesto"]["nombre"] == "Diseño de utillajes"
    assert alcance() == {ot.id}
    assert (uid, planta.tareas["ot"].id) in recalculos
    assert _auditado(bd, "asignar_formacion", f["id"]) is not None

    # Reglas: no en su propio departamento, no duplicada, puesto del departamento, fecha futura.
    assert cliente.post(f"/api/admin/empleados/{uid}/formaciones", headers=h_admin,
                        json={"departamento_id": planta.deps["prod"].id}).status_code == 400
    assert cliente.post(f"/api/admin/empleados/{uid}/formaciones", headers=h_admin,
                        json={"departamento_id": ot.id}).status_code == 409
    detalle = cliente.get(f"/api/admin/empleados/{uid}", headers=h_admin).json()
    assert detalle["formaciones_activas"] == 1 and detalle["formaciones"][0]["id"] == f["id"]

    # Cancelar retira el acceso; una nueva se puede completar.
    assert cliente.post(f"/api/admin/formaciones/{f['id']}/cancelar", headers=h_admin).json()["estado"] == "cancelada"
    assert alcance() == set()
    assert cliente.post(f"/api/admin/formaciones/{f['id']}/cancelar", headers=h_admin).status_code == 400
    r = cliente.post(f"/api/admin/empleados/{uid}/formaciones", headers=h_admin, json={"departamento_id": ot.id})
    f2 = r.json()
    assert alcance() == {ot.id}
    assert cliente.post(f"/api/admin/formaciones/{f2['id']}/completar", headers=h_admin).json()["estado"] == "completada"
    assert alcance() == set()
    bd.expire_all()
    assert bd.get(Formacion, f2["id"]).estado == "completada"
    # Un jefe no puede asignar ni cerrar formaciones.
    h_jefe = cab(cliente, "javier")
    assert cliente.post(f"/api/admin/formaciones/{f2['id']}/cancelar", headers=h_jefe).status_code == 403


def test_filtros_de_empleados(cliente, planta, h_admin):
    r = cliente.get("/api/admin/empleados", headers=h_admin, params={"rol": "jefe"}).json()
    assert {"ana", "javier"} <= {e["usuario"] for e in r["empleados"]}
    assert all(e["rol"] == "jefe" for e in r["empleados"])
    r = cliente.get("/api/admin/empleados", headers=h_admin, params={"departamento_id": planta.deps["ot"].id}).json()
    assert all(e["departamento"]["id"] == planta.deps["ot"].id for e in r["empleados"])
    assert cliente.get("/api/admin/empleados", headers=h_admin, params={"rol": "rey"}).status_code == 400


# --------------------------------------------------------------------------- modelos


@pytest.fixture
def servidor_modelos(monkeypatch):
    from cidia.ia import llm

    estado = {"ok": True, "modelos": ["qwen3:0.6b", "qwen3-embedding:0.6b", "qwen3.5:9b"]}
    monkeypatch.setattr(llm, "salud", lambda: estado)
    return estado


def test_modelos_permitidos(cliente, bd, h_admin, servidor_modelos, monkeypatch):
    datos = cliente.get("/api/admin/modelos", headers=h_admin).json()
    nube = [m for m in datos["modelos"] if m["ubicacion"] == "nube"]
    assert nube and all(m["bloqueado"] and not m["permitido"] and m["uso"] == "Nadie" for m in nube)
    chat = next(m for m in datos["modelos"] if m["ref"] == "qwen3:0.6b" and m["tipo"] == "chat")
    assert chat["descargado"] is True and chat["predeterminado"] and chat["donde"] == "En el servidor de la empresa"
    assert "qwen3.5:9b" in datos["servidor"]["sin_registrar"]

    # La nube está bloqueada por la política del servidor.
    r = cliente.put(f"/api/admin/modelos/{nube[0]['id']}", headers=h_admin, json={"permitido": True})
    assert r.status_code == 400 and "nube" in r.json()["detail"]

    # Añadir un modelo local y hacerlo predeterminado: un solo predeterminado por tipo.
    r = cliente.post("/api/admin/modelos", headers=h_admin,
                     json={"ref": "qwen3.5:9b", "nombre": "Qwen3.5 9B", "tipo": "chat", "soporta_vision": True})
    assert r.status_code == 200, r.text
    nuevo = r.json()["creado"]
    assert nuevo["descargado"] is True and not nuevo["permitido"]
    assert cliente.post("/api/admin/modelos", headers=h_admin, json={"ref": "qwen3.5:9b"}).status_code == 409
    assert cliente.post("/api/admin/modelos", headers=h_admin, json={"ref": "mal nombre!"}).status_code == 400
    r = cliente.put(f"/api/admin/modelos/{nuevo['id']}", headers=h_admin, json={"predeterminado": True})
    assert r.status_code == 200, r.text
    predet = [m for m in r.json()["modelos"] if m["tipo"] == "chat" and m["predeterminado"]]
    assert [m["ref"] for m in predet] == ["qwen3.5:9b"] and predet[0]["permitido"]
    assert _auditado(bd, "cambiar_modelo", nuevo["id"]).detalle["resumen"].startswith("Hizo predeterminado")

    from cidia.ia import llm

    assert llm.modelo_permitido(bd, "chat") == "qwen3.5:9b"

    # Desactivar el predeterminado pasa el papel a otro permitido.
    r = cliente.put(f"/api/admin/modelos/{nuevo['id']}", headers=h_admin, json={"permitido": False})
    predet = [m["ref"] for m in r.json()["modelos"] if m["tipo"] == "chat" and m["predeterminado"]]
    assert predet == ["qwen3:0.6b"]

    # No se puede quedar sin modelo de búsqueda.
    emb = next(m for m in r.json()["modelos"] if m["tipo"] == "embeddings" and m["permitido"])
    r = cliente.put(f"/api/admin/modelos/{emb['id']}", headers=h_admin, json={"permitido": False})
    assert r.status_code == 400 and "al menos un modelo" in r.json()["detail"]

    # Un modelo que no está descargado no puede ser predeterminado.
    r = cliente.post("/api/admin/modelos", headers=h_admin, json={"ref": "gemma4:12b", "tipo": "chat"})
    falta = r.json()["creado"]
    assert falta["descargado"] is False
    r = cliente.put(f"/api/admin/modelos/{falta['id']}", headers=h_admin, json={"predeterminado": True})
    assert r.status_code == 400 and "descargado" in r.json()["detail"]
    # Se puede quitar de la lista si no está permitido; uno permitido, no.
    chat_id = next(m["id"] for m in cliente.get("/api/admin/modelos", headers=h_admin).json()["modelos"]
                   if m["ref"] == "qwen3:0.6b" and m["tipo"] == "chat")
    assert cliente.delete(f"/api/admin/modelos/{chat_id}", headers=h_admin).status_code == 400
    assert cliente.delete(f"/api/admin/modelos/{falta['id']}", headers=h_admin).status_code == 200
    assert cliente.delete(f"/api/admin/modelos/{nuevo['id']}", headers=h_admin).status_code == 200

    # Si la política lo permite, la nube se puede habilitar.
    from cidia.config import ajustes

    monkeypatch.setattr(ajustes(), "permitir_modelos_nube", True)
    r = cliente.put(f"/api/admin/modelos/{nube[0]['id']}", headers=h_admin, json={"permitido": True})
    assert r.status_code == 200
    r = cliente.put(f"/api/admin/modelos/{nube[0]['id']}", headers=h_admin, json={"permitido": False})
    assert r.status_code == 200


def test_modelos_con_servidor_caido(cliente, h_admin, monkeypatch):
    from cidia.ia import llm

    monkeypatch.setattr(llm, "salud", lambda: {"ok": False, "error": "sin conexión"})
    datos = cliente.get("/api/admin/modelos", headers=h_admin).json()
    assert datos["servidor"]["ok"] is False
    assert all(m["descargado"] is None for m in datos["modelos"])


# --------------------------------------------------------------------------- registro


def test_registro_xapi_y_auditoria(cliente, planta, h_admin):
    cab(cliente, "luis")  # inicio de sesión: deja una sentencia «inició»
    r = cliente.get("/api/admin/xapi", headers=h_admin, params={"actor": "luis", "verbo": "inicio", "por_pagina": 5})
    assert r.status_code == 200
    datos = r.json()
    assert datos["total"] >= 1 and len(datos["sentencias"]) <= 5
    s = datos["sentencias"][0]
    assert s["actor_nombre"] == "Luis García" and s["texto"].startswith("Luis García inició")
    assert s["sentencia"]["verb"]["id"].endswith("launched")
    assert any(v["clave"] == "completo" for v in datos["verbos"])
    # Paginación coherente.
    p2 = cliente.get("/api/admin/xapi", headers=h_admin, params={"por_pagina": 1, "pagina": 2}).json()
    assert p2["pagina"] == 2 and len(p2["sentencias"]) == 1
    # Fechas.
    assert cliente.get("/api/admin/xapi", headers=h_admin, params={"desde": "ayer"}).status_code == 400
    futuro = cliente.get("/api/admin/xapi", headers=h_admin, params={"desde": "2099-01-01"}).json()
    assert futuro["total"] == 0
    r = cliente.get("/api/admin/xapi", headers=h_admin, params={"actor": "99999999999999999999"})
    assert r.status_code == 200 and r.json()["total"] == 0
    r = cliente.get("/api/admin/auditoria", headers=h_admin, params={"usuario": "99999999999999999999"})
    assert r.status_code == 200 and r.json()["total"] == 0

    r = cliente.get("/api/admin/xapi/exportar", headers=h_admin, params={"actor": "luis"})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    lista = r.json()
    assert isinstance(lista, list) and lista and {"id", "actor", "verb", "object", "timestamp"} <= set(lista[0])

    aud = cliente.get("/api/admin/auditoria", headers=h_admin, params={"accion": "exportar_xapi"}).json()
    assert aud["total"] >= 1 and aud["filas"][0]["texto"].startswith("Exportó")
    assert "exportar_xapi" in aud["acciones"]
    aud = cliente.get("/api/admin/auditoria", headers=h_admin, params={"texto": "exportó", "usuario": "admin"}).json()
    assert aud["total"] >= 1


# --------------------------------------------------------------------------- historial y movimientos


def test_no_se_pierde_historial_al_mover_o_borrar(cliente, bd, planta, h_admin):
    """Puestos y tareas con historial no cambian de departamento; observaciones y formaciones pasadas
    impiden borrar lo que las sostiene."""
    s = _sufijo()
    dep_a = cliente.post("/api/admin/departamentos", headers=h_admin, json={"nombre": f"Prensas {s}"}).json()
    dep_b = cliente.post("/api/admin/departamentos", headers=h_admin, json={"nombre": f"Pintura {s}"}).json()

    def nuevo_puesto(dep: dict, nombre: str) -> dict:
        r = cliente.post("/api/admin/puestos", headers=h_admin, json={"departamento_id": dep["id"], "nombre": nombre})
        assert r.status_code == 200, r.text
        return r.json()

    puesto, otro_a, puesto_b = nuevo_puesto(dep_a, "Prensa 1"), nuevo_puesto(dep_a, "Prensa 2"), nuevo_puesto(dep_b, "Cabina")
    tarea = cliente.post("/api/admin/tareas", headers=h_admin, json={"puesto_id": puesto["id"], "nombre": "Cambio de matriz"}).json()

    # Faltan datos obligatorios: 400 con explicación (no 404).
    r = cliente.post("/api/admin/puestos", headers=h_admin, json={"nombre": "Sin departamento"})
    assert r.status_code == 400 and "departamento" in r.json()["detail"]
    r = cliente.post("/api/admin/tareas", headers=h_admin, json={"nombre": "Sin puesto"})
    assert r.status_code == 400 and "puesto" in r.json()["detail"]

    # Con instrucciones, el puesto no se lleva sus tareas a otro departamento.
    bd.add(Instruccion(tarea_id=tarea["id"], titulo="IT matriz", estado="publicada"))
    bd.commit()
    r = cliente.put(f"/api/admin/puestos/{puesto['id']}", headers=h_admin, json={"departamento_id": dep_b["id"]})
    assert r.status_code == 409 and "Crea un puesto nuevo" in r.json()["detail"]
    # Ni la tarea cambia de departamento; dentro del mismo departamento, sí.
    r = cliente.put(f"/api/admin/tareas/{tarea['id']}", headers=h_admin, json={"puesto_id": puesto_b["id"]})
    assert r.status_code == 409 and "mismo departamento" in r.json()["detail"]
    r = cliente.put(f"/api/admin/tareas/{tarea['id']}", headers=h_admin, json={"puesto_id": otro_a["id"]})
    assert r.status_code == 200 and r.json()["puesto_id"] == otro_a["id"]
    bd.expire_all()
    assert bd.get(Tarea, tarea["id"]).puesto_id == otro_a["id"]

    # Un puesto sin historial sí se mueve.
    r = cliente.put(f"/api/admin/puestos/{puesto['id']}", headers=h_admin, json={"departamento_id": dep_b["id"]})
    assert r.status_code == 200 and r.json()["departamento_id"] == dep_b["id"]

    # Una observación en el puesto impide borrar la tarea (se perdería en cascada) y su puesto.
    t2 = cliente.post("/api/admin/tareas", headers=h_admin, json={"puesto_id": puesto_b["id"], "nombre": "Lijado"}).json()
    bd.add(Observacion(usuario_id=planta.personas["pedro"].id, tarea_id=t2["id"], aprobada=True))
    bd.commit()
    r = cliente.delete(f"/api/admin/tareas/{t2['id']}", headers=h_admin)
    assert r.status_code == 409 and "observación" in r.json()["detail"]
    assert cliente.delete(f"/api/admin/puestos/{puesto_b['id']}", headers=h_admin).status_code == 409

    # Una formación ya cancelada también es historial: el departamento no se borra.
    dep_c = cliente.post("/api/admin/departamentos", headers=h_admin, json={"nombre": f"Logística {s}"}).json()
    f = cliente.post(f"/api/admin/empleados/{planta.personas['pedro'].id}/formaciones", headers=h_admin,
                     json={"departamento_id": dep_c["id"]}).json()
    assert cliente.post(f"/api/admin/formaciones/{f['id']}/cancelar", headers=h_admin).status_code == 200
    r = cliente.delete(f"/api/admin/departamentos/{dep_c['id']}", headers=h_admin)
    assert r.status_code == 409 and "formación registrada" in r.json()["detail"]


def test_modelo_de_busqueda_lo_fija_el_servidor(cliente, h_admin, servidor_modelos):
    """El modelo con el que están indexados los documentos no se desactiva ni se sustituye desde aquí."""
    from cidia.config import ajustes

    configurado = ajustes().llm_modelo_embeddings
    servidor_modelos["modelos"].append("nomic-embed-text:latest")
    datos = cliente.get("/api/admin/modelos", headers=h_admin).json()
    actual = next(m for m in datos["modelos"] if m["tipo"] == "embeddings" and m["ref"] == configurado)
    assert actual["indexa_documentos"] and actual["uso"] == "Búsqueda de documentos"
    assert not any(m["indexa_documentos"] for m in datos["modelos"] if m["id"] != actual["id"])

    r = cliente.post("/api/admin/modelos", headers=h_admin,
                     json={"ref": "nomic-embed-text", "tipo": "embeddings", "permitido": True})
    assert r.status_code == 200, r.text
    nuevo = r.json()["creado"]
    assert nuevo["descargado"] is True and not nuevo["indexa_documentos"] and nuevo["uso"].startswith("Reserva")
    try:
        # Aunque haya otro permitido, el que indexa los documentos no se desactiva ni deja de ser predeterminado.
        r = cliente.put(f"/api/admin/modelos/{actual['id']}", headers=h_admin, json={"permitido": False})
        assert r.status_code == 400 and "indexados" in r.json()["detail"]
        r = cliente.put(f"/api/admin/modelos/{actual['id']}", headers=h_admin, json={"predeterminado": False})
        assert r.status_code == 400
        r = cliente.put(f"/api/admin/modelos/{nuevo['id']}", headers=h_admin, json={"predeterminado": True})
        assert r.status_code == 400 and "indexar" in r.json()["detail"]
        predet = [m["ref"] for m in cliente.get("/api/admin/modelos", headers=h_admin).json()["modelos"]
                  if m["tipo"] == "embeddings" and m["predeterminado"]]
        assert predet == [configurado]
    finally:
        assert cliente.put(f"/api/admin/modelos/{nuevo['id']}", headers=h_admin, json={"permitido": False}).status_code == 200
        assert cliente.delete(f"/api/admin/modelos/{nuevo['id']}", headers=h_admin).status_code == 200
