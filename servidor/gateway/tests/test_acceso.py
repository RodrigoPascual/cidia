"""Acceso: contraseña inicial o temporal que hay que cambiar en el primer acceso."""

import uuid

from fabrica import CONTRASENA, cab
from sqlalchemy import inspect, select

from cidia.db import inicializar_bd, motor_bd
from cidia.modelos import Sesion, Usuario


def _alta(cliente, h_admin, planta) -> tuple[dict, str]:
    s = uuid.uuid4().hex[:6]
    r = cliente.post("/api/admin/empleados", headers=h_admin, json={
        "usuario": f"nuevo.{s}", "nombre": "Nuevo Operario", "departamento_id": planta.deps["prod"].id,
        "nivel_id": planta.niveles[1].id, "rol": "empleado"})
    assert r.status_code == 200, r.text
    return r.json()["empleado"], r.json()["contrasena_inicial"]


def _entrar(cliente, usuario: str, contrasena: str) -> tuple[dict, dict]:
    r = cliente.post("/api/auth/login", json={"usuario": usuario, "contrasena": contrasena})
    assert r.status_code == 200, r.text
    return r.json()["perfil"], {"Authorization": f"Bearer {r.json()['token']}"}


def test_columna_nueva_idempotente():
    inicializar_bd()
    inicializar_bd()  # la segunda vez no falla (ADD COLUMN IF NOT EXISTS)
    columnas = {c["name"] for c in inspect(motor_bd()).get_columns("usuarios")}
    assert "debe_cambiar_contrasena" in columnas


def test_cuentas_normales_no_tienen_que_cambiarla(cliente, planta):
    perfil, h = _entrar(cliente, "luis", CONTRASENA)
    assert perfil["debe_cambiar_contrasena"] is False
    assert cliente.get("/api/auth/yo", headers=h).json()["debe_cambiar_contrasena"] is False
    assert cliente.get("/api/auth/yo", headers=cab(cliente, "invitado")).json().get("debe_cambiar_contrasena") is None


def test_contrasena_inicial_hay_que_cambiarla(cliente, bd, planta):
    h_admin = cab(cliente, "admin")
    emp, inicial = _alta(cliente, h_admin, planta)
    perfil, h = _entrar(cliente, emp["usuario"], inicial)
    assert perfil["debe_cambiar_contrasena"] is True
    assert cliente.get("/api/auth/yo", headers=h).json()["debe_cambiar_contrasena"] is True
    _, h_otra = _entrar(cliente, emp["usuario"], inicial)  # otra sesión abierta (otro equipo)

    # Validaciones: actual incorrecta, demasiado corta e igual que la actual.
    r = cliente.post("/api/auth/contrasena", headers=h, json={"actual": "mala", "nueva": "una frase larga"})
    assert r.status_code == 400 and "actual" in r.json()["detail"]
    r = cliente.post("/api/auth/contrasena", headers=h, json={"actual": inicial, "nueva": "corta"})
    assert r.status_code == 400 and "8 caracteres" in r.json()["detail"]
    r = cliente.post("/api/auth/contrasena", headers=h, json={"actual": inicial, "nueva": inicial})
    assert r.status_code == 400 and "distinta" in r.json()["detail"]
    assert cliente.get("/api/auth/yo", headers=h).json()["debe_cambiar_contrasena"] is True

    # El cambio limpia la marca, mantiene esta sesión y cierra las demás.
    r = cliente.post("/api/auth/contrasena", headers=h, json={"actual": inicial, "nueva": "mi frase de la planta"})
    assert r.status_code == 200, r.text
    assert cliente.get("/api/auth/yo", headers=h).json()["debe_cambiar_contrasena"] is False
    assert cliente.get("/api/auth/yo", headers=h_otra).status_code == 401
    bd.expire_all()
    u = bd.get(Usuario, emp["id"])
    assert u.debe_cambiar_contrasena is False
    assert bd.scalar(select(Sesion).where(Sesion.usuario_id == u.id, Sesion.revocada.is_(False))) is not None

    # La inicial ya no vale; la nueva sí, sin pedir otro cambio.
    assert cliente.post("/api/auth/login", json={"usuario": emp["usuario"], "contrasena": inicial}).status_code == 401
    perfil, _ = _entrar(cliente, emp["usuario"], "mi frase de la planta")
    assert perfil["debe_cambiar_contrasena"] is False


def test_contrasena_temporal_hay_que_cambiarla(cliente, planta):
    h_admin = cab(cliente, "admin")
    emp, inicial = _alta(cliente, h_admin, planta)
    _, h = _entrar(cliente, emp["usuario"], inicial)
    assert cliente.post("/api/auth/contrasena", headers=h,
                        json={"actual": inicial, "nueva": "otra frase segura"}).status_code == 200
    r = cliente.post(f"/api/admin/empleados/{emp['id']}/contrasena", headers=h_admin)
    assert r.status_code == 200, r.text
    perfil, _ = _entrar(cliente, emp["usuario"], r.json()["contrasena_temporal"])
    assert perfil["debe_cambiar_contrasena"] is True


def test_cuenta_externa_nunca_pide_cambio(cliente, bd, planta):
    h_admin = cab(cliente, "admin")
    s = uuid.uuid4().hex[:6]
    r = cliente.post("/api/admin/empleados", headers=h_admin, json={
        "usuario": f"ldap.{s}", "nombre": "Persona del directorio", "departamento_id": planta.deps["prod"].id,
        "rol": "empleado", "origen_identidad": "ldap"})
    assert r.status_code == 200, r.text
    assert r.json()["contrasena_inicial"] is None
    u = bd.get(Usuario, r.json()["empleado"]["id"])
    assert u.debe_cambiar_contrasena is False
