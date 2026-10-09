"""Instalador del servidor y herramienta de administración `cidia`.

1. Cuenta de administración que crean el instalador y `cidia admin-restablecer`: la herramienta
   ejecuta dentro del contenedor del gateway un pequeño programa en Python (PY_ADMIN) que recibe
   la contraseña por la entrada estándar. Aquí se extrae ese programa del script y se ejecuta
   igual, contra la base de pruebas.
2. Los dos scripts de bash, con Docker simulado: se cargan sus funciones (todo menos la última
   línea, que llama a main) y se comprueban la configuración y los secretos, las carpetas
   protegidas, la copia del código, las copias de seguridad y la restauración. Necesitan bash
   (en Windows, el de Git); si no lo hay, se saltan.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from cidia.arranque import valores_por_defecto
from cidia.modelos import Auditoria, Nivel, Sesion, Usuario
from cidia.seguridad import verificar_contrasena

RAIZ_GATEWAY = Path(__file__).resolve().parents[1]
HERRAMIENTA = RAIZ_GATEWAY.parent / "despliegue" / "cidia"
INSTALADOR = RAIZ_GATEWAY.parent / "despliegue" / "instalar-servidor.sh"


def _codigo_admin() -> str:
    texto = HERRAMIENTA.read_text(encoding="utf-8")
    m = re.search(r"read -r -d '' PY_ADMIN <<'PY' \|\| true\n(.*?)\nPY\n", texto, re.S)
    assert m, "No se encuentra el bloque PY_ADMIN en servidor/despliegue/cidia"
    return m.group(1)


def _ejecutar(modo: str, usuario: str, clave: str) -> tuple[int, str]:
    """Ejecuta PY_ADMIN como lo hace la herramienta: argumentos modo y usuario, clave por stdin."""
    r = subprocess.run(
        [sys.executable, "-c", _codigo_admin(), modo, usuario],
        input=clave + "\n", capture_output=True, text=True, cwd=RAIZ_GATEWAY, env=os.environ.copy(), timeout=120,
    )
    lineas = [ln for ln in r.stdout.splitlines() if ln.startswith("RESULTADO ")]
    assert lineas, f"Sin respuesta RESULTADO (código {r.returncode}): {r.stderr[-800:]}"
    return r.returncode, lineas[-1].removeprefix("RESULTADO ")


def _sin_administradores(bd) -> None:
    """Deja la base sin cuentas de administración y libre el nombre «admin»."""
    for u in bd.scalars(select(Usuario).where(Usuario.rol == "admin")):
        u.rol = "empleado"
    previo = bd.scalar(select(Usuario).where(Usuario.usuario == "admin"))
    if previo is not None:
        previo.usuario = f"admin-retirado-{previo.id}"
    bd.commit()


def _admin(bd) -> Usuario:
    bd.expire_all()
    u = bd.scalar(select(Usuario).where(Usuario.usuario == "admin"))
    assert u is not None
    return u


@pytest.fixture
def base(app, bd):
    valores_por_defecto()
    _sin_administradores(bd)
    return bd


def test_crea_el_administrador_si_no_hay_ninguno(base):
    codigo, res = _ejecutar("crear", "", "Abcd-Efgh-Jkmn-Pqrs")
    assert (codigo, res) == (0, "CREADO admin")
    u = _admin(base)
    assert u.rol == "admin" and u.activo
    assert verificar_contrasena(u.hash_contrasena, "Abcd-Efgh-Jkmn-Pqrs")
    nivel_max = base.scalar(select(Nivel).order_by(Nivel.orden.desc()))
    assert u.nivel_id == nivel_max.id
    auditoria = base.scalar(select(Auditoria).where(Auditoria.accion == "crear_administrador", Auditoria.entidad_id == str(u.id)))
    assert auditoria is not None and auditoria.detalle["usuario"] == "admin"


def test_crear_no_toca_un_administrador_existente(base):
    _ejecutar("crear", "", "Primera-Clave-1234")
    hash_antes = _admin(base).hash_contrasena
    codigo, res = _ejecutar("crear", "", "Segunda-Clave-5678")
    assert (codigo, res) == (0, "EXISTE admin")
    assert _admin(base).hash_contrasena == hash_antes


def test_restablecer_cambia_la_clave_y_cierra_sesiones(base, cliente):
    from datetime import timedelta

    from cidia.modelos import ahora

    _ejecutar("crear", "", "Clave-Antigua-1234")
    u = _admin(base)
    base.add(Sesion(usuario_id=u.id, expira=ahora() + timedelta(hours=2)))
    base.commit()

    codigo, res = _ejecutar("restablecer", "", "Clave-Nueva-5678")
    assert (codigo, res) == (0, "RESTABLECIDO admin")
    u = _admin(base)
    assert verificar_contrasena(u.hash_contrasena, "Clave-Nueva-5678")
    assert not verificar_contrasena(u.hash_contrasena, "Clave-Antigua-1234")
    assert all(s.revocada for s in base.scalars(select(Sesion).where(Sesion.usuario_id == u.id)))
    assert base.scalar(select(Auditoria).where(Auditoria.accion == "restablecer_contrasena")) is not None
    # Con la clave nueva se puede entrar en la app; con la antigua, no.
    assert cliente.post("/api/auth/login", json={"usuario": "admin", "contrasena": "Clave-Nueva-5678"}).status_code == 200
    assert cliente.post("/api/auth/login", json={"usuario": "admin", "contrasena": "Clave-Antigua-1234"}).status_code != 200


def test_restablecer_sin_administrador_lo_crea(base):
    codigo, res = _ejecutar("restablecer", "", "Clave-Rescate-1234")
    assert (codigo, res) == (0, "CREADO admin")


def test_no_restablece_cuentas_que_no_son_de_administracion(base, planta):
    hash_antes = planta.personas["luis"].hash_contrasena
    codigo, res = _ejecutar("restablecer", "luis", "Clave-Intrusa-1234")
    assert codigo == 2
    assert "no es una cuenta de administración" in res
    base.expire_all()
    assert base.scalar(select(Usuario).where(Usuario.usuario == "luis")).hash_contrasena == hash_antes


def test_cuenta_inexistente(base):
    codigo, res = _ejecutar("restablecer", "nadie", "Clave-Cualquiera-1234")
    assert codigo == 2 and "No existe la cuenta" in res


def test_no_ocupa_un_nombre_ya_usado_por_otra_cuenta(base):
    base.add(Usuario(usuario="admin", nombre="Homónimo", rol="empleado"))
    base.commit()
    codigo, res = _ejecutar("crear", "", "Clave-Choque-1234")
    assert codigo == 2 and "que no es de administración" in res


def test_rechaza_una_clave_corta(base):
    codigo, res = _ejecutar("crear", "", "corta")
    assert codigo == 1 and "no es válida" in res


def test_restablece_un_administrador_por_su_nombre_y_lo_reactiva(base):
    base.add(Usuario(usuario="jefa-sistemas", nombre="Jefa de sistemas", rol="admin", activo=False))
    base.commit()
    codigo, res = _ejecutar("restablecer", "jefa-sistemas", "Clave-Rescate-9876")
    assert (codigo, res) == (0, "RESTABLECIDO jefa-sistemas")
    base.expire_all()
    u = base.scalar(select(Usuario).where(Usuario.usuario == "jefa-sistemas"))
    assert u.activo and verificar_contrasena(u.hash_contrasena, "Clave-Rescate-9876")


def test_no_restablece_cuentas_del_directorio_de_la_empresa(base):
    base.add(Usuario(usuario="admin-ldap", nombre="Admin LDAP", rol="admin", origen_identidad="ldap"))
    base.commit()
    codigo, res = _ejecutar("restablecer", "admin-ldap", "Clave-Directorio-1234")
    assert codigo == 2 and "directorio de la empresa" in res
    base.expire_all()
    assert base.scalar(select(Usuario).where(Usuario.usuario == "admin-ldap")).hash_contrasena is None


# --------------------------------------------------------------------------- scripts de bash


def _bash() -> str | None:
    """Bash con el que probar los scripts: el de Git en Windows (no el de WSL) o el del sistema."""
    candidatos = []
    if os.name == "nt":
        candidatos += [r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"]
    if shutil.which("bash"):
        candidatos.append(shutil.which("bash"))
    for c in candidatos:
        if c and Path(c).exists() and "system32" not in c.lower():
            return c
    return None


BASH = _bash()
requiere_bash = pytest.mark.skipif(BASH is None, reason="hace falta bash para probar los scripts")
BANCOS = Path(__file__).resolve().parent / "bancos_instalador"


def _banco(nombre: str, script: Path) -> str:
    """Ejecuta un banco de pruebas de bash (tests/bancos_instalador/<nombre>.sh) sobre un script.

    Cada comprobación imprime «OK …» o «MAL …» y el banco sale con el número de fallos.
    """
    r = subprocess.run(
        [BASH, (BANCOS / f"{nombre}.sh").as_posix(), script.as_posix()],
        capture_output=True, encoding="utf-8", errors="replace", timeout=240,
        env={**os.environ, "LC_ALL": "C.UTF-8", "NO_COLOR": "1"},
    )
    salida = r.stdout + r.stderr
    assert r.returncode == 0 and "MAL " not in salida, salida[-4000:]
    assert "OK " in salida, salida[-4000:]
    return salida


@requiere_bash
def test_scripts_sin_errores_de_sintaxis():
    for script in (INSTALADOR, HERRAMIENTA):
        r = subprocess.run([BASH, "-n", script.as_posix()], capture_output=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, r.stderr
        texto = script.read_bytes()
        assert b"\r\n" not in texto, f"{script.name} tiene finales de línea de Windows"
        # Todo el programa va en funciones y la última línea llama a main: así se pueden cargar
        # sus funciones en los bancos y actualizar el script mientras se ejecuta no le afecta.
        assert texto.rstrip(b"\n").splitlines()[-1].startswith(b'main "$@"; exit'), script.name


@requiere_bash
def test_instalador_carpetas_subredes_y_credenciales():
    _banco("utilidades_instalador", INSTALADOR)


@requiere_bash
def test_instalador_configuracion_y_secretos():
    _banco("configuracion_instalador", INSTALADOR)


@requiere_bash
def test_instalador_copia_el_codigo_sin_secretos_y_conserva_perfiles_locales():
    _banco("codigo_instalador", INSTALADOR)


@requiere_bash
def test_herramienta_utilidades_y_ordenes():
    _banco("utilidades_herramienta", HERRAMIENTA)


@requiere_bash
def test_herramienta_copia_y_restauracion_con_docker_simulado():
    _banco("copias_herramienta", HERRAMIENTA)
