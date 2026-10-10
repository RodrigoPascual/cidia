"""Datos de prueba reutilizables (sintéticos).

`crear_planta(bd)` crea, si no existen, dos departamentos (Producción y Oficina técnica),
los cuatro niveles, un puesto y una tarea por departamento, y estas personas:

| usuario | departamento | nivel | rol | otros |
|---|---|---|---|---|
| ana     | Oficina técnica | 3 | jefe | experta |
| luis    | Oficina técnica | 1 | empleado | |
| marta   | Producción | 2 | empleado | formación activa en Oficina técnica |
| pedro   | Producción | 1 | empleado | |
| javier  | Producción | 3 | jefe | |
| carmen  | Producción | 2 | empleado | experta |
| admin   | (ninguno) | 4 | admin | |

Contraseña de todos: CONTRASENA. `token(cliente, usuario)` inicia sesión y devuelve el token.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cidia.modelos import Departamento, Formacion, Nivel, Puesto, Tarea, Usuario
from cidia.seguridad import hash_contrasena

CONTRASENA = "prueba-1234"
_HASH: str | None = None


@dataclass
class Planta:
    deps: dict[str, Departamento] = field(default_factory=dict)
    niveles: dict[int, Nivel] = field(default_factory=dict)
    puestos: dict[str, Puesto] = field(default_factory=dict)
    tareas: dict[str, Tarea] = field(default_factory=dict)
    personas: dict[str, Usuario] = field(default_factory=dict)


def _hash() -> str:
    global _HASH
    if _HASH is None:
        _HASH = hash_contrasena(CONTRASENA)
    return _HASH


def crear_planta(bd: Session) -> Planta:
    p = Planta()
    for orden, nombre in ((1, "Operario"), (2, "Técnico"), (3, "Responsable"), (4, "Dirección")):
        n = bd.scalar(select(Nivel).where(Nivel.orden == orden))
        if n is None:
            n = Nivel(orden=orden, nombre=nombre)
            bd.add(n)
            bd.flush()
        p.niveles[orden] = n
    for clave, nombre in (("prod", "Producción"), ("ot", "Oficina técnica")):
        d = bd.scalar(select(Departamento).where(Departamento.nombre == nombre))
        if d is None:
            d = Departamento(nombre=nombre, codigo=clave.upper())
            bd.add(d)
            bd.flush()
        p.deps[clave] = d
    for clave, dep, puesto, tarea, codigo in (
        ("prod", "prod", "Montaje línea 2", "Montaje de la brida B", "IT-023"),
        ("ot", "ot", "Diseño de utillajes", "Diseño de un utillaje de soldadura", "IT-101"),
    ):
        pu = bd.scalar(select(Puesto).where(Puesto.nombre == puesto))
        if pu is None:
            pu = Puesto(departamento_id=p.deps[dep].id, nombre=puesto)
            bd.add(pu)
            bd.flush()
        p.puestos[clave] = pu
        t = bd.scalar(select(Tarea).where(Tarea.codigo == codigo))
        if t is None:
            t = Tarea(puesto_id=pu.id, codigo=codigo, nombre=tarea, criticidad=3)
            bd.add(t)
            bd.flush()
        p.tareas[clave] = t
    filas: list[tuple[str, str, str | None, int, str, bool]] = [
        ("ana", "Ana López", "ot", 3, "jefe", True),
        ("luis", "Luis García", "ot", 1, "empleado", False),
        ("marta", "Marta Sanz", "prod", 2, "empleado", False),
        ("pedro", "Pedro Ruiz", "prod", 1, "empleado", False),
        ("javier", "Javier Martín", "prod", 3, "jefe", False),
        ("carmen", "Carmen Díaz", "prod", 2, "empleado", True),
        ("admin", "Administración", None, 4, "admin", False),
    ]
    for usuario, nombre, dep, nivel, rol, experto in filas:
        u = bd.scalar(select(Usuario).where(Usuario.usuario == usuario))
        if u is None:
            u = Usuario(
                usuario=usuario, nombre=nombre, hash_contrasena=_hash(),
                departamento_id=p.deps[dep].id if dep else None, nivel_id=p.niveles[nivel].id,
                puesto_id=p.puestos[dep].id if dep else None, rol=rol, es_experto=experto,
            )
            bd.add(u)
            bd.flush()
        elif getattr(u, "debe_cambiar_contrasena", False):
            # Otra prueba del mismo fichero pudo restablecer su contraseña: vuelve al estado inicial.
            u.debe_cambiar_contrasena = False
            u.hash_contrasena = _hash()
        p.personas[usuario] = u
    marta = p.personas["marta"]
    if not bd.scalar(select(Formacion).where(Formacion.usuario_id == marta.id)):
        bd.add(Formacion(usuario_id=marta.id, departamento_id=p.deps["ot"].id, estado="activa"))
    bd.commit()
    return p


def token(cliente: Any, usuario: str) -> str:
    r = cliente.post("/api/auth/login", json={"usuario": usuario, "contrasena": CONTRASENA})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def cab(cliente: Any, usuario: str) -> dict[str, str]:
    """Cabeceras con la sesión de `usuario` (o de invitado si usuario == 'invitado')."""
    if usuario == "invitado":
        t = cliente.post("/api/auth/invitado").json()["token"]
    else:
        t = token(cliente, usuario)
    return {"Authorization": f"Bearer {t}"}
