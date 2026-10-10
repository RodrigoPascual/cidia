"""Administración de empleados: cuentas, roles, contraseñas y formaciones en otros departamentos.

* La administración da de alta, edita, activa o desactiva cuentas y asigna formaciones.
* Un jefe puede consultar (solo lectura) a las personas de su departamento.
* Las contraseñas solo se generan en el servidor y se devuelven UNA vez (alta y
  restablecimiento); nunca se devuelve el hash. Las cuentas de un directorio externo
  (LDAP u OIDC) no tienen contraseña en CidIA.
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import date, datetime, time, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from cidia.db import obtener_bd
from cidia.modelos import Departamento, Formacion, Nivel, Puesto, Sesion, Tarea, Usuario
from cidia.rutas.admin import cambios, columna_sin_tildes, obtener, sin_tildes, texto_limpio
from cidia.seguridad import Actor, hash_contrasena, requiere_admin, requiere_jefe
from cidia.servicios import iluo
from cidia.xapi import auditar, registrar

log = logging.getLogger("cidia.admin")

router = APIRouter(prefix="/api/admin", tags=["administración"])

ROLES = ("empleado", "jefe", "admin")
NOMBRE_ROL = {"empleado": "empleado", "jefe": "jefe de equipo", "admin": "administración"}
ORIGENES = {"local": "Cuenta de CidIA", "ldap": "Directorio de la empresa (LDAP)", "oidc": "Inicio de sesión único (OIDC)"}
_USUARIO = re.compile(r"^[a-z0-9][a-z0-9._-]{1,79}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Sin caracteres que se confunden al dictarlos o copiarlos a mano (0/O, 1/l/I).
_ALFABETO = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generar_contrasena() -> str:
    """Contraseña aleatoria legible, p. ej. «Kp7m-Rt4x-9Wqz» (unos 70 bits de entropía)."""
    return "-".join("".join(secrets.choice(_ALFABETO) for _ in range(4)) for _ in range(3))


def iniciales(nombre: str) -> str:
    partes = [p for p in nombre.split() if p]
    return ("".join(p[0] for p in partes[:2]) or "?").upper()


# --------------------------------------------------------------------------- representación


def formacion_dict(f: Formacion) -> dict[str, Any]:
    return {
        "id": f.id,
        "usuario_id": f.usuario_id,
        "departamento": {"id": f.departamento_id, "nombre": f.departamento.nombre if f.departamento else None,
                         "color": f.departamento.color if f.departamento else None},
        "puesto": {"id": f.puesto_id, "nombre": f.puesto.nombre} if f.puesto else None,
        "estado": f.estado,
        "inicio": f.inicio.isoformat() if f.inicio else None,
        "fin_previsto": f.fin_previsto.date().isoformat() if f.fin_previsto else None,
        "asignada_por_id": f.asignada_por_id,
    }


def empleado_dict(u: Usuario, formaciones_activas: int = 0) -> dict[str, Any]:
    """Datos públicos de una cuenta para la administración (nunca el hash de la contraseña)."""
    return {
        "id": u.id,
        "usuario": u.usuario,
        "nombre": u.nombre,
        "iniciales": iniciales(u.nombre),
        "email": u.email,
        "departamento": ({"id": u.departamento.id, "nombre": u.departamento.nombre, "color": u.departamento.color}
                         if u.departamento else None),
        "nivel": {"id": u.nivel.id, "orden": u.nivel.orden, "nombre": u.nivel.nombre} if u.nivel else None,
        "puesto": {"id": u.puesto.id, "nombre": u.puesto.nombre} if u.puesto else None,
        "rol": u.rol,
        "es_experto": u.es_experto,
        "activo": u.activo,
        "origen_identidad": u.origen_identidad,
        "origen_texto": ORIGENES.get(u.origen_identidad, u.origen_identidad),
        "contrasena_gestionable": u.origen_identidad == "local",
        "formaciones_activas": formaciones_activas,
        "creado": u.creado.isoformat() if u.creado else None,
        "ultimo_acceso": u.ultimo_acceso.isoformat() if u.ultimo_acceso else None,
    }


def _activas_por_usuario(bd: Session, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    filas = bd.execute(select(Formacion.usuario_id, func.count()).where(
        Formacion.usuario_id.in_(ids), Formacion.estado == "activa").group_by(Formacion.usuario_id)).all()
    return dict(filas)


def _ver_empleado(bd: Session, actor: Actor, usuario_id: int) -> Usuario:
    """Carga una persona comprobando que quien pregunta puede verla."""
    u = obtener(bd, Usuario, usuario_id, "esa persona")
    if not actor.es_admin and (actor.departamento_id is None or u.departamento_id != actor.departamento_id):
        raise HTTPException(403, "Solo puedes ver a las personas de tu departamento.")
    return u


def _revocar_sesiones(bd: Session, usuario_id: int, salvo: str | None = None) -> None:
    q = update(Sesion).where(Sesion.usuario_id == usuario_id, Sesion.revocada.is_(False))
    if salvo:
        q = q.where(Sesion.id != salvo)
    bd.execute(q.values(revocada=True))


def _otros_admins_activos(bd: Session, usuario_id: int) -> int:
    return bd.scalar(select(func.count(Usuario.id)).where(
        Usuario.rol == "admin", Usuario.activo.is_(True), Usuario.id != usuario_id)) or 0


# --------------------------------------------------------------------------- consulta


@router.get("/empleados")
def listar(
    departamento_id: int | None = None,
    rol: str | None = None,
    activo: bool | None = None,
    texto: str | None = None,
    puesto_id: int | None = None,
    actor: Actor = Depends(requiere_jefe),
    bd: Session = Depends(obtener_bd),
) -> dict[str, Any]:
    """Lista con filtros. Un jefe solo ve su departamento (y en modo lectura)."""
    q = select(Usuario)
    if not actor.es_admin:
        if actor.departamento_id is None:
            return {"empleados": [], "total": 0, "solo_lectura": True}
        if departamento_id is not None and departamento_id != actor.departamento_id:
            raise HTTPException(403, "Solo puedes ver a las personas de tu departamento.")
        departamento_id = actor.departamento_id
    if departamento_id is not None:
        q = q.where(Usuario.departamento_id == departamento_id)
    if puesto_id is not None:
        q = q.where(Usuario.puesto_id == puesto_id)
    if rol:
        if rol not in ROLES:
            raise HTTPException(400, "El rol debe ser empleado, jefe o admin.")
        q = q.where(Usuario.rol == rol)
    if activo is not None:
        q = q.where(Usuario.activo.is_(activo))
    if texto and texto.strip():
        # Sin distinguir tildes ni mayúsculas: «garcia» encuentra a «Luis García».
        patron = f"%{sin_tildes(texto)}%"
        q = q.where(or_(columna_sin_tildes(Usuario.nombre).like(patron), columna_sin_tildes(Usuario.usuario).like(patron),
                        columna_sin_tildes(func.coalesce(Usuario.email, "")).like(patron)))
    # Departamento, nivel y puesto en tres consultas en total (no tres por persona).
    q = q.options(selectinload(Usuario.departamento), selectinload(Usuario.nivel), selectinload(Usuario.puesto))
    filas = bd.scalars(q.order_by(Usuario.activo.desc(), Usuario.nombre).limit(2000)).all()
    activas = _activas_por_usuario(bd, [u.id for u in filas])
    return {
        "empleados": [empleado_dict(u, activas.get(u.id, 0)) for u in filas],
        "total": len(filas),
        "solo_lectura": not actor.es_admin,
    }


@router.get("/empleados/{usuario_id}")
def detalle(usuario_id: int, actor: Actor = Depends(requiere_jefe), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    u = _ver_empleado(bd, actor, usuario_id)
    formaciones = bd.scalars(select(Formacion).where(Formacion.usuario_id == u.id)
                             .order_by(Formacion.estado != "activa", Formacion.inicio.desc())).all()
    datos = empleado_dict(u, sum(1 for f in formaciones if f.estado == "activa"))
    datos["formaciones"] = [formacion_dict(f) for f in formaciones]
    return datos


# --------------------------------------------------------------------------- alta y edición


class DatosEmpleado(BaseModel):
    usuario: str | None = None
    nombre: str | None = None
    email: str | None = None
    departamento_id: int | None = None
    nivel_id: int | None = None
    puesto_id: int | None = None
    rol: str | None = None
    es_experto: bool | None = None
    origen_identidad: str | None = None
    id_externo: str | None = None


def _validar_empleado(bd: Session, datos: dict[str, Any], actual: Usuario | None) -> dict[str, Any]:
    """Valida y normaliza los datos de una cuenta. Solo devuelve los campos presentes."""
    limpio: dict[str, Any] = {}
    if actual is None:
        usuario = (datos.get("usuario") or "").strip().lower()
        if not _USUARIO.match(usuario):
            raise HTTPException(400, "El usuario debe tener entre 2 y 80 caracteres: letras sin tilde, números, "
                                     "punto, guion o guion bajo, y empezar por letra o número.")
        if bd.scalar(select(Usuario).where(func.lower(Usuario.usuario) == usuario)) is not None:
            raise HTTPException(409, f"Ya existe una cuenta con el usuario «{usuario}».")
        limpio["usuario"] = usuario
        origen = datos.get("origen_identidad") or "local"
        if origen not in ORIGENES:
            raise HTTPException(400, "El origen de identidad debe ser local, ldap u oidc.")
        limpio["origen_identidad"] = origen
        limpio["id_externo"] = texto_limpio(datos.get("id_externo"), "el identificador externo", 200)
    elif "usuario" in datos and (datos["usuario"] or "").strip().lower() != actual.usuario.lower():
        raise HTTPException(400, "El nombre de usuario no se puede cambiar: identifica a la persona en el registro.")
    if actual is None or "nombre" in datos:
        limpio["nombre"] = texto_limpio(datos.get("nombre"), "el nombre", 150, obligatorio=True)
    if "email" in datos:
        email = texto_limpio(datos.get("email"), "el correo", 200)
        if email and not _EMAIL.match(email):
            raise HTTPException(400, "El correo electrónico no tiene un formato válido.")
        limpio["email"] = email

    dep_id = datos["departamento_id"] if "departamento_id" in datos else (actual.departamento_id if actual else None)
    puesto_id = datos["puesto_id"] if "puesto_id" in datos else (actual.puesto_id if actual else None)
    if "departamento_id" in datos and dep_id is not None:
        obtener(bd, Departamento, dep_id, "el departamento elegido")
    if puesto_id is not None:
        puesto = obtener(bd, Puesto, puesto_id, "el puesto elegido")
        if dep_id is None and "departamento_id" not in datos:
            dep_id = puesto.departamento_id  # el puesto fija el departamento si no se indica
        elif puesto.departamento_id != dep_id:
            if "puesto_id" in datos:
                raise HTTPException(400, f"El puesto «{puesto.nombre}» no pertenece al departamento elegido.")
            puesto_id = None  # cambio de departamento: el puesto anterior deja de valer
    if actual is None or "departamento_id" in datos or "puesto_id" in datos:
        limpio["departamento_id"] = dep_id
        limpio["puesto_id"] = puesto_id

    if "nivel_id" in datos and datos["nivel_id"] is not None:
        obtener(bd, Nivel, datos["nivel_id"], "el nivel elegido")
        limpio["nivel_id"] = datos["nivel_id"]
    elif actual is None:
        # Sin nivel indicado, el más bajo de la empresa.
        limpio["nivel_id"] = bd.scalar(select(Nivel.id).order_by(Nivel.orden).limit(1))

    rol = datos.get("rol") if datos.get("rol") is not None else (actual.rol if actual else "empleado")
    if rol not in ROLES:
        raise HTTPException(400, "El rol debe ser empleado, jefe o admin.")
    if rol == "jefe" and dep_id is None:
        raise HTTPException(400, "Un jefe de equipo necesita un departamento.")
    if actual is None or "rol" in datos:
        limpio["rol"] = rol
    if datos.get("es_experto") is not None:
        limpio["es_experto"] = bool(datos["es_experto"])
    return limpio


@router.post("/empleados")
def crear(datos: DatosEmpleado, actor: Actor = Depends(requiere_admin), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Alta de una cuenta. Si es local, la contraseña inicial se devuelve solo en esta respuesta."""
    limpio = _validar_empleado(bd, datos.model_dump(exclude_unset=True), None)
    contrasena = generar_contrasena() if limpio["origen_identidad"] == "local" else None
    u = Usuario(**limpio, hash_contrasena=hash_contrasena(contrasena) if contrasena else None,
                debe_cambiar_contrasena=bool(contrasena))  # la inicial se cambia en el primer acceso
    bd.add(u)
    bd.flush()
    bd.refresh(u)
    auditar(bd, actor, "crear_empleado", "usuario", u.id, {
        "resumen": f"Dio de alta a {u.nombre} ({u.usuario}) como {NOMBRE_ROL[u.rol]}",
        "departamento": u.departamento.nombre if u.departamento else None,
        "origen_identidad": u.origen_identidad,
    })
    bd.commit()
    return {"empleado": empleado_dict(u), "contrasena_inicial": contrasena}


@router.put("/empleados/{usuario_id}")
def editar(usuario_id: int, datos: DatosEmpleado, actor: Actor = Depends(requiere_admin),
           bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    u = obtener(bd, Usuario, usuario_id, "esa persona")
    entrada = datos.model_dump(exclude_unset=True)
    entrada.pop("origen_identidad", None)  # el origen no se cambia desde aquí
    entrada.pop("id_externo", None)
    limpio = _validar_empleado(bd, entrada, u)
    if u.rol == "admin" and limpio.get("rol", "admin") != "admin":
        if u.id == actor.id:
            raise HTTPException(400, "No puedes quitarte a ti mismo el rol de administración.")
        if not _otros_admins_activos(bd, u.id):
            raise HTTPException(400, "Es la única cuenta de administración activa. Nombra antes a otra persona.")
    hechos = cambios(u, limpio)
    if hechos:
        bd.flush()
        bd.refresh(u)
        auditar(bd, actor, "editar_empleado", "usuario", u.id,
                {"resumen": f"Editó la cuenta de {u.nombre}", "cambios": hechos})
    bd.commit()
    activas = _activas_por_usuario(bd, [u.id])
    return empleado_dict(u, activas.get(u.id, 0))


@router.post("/empleados/{usuario_id}/desactivar")
def desactivar(usuario_id: int, actor: Actor = Depends(requiere_admin), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Desactiva la cuenta y cierra sus sesiones abiertas. Su historial se conserva."""
    u = obtener(bd, Usuario, usuario_id, "esa persona")
    if u.id == actor.id:
        raise HTTPException(400, "No puedes desactivar tu propia cuenta.")
    if u.rol == "admin" and u.activo and not _otros_admins_activos(bd, u.id):
        raise HTTPException(400, "Es la única cuenta de administración activa.")
    if u.activo:
        u.activo = False
        _revocar_sesiones(bd, u.id)
        auditar(bd, actor, "desactivar_empleado", "usuario", u.id, {"resumen": f"Desactivó la cuenta de {u.nombre}"})
    bd.commit()
    return empleado_dict(u)


@router.post("/empleados/{usuario_id}/activar")
def activar(usuario_id: int, actor: Actor = Depends(requiere_admin), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    u = obtener(bd, Usuario, usuario_id, "esa persona")
    if not u.activo:
        u.activo = True
        auditar(bd, actor, "activar_empleado", "usuario", u.id, {"resumen": f"Reactivó la cuenta de {u.nombre}"})
    bd.commit()
    return empleado_dict(u)


@router.post("/empleados/{usuario_id}/contrasena")
def restablecer_contrasena(usuario_id: int, actor: Actor = Depends(requiere_admin),
                           bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Genera una contraseña temporal (se devuelve solo aquí) y cierra las sesiones abiertas."""
    u = obtener(bd, Usuario, usuario_id, "esa persona")
    if u.origen_identidad != "local":
        raise HTTPException(400, f"La contraseña de {u.nombre} se gestiona en "
                                 f"{ORIGENES.get(u.origen_identidad, 'el directorio de la empresa').lower()}, no en CidIA.")
    temporal = generar_contrasena()
    u.hash_contrasena = hash_contrasena(temporal)
    u.debe_cambiar_contrasena = True  # la temporal se cambia en el siguiente acceso
    _revocar_sesiones(bd, u.id, salvo=actor.sesion.id if u.id == actor.id else None)
    auditar(bd, actor, "restablecer_contrasena", "usuario", u.id,
            {"resumen": f"Restableció la contraseña de {u.nombre}"})
    bd.commit()
    return {"contrasena_temporal": temporal, "usuario": u.usuario}


# --------------------------------------------------------------------------- formaciones


class DatosFormacion(BaseModel):
    departamento_id: int
    puesto_id: int | None = None
    fin_previsto: date | None = None


def _tareas_de_formacion(bd: Session, f: Formacion) -> list[int]:
    q = select(Tarea.id).join(Puesto).where(Puesto.departamento_id == f.departamento_id)
    if f.puesto_id:
        q = q.where(Tarea.puesto_id == f.puesto_id)
    return list(bd.scalars(q).all())


def _recalcular_iluo(bd: Session, f: Formacion) -> None:
    """El nivel I depende de las formaciones activas: se recalcula en las tareas afectadas.

    Va en un punto de guardado para que un fallo del cálculo no impida asignar la formación.
    """
    for tarea_id in _tareas_de_formacion(bd, f):
        try:
            with bd.begin_nested():
                iluo.recalcular(bd, f.usuario_id, tarea_id)
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo recalcular ILUO de %s en la tarea %s: %s", f.usuario_id, tarea_id, e)


@router.get("/empleados/{usuario_id}/formaciones")
def formaciones(usuario_id: int, actor: Actor = Depends(requiere_jefe),
                bd: Session = Depends(obtener_bd)) -> list[dict[str, Any]]:
    u = _ver_empleado(bd, actor, usuario_id)
    filas = bd.scalars(select(Formacion).where(Formacion.usuario_id == u.id)
                       .order_by(Formacion.estado != "activa", Formacion.inicio.desc())).all()
    return [formacion_dict(f) for f in filas]


@router.post("/empleados/{usuario_id}/formaciones")
def asignar_formacion(usuario_id: int, datos: DatosFormacion, actor: Actor = Depends(requiere_admin),
                      bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Formación en otro departamento: da acceso a su material de formación (ver permisos.py)."""
    u = obtener(bd, Usuario, usuario_id, "esa persona")
    dep = obtener(bd, Departamento, datos.departamento_id, "el departamento elegido")
    if dep.id == u.departamento_id:
        raise HTTPException(400, f"{u.nombre} ya pertenece a {dep.nombre}. La formación es para aprender en otro departamento.")
    puesto = None
    if datos.puesto_id is not None:
        puesto = obtener(bd, Puesto, datos.puesto_id, "el puesto elegido")
        if puesto.departamento_id != dep.id:
            raise HTTPException(400, f"El puesto «{puesto.nombre}» no pertenece a {dep.nombre}.")
    if bd.scalar(select(Formacion).where(Formacion.usuario_id == u.id, Formacion.departamento_id == dep.id,
                                         Formacion.estado == "activa")) is not None:
        raise HTTPException(409, f"{u.nombre} ya tiene una formación activa en {dep.nombre}.")
    fin = None
    if datos.fin_previsto is not None:
        if datos.fin_previsto < datetime.now(timezone.utc).date():
            raise HTTPException(400, "La fecha prevista de fin no puede ser anterior a hoy.")
        fin = datetime.combine(datos.fin_previsto, time(12), tzinfo=timezone.utc)
    f = Formacion(usuario_id=u.id, departamento_id=dep.id, puesto_id=puesto.id if puesto else None,
                  estado="activa", fin_previsto=fin, asignada_por_id=actor.id)
    bd.add(f)
    bd.flush()
    bd.refresh(f)
    nombre = f"Formación en {dep.nombre}" + (f" · {puesto.nombre}" if puesto else "")
    registrar(bd, None, "inicio", "formacion", f.id, nombre, actor_id=u.id, actor_nombre=u.nombre,
              contexto={"departamento_id": dep.id, "puesto_id": f.puesto_id, "asignada_por": actor.nombre})
    auditar(bd, actor, "asignar_formacion", "formacion", f.id,
            {"resumen": f"Asignó a {u.nombre} una formación en {dep.nombre}" + (f" ({puesto.nombre})" if puesto else ""),
             "usuario_id": u.id, "fin_previsto": datos.fin_previsto.isoformat() if datos.fin_previsto else None})
    _recalcular_iluo(bd, f)
    bd.commit()
    return formacion_dict(f)


def _cerrar_formacion(bd: Session, actor: Actor, formacion_id: int, estado: str) -> dict[str, Any]:
    f = obtener(bd, Formacion, formacion_id, "esa formación")
    if f.estado != "activa":
        raise HTTPException(400, "Esa formación ya no está activa.")
    u = bd.get(Usuario, f.usuario_id)
    f.estado = estado
    dep = f.departamento.nombre if f.departamento else "otro departamento"
    if estado == "completada":
        registrar(bd, None, "completo", "formacion", f.id, f"Formación en {dep}", actor_id=f.usuario_id,
                  actor_nombre=u.nombre if u else None, resultado={"completion": True},
                  contexto={"departamento_id": f.departamento_id, "validada_por": actor.nombre})
    verbo = "Dio por completada" if estado == "completada" else "Canceló"
    auditar(bd, actor, f"{'completar' if estado == 'completada' else 'cancelar'}_formacion", "formacion", f.id,
            {"resumen": f"{verbo} la formación de {u.nombre if u else 'una persona'} en {dep}", "usuario_id": f.usuario_id})
    bd.flush()
    _recalcular_iluo(bd, f)
    bd.commit()
    return formacion_dict(f)


@router.post("/formaciones/{formacion_id}/completar")
def completar_formacion(formacion_id: int, actor: Actor = Depends(requiere_admin),
                        bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return _cerrar_formacion(bd, actor, formacion_id, "completada")


@router.post("/formaciones/{formacion_id}/cancelar")
def cancelar_formacion(formacion_id: int, actor: Actor = Depends(requiere_admin),
                       bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    return _cerrar_formacion(bd, actor, formacion_id, "cancelada")
