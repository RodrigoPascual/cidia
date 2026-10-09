"""Niveles ILUO: reglas, caducidad, reevaluación, validación de formadores y ajustes manuales.

Reglas (docs/arquitectura.md §7, ajustables en `empresa.config_iluo`):

* **I** ha empezado el itinerario de la tarea: micro-lección vista, ejecución iniciada,
  formación activa que incluye el puesto de la tarea (o cualquier evaluación ya hecha).
* **L** cuestionario aprobado de la instrucción vigente y al menos `ejecuciones_para_L`
  ejecuciones completadas.
* **U** L, observación aprobada por un supervisor y la última ejecución completada sin
  consultas en pasos críticos.
* **O** U y validado como formador por un jefe o un experto del departamento.

Solo cuentan las evidencias de la ventana de validez: los últimos `meses_validez` meses y,
si un jefe bajó el nivel a mano, las posteriores a ese ajuste («corte»). El nivel guardado
nunca baja solo: únicamente al caducar, cuando se vuelve a calcular con las evidencias
recientes (si siguen respaldándolo, se renueva). Al publicarse una versión nueva de la
instrucción, quien tenía L o más queda marcado para reevaluación hasta que sus evidencias
con la versión nueva vuelven a respaldar su nivel.

Las funciones no hacen commit (lo hace quien llama).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cidia.modelos import (
    Ejecucion,
    Empresa,
    Formacion,
    Instruccion,
    IntentoEval,
    Microleccion,
    MicroleccionVista,
    NivelIluo,
    Observacion,
    Tarea,
    Usuario,
    ahora,
)
from cidia.seguridad import Actor
from cidia.xapi import auditar, registrar

LETRAS = ["", "I", "L", "U", "O"]
NOMBRES = ["Sin iniciar", "En formación", "Ejecuta con apoyo", "Autónomo", "Puede formar a otros"]
CONFIG_POR_DEFECTO: dict[str, Any] = {"ejecuciones_para_L": 3, "umbral_cuestionario": 0.8, "meses_validez": 12}
MAX_HISTORIAL = 40


def nivel_letra(n: int) -> str:
    return LETRAS[n] if 0 <= n < len(LETRAS) else ""


def nivel_nombre(n: int) -> str:
    return NOMBRES[n] if 0 <= n < len(NOMBRES) else ""


# --------------------------------------------------------------------------- utilidades


def configuracion(bd: Session) -> dict[str, Any]:
    """Reglas ILUO de la empresa con valores por defecto y tipos saneados."""
    cfg = dict(CONFIG_POR_DEFECTO)
    emp = bd.scalar(select(Empresa).order_by(Empresa.id).limit(1))
    if emp and isinstance(emp.config_iluo, dict):
        cfg.update({k: v for k, v in emp.config_iluo.items() if v is not None})
    try:
        umbral = float(cfg["umbral_cuestionario"])
    except (TypeError, ValueError):
        umbral = CONFIG_POR_DEFECTO["umbral_cuestionario"]
    if umbral > 1:  # admite «80» además de «0.8»
        umbral /= 100
    try:
        ejecuciones = max(1, int(cfg["ejecuciones_para_L"]))
    except (TypeError, ValueError):
        ejecuciones = CONFIG_POR_DEFECTO["ejecuciones_para_L"]
    try:
        meses = max(1, int(cfg["meses_validez"]))
    except (TypeError, ValueError):
        meses = CONFIG_POR_DEFECTO["meses_validez"]
    return {"ejecuciones_para_L": ejecuciones, "umbral_cuestionario": min(1.0, max(0.0, umbral)),
            "meses_validez": meses}


def sumar_meses(f: datetime, meses: int) -> datetime:
    """Suma (o resta) meses de calendario conservando el día cuando existe."""
    total = f.month - 1 + meses
    anio, mes = f.year + total // 12, total % 12 + 1
    return f.replace(year=anio, month=mes, day=min(f.day, calendar.monthrange(anio, mes)[1]))


def iso(f: datetime | None) -> str | None:
    return f.isoformat() if f else None


def leer_fecha(texto: Any) -> datetime | None:
    if not texto or not isinstance(texto, str):
        return None
    try:
        f = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return f if f.tzinfo else f.replace(tzinfo=timezone.utc)


def instruccion_vigente(bd: Session, tarea_id: int) -> Instruccion | None:
    """La versión publicada más reciente de la instrucción de una tarea."""
    return bd.scalar(
        select(Instruccion)
        .where(Instruccion.tarea_id == tarea_id, Instruccion.estado == "publicada")
        .order_by(Instruccion.version.desc())
        .limit(1)
    )


def fila_de(bd: Session, usuario_id: int, tarea_id: int) -> NivelIluo | None:
    return bd.scalar(select(NivelIluo).where(NivelIluo.usuario_id == usuario_id, NivelIluo.tarea_id == tarea_id))


def caducado(fila: NivelIluo | None, momento: datetime | None = None) -> bool:
    return bool(fila and fila.nivel > 0 and fila.caduca and fila.caduca <= (momento or ahora()))


def _cargar(bd: Session, usuario_id: int, tarea_id: int) -> tuple[Usuario, Tarea]:
    usuario = bd.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "No existe esa persona.")
    tarea = bd.get(Tarea, tarea_id)
    if tarea is None:
        raise HTTPException(404, "No existe esa tarea.")
    return usuario, tarea


# --------------------------------------------------------------------------- quién puede evaluar a quién


def departamento_de_tarea(tarea: Tarea) -> int | None:
    return tarea.puesto.departamento_id if tarea.puesto else None


def en_formacion(bd: Session, usuario_id: int, departamento_id: int) -> bool:
    """¿Tiene la persona una formación activa en ese departamento?"""
    n = bd.scalar(
        select(func.count(Formacion.id)).where(
            Formacion.usuario_id == usuario_id,
            Formacion.departamento_id == departamento_id,
            Formacion.estado == "activa",
        )
    )
    return bool(n)


def gestiona_persona(bd: Session, actor: Actor, usuario: Usuario) -> bool:
    """Administración, o jefe del departamento de la persona o del departamento en el que se forma."""
    if actor.es_admin:
        return True
    if actor.rol != "jefe" or not actor.departamento_id:
        return False
    return usuario.departamento_id == actor.departamento_id or en_formacion(bd, usuario.id, actor.departamento_id)


def puede_evaluar(bd: Session, actor: Actor, usuario: Usuario, tarea: Tarea, expertos: bool = False) -> bool:
    """¿Puede el actor observar, ajustar o (con `expertos`) validar a `usuario` en `tarea`?

    Administración; o jefe (y experto, si `expertos`) del departamento de la tarea, cuando la
    persona es de ese departamento o se forma en él. Nadie se evalúa a sí mismo.
    """
    if actor.id == usuario.id:
        return False
    if actor.es_admin:
        return True
    dep = departamento_de_tarea(tarea)
    if not dep or actor.departamento_id != dep:
        return False
    if not (actor.rol == "jefe" or (expertos and actor.es_experto)):
        return False
    return usuario.departamento_id == dep or en_formacion(bd, usuario.id, dep)


# --------------------------------------------------------------------------- evidencias


@dataclass
class Evidencias:
    """Evidencias vigentes de una persona en una tarea y el nivel que respaldan."""

    ventana: datetime
    necesarias: int
    instruccion: Instruccion | None = None
    actividad: dict[str, Any] | None = None
    cuestionario: dict[str, Any] | None = None
    completadas: list[dict[str, Any]] = field(default_factory=list)
    observacion: dict[str, Any] | None = None
    formador: dict[str, Any] | None = None

    @property
    def ultima(self) -> dict[str, Any] | None:
        return self.completadas[-1] if self.completadas else None

    @property
    def ultima_sin_criticos(self) -> bool:
        u = self.ultima
        return bool(u is not None and not u["consultas_criticos"])

    @property
    def nivel(self) -> int:
        n = 1 if self.actividad else 0
        if n and self.cuestionario and len(self.completadas) >= self.necesarias:
            n = 2
        if n >= 2 and self.observacion and self.ultima_sin_criticos:
            n = 3
        if n >= 3 and self.formador:
            n = 4
        return n

    def requisitos(self) -> list[dict[str, Any]]:
        """Requisitos de cada nivel, en orden, con su estado y el texto de lo que falta."""
        k, n = len(self.completadas), self.necesarias
        faltan = n - k
        ins = self.instruccion
        return [
            {"clave": "inicio", "nivel": 1, "cumplido": bool(self.actividad),
             "texto": "Empezar el itinerario de la tarea",
             "falta": "Falta empezar la formación: una micro-lección o una ejecución en modo planta."},
            {"clave": "cuestionario", "nivel": 2, "cumplido": bool(self.cuestionario),
             "texto": f"Cuestionario aprobado de la versión vigente{f' (v{ins.version})' if ins else ''}",
             "falta": "Falta aprobar el cuestionario de la versión vigente." if ins
             else "La tarea aún no tiene una instrucción publicada."},
            {"clave": "ejecuciones", "nivel": 2, "cumplido": k >= n,
             "texto": f"{n} ejecuciones completadas ({min(k, n)} de {n})",
             "falta": "Falta 1 ejecución completada en modo planta." if faltan == 1
             else f"Faltan {faltan} ejecuciones completadas en modo planta."},
            {"clave": "observacion", "nivel": 3, "cumplido": bool(self.observacion),
             "texto": "Observación en el puesto aprobada por el supervisor",
             "falta": "Falta la observación del supervisor."},
            {"clave": "sin_criticos", "nivel": 3, "cumplido": self.ultima_sin_criticos,
             "texto": "Última ejecución sin consultas en pasos críticos",
             "falta": "Falta una ejecución completa sin consultas en los pasos críticos."},
            {"clave": "formador", "nivel": 4, "cumplido": bool(self.formador),
             "texto": "Validación como formador por un jefe o un experto",
             "falta": "Falta la validación como formador por un jefe o un experto."},
        ]

    def porcentaje(self) -> int:
        """Avance hacia la autonomía (U = 100 %)."""
        k = min(1.0, len(self.completadas) / self.necesarias) if self.necesarias else 1.0
        pts = 25.0 * bool(self.actividad) + 25.0 * bool(self.cuestionario) + 25.0 * k
        pts += 12.5 * bool(self.observacion) + 12.5 * self.ultima_sin_criticos
        return int(round(pts))

    def a_dict(self) -> dict[str, Any]:
        """Resumen (ids y fechas) que se guarda en NivelIluo.evidencias."""
        ultima = self.ultima
        return {
            "ventana_desde": iso(self.ventana),
            "instruccion": {"id": self.instruccion.id, "version": self.instruccion.version}
            if self.instruccion else None,
            "actividad": self.actividad,
            "cuestionario": self.cuestionario,
            "ejecuciones": {
                "completadas": len(self.completadas),
                "necesarias": self.necesarias,
                "ids": [e["id"] for e in self.completadas][-10:],
                "ultima": ultima,
            },
            "observacion": self.observacion,
        }


def _fecha_ejecucion():
    return func.coalesce(Ejecucion.fin, Ejecucion.inicio)


def inicio_ventana(fila: NivelIluo | None, cfg: dict[str, Any], momento: datetime | None = None) -> datetime:
    """Desde cuándo cuentan las evidencias: los últimos `meses_validez` meses y, si un jefe
    bajó el nivel a mano, solo las posteriores a ese ajuste («corte»)."""
    ventana = sumar_meses(momento or ahora(), -cfg["meses_validez"])
    corte = leer_fecha(((fila.evidencias or {}) if fila is not None else {}).get("corte"))
    return corte if corte and corte > ventana else ventana


def evaluar(bd: Session, usuario_id: int, tarea: Tarea, fila: NivelIluo | None = None,
            cfg: dict[str, Any] | None = None, momento: datetime | None = None) -> Evidencias:
    """Reúne las evidencias vigentes (sin escribir nada)."""
    cfg = cfg or configuracion(bd)
    momento = momento or ahora()
    ventana = inicio_ventana(fila, cfg, momento)
    datos = (fila.evidencias or {}) if fila is not None else {}
    ev = Evidencias(ventana=ventana, necesarias=cfg["ejecuciones_para_L"])
    ev.instruccion = ins = instruccion_vigente(bd, tarea.id)

    # Actividad: lo primero que hizo dentro de la ventana (o una formación activa que la incluye).
    candidatas: list[tuple[str, int, datetime]] = []
    vista = bd.execute(
        select(MicroleccionVista.id, MicroleccionVista.completada_en)
        .join(Microleccion, Microleccion.id == MicroleccionVista.microleccion_id)
        .join(Instruccion, Instruccion.id == Microleccion.instruccion_id)
        .where(MicroleccionVista.usuario_id == usuario_id, Instruccion.tarea_id == tarea.id,
               MicroleccionVista.completada_en >= ventana)
        .order_by(MicroleccionVista.completada_en).limit(1)
    ).first()
    if vista:
        candidatas.append(("microleccion", vista.id, vista.completada_en))
    eje = bd.execute(
        select(Ejecucion.id, Ejecucion.inicio)
        .where(Ejecucion.usuario_id == usuario_id, Ejecucion.tarea_id == tarea.id, Ejecucion.inicio >= ventana)
        .order_by(Ejecucion.inicio).limit(1)
    ).first()
    if eje:
        candidatas.append(("ejecucion", eje.id, eje.inicio))
    dep = departamento_de_tarea(tarea)
    form = bd.execute(
        select(Formacion.id, Formacion.inicio)
        .where(Formacion.usuario_id == usuario_id, Formacion.estado == "activa",
               or_(Formacion.puesto_id == tarea.puesto_id,
                   (Formacion.puesto_id.is_(None)) & (Formacion.departamento_id == dep)))
        .order_by(Formacion.inicio).limit(1)
    ).first()
    if form:
        candidatas.append(("formacion", form.id, form.inicio))
    intento = bd.execute(
        select(IntentoEval.id, IntentoEval.creado)
        .join(Instruccion, Instruccion.id == IntentoEval.instruccion_id)
        .where(IntentoEval.usuario_id == usuario_id, Instruccion.tarea_id == tarea.id, IntentoEval.creado >= ventana)
        .order_by(IntentoEval.creado).limit(1)
    ).first()
    if intento:
        candidatas.append(("cuestionario", intento.id, intento.creado))
    obs_cualquiera = bd.execute(
        select(Observacion.id, Observacion.creada)
        .where(Observacion.usuario_id == usuario_id, Observacion.tarea_id == tarea.id, Observacion.creada >= ventana)
        .order_by(Observacion.creada).limit(1)
    ).first()
    if obs_cualquiera:
        candidatas.append(("observacion", obs_cualquiera.id, obs_cualquiera.creada))
    if candidatas:
        tipo, ident, fecha = min(candidatas, key=lambda c: c[2])
        ev.actividad = {"tipo": tipo, "id": ident, "fecha": iso(fecha)}

    # Cuestionario aprobado de la versión vigente (el más reciente).
    if ins is not None:
        it = bd.scalar(
            select(IntentoEval)
            .where(IntentoEval.usuario_id == usuario_id, IntentoEval.instruccion_id == ins.id,
                   IntentoEval.aprobado.is_(True), IntentoEval.creado >= ventana)
            .order_by(IntentoEval.creado.desc()).limit(1)
        )
        if it:
            ev.cuestionario = {"intento_id": it.id, "instruccion_id": ins.id, "version": ins.version,
                               "puntuacion": round(it.puntuacion, 3), "fecha": iso(it.creado)}

    # Ejecuciones completadas (de cualquier versión), en orden.
    filas_e = bd.execute(
        select(Ejecucion.id, Ejecucion.inicio, Ejecucion.fin, Ejecucion.consultas, Ejecucion.consultas_criticos)
        .where(Ejecucion.usuario_id == usuario_id, Ejecucion.tarea_id == tarea.id,
               Ejecucion.estado == "completada", _fecha_ejecucion() >= ventana)
        .order_by(_fecha_ejecucion(), Ejecucion.id)
    ).all()
    ev.completadas = [{"id": e.id, "fecha": iso(e.fin or e.inicio), "consultas": e.consultas or 0,
                       "consultas_criticos": e.consultas_criticos or 0} for e in filas_e]

    # Observación aprobada (la más reciente).
    obs = bd.scalar(
        select(Observacion)
        .where(Observacion.usuario_id == usuario_id, Observacion.tarea_id == tarea.id,
               Observacion.aprobada.is_(True), Observacion.creada >= ventana)
        .order_by(Observacion.creada.desc()).limit(1)
    )
    if obs:
        evaluador = bd.get(Usuario, obs.evaluador_id) if obs.evaluador_id else None
        ev.observacion = {"id": obs.id, "fecha": iso(obs.creada), "evaluador_id": obs.evaluador_id,
                          "evaluador": evaluador.nombre if evaluador else None}

    # Validación como formador (si sigue dentro de la ventana).
    if fila is not None and fila.formador_validado:
        fd = datos.get("formador") if isinstance(datos.get("formador"), dict) else None
        fecha_f = leer_fecha(fd.get("fecha")) if fd else None
        if fecha_f is None or fecha_f >= ventana:
            ev.formador = fd or {"por_id": fila.formador_validado_por_id, "fecha": None}
    return ev


# --------------------------------------------------------------------------- recálculo


def _anotar(datos: dict[str, Any], **entrada: Any) -> None:
    historial = list(datos.get("historial") or [])
    historial.append(entrada)
    datos["historial"] = historial[-MAX_HISTORIAL:]


def _certificar(bd: Session, usuario: Usuario, tarea: Tarea, nivel: int, anterior: int,
                motivo: str, por: Actor | None = None) -> None:
    """xAPI «certifico»: la persona alcanza (o renueva) un nivel en la tarea."""
    contexto: dict[str, Any] = {"usuario_id": usuario.id, "tarea_id": tarea.id, "motivo": motivo}
    if por is not None:
        contexto["por_id"], contexto["por"] = por.id, por.nombre
    registrar(
        bd, None, "certifico", "tarea", tarea.id, tarea.nombre,
        resultado={"nivel": nivel_letra(nivel), "nivel_numero": nivel, "nivel_anterior": nivel_letra(anterior),
                   "success": True},
        contexto=contexto, actor_id=usuario.id, actor_nombre=usuario.nombre,
    )


def recalcular_con_evidencias(bd: Session, usuario_id: int, tarea_id: int) -> tuple[NivelIluo, Evidencias]:
    """Como `recalcular`, pero devuelve también las evidencias calculadas."""
    usuario, tarea = _cargar(bd, usuario_id, tarea_id)
    cfg = configuracion(bd)
    momento = ahora()
    fila = fila_de(bd, usuario_id, tarea_id)
    nueva = fila is None
    if fila is None:
        fila = NivelIluo(usuario_id=usuario_id, tarea_id=tarea_id, nivel=0, evidencias={},
                         requiere_reevaluacion=False, formador_validado=False)
    ev = evaluar(bd, usuario_id, tarea, fila, cfg, momento)
    calculado = ev.nivel
    datos = dict(fila.evidencias or {})
    anterior = fila.nivel or 0
    certificar: str | None = None

    if caducado(fila, momento):
        # Caducidad: se vuelve a calcular con las evidencias recientes (puede renovarse o bajar).
        _anotar(datos, tipo="caducidad", fecha=iso(momento), nivel_anterior=anterior, nivel=calculado)
        fila.nivel = calculado
        fila.requiere_reevaluacion = False
        if not ev.formador:
            fila.formador_validado = False
            datos.pop("formador", None)
        if calculado > 0:
            fila.desde, fila.caduca = momento, sumar_meses(momento, cfg["meses_validez"])
            certificar = "renovacion"
        else:
            fila.desde = fila.caduca = None
    elif calculado > anterior:
        fila.nivel = calculado
        fila.desde, fila.caduca = momento, sumar_meses(momento, cfg["meses_validez"])
        _anotar(datos, tipo="subida", fecha=iso(momento), nivel_anterior=anterior, nivel=calculado)
        certificar = "evidencias"

    if fila.requiere_reevaluacion and calculado >= fila.nivel:
        # Las evidencias con la versión nueva vuelven a respaldar su nivel: reevaluado y renovado.
        fila.requiere_reevaluacion = False
        fila.caduca = sumar_meses(momento, cfg["meses_validez"])
        _anotar(datos, tipo="reevaluado", fecha=iso(momento), nivel=fila.nivel)

    datos.update(ev.a_dict())
    datos["calculado"] = calculado
    datos["actualizado"] = iso(momento)
    fila.evidencias = datos  # dict nuevo: SQLAlchemy detecta el cambio en JSONB

    if nueva and fila.nivel == 0:
        return fila, ev  # sin nada que guardar: no se crea la fila
    if nueva:
        try:
            with bd.begin_nested():
                bd.add(fila)
                bd.flush()
        except IntegrityError:
            # Otra petición creó la fila a la vez: se recalcula sobre la suya.
            return recalcular_con_evidencias(bd, usuario_id, tarea_id)
    if certificar:
        _certificar(bd, usuario, tarea, fila.nivel, anterior, certificar)
    bd.flush()
    return fila, ev


def recalcular(bd: Session, usuario_id: int, tarea_id: int) -> NivelIluo:
    """Aplica las reglas ILUO; registra xAPI «certifico» si sube (o se renueva tras caducar).

    Si la persona no tiene ninguna evidencia devuelve un NivelIluo con nivel 0 sin guardarlo.
    """
    return recalcular_con_evidencias(bd, usuario_id, tarea_id)[0]


def marcar_reevaluacion(bd: Session, tarea_id: int) -> int:
    """Nueva versión publicada: quien tiene L o más en la tarea queda pendiente de reevaluación."""
    filas = bd.scalars(select(NivelIluo).where(NivelIluo.tarea_id == tarea_id, NivelIluo.nivel >= 2)).all()
    momento = iso(ahora())
    for f in filas:
        f.requiere_reevaluacion = True
        datos = dict(f.evidencias or {})
        _anotar(datos, tipo="reevaluacion", fecha=momento, nivel=f.nivel)
        f.evidencias = datos
    bd.flush()
    return len(filas)


# --------------------------------------------------------------------------- acciones de jefes y expertos


def validar_formador(bd: Session, actor: Actor, usuario_id: int, tarea_id: int) -> NivelIluo:
    """Un jefe o un experto del departamento de la tarea valida a la persona como formadora (nivel O)."""
    usuario, tarea = _cargar(bd, usuario_id, tarea_id)
    if not puede_evaluar(bd, actor, usuario, tarea, expertos=True):
        raise HTTPException(403, "Solo un jefe o un experto del departamento de la tarea puede validar formadores.")
    fila = recalcular(bd, usuario_id, tarea_id)
    if fila.nivel >= 4 and fila.formador_validado:
        return fila
    if fila.nivel < 3:
        raise HTTPException(400, f"{usuario.nombre} necesita el nivel U (autónomo) en esta tarea "
                                 "antes de validarle como formador.")
    if fila.requiere_reevaluacion:
        raise HTTPException(400, f"{usuario.nombre} tiene pendiente la reevaluación de la versión nueva. "
                                 "Valídale como formador cuando la supere.")
    momento = ahora()
    datos = dict(fila.evidencias or {})
    datos["formador"] = {"por_id": actor.id, "por": actor.nombre, "fecha": iso(momento)}
    fila.evidencias = datos
    fila.formador_validado = True
    fila.formador_validado_por_id = actor.id
    registrar(bd, actor, "valido", "formador", f"{usuario.id}-{tarea.id}", f"{usuario.nombre} · {tarea.nombre}",
              resultado={"success": True}, contexto={"usuario_id": usuario.id, "tarea_id": tarea.id})
    bd.flush()
    fila = recalcular(bd, usuario_id, tarea_id)
    if fila.nivel == 3:
        # La U vino de un ajuste manual (sin evidencias que la respalden): el recálculo no sube
        # solo, pero la validación como formador sí lleva a O.
        datos = dict(fila.evidencias or {})
        _anotar(datos, tipo="subida", fecha=iso(momento), nivel_anterior=3, nivel=4)
        fila.evidencias = datos
        fila.nivel = 4
        fila.desde, fila.caduca = momento, sumar_meses(momento, configuracion(bd)["meses_validez"])
        _certificar(bd, usuario, tarea, 4, 3, "formador", por=actor)
        bd.flush()
    return fila


def ajustar(bd: Session, actor: Actor, usuario_id: int, tarea_id: int, nivel: int, motivo: str) -> NivelIluo:
    """Ajuste manual del nivel por un jefe del departamento de la tarea (o la administración).

    Si baja el nivel, las evidencias anteriores dejan de contar («corte») para que el
    recálculo automático no lo vuelva a subir con ellas.
    """
    usuario, tarea = _cargar(bd, usuario_id, tarea_id)
    if not (actor.es_admin or actor.rol == "jefe") or not puede_evaluar(bd, actor, usuario, tarea):
        raise HTTPException(403, "Solo el jefe del departamento de la tarea o la administración pueden ajustar niveles.")
    if not isinstance(nivel, int) or not 0 <= nivel <= 4:
        raise HTTPException(400, "El nivel debe ser 0 (sin iniciar), 1 (I), 2 (L), 3 (U) o 4 (O).")
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise HTTPException(400, "Explica el motivo del ajuste en unas palabras.")
    cfg = configuracion(bd)
    momento = ahora()
    fila = fila_de(bd, usuario_id, tarea_id)
    if fila is None:
        fila = NivelIluo(usuario_id=usuario_id, tarea_id=tarea_id, nivel=0, evidencias={},
                         requiere_reevaluacion=False, formador_validado=False)
        bd.add(fila)
    anterior = fila.nivel or 0
    datos = dict(fila.evidencias or {})
    _anotar(datos, tipo="ajuste", fecha=iso(momento), nivel_anterior=anterior, nivel=nivel,
            por_id=actor.id, por=actor.nombre, motivo=motivo[:500])
    if nivel < anterior:
        datos["corte"] = iso(momento)
    fila.nivel = nivel
    if nivel > 0:
        fila.desde, fila.caduca = momento, sumar_meses(momento, cfg["meses_validez"])
    else:
        fila.desde = fila.caduca = None
    fila.requiere_reevaluacion = False
    if nivel >= 4:
        fila.formador_validado = True
        fila.formador_validado_por_id = actor.id
        datos["formador"] = {"por_id": actor.id, "por": actor.nombre, "fecha": iso(momento)}
    else:
        fila.formador_validado = False
        fila.formador_validado_por_id = None
        datos.pop("formador", None)
    fila.evidencias = datos
    auditar(bd, actor, "ajustar_nivel_iluo", "iluo", f"{usuario.id}-{tarea.id}", {
        "usuario_id": usuario.id, "usuario": usuario.nombre, "tarea_id": tarea.id, "tarea": tarea.nombre,
        "de": nivel_letra(anterior) or "-", "a": nivel_letra(nivel) or "-", "motivo": motivo[:500],
    })
    if nivel > anterior:
        _certificar(bd, usuario, tarea, nivel, anterior, "ajuste_manual", por=actor)
    bd.flush()
    return fila
