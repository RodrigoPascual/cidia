"""Administración: organización (departamentos, niveles, puestos y tareas) y datos de la empresa.

Solo la administración puede cambiar la organización; cada cambio deja una fila de auditoría
con un `resumen` legible en `detalle`. Los borrados que romperían el historial (personas,
documentos, instrucciones o niveles ILUO que dependen del elemento) se rechazan con una
explicación de qué hacer en su lugar.

Las utilidades de validación de este módulo (`texto_limpio`, `obtener`, `cambios`) las usan
también los demás routers de administración (`admin_*.py`).
"""

from __future__ import annotations

import re
from typing import Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from cidia.arranque import CONFIG_ILUO_POR_DEFECTO
from cidia.db import obtener_bd
from cidia.modelos import (
    Aportacion,
    Departamento,
    Documento,
    Empresa,
    Formacion,
    Instruccion,
    Nivel,
    NivelIluo,
    Observacion,
    Puesto,
    Tarea,
    Usuario,
)
from cidia.seguridad import Actor, requiere_admin
from cidia.xapi import auditar

router = APIRouter(prefix="/api/admin", tags=["administración"])

T = TypeVar("T")

# Colores que se asignan a los departamentos nuevos si no se elige ninguno.
PALETA_DEPARTAMENTOS = ["#1F8A70", "#2F6FBF", "#C8442F", "#7A4FB5", "#D97A00", "#0E7C86", "#8A6D00", "#3A4048"]
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


# --------------------------------------------------------------------------- utilidades comunes


def texto_limpio(valor: str | None, campo: str, maximo: int, obligatorio: bool = False) -> str | None:
    """Recorta espacios y valida longitud. Devuelve None si queda vacío."""
    v = (valor or "").strip()
    if obligatorio and not v:
        raise HTTPException(400, f"Falta {campo}.")
    if len(v) > maximo:
        raise HTTPException(400, f"El campo {campo} no puede superar {maximo} caracteres.")
    return v or None


def obtener(bd: Session, modelo: type[T], ident: int | None, nombre: str) -> T:
    """Carga una fila por id o responde 404 con un mensaje claro."""
    fila = bd.get(modelo, ident) if ident is not None else None
    if fila is None:
        raise HTTPException(404, f"No existe {nombre}.")
    return fila


def cambios(fila: Any, datos: dict[str, Any]) -> dict[str, list[Any]]:
    """Aplica `datos` a `fila` y devuelve {campo: [antes, después]} de lo que ha cambiado."""
    hechos: dict[str, list[Any]] = {}
    for campo, nuevo in datos.items():
        antes = getattr(fila, campo)
        if antes != nuevo:
            setattr(fila, campo, nuevo)
            hechos[campo] = [antes, nuevo]
    return hechos


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _explicar_uso(uso: dict[str, int]) -> str:
    """«3 personas, 2 documentos y 1 tarea con instrucciones»."""
    nombres = {
        "personas": ("persona", "personas"),
        "documentos": ("documento", "documentos"),
        "formaciones": ("formación activa", "formaciones activas"),
        "formaciones_registradas": ("formación registrada", "formaciones registradas"),
        "tareas_con_historial": ("tarea con instrucciones, niveles ILUO u observaciones",
                                 "tareas con instrucciones, niveles ILUO u observaciones"),
        "instrucciones": ("instrucción", "instrucciones"),
        "niveles_iluo": ("nivel ILUO registrado", "niveles ILUO registrados"),
        "observaciones": ("observación en el puesto", "observaciones en el puesto"),
        "tareas": ("tarea", "tareas"),
        "aportaciones": ("aportación", "aportaciones"),
    }
    partes = [_plural(n, *nombres[k]) for k, n in uso.items() if n]
    if len(partes) > 1:
        return ", ".join(partes[:-1]) + " y " + partes[-1]
    return partes[0] if partes else ""


# --------------------------------------------------------------------------- representación


def nivel_dict(n: Nivel, personas: int = 0) -> dict[str, Any]:
    return {"id": n.id, "orden": n.orden, "nombre": n.nombre, "descripcion": n.descripcion, "n_personas": personas}


def departamento_dict(d: Departamento, personas: int = 0) -> dict[str, Any]:
    return {"id": d.id, "nombre": d.nombre, "codigo": d.codigo, "descripcion": d.descripcion, "color": d.color,
            "n_personas": personas, "creado": d.creado.isoformat() if d.creado else None}


def puesto_dict(p: Puesto, personas: int = 0) -> dict[str, Any]:
    return {"id": p.id, "departamento_id": p.departamento_id, "nombre": p.nombre, "descripcion": p.descripcion,
            "n_personas": personas}


def tarea_dict(t: Tarea, departamento_id: int | None = None, instrucciones: int = 0,
               publicada: bool = False) -> dict[str, Any]:
    return {
        "id": t.id, "puesto_id": t.puesto_id, "departamento_id": departamento_id, "codigo": t.codigo,
        "nombre": t.nombre, "descripcion": t.descripcion, "criticidad": t.criticidad, "riesgos_prl": t.riesgos_prl,
        "nivel_minimo": t.nivel_minimo, "activa": t.activa, "n_instrucciones": instrucciones,
        "instruccion_publicada": publicada, "creada": t.creada.isoformat() if t.creada else None,
    }


def _tareas_con_historial(bd: Session, tareas: Any) -> int:
    """Cuántas de las tareas (subconsulta de ids) tienen historial que un borrado en cascada perdería:
    instrucciones (y con ellas ejecuciones y evaluaciones), niveles ILUO u observaciones en el puesto."""
    return bd.scalar(select(func.count(Tarea.id)).where(
        Tarea.id.in_(tareas),
        Tarea.id.in_(select(Instruccion.tarea_id)) | Tarea.id.in_(select(NivelIluo.tarea_id))
        | Tarea.id.in_(select(Observacion.tarea_id)))) or 0


def _conteo(bd: Session, columna: Any) -> dict[int, int]:
    """Personas (activas o no) agrupadas por una columna de Usuario."""
    return {k: n for k, n in bd.execute(select(columna, func.count()).group_by(columna)).all() if k is not None}


# --------------------------------------------------------------------------- árbol completo


@router.get("/organizacion")
def organizacion(_: Actor = Depends(requiere_admin), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    """Departamentos → puestos → tareas, con niveles y cifras para la vista de organización."""
    por_dep = _conteo(bd, Usuario.departamento_id)
    por_puesto = _conteo(bd, Usuario.puesto_id)
    por_nivel = _conteo(bd, Usuario.nivel_id)
    instr = dict(bd.execute(select(Instruccion.tarea_id, func.count()).group_by(Instruccion.tarea_id)).all())
    publicadas = set(bd.scalars(select(Instruccion.tarea_id).where(Instruccion.estado == "publicada")).all())
    deps = bd.scalars(select(Departamento).order_by(Departamento.nombre)).all()
    puestos = bd.scalars(select(Puesto).order_by(Puesto.nombre)).all()
    tareas = bd.scalars(select(Tarea).order_by(Tarea.codigo.nulls_last(), Tarea.nombre)).all()
    dep_de_puesto = {p.id: p.departamento_id for p in puestos}

    tareas_por_puesto: dict[int, list[dict[str, Any]]] = {}
    for t in tareas:
        tareas_por_puesto.setdefault(t.puesto_id, []).append(
            tarea_dict(t, dep_de_puesto.get(t.puesto_id), instr.get(t.id, 0), t.id in publicadas))
    puestos_por_dep: dict[int, list[dict[str, Any]]] = {}
    for p in puestos:
        datos = puesto_dict(p, por_puesto.get(p.id, 0))
        datos["tareas"] = tareas_por_puesto.get(p.id, [])
        puestos_por_dep.setdefault(p.departamento_id, []).append(datos)

    salida = []
    for d in deps:
        datos = departamento_dict(d, por_dep.get(d.id, 0))
        datos["puestos"] = puestos_por_dep.get(d.id, [])
        salida.append(datos)
    niveles = bd.scalars(select(Nivel).order_by(Nivel.orden)).all()
    return {
        "departamentos": salida,
        "niveles": [nivel_dict(n, por_nivel.get(n.id, 0)) for n in niveles],
        "resumen": {
            "departamentos": len(deps),
            "puestos": len(puestos),
            "tareas": len(tareas),
            "tareas_activas": sum(1 for t in tareas if t.activa),
            "personas": sum(por_dep.values()),
        },
    }


# --------------------------------------------------------------------------- departamentos


class DatosDepartamento(BaseModel):
    nombre: str | None = None
    codigo: str | None = None
    descripcion: str | None = None
    color: str | None = None


def _validar_departamento(bd: Session, datos: dict[str, Any], actual: Departamento | None) -> dict[str, Any]:
    limpio: dict[str, Any] = {}
    if "nombre" in datos or actual is None:
        nombre = texto_limpio(datos.get("nombre"), "el nombre del departamento", 150, obligatorio=True)
        otro = bd.scalar(select(Departamento).where(func.lower(Departamento.nombre) == nombre.lower()))
        if otro is not None and otro is not actual:
            raise HTTPException(409, f"Ya hay un departamento llamado «{otro.nombre}».")
        limpio["nombre"] = nombre
    if "codigo" in datos:
        codigo = texto_limpio(datos.get("codigo"), "el código", 30)
        if codigo:
            codigo = codigo.upper()
            otro = bd.scalar(select(Departamento).where(func.upper(Departamento.codigo) == codigo))
            if otro is not None and otro is not actual:
                raise HTTPException(409, f"El código {codigo} ya lo usa el departamento «{otro.nombre}».")
        limpio["codigo"] = codigo
    if "descripcion" in datos:
        limpio["descripcion"] = texto_limpio(datos.get("descripcion"), "la descripción", 2000)
    if "color" in datos:
        color = (datos.get("color") or "").strip() or None
        if color and not _COLOR.match(color):
            raise HTTPException(400, "El color debe tener el formato #RRGGBB (por ejemplo, #1F8A70).")
        limpio["color"] = color.upper() if color else None
    return limpio


@router.post("/departamentos")
def crear_departamento(datos: DatosDepartamento, actor: Actor = Depends(requiere_admin),
                       bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    limpio = _validar_departamento(bd, datos.model_dump(exclude_unset=True), None)
    if not limpio.get("color"):
        n = bd.scalar(select(func.count(Departamento.id))) or 0
        limpio["color"] = PALETA_DEPARTAMENTOS[n % len(PALETA_DEPARTAMENTOS)]
    d = Departamento(**limpio)
    bd.add(d)
    bd.flush()
    auditar(bd, actor, "crear_departamento", "departamento", d.id,
            {"resumen": f"Creó el departamento «{d.nombre}»", **limpio})
    bd.commit()
    return departamento_dict(d)


@router.put("/departamentos/{dep_id}")
def editar_departamento(dep_id: int, datos: DatosDepartamento, actor: Actor = Depends(requiere_admin),
                        bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    d = obtener(bd, Departamento, dep_id, "ese departamento")
    hechos = cambios(d, _validar_departamento(bd, datos.model_dump(exclude_unset=True), d))
    if hechos:
        auditar(bd, actor, "editar_departamento", "departamento", d.id,
                {"resumen": f"Editó el departamento «{d.nombre}»", "cambios": hechos})
    bd.commit()
    return departamento_dict(d, bd.scalar(select(func.count(Usuario.id)).where(Usuario.departamento_id == d.id)) or 0)


@router.delete("/departamentos/{dep_id}")
def borrar_departamento(dep_id: int, actor: Actor = Depends(requiere_admin),
                        bd: Session = Depends(obtener_bd)) -> dict[str, bool]:
    d = obtener(bd, Departamento, dep_id, "ese departamento")
    tareas = select(Tarea.id).join(Puesto).where(Puesto.departamento_id == d.id)
    uso = {
        "personas": bd.scalar(select(func.count(Usuario.id)).where(Usuario.departamento_id == d.id)) or 0,
        "documentos": bd.scalar(select(func.count(Documento.id)).where(Documento.departamento_id == d.id)) or 0,
        "aportaciones": bd.scalar(select(func.count(Aportacion.id)).where(Aportacion.departamento_id == d.id)) or 0,
        # Cualquier formación (también las pasadas): forman parte del historial de las personas.
        "formaciones_registradas": bd.scalar(select(func.count(Formacion.id)).where(
            Formacion.departamento_id == d.id)) or 0,
        "tareas_con_historial": _tareas_con_historial(bd, tareas),
    }
    if any(uso.values()):
        raise HTTPException(
            409, f"No se puede borrar «{d.nombre}» porque tiene {_explicar_uso(uso)}. "
                 "Mueve o retira antes lo que depende de él.")
    nombre = d.nombre
    bd.delete(d)
    auditar(bd, actor, "borrar_departamento", "departamento", dep_id, {"resumen": f"Borró el departamento «{nombre}»"})
    bd.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- niveles


class DatosNivel(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    orden: int | None = None


class OrdenNiveles(BaseModel):
    ids: list[int]


def _validar_nombre_nivel(bd: Session, nombre: str | None, actual: Nivel | None) -> str:
    limpio = texto_limpio(nombre, "el nombre del nivel", 100, obligatorio=True)
    otro = bd.scalar(select(Nivel).where(func.lower(Nivel.nombre) == limpio.lower()))
    if otro is not None and otro is not actual:
        raise HTTPException(409, f"Ya hay un nivel llamado «{otro.nombre}».")
    return limpio


@router.get("/niveles")
def niveles(_: Actor = Depends(requiere_admin), bd: Session = Depends(obtener_bd)) -> list[dict[str, Any]]:
    por_nivel = _conteo(bd, Usuario.nivel_id)
    return [nivel_dict(n, por_nivel.get(n.id, 0)) for n in bd.scalars(select(Nivel).order_by(Nivel.orden)).all()]


@router.post("/niveles")
def crear_nivel(datos: DatosNivel, actor: Actor = Depends(requiere_admin),
                bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    nombre = _validar_nombre_nivel(bd, datos.nombre, None)
    orden = datos.orden
    if orden is None:
        orden = (bd.scalar(select(func.max(Nivel.orden))) or 0) + 1
    elif orden < 1:
        raise HTTPException(400, "El orden del nivel empieza en 1.")
    elif bd.scalar(select(Nivel).where(Nivel.orden == orden)) is not None:
        raise HTTPException(409, f"Ya hay un nivel con el orden {orden}.")
    n = Nivel(orden=orden, nombre=nombre, descripcion=texto_limpio(datos.descripcion, "la descripción", 1000))
    bd.add(n)
    bd.flush()
    auditar(bd, actor, "crear_nivel", "nivel", n.id, {"resumen": f"Creó el nivel «{n.nombre}» ({orden})"})
    bd.commit()
    return nivel_dict(n)


@router.put("/niveles/orden")
def ordenar_niveles(datos: OrdenNiveles, actor: Actor = Depends(requiere_admin),
                    bd: Session = Depends(obtener_bd)) -> list[dict[str, Any]]:
    """Reordena los niveles (el primero es el más bajo).

    El orden es el número que usan `nivel_minimo` de tareas, documentos y aportaciones, así
    que se traducen también esos valores para que cada elemento siga apuntando al mismo
    nivel por su nombre.
    """
    todos = {n.id: n for n in bd.scalars(select(Nivel)).all()}
    if sorted(datos.ids) != sorted(todos) or len(set(datos.ids)) != len(datos.ids):
        raise HTTPException(400, "La lista debe contener todos los niveles una sola vez.")
    antes = {n.id: n.orden for n in todos.values()}
    nuevo = {nid: i for i, nid in enumerate(datos.ids, start=1)}
    traduccion = {antes[nid]: nuevo[nid] for nid in datos.ids if antes[nid] != nuevo[nid]}
    if traduccion:
        # Dos pasos para no chocar con la restricción única de `orden`.
        for n in todos.values():
            n.orden = -n.orden
        bd.flush()
        for nid, orden in nuevo.items():
            todos[nid].orden = orden
        bd.flush()
        for modelo in (Tarea, Documento, Aportacion):
            col = modelo.nivel_minimo
            bd.execute(update(modelo).where(col.in_(list(traduccion)))
                       .values(nivel_minimo=case(traduccion, value=col)))
        auditar(bd, actor, "ordenar_niveles", "nivel", None, {
            "resumen": "Cambió el orden de los niveles: " + " → ".join(todos[i].nombre for i in datos.ids),
            "traduccion": {str(k): v for k, v in traduccion.items()},
        })
    bd.commit()
    por_nivel = _conteo(bd, Usuario.nivel_id)
    return [nivel_dict(todos[i], por_nivel.get(i, 0)) for i in datos.ids]


@router.put("/niveles/{nivel_id}")
def editar_nivel(nivel_id: int, datos: DatosNivel, actor: Actor = Depends(requiere_admin),
                 bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    n = obtener(bd, Nivel, nivel_id, "ese nivel")
    entrada = datos.model_dump(exclude_unset=True)
    limpio: dict[str, Any] = {}
    if "nombre" in entrada:
        limpio["nombre"] = _validar_nombre_nivel(bd, entrada["nombre"], n)
    if "descripcion" in entrada:
        limpio["descripcion"] = texto_limpio(entrada["descripcion"], "la descripción", 1000)
    if "orden" in entrada and entrada["orden"] != n.orden:
        raise HTTPException(400, "Para cambiar el orden, arrastra el nivel en la lista de niveles.")
    hechos = cambios(n, limpio)
    if hechos:
        auditar(bd, actor, "editar_nivel", "nivel", n.id, {"resumen": f"Editó el nivel «{n.nombre}»", "cambios": hechos})
    bd.commit()
    return nivel_dict(n, bd.scalar(select(func.count(Usuario.id)).where(Usuario.nivel_id == n.id)) or 0)


@router.delete("/niveles/{nivel_id}")
def borrar_nivel(nivel_id: int, actor: Actor = Depends(requiere_admin),
                 bd: Session = Depends(obtener_bd)) -> dict[str, bool]:
    n = obtener(bd, Nivel, nivel_id, "ese nivel")
    if (bd.scalar(select(func.count(Nivel.id))) or 0) <= 1:
        raise HTTPException(400, "Debe quedar al menos un nivel.")
    uso = {
        "personas": bd.scalar(select(func.count(Usuario.id)).where(Usuario.nivel_id == n.id)) or 0,
        "tareas": bd.scalar(select(func.count(Tarea.id)).where(Tarea.nivel_minimo == n.orden)) or 0,
        "documentos": bd.scalar(select(func.count(Documento.id)).where(Documento.nivel_minimo == n.orden)) or 0,
        "aportaciones": bd.scalar(select(func.count(Aportacion.id)).where(Aportacion.nivel_minimo == n.orden)) or 0,
    }
    if any(uso.values()):
        raise HTTPException(409, f"El nivel «{n.nombre}» está en uso ({_explicar_uso(uso)}). "
                                 "Cámbialos a otro nivel antes de borrarlo.")
    nombre = n.nombre
    bd.delete(n)
    auditar(bd, actor, "borrar_nivel", "nivel", nivel_id, {"resumen": f"Borró el nivel «{nombre}»"})
    bd.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- puestos


class DatosPuesto(BaseModel):
    departamento_id: int | None = None
    nombre: str | None = None
    descripcion: str | None = None


def _validar_puesto(bd: Session, datos: dict[str, Any], actual: Puesto | None) -> dict[str, Any]:
    limpio: dict[str, Any] = {}
    dep_id = datos.get("departamento_id", actual.departamento_id if actual else None)
    if actual is None or "departamento_id" in datos:
        if dep_id is None:
            raise HTTPException(400, "Elige el departamento del puesto.")
        obtener(bd, Departamento, dep_id, "el departamento elegido")
        limpio["departamento_id"] = dep_id
    if actual is None or "nombre" in datos or "departamento_id" in datos:
        nombre = texto_limpio(datos.get("nombre", actual.nombre if actual else None), "el nombre del puesto", 150,
                              obligatorio=True)
        otro = bd.scalar(select(Puesto).where(Puesto.departamento_id == dep_id,
                                              func.lower(Puesto.nombre) == nombre.lower()))
        if otro is not None and otro is not actual:
            raise HTTPException(409, f"Ese departamento ya tiene un puesto llamado «{otro.nombre}».")
        limpio["nombre"] = nombre
    if "descripcion" in datos:
        limpio["descripcion"] = texto_limpio(datos.get("descripcion"), "la descripción", 2000)
    return limpio


@router.post("/puestos")
def crear_puesto(datos: DatosPuesto, actor: Actor = Depends(requiere_admin),
                 bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    p = Puesto(**_validar_puesto(bd, datos.model_dump(exclude_unset=True), None))
    bd.add(p)
    bd.flush()
    dep = bd.get(Departamento, p.departamento_id)
    auditar(bd, actor, "crear_puesto", "puesto", p.id,
            {"resumen": f"Creó el puesto «{p.nombre}» en {dep.nombre if dep else 'el departamento'}"})
    bd.commit()
    return puesto_dict(p)


@router.put("/puestos/{puesto_id}")
def editar_puesto(puesto_id: int, datos: DatosPuesto, actor: Actor = Depends(requiere_admin),
                  bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    p = obtener(bd, Puesto, puesto_id, "ese puesto")
    entrada = datos.model_dump(exclude_unset=True)
    if entrada.get("departamento_id") is not None and entrada["departamento_id"] != p.departamento_id:
        # Las personas con este puesto quedarían en otro departamento: se exige moverlas antes.
        personas = bd.scalar(select(func.count(Usuario.id)).where(Usuario.puesto_id == p.id)) or 0
        if personas:
            raise HTTPException(409, f"El puesto tiene {_plural(personas, 'persona asignada', 'personas asignadas')}. "
                                     "Cámbiales el puesto antes de moverlo de departamento.")
        # Las instrucciones ya publicadas están indexadas en el departamento actual y las
        # formaciones apuntan a él: moverlo dejaría permisos y niveles ILUO incoherentes.
        uso = {
            "formaciones": bd.scalar(select(func.count(Formacion.id)).where(
                Formacion.puesto_id == p.id, Formacion.estado == "activa")) or 0,
            "tareas_con_historial": _tareas_con_historial(bd, select(Tarea.id).where(Tarea.puesto_id == p.id)),
        }
        if any(uso.values()):
            raise HTTPException(409, f"El puesto «{p.nombre}» tiene {_explicar_uso(uso)} en su departamento actual. "
                                     "Crea un puesto nuevo en el otro departamento en lugar de moverlo.")
    hechos = cambios(p, _validar_puesto(bd, entrada, p))
    if hechos:
        auditar(bd, actor, "editar_puesto", "puesto", p.id, {"resumen": f"Editó el puesto «{p.nombre}»", "cambios": hechos})
    bd.commit()
    return puesto_dict(p, bd.scalar(select(func.count(Usuario.id)).where(Usuario.puesto_id == p.id)) or 0)


@router.delete("/puestos/{puesto_id}")
def borrar_puesto(puesto_id: int, actor: Actor = Depends(requiere_admin),
                  bd: Session = Depends(obtener_bd)) -> dict[str, bool]:
    p = obtener(bd, Puesto, puesto_id, "ese puesto")
    tareas = select(Tarea.id).where(Tarea.puesto_id == p.id)
    uso = {
        "personas": bd.scalar(select(func.count(Usuario.id)).where(Usuario.puesto_id == p.id)) or 0,
        "formaciones": bd.scalar(select(func.count(Formacion.id)).where(
            Formacion.puesto_id == p.id, Formacion.estado == "activa")) or 0,
        "tareas_con_historial": _tareas_con_historial(bd, tareas),
    }
    if any(uso.values()):
        raise HTTPException(409, f"No se puede borrar el puesto «{p.nombre}» porque tiene {_explicar_uso(uso)}.")
    nombre = p.nombre
    bd.delete(p)
    auditar(bd, actor, "borrar_puesto", "puesto", puesto_id, {"resumen": f"Borró el puesto «{nombre}»"})
    bd.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- tareas


class DatosTarea(BaseModel):
    puesto_id: int | None = None
    codigo: str | None = None
    nombre: str | None = None
    descripcion: str | None = None
    criticidad: int | None = None
    riesgos_prl: str | None = None
    nivel_minimo: int | None = None
    activa: bool | None = None


def _validar_tarea(bd: Session, datos: dict[str, Any], actual: Tarea | None) -> dict[str, Any]:
    limpio: dict[str, Any] = {}
    if actual is None or "puesto_id" in datos:
        if datos.get("puesto_id") is None:
            raise HTTPException(400, "Elige el puesto al que pertenece la tarea.")
        nuevo = obtener(bd, Puesto, datos["puesto_id"], "el puesto elegido")
        if actual is not None and nuevo.id != actual.puesto_id:
            anterior = bd.get(Puesto, actual.puesto_id)
            if anterior is not None and anterior.departamento_id != nuevo.departamento_id and _tareas_con_historial(
                    bd, select(Tarea.id).where(Tarea.id == actual.id)):
                raise HTTPException(409, f"La tarea «{actual.nombre}» ya tiene historial en su departamento "
                                         "(instrucciones, niveles ILUO u observaciones). Solo se puede mover a otro "
                                         "puesto del mismo departamento.")
        limpio["puesto_id"] = nuevo.id
    if actual is None or "nombre" in datos:
        limpio["nombre"] = texto_limpio(datos.get("nombre"), "el nombre de la tarea", 200, obligatorio=True)
    if "codigo" in datos:
        codigo = texto_limpio(datos.get("codigo"), "el código", 30)
        if codigo:
            codigo = codigo.upper()
            otra = bd.scalar(select(Tarea).where(func.upper(Tarea.codigo) == codigo))
            if otra is not None and otra is not actual:
                raise HTTPException(409, f"El código {codigo} ya lo usa la tarea «{otra.nombre}».")
        limpio["codigo"] = codigo
    if "descripcion" in datos:
        limpio["descripcion"] = texto_limpio(datos.get("descripcion"), "la descripción", 4000)
    if "riesgos_prl" in datos:
        limpio["riesgos_prl"] = texto_limpio(datos.get("riesgos_prl"), "los riesgos PRL", 4000)
    if datos.get("criticidad") is not None:
        if datos["criticidad"] not in (1, 2, 3):
            raise HTTPException(400, "La criticidad es 1 (baja), 2 (media) o 3 (alta).")
        limpio["criticidad"] = datos["criticidad"]
    if datos.get("nivel_minimo") is not None:
        if bd.scalar(select(Nivel).where(Nivel.orden == datos["nivel_minimo"])) is None:
            raise HTTPException(400, "El nivel mínimo elegido no existe. Revisa la lista de niveles.")
        limpio["nivel_minimo"] = datos["nivel_minimo"]
    if datos.get("activa") is not None:
        limpio["activa"] = bool(datos["activa"])
    return limpio


def _tarea_respuesta(bd: Session, t: Tarea) -> dict[str, Any]:
    puesto = bd.get(Puesto, t.puesto_id)
    n = bd.scalar(select(func.count(Instruccion.id)).where(Instruccion.tarea_id == t.id)) or 0
    pub = bd.scalar(select(func.count(Instruccion.id)).where(Instruccion.tarea_id == t.id,
                                                             Instruccion.estado == "publicada")) or 0
    return tarea_dict(t, puesto.departamento_id if puesto else None, n, pub > 0)


@router.post("/tareas")
def crear_tarea(datos: DatosTarea, actor: Actor = Depends(requiere_admin),
                bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    limpio = _validar_tarea(bd, datos.model_dump(exclude_unset=True), None)
    limpio.setdefault("nivel_minimo", bd.scalar(select(func.min(Nivel.orden))) or 1)
    t = Tarea(**limpio)
    bd.add(t)
    bd.flush()
    auditar(bd, actor, "crear_tarea", "tarea", t.id,
            {"resumen": f"Creó la tarea «{t.nombre}»" + (f" ({t.codigo})" if t.codigo else "")})
    bd.commit()
    return _tarea_respuesta(bd, t)


@router.put("/tareas/{tarea_id}")
def editar_tarea(tarea_id: int, datos: DatosTarea, actor: Actor = Depends(requiere_admin),
                 bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    t = obtener(bd, Tarea, tarea_id, "esa tarea")
    hechos = cambios(t, _validar_tarea(bd, datos.model_dump(exclude_unset=True), t))
    if hechos:
        if set(hechos) == {"activa"}:
            resumen = f"{'Activó' if t.activa else 'Desactivó'} la tarea «{t.nombre}»"
        else:
            resumen = f"Editó la tarea «{t.nombre}»"
        auditar(bd, actor, "editar_tarea", "tarea", t.id, {"resumen": resumen, "cambios": hechos})
    bd.commit()
    return _tarea_respuesta(bd, t)


@router.delete("/tareas/{tarea_id}")
def borrar_tarea(tarea_id: int, actor: Actor = Depends(requiere_admin),
                 bd: Session = Depends(obtener_bd)) -> dict[str, bool]:
    t = obtener(bd, Tarea, tarea_id, "esa tarea")
    uso = {
        "instrucciones": bd.scalar(select(func.count(Instruccion.id)).where(Instruccion.tarea_id == t.id)) or 0,
        "niveles_iluo": bd.scalar(select(func.count(NivelIluo.id)).where(NivelIluo.tarea_id == t.id)) or 0,
        "observaciones": bd.scalar(select(func.count(Observacion.id)).where(Observacion.tarea_id == t.id)) or 0,
    }
    if any(uso.values()):
        raise HTTPException(409, f"La tarea «{t.nombre}» tiene {_explicar_uso(uso)}. "
                                 "Desactívala en lugar de borrarla para conservar el historial.")
    nombre = t.nombre
    bd.delete(t)
    auditar(bd, actor, "borrar_tarea", "tarea", tarea_id, {"resumen": f"Borró la tarea «{nombre}»"})
    bd.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- empresa y reglas ILUO

# Límites de cada regla: (tipo, mínimo, máximo, mensaje de error).
REGLAS_ILUO: dict[str, tuple[type, float, float, str]] = {
    "ejecuciones_para_L": (int, 1, 100, "Las ejecuciones para alcanzar L deben estar entre 1 y 100."),
    "umbral_cuestionario": (float, 0.5, 1.0, "El umbral del cuestionario debe estar entre el 50 % y el 100 %."),
    "meses_validez": (int, 1, 120, "La validez de un nivel debe estar entre 1 y 120 meses."),
}


class DatosEmpresa(BaseModel):
    nombre: str | None = None
    sector: str | None = None
    config_iluo: dict[str, Any] | None = None


def config_iluo(empresa: Empresa | None) -> dict[str, Any]:
    """Reglas ILUO vigentes: las guardadas completadas con los valores por defecto."""
    return {**CONFIG_ILUO_POR_DEFECTO, **((empresa.config_iluo if empresa else None) or {})}


def _validar_iluo(entrada: dict[str, Any]) -> dict[str, Any]:
    limpio: dict[str, Any] = {}
    for clave, valor in entrada.items():
        if clave not in REGLAS_ILUO:
            raise HTTPException(400, f"La regla «{clave}» no existe.")
        tipo, minimo, maximo, mensaje = REGLAS_ILUO[clave]
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise HTTPException(400, mensaje)
        if tipo is int and float(valor) != int(valor):
            raise HTTPException(400, mensaje)
        valor = tipo(valor)
        if not minimo <= valor <= maximo:
            raise HTTPException(400, mensaje)
        limpio[clave] = valor
    return limpio


def _empresa(bd: Session) -> Empresa:
    e = bd.scalar(select(Empresa).order_by(Empresa.id))
    if e is None:
        e = Empresa(nombre="Mi empresa", config_iluo=dict(CONFIG_ILUO_POR_DEFECTO), config={})
        bd.add(e)
        bd.flush()
    return e


def _empresa_dict(e: Empresa) -> dict[str, Any]:
    return {"nombre": e.nombre, "sector": e.sector, "config_iluo": config_iluo(e),
            "por_defecto": dict(CONFIG_ILUO_POR_DEFECTO)}


@router.get("/empresa")
def ver_empresa(_: Actor = Depends(requiere_admin), bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    e = _empresa(bd)
    bd.commit()
    return _empresa_dict(e)


@router.put("/empresa")
def editar_empresa(datos: DatosEmpresa, actor: Actor = Depends(requiere_admin),
                   bd: Session = Depends(obtener_bd)) -> dict[str, Any]:
    e = _empresa(bd)
    entrada = datos.model_dump(exclude_unset=True)
    limpio: dict[str, Any] = {}
    if "nombre" in entrada:
        limpio["nombre"] = texto_limpio(entrada["nombre"], "el nombre de la empresa", 200, obligatorio=True)
    if "sector" in entrada:
        limpio["sector"] = texto_limpio(entrada["sector"], "el sector", 200)
    if entrada.get("config_iluo") is not None:
        # Se conservan las claves que no se tocan (otros módulos pueden guardar las suyas).
        limpio["config_iluo"] = {**(e.config_iluo or {}), **_validar_iluo(entrada["config_iluo"])}
    hechos = cambios(e, limpio)
    if hechos:
        resumen = "Cambió las reglas ILUO" if set(hechos) == {"config_iluo"} else "Editó los datos de la empresa"
        auditar(bd, actor, "editar_empresa", "empresa", e.id, {"resumen": resumen, "cambios": hechos})
    bd.commit()
    return _empresa_dict(e)
