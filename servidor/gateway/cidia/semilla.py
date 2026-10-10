"""Datos sintéticos de demostración: Metalúrgica Arlanza, S. L. (empresa ficticia de Burgos).

`sembrar(bd, forzar=False)` crea la organización (4 departamentos con sus puestos y tareas IT-0xx),
14 personas y la administración, los documentos de conocimiento (Markdown y PDF, indexados), 5
instrucciones publicadas con una imagen esquemática por paso, micro-lecciones, preguntas de
cuestionario y seis semanas de actividad coherente: lagunas, aportaciones, ejecuciones en el modo
planta (con su curva de autonomía), cuestionarios, observaciones, niveles ILUO y sus sentencias xAPI
con las fechas repartidas.

Usa los servicios de los demás módulos (publicar instrucciones, validar aportaciones, calcular las
evidencias ILUO, indexar documentos). Si alguno no está disponible, escribe la tabla con el mismo
formato. Es idempotente: si la base ya está sembrada (marca en empresa.config o la cuenta «ana» de
la semilla) no hace nada, salvo con `forzar=True`, que antes vacía el contenido de demostración
(pensado solo para servidores de demostración).

Nunca se mezcla con datos reales: si la base ya tiene departamentos, documentos o personas que no
puso la semilla (`estado_base` = «con_datos»; también una «ana» con un correo que no es el ficticio
@arlanza.example), no siembra ni vacía nada, tampoco con `forzar=True`.
Así un CIDIA_CREAR_SEMILLA=true olvidado no crea cuentas con una contraseña compartida en una
instalación de verdad.

`sembrar_si_vacio()` la llama arranque.py cuando CIDIA_CREAR_SEMILLA=true: comprueba si hace falta
y encola la siembra como trabajo en segundo plano, para no retrasar el arranque del servidor. Si
una siembra anterior quedó a medias (el servidor se reinició mientras sembraba), la repite desde
cero: la marca de empresa.config demuestra que esos datos son de la semilla. Un cerrojo de
PostgreSQL impide dos siembras a la vez (la del arranque y otra lanzada a mano).

Contraseña común de las cuentas de demostración: la de CIDIA_DEMO_CONTRASENA o, si no existe, una
aleatoria que se guarda en <dir_datos>/usuarios-demo.txt (solo legible por su propietario). Nunca
se escribe en los registros.

Uso manual:
    python -m cidia.semilla [--forzar]       siembra (o vuelve a sembrar) la base configurada
    python -m cidia.semilla --exportar DIR   escribe los documentos (Markdown y PDF) en DIR
"""

from __future__ import annotations

import logging
import os
import random
import re
import secrets
import shutil
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import delete, event, func, insert, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from cidia import trabajos, xapi
from cidia.config import ajustes
from cidia.conocimiento import motor
from cidia.conocimiento.extraccion import tipo_por_extension
from cidia.db import Base, sesion_bd
from cidia.ficheros import relativa
from cidia.ia import llm
from cidia.modelos import (
    Aportacion,
    Auditoria,
    Consulta,
    Departamento,
    Documento,
    Ejecucion,
    EjecucionPaso,
    Empresa,
    Formacion,
    Fragmento,
    Instruccion,
    IntentoEval,
    Laguna,
    Microleccion,
    MicroleccionVista,
    Nivel,
    NivelIluo,
    Observacion,
    Paso,
    PreguntaEval,
    Puesto,
    SentenciaXapi,
    Tarea,
    Usuario,
    ahora,
)
from cidia.permisos import alcance_de, puede_ver
from cidia.seguridad import Actor, hash_contrasena
from cidia.semilla_datos import actividad as ACT
from cidia.semilla_datos import documentos as DOCS
from cidia.semilla_datos import instrucciones as INS
from cidia.semilla_datos import organizacion as ORG
from cidia.servicios import documentos

log = logging.getLogger("cidia.semilla")

USUARIO_TESTIGO = "ana"  # si existe, la base ya está sembrada
CARPETA = "semilla"  # ficheros generados, dentro de dir_datos
FICHERO_CONTRASENA = "usuarios-demo.txt"
DIR_AUDIO = Path(__file__).resolve().parent / "semilla_datos" / "audio"
PIE_PDF = "Metalúrgica Arlanza, S. L. (ficticia) · Documento sintético de demostración"
VERSION_SEMILLA = 1
CERROJO = 7_301_412_026  # clave del cerrojo de PostgreSQL: una sola siembra a la vez en la base

# Tablas de contenido que se vacían con forzar=True (la organización y las cuentas ajenas se conservan).
TABLAS_CONTENIDO = [
    "fragmentos", "documentos", "capturas", "pasos", "instrucciones", "microleccion_vistas", "microlecciones",
    "ejecucion_pasos", "ejecuciones", "consultas", "lagunas", "aportaciones", "preguntas_eval", "intentos_eval",
    "observaciones", "iluo", "xapi", "memorias",
]


# --------------------------------------------------------------------------- utilidades


def _actor(u: Usuario) -> Actor:
    """Actor sin sesión para llamar a los servicios en nombre de una persona sembrada."""
    return Actor(sesion=None, usuario=u)  # type: ignore[arg-type]


def _iso(f: datetime | None) -> str | None:
    return f.isoformat() if f else None


def _fechar(fila: SentenciaXapi, cuando: datetime) -> None:
    fila.momento = cuando
    sentencia = dict(fila.sentencia or {})
    sentencia["timestamp"] = cuando.isoformat()
    fila.sentencia = sentencia  # dict nuevo: JSONB detecta el cambio


def _id(valor: Any) -> Any:
    """Id de una fila (ya guardada) o el propio valor."""
    return valor.id if isinstance(valor, Base) else valor


def _ids(datos: dict[str, Any] | None) -> dict[str, Any] | None:
    return {k: _id(v) for k, v in datos.items()} if datos else datos


def _primera_frase(texto: str, maximo: int = 100) -> str:
    t = re.split(r"(?<=[.!?])\s", (texto or "").strip(), maxsplit=1)[0]
    return t if len(t) <= maximo else t[: maximo - 1].rstrip() + "…"


def _como_listo(doc: Documento) -> Any:
    """Copia ligera del documento como si ya estuviera indexado, para aplicar permisos.puede_ver."""
    return SimpleNamespace(estado="listo", es_publico=doc.es_publico, departamento_id=doc.departamento_id,
                           es_formacion=doc.es_formacion, nivel_minimo=doc.nivel_minimo)


def duracion_ogg_opus(datos: bytes) -> float | None:
    """Segundos de un Ogg Opus: posición de la última página menos el preskip, a 48 kHz."""
    cabecera, ultima = datos.find(b"OpusHead"), datos.rfind(b"OggS")
    if cabecera < 0 or ultima < 0:
        return None
    granulo = int.from_bytes(datos[ultima + 6:ultima + 14], "little")
    preskip = int.from_bytes(datos[cabecera + 10:cabecera + 12], "little")
    return round(max(0, granulo - preskip) / 48000, 1)


def ya_sembrado(bd: Session) -> bool:
    """Existe la cuenta testigo («ana») con el correo ficticio de la semilla.

    Una «ana» de verdad (otro dominio de correo) no cuenta: esa base tiene datos propios.
    """
    correo = bd.scalar(select(Usuario.email).where(Usuario.usuario == USUARIO_TESTIGO))
    return bool(correo) and correo.lower().endswith("@" + ORG.DOMINIO_CORREO)


def marca_semilla(bd: Session) -> dict[str, Any]:
    """Lo que anotó la semilla en empresa.config: estado, cuentas y departamentos que creó."""
    emp = bd.scalar(select(Empresa).order_by(Empresa.id))
    return dict((emp.config or {}).get("semilla") or {}) if emp else {}


def estado_base(bd: Session) -> str:
    """Situación de la base para la semilla.

    * «incompleta»: una siembra empezó y no terminó (el servidor se reinició a mitad).
    * «sembrada»: ya tiene los datos de demostración (la marca de la semilla o, en siembras
      anteriores a la marca, la cuenta «ana» con el correo ficticio @arlanza.example).
    * «con_datos»: tiene departamentos, documentos o personas propias (también una «ana» real).
      No se toca nunca.
    * «vacia»: solo lo que crea el arranque (empresa, niveles, modelos y la administración).
    """
    marca = marca_semilla(bd)
    if marca.get("estado") == "en_curso":
        return "incompleta"
    if marca or ya_sembrado(bd):
        return "sembrada"
    nombres = [p[0] for p in ORG.PERSONAS]  # una cuenta de administración llamada «ana» también es propia
    propios = (bd.scalar(select(Departamento.id).limit(1)) is not None
               or bd.scalar(select(Documento.id).limit(1)) is not None
               or bd.scalar(select(Usuario.id).where((Usuario.rol != "admin") | Usuario.usuario.in_(nombres))
                            .limit(1)) is not None)
    return "con_datos" if propios else "vacia"


# --------------------------------------------------------------------------- contraseña de demostración


def _leer_contrasena(ruta: Path) -> str | None:
    try:
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if linea.startswith("contrasena="):
                return linea.split("=", 1)[1].strip() or None
    except OSError:
        return None
    return None


def _escribir_contrasena(ruta: Path, contrasena: str) -> None:
    """Fichero solo legible por el propietario (en Windows el modo se ignora en parte)."""
    usuarios = ", ".join(p[0] for p in ORG.PERSONAS)
    contenido = (
        "# CidIA · cuentas de demostración de Metalúrgica Arlanza, S. L. (empresa ficticia)\n"
        "# Generado por la semilla. No lo compartas fuera del equipo de demostración.\n"
        "# También vale para «admin» si la semilla creó esa cuenta (si ya había una cuenta de\n"
        "# administración, conserva su propia contraseña).\n"
        f"usuarios={usuarios}\n"
        f"contrasena={contrasena}\n"
    )
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(contenido)
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass


def contrasena_demo() -> tuple[str, str]:
    """(contraseña, de dónde sale). La de CIDIA_DEMO_CONTRASENA o una aleatoria guardada en dir_datos.

    La variable se lee del entorno del proceso y, si no está, de los ajustes (fichero .env).
    """
    ruta = ajustes().dir_datos / FICHERO_CONTRASENA
    env = (os.environ.get("CIDIA_DEMO_CONTRASENA", "").strip()
           or str(getattr(ajustes(), "demo_contrasena", "") or "").strip())
    if env:
        try:
            ruta.unlink(missing_ok=True)  # una contraseña generada antes ya no vale: que no confunda
        except OSError as e:  # (fichero bloqueado o de solo lectura: no impide sembrar)
            log.warning("No se pudo borrar %s, que ya no vale: %s", ruta, e)
        if len(env) < 8:
            log.warning("CIDIA_DEMO_CONTRASENA es muy corta (menos de 8 caracteres): úsala solo en una red de pruebas")
        return env, "la variable CIDIA_DEMO_CONTRASENA"
    existente = _leer_contrasena(ruta)
    if existente:
        return existente, str(ruta)
    nueva = secrets.token_urlsafe(12)
    _escribir_contrasena(ruta, nueva)
    return nueva, str(ruta)


# --------------------------------------------------------------------------- documentos de ejemplo


def contenido_documento(d: dict[str, Any]) -> bytes:
    """Bytes del documento: Markdown tal cual o PDF generado (semilla_datos/pdf.py)."""
    if d["formato"] == "pdf":
        from cidia.semilla_datos.pdf import markdown_a_pdf

        return markdown_a_pdf(d["texto"], titulo_doc=d["titulo"], cabecera=d.get("cabecera", ""), pie=PIE_PDF)
    return d["texto"].encode("utf-8")


def exportar_documentos(destino: Path) -> int:
    """Escribe los documentos sintéticos en una carpeta (copias para datos-demo/documentos)."""
    destino.mkdir(parents=True, exist_ok=True)
    for d in DOCS.DOCUMENTOS:
        (destino / d["fichero"]).write_bytes(contenido_documento(d))
    return len(DOCS.DOCUMENTOS)


# --------------------------------------------------------------------------- una siembra a la vez


OCUPADA = "Ya hay otra siembra de los datos de demostración en marcha. Espera a que termine."


@contextmanager
def _cerrojo(base: Engine) -> Iterator[bool]:
    """Cerrojo de PostgreSQL (pg_try_advisory_lock) mientras dura una siembra. Da False si otra lo tiene.

    Dos siembras a la vez se pisarían: la del arranque (que puede pasar minutos esperando al
    modelo) y un `python -m cidia.semilla --forzar` lanzado a mano en el servidor, que vaciaría lo
    que la otra está creando. El cerrojo vive en una conexión propia, porque la sesión de la
    siembra hace commit por etapas y puede cambiar de conexión. Si no se puede soltar, la conexión
    se descarta y PostgreSQL lo suelta al cerrarse; también si el proceso muere a mitad.
    """
    conexion = base.connect()
    conseguido = False
    try:
        conseguido = bool(conexion.execute(select(func.pg_try_advisory_lock(CERROJO))).scalar())
        conexion.commit()  # el cerrojo es de la conexión, no de la transacción: no se queda una abierta
        yield conseguido
    finally:
        try:
            if conseguido:
                conexion.execute(select(func.pg_advisory_unlock(CERROJO)))
                conexion.commit()
        except Exception:  # noqa: BLE001
            conexion.invalidate()
        conexion.close()


# --------------------------------------------------------------------------- servicios con alternativa


@contextmanager
def _sin_generacion_automatica() -> Iterator[None]:
    """Al publicar no se encolan micro-lecciones ni preguntas con el LLM: la semilla trae las suyas.

    Sustituye un momento las funciones del módulo (instrucciones.publicar las llama a través de él).
    La sustituta solo calla en el hilo que siembra: si a la vez alguien publica una instrucción
    desde la interfaz (otro hilo del servidor), su material se genera como siempre.
    """
    from cidia.servicios import evaluacion, formacion

    hilo = threading.get_ident()

    def sustituta(original: Callable[..., Any]) -> Callable[..., Any]:
        def encolar(*a: Any, **k: Any) -> Any:
            return None if threading.get_ident() == hilo else original(*a, **k)

        return encolar

    originales = []
    for mod in (formacion, evaluacion):
        if hasattr(mod, "encolar_generacion"):
            original = mod.encolar_generacion
            originales.append((mod, original))
            mod.encolar_generacion = sustituta(original)
    try:
        yield
    finally:
        for mod, original in reversed(originales):
            mod.encolar_generacion = original


def _texto_indexable(ins: Instruccion) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
    """Mismo formato que servicios/instrucciones.texto_indexable (por si el servicio no está)."""
    base = {"instruccion_id": ins.id, "codigo": ins.codigo}
    general = [f"{ins.codigo} · {ins.titulo} (versión {ins.version})", f"Tarea: {ins.tarea.nombre}"]
    for etiqueta, valor in (("Resumen", ins.resumen), ("Riesgos", ins.riesgos), ("EPIs", ins.epis),
                            ("Herramientas", ins.herramientas)):
        if valor:
            general.append(f"{etiqueta}: {valor}")
    partes = [("\n".join(general), {**base, "paso": 0, "paso_id": None, "seccion": "general"})]
    for p in ins.pasos:
        marcas = [m for m, si in (("PASO CRÍTICO", p.es_critico), ("SEGURIDAD", p.es_seguridad)) if si]
        lineas = [f"Paso {p.orden}. {p.titulo}" + (f" [{' · '.join(marcas)}]" if marcas else "")]
        if p.texto:
            lineas.append(p.texto)
        if p.criterio_aceptacion:
            lineas.append(f"Criterio de aceptación: {p.criterio_aceptacion}")
        partes.append(("\n".join(lineas), {**base, "paso": p.orden, "paso_id": p.id}))
    return "\n\n".join(t for t, _ in partes), partes


# --------------------------------------------------------------------------- la siembra


class _Semilla:
    """Estado de una siembra: la sesión, el reloj de referencia y lo creado hasta ahora."""

    def __init__(self, bd: Session, progreso: Callable[..., None] | None = None) -> None:
        self.bd = bd
        self.base = ahora().replace(microsecond=0)
        self.rnd = random.Random(20261009)
        self.progreso = progreso or (lambda pct, msg=None: None)
        self.empresa: Empresa | None = None
        self.niveles: dict[int, Nivel] = {}
        self.deps: dict[str, Departamento] = {}
        self.puestos: dict[str, Puesto] = {}
        self.tareas: dict[str, Tarea] = {}
        self.personas: dict[str, Usuario] = {}
        self.creados: list[str] = []  # cuentas que crea esta siembra (las borra vaciar)
        self.deps_creados: list[str] = []  # departamentos que crea esta siembra
        self.docs: dict[str, Documento] = {}
        self.instr: dict[str, Instruccion] = {}
        self.anteriores: dict[tuple[str, int], Instruccion] = {}
        self.definicion: dict[str, dict[str, Any]] = {d["codigo"]: d for d in INS.INSTRUCCIONES}
        self.lagunas_de: dict[str, Laguna] = {}  # aportación que resuelve la laguna -> laguna
        self.aps: dict[str, Aportacion] = {}
        self.cuenta: Counter[str] = Counter()
        self.avisos: list[str] = []
        self._xapi: list[tuple[Any, ...]] = []
        self._auditoria: list[tuple[Any, ...]] = []
        self._fragmentos: dict[int, list[str]] = {}

    # ------------------------------------------------------------------ reloj

    def hace(self, dias: float, hora: float | None = None) -> datetime:
        """Fecha `dias` atrás en día laborable, a una hora de turno (UTC). Nunca en el futuro."""
        d = self.base - timedelta(days=dias)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        h = self.rnd.uniform(5.5, 18.0) if hora is None else hora
        d = d.replace(hour=int(h), minute=int(h % 1 * 60), second=self.rnd.randint(0, 59))
        limite = self.base - timedelta(minutes=self.rnd.randint(3, 40))
        return min(d, limite)

    def implantacion(self) -> datetime:
        """Primer día con CidIA (a las 00:00): lo anterior viene de la etapa en papel y no deja trazas.
        Se alinea al día para que el resultado no dependa de la hora a la que se siembra."""
        d = (self.base - timedelta(days=ACT.DIAS_IMPLANTACION)).replace(hour=0, minute=0, second=0)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d

    # ------------------------------------------------------------------ trazas

    def xapi(self, cuando: datetime, usuario: Usuario | None, verbo: str, objeto_tipo: str, objeto: Any,
             nombre: str | None, resultado: dict[str, Any] | None = None,
             contexto: dict[str, Any] | None = None) -> None:
        """Sentencia xAPI con fecha pasada. Antes de implantar CidIA no había registro: se omite.

        Se escribe al volcar (`volcar`), cuando ya se conocen los ids: `objeto` y los valores de
        `resultado` y `contexto` pueden ser filas aún sin guardar. Así se ahorran viajes a la base.
        """
        if cuando >= self.implantacion():
            self._xapi.append((cuando, usuario, verbo, objeto_tipo, objeto, nombre, resultado, contexto))

    def auditar(self, cuando: datetime, usuario: Usuario | None, accion: str, entidad: str, objeto: Any,
                detalle: dict[str, Any]) -> None:
        """Fila de auditoría con fecha pasada (también se escribe al volcar)."""
        self._auditoria.append((cuando, usuario, accion, entidad, objeto, detalle))

    def volcar(self) -> None:
        """Guarda lo pendiente y escribe las trazas aplazadas.

        Las sentencias xAPI se construyen con xapi.registrar (mismo formato que el resto de CidIA)
        y se insertan en bloque con un único INSERT de varias filas: su clave se genera en Python,
        así que el ORM las enviaría de una en una.
        """
        bd = self.bd
        bd.flush()
        columnas = [c.key for c in SentenciaXapi.__table__.columns]
        filas = []
        for cuando, usuario, verbo, tipo, objeto, nombre, resultado, contexto in self._xapi:
            fila = xapi.registrar(bd, None, verbo, tipo, _id(objeto), nombre, _ids(resultado), _ids(contexto),
                                  actor_id=usuario.id if usuario else None,
                                  actor_nombre=usuario.nombre if usuario else None)
            bd.expunge(fila)
            _fechar(fila, cuando)
            filas.append({c: getattr(fila, c) for c in columnas})
        for i in range(0, len(filas), 400):
            bd.execute(insert(SentenciaXapi).values(filas[i:i + 400]))
        for cuando, usuario, accion, entidad, objeto, detalle in self._auditoria:
            ident = _id(objeto)
            bd.add(Auditoria(usuario_id=usuario.id if usuario else None,
                             usuario_nombre=usuario.nombre if usuario else "Sistema", accion=accion, entidad=entidad,
                             entidad_id=str(ident) if ident is not None else None, detalle=_ids(detalle),
                             momento=cuando))
        self._xapi.clear()
        self._auditoria.clear()
        bd.flush()

    def guardar(self) -> None:
        self.volcar()
        self.bd.commit()

    @contextmanager
    def con_fecha(self, cuando: datetime) -> Iterator[None]:
        """Lo que registren los servicios llamados dentro (xAPI y auditoría) pasa a la fecha `cuando`.

        Solo las filas que guarda esta sesión: se anotan cuando llegan a la base (evento de la
        sesión). Buscar «lo registrado desde hace un segundo» cambiaría también la fecha de lo que
        registren a la vez otras peticiones del servidor (p. ej. un inicio de sesión al arrancar).
        """
        self.volcar()
        nuevas: list[tuple[type[Base], Any]] = []

        def anotar(_sesion: Session, fila: Any) -> None:
            if isinstance(fila, (SentenciaXapi, Auditoria)):
                nuevas.append((type(fila), fila.id))

        event.listen(self.bd, "pending_to_persistent", anotar)
        try:
            yield
            self.bd.flush()
        finally:
            event.remove(self.bd, "pending_to_persistent", anotar)
        for clase, ident in nuevas:
            fila = self.bd.get(clase, ident)
            if fila is None:  # se deshizo con un rollback
                continue
            if isinstance(fila, SentenciaXapi):
                _fechar(fila, cuando)
            else:
                fila.momento = cuando

    # ------------------------------------------------------------------ 1. organización

    def organizacion(self, cifrada: str) -> None:
        """Empresa, niveles, cuenta de administración, departamentos, puestos y tareas."""
        from cidia.arranque import CONFIG_ILUO_POR_DEFECTO, NIVELES_POR_DEFECTO

        bd = self.bd
        alta = self.hace(ACT.DIAS_IMPLANTACION, 7.0)
        emp = bd.scalar(select(Empresa).order_by(Empresa.id))
        if emp is None:
            emp = Empresa(config={}, config_iluo=dict(CONFIG_ILUO_POR_DEFECTO))
            bd.add(emp)
        emp.nombre = ORG.EMPRESA["nombre"]
        emp.sector = ORG.EMPRESA["sector"]
        emp.config_iluo = {**CONFIG_ILUO_POR_DEFECTO, **(emp.config_iluo or {})}
        self.empresa = emp
        self.niveles = {n.orden: n for n in bd.scalars(select(Nivel)).all()}
        for orden, nombre, desc in NIVELES_POR_DEFECTO:
            if orden not in self.niveles:
                self.niveles[orden] = Nivel(orden=orden, nombre=nombre, descripcion=desc)
                bd.add(self.niveles[orden])
        # La administración: si ya hay una cuenta (la del instalador o la de CIDIA_ADMIN_CONTRASENA,
        # se llame como se llame) se usa esa y conserva su contraseña; si no, una de demostración.
        admin = bd.scalar(select(Usuario).where(Usuario.rol == "admin")
                          .order_by(Usuario.usuario != "admin", Usuario.activo.desc(), Usuario.id).limit(1))
        if admin is None:
            usuario, nombre, _, nivel, rol, _, _ = ORG.ADMIN
            admin = Usuario(usuario=usuario, nombre=nombre, rol=rol, hash_contrasena=cifrada,
                            nivel=self.niveles[nivel], email=f"{usuario}@{ORG.DOMINIO_CORREO}", creado=alta)
            bd.add(admin)
            self.creados.append("admin")
        self.personas["admin"] = admin
        # Se reutiliza lo que ya exista con el mismo nombre (una base con organización propia).
        deps = {d.nombre: d for d in bd.scalars(select(Departamento)).all()}
        puestos = {(p.departamento_id, p.nombre): p for p in bd.scalars(select(Puesto)).all()}
        tareas = {(t.puesto_id, t.codigo): t for t in bd.scalars(select(Tarea)).all()}
        for d in ORG.DEPARTAMENTOS:
            dep = deps.get(d["nombre"])
            if dep is None:
                dep = Departamento(nombre=d["nombre"], codigo=d["codigo"], color=d["color"],
                                   descripcion=d["descripcion"], creado=alta)
                bd.add(dep)
                self.deps_creados.append(dep.nombre)
                self.auditar(alta, admin, "crear_departamento", "departamento", dep,
                             {"resumen": f"Creó el departamento «{dep.nombre}»", "origen": "semilla"})
            self.deps[d["clave"]] = dep
        for p in ORG.PUESTOS:
            dep = self.deps[p["departamento"]]
            pu = puestos.get((dep.id, p["nombre"])) if dep.id else None
            if pu is None:
                pu = Puesto(departamento=dep, nombre=p["nombre"], descripcion=p["descripcion"])
                bd.add(pu)
                self.auditar(alta, admin, "crear_puesto", "puesto", pu,
                             {"resumen": f"Creó el puesto «{pu.nombre}» en {dep.nombre}", "origen": "semilla"})
            self.puestos[p["clave"]] = pu
            for t in p["tareas"]:
                ta = tareas.get((pu.id, t["codigo"])) if pu.id else None
                if ta is None:
                    ta = Tarea(puesto=pu, codigo=t["codigo"], nombre=t["nombre"], descripcion=t["descripcion"],
                               criticidad=t["criticidad"], riesgos_prl=t["riesgos_prl"],
                               nivel_minimo=t["nivel_minimo"], creada=alta)
                    bd.add(ta)
                    self.auditar(alta, admin, "crear_tarea", "tarea", ta,
                                 {"resumen": f"Creó la tarea «{ta.nombre}» ({ta.codigo})", "origen": "semilla"})
                self.tareas[t["codigo"]] = ta
        bd.flush()
        self.cuenta["departamentos"] = len(self.deps)
        self.cuenta["puestos"] = len(self.puestos)
        self.cuenta["tareas"] = len(self.tareas)

    # ------------------------------------------------------------------ 2. personas

    def personas_y_formaciones(self, cifrada: str) -> None:
        bd = self.bd
        alta = self.hace(ACT.DIAS_IMPLANTACION, 7.5)
        admin = self.personas["admin"]
        existentes = {u.usuario: u for u in bd.scalars(select(Usuario)).all()}
        for usuario, nombre, dep, nivel, rol, experto, puesto in ORG.PERSONAS:
            u = existentes.get(usuario)
            if u is None:
                u = Usuario(
                    usuario=usuario, nombre=nombre, email=f"{usuario}@{ORG.DOMINIO_CORREO}", hash_contrasena=cifrada,
                    departamento=self.deps[dep], nivel=self.niveles[nivel], puesto=self.puestos[puesto], rol=rol,
                    es_experto=experto, creado=alta,
                    ultimo_acceso=self.hace(self.rnd.choice([0, 0, 1, 1, 2, 3, 6]), self.rnd.uniform(6, 14)),
                )
                bd.add(u)
                self.creados.append(usuario)
                self.auditar(alta, admin, "crear_empleado", "usuario", u, {
                    "resumen": f"Dio de alta a {nombre} ({usuario}) con el rol {rol}",
                    "departamento": self.deps[dep].nombre, "origen_identidad": "local",
                })
            self.personas[usuario] = u
        bd.flush()
        for f in ORG.FORMACIONES:
            u, quien = self.personas[f["usuario"]], self.personas[f["asignada_por"]]
            dep, puesto = self.deps[f["departamento"]], self.puestos[f["puesto"]]
            inicio = self.hace(f["inicio"], 7.2)
            fin = self.base - timedelta(days=f["fin_previsto"])
            fo = Formacion(usuario_id=u.id, departamento=dep, puesto=puesto, estado=f["estado"], inicio=inicio,
                           fin_previsto=fin, asignada_por_id=quien.id)
            bd.add(fo)
            self.xapi(inicio, u, "inicio", "formacion", fo, f"Formación en {dep.nombre} · {puesto.nombre}",
                      contexto={"departamento_id": dep.id, "puesto_id": puesto.id, "asignada_por": quien.nombre})
            if inicio >= self.implantacion():
                self.auditar(inicio, quien, "asignar_formacion", "formacion", fo, {
                    "resumen": f"Asignó a {u.nombre} una formación en {dep.nombre} ({puesto.nombre})",
                    "usuario_id": u.id, "fin_previsto": fin.date().isoformat(),
                })
            if f["estado"] == "completada":
                self.xapi(fin, u, "completo", "formacion", fo, f"Formación en {dep.nombre}",
                          resultado={"completion": True}, contexto={"departamento_id": dep.id})
        self.volcar()
        self.cuenta["personas"] = len(self.personas)

    # ------------------------------------------------------------------ 3. documentos

    def documentos(self) -> None:
        bd = self.bd
        raiz = ajustes().dir_datos / CARPETA / "documentos"
        raiz.mkdir(parents=True, exist_ok=True)
        for i, d in enumerate(DOCS.DOCUMENTOS):
            self.progreso(10 + i * 2, f"Indexando «{d['titulo']}»")
            datos = contenido_documento(d)
            ruta = raiz / d["fichero"]
            ruta.write_bytes(datos)
            dep = self.deps[d["departamento"]] if d["departamento"] else None
            autor, sube = self.personas[d["autor"]], self.personas[d["subido_por"]]
            doc = Documento(
                titulo=d["titulo"], descripcion=d["descripcion"], tipo=tipo_por_extension(d["fichero"]),
                departamento_id=dep.id if dep else None, nivel_minimo=d["nivel"], es_formacion=d["formacion"],
                es_publico=d["publico"], estado="procesando", ruta_fichero=relativa(ruta), nombre_fichero=d["fichero"],
                mime="application/pdf" if d["formato"] == "pdf" else "text/markdown", tamano=len(datos),
                autor_id=autor.id, subido_por_id=sube.id, origen="subida",
            )
            bd.add(doc)
            bd.flush()
            documentos.indexar(bd, doc)  # en esta misma pasada: sin trabajos en segundo plano
            if doc.estado != "listo":
                self.avisos.append(f"«{doc.titulo}» no se pudo indexar: {doc.mensaje_estado}")
            fecha = self.hace(d["dias"], self.rnd.uniform(7, 12))
            doc.creado = doc.actualizado = fecha
            self.xapi(fecha, sube, "subio", "documento", doc, doc.titulo,
                      contexto={"departamento_id": doc.departamento_id, "nivel_minimo": doc.nivel_minimo})
            self.docs[d["clave"]] = doc
        self.guardar()
        self.cuenta["documentos"] += len(DOCS.DOCUMENTOS)

    # ------------------------------------------------------------------ 4. instrucciones

    def _imagen(self, defi: dict[str, Any], version: int, orden: int, total: int, paso: dict[str, Any],
                color: str) -> str | None:
        """Imagen esquemática del paso (PNG). Si Pillow falla, el paso se queda sin imagen."""
        destino = ajustes().dir_datos / CARPETA / "instrucciones" / f"{defi['codigo']}-v{version}" / f"paso-{orden:02d}.png"
        try:
            from cidia.semilla_datos.imagenes import imagen_paso

            destino.parent.mkdir(parents=True, exist_ok=True)
            im = imagen_paso(defi["codigo"], defi["titulo"], version, orden, total, paso["titulo"],
                             paso.get("dibujo", "check"), color, paso.get("dato", ""),
                             bool(paso.get("critico")), bool(paso.get("seguridad")))
            im.save(destino, optimize=True)
            return relativa(destino)
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo generar la imagen del paso %s de %s: %s", orden, defi["codigo"], e)
            return None

    def _crear_instruccion(self, defi: dict[str, Any], version: int, pasos_def: list[dict[str, Any]],
                           dias: int) -> Instruccion:
        bd = self.bd
        tarea = self.tareas[defi["tarea"]]
        color = bd.get(Departamento, tarea.puesto.departamento_id).color or "#5b6573"
        pasos = []
        for orden, p in enumerate(pasos_def, start=1):
            pasos.append({"titulo": p["titulo"], "texto": p["texto"], "es_critico": bool(p.get("critico")),
                          "es_seguridad": bool(p.get("seguridad")), "criterio_aceptacion": p.get("criterio"),
                          "imagen_ruta": self._imagen(defi, version, orden, len(pasos_def), p, color)})
        datos = {k: defi[k] for k in ("codigo", "titulo", "resumen", "riesgos", "epis", "herramientas")}
        datos["pasos"] = pasos
        autor = self.personas[defi["autor"]]
        try:
            from cidia.servicios.instrucciones import crear_borrador

            ins = crear_borrador(bd, tarea, autor.id, datos)
        except ImportError:
            ins = Instruccion(tarea_id=tarea.id, estado="borrador", autor_id=autor.id,
                              **{k: v for k, v in datos.items() if k != "pasos"})
            ins.pasos = [Paso(orden=i, **p) for i, p in enumerate(pasos, start=1)]
            bd.add(ins)
        ins.version = version
        ins.creada = self.hace(dias + 2)
        self.xapi(ins.creada, autor, "capturo", "instruccion", ins, f"{ins.codigo} · {ins.titulo}",
                  contexto={"origen": "manual", "tarea_id": tarea.id, "version": version})
        return ins

    def _publicar_directo(self, ins: Instruccion, revisor: Usuario) -> None:
        """Publicación con el contrato de servicios/instrucciones.publicar (si el servicio no está)."""
        bd = self.bd
        tarea = ins.tarea
        dep_id = tarea.puesto.departamento_id
        for o in bd.scalars(select(Instruccion).where(Instruccion.tarea_id == tarea.id, Instruccion.id != ins.id,
                                                      Instruccion.estado == "publicada")).all():
            o.estado = "obsoleta"
        texto, partes = _texto_indexable(ins)
        doc = documentos.crear_desde_texto(
            bd, titulo=f"{ins.codigo} · {ins.titulo} (v{ins.version})", texto=texto, tipo="instruccion",
            departamento_id=dep_id, nivel_minimo=tarea.nivel_minimo or 1, es_formacion=True, es_publico=False,
            autor_id=ins.autor_id, validador_id=revisor.id, subido_por_id=revisor.id, origen="instruccion",
            origen_id=ins.id, version=ins.version, partes=partes, en_segundo_plano=False, descripcion=ins.resumen,
        )
        ins.documento_id = doc.id
        ins.estado = "publicada"
        ins.revisor_id = revisor.id
        nombre = f"{ins.codigo} v{ins.version} · {ins.titulo}"
        xapi.registrar(bd, _actor(revisor), "publico", "instruccion", ins.id, nombre,
                       resultado={"version": ins.version, "pasos": len(ins.pasos), "reevaluaciones": 0},
                       contexto={"tarea_id": tarea.id, "departamento_id": dep_id})
        xapi.auditar(bd, _actor(revisor), "publicar_instruccion", "instruccion", ins.id,
                     {"tarea_id": tarea.id, "version": ins.version})

    def _publicar(self, ins: Instruccion, defi: dict[str, Any], dias: int) -> None:
        bd = self.bd
        revisor = self.personas[defi["revisor"]]
        fecha = self.hace(dias, self.rnd.uniform(8, 12))
        self.guardar()  # lo creado hasta aquí no se pierde si el servicio falla
        publicada = False
        with self.con_fecha(fecha):
            try:
                from cidia.servicios import instrucciones as servicio

                with _sin_generacion_automatica():
                    servicio.publicar(bd, _actor(revisor), ins.id)
                publicada = True
            except NotImplementedError:
                bd.rollback()
            except Exception as e:  # noqa: BLE001
                log.warning("No se pudo publicar %s con el servicio (%s); se publica directamente", ins.codigo, e)
                bd.rollback()
            if not publicada:
                # El servicio hace commit antes de terminar: si falló después, ya está publicada.
                bd.refresh(ins)
                publicada = ins.estado == "publicada"
            if not publicada or not ins.documento_id:
                self._publicar_directo(ins, revisor)
        ins.estado = "publicada"
        ins.publicada_en = fecha
        doc = bd.get(Documento, ins.documento_id) if ins.documento_id else None
        if doc is not None:
            bd.refresh(doc)  # el indexado pudo hacerse en otra sesión (trabajo en segundo plano)
            doc.creado = doc.actualizado = fecha
            if doc.estado == "error":
                self.avisos.append(f"«{doc.titulo}» no se pudo indexar: {doc.mensaje_estado}")
        bd.commit()

    def _material(self, ins: Instruccion, defi: dict[str, Any], vigente: bool) -> None:
        """Micro-lecciones (solo la versión vigente) y preguntas de cuestionario de la instrucción."""
        bd = self.bd
        bd.flush()
        if vigente:  # por si algún generador automático se adelantó: el material de la semilla manda
            bd.execute(delete(Microleccion).where(Microleccion.instruccion_id == ins.id))
            bd.execute(delete(PreguntaEval).where(PreguntaEval.instruccion_id == ins.id))
        experto = self.personas[defi["autor"]]
        if vigente:
            for i, m in enumerate(defi["microlecciones"], start=1):
                bd.add(Microleccion(instruccion_id=ins.id, orden=i, titulo=m["titulo"], contenido=m["contenido"],
                                    punto_clave=m["punto_clave"], pregunta=m["pregunta"]))
        por_titulo = {p.titulo: p for p in ins.pasos}
        creada = (ins.publicada_en or self.base) + timedelta(hours=3)
        for q in defi["preguntas"]:
            paso = None
            if q["paso"]:
                paso = por_titulo.get(defi["pasos"][q["paso"] - 1]["titulo"])
                if paso is None:  # el paso no existe en esta versión
                    continue
            estado = q["estado"] if vigente else "aprobada"
            p = PreguntaEval(instruccion_id=ins.id, paso_id=paso.id if paso else None, enunciado=q["enunciado"],
                             opciones=q["opciones"], correcta=q["correcta"], explicacion=q["explicacion"],
                             estado=estado, aprobada_por_id=experto.id if estado == "aprobada" else None,
                             creada=creada)
            bd.add(p)
            if estado == "aprobada":
                self.xapi(creada + timedelta(minutes=20), experto, "valido", "pregunta", p, q["enunciado"][:120],
                          contexto={"instruccion_id": ins.id})
            self.cuenta["preguntas"] += 1
        self.cuenta["microlecciones"] += len(defi["microlecciones"]) if vigente else 0

    def instrucciones(self) -> None:
        for k, defi in enumerate(INS.INSTRUCCIONES):
            self.progreso(35 + k * 5, f"Publicando {defi['codigo']}")
            # Versiones anteriores ya obsoletas: se crean como tales (sin documento en el índice).
            for ant in defi.get("anteriores", []):
                pasos = [p for i, p in enumerate(defi["pasos"], start=1) if i not in ant["sin_pasos"]]
                vieja = self._crear_instruccion(defi, ant["version"], pasos, ant["dias"])
                vieja.estado = "obsoleta"
                vieja.revisor_id = self.personas[defi["revisor"]].id
                vieja.publicada_en = self.hace(ant["dias"], 9.0)
                self.xapi(vieja.publicada_en, self.personas[defi["revisor"]], "publico", "instruccion", vieja,
                          f"{vieja.codigo} v{vieja.version} · {vieja.titulo}",
                          resultado={"version": vieja.version, "pasos": len(vieja.pasos), "reevaluaciones": 0},
                          contexto={"tarea_id": vieja.tarea_id})
                self._material(vieja, defi, vigente=False)
                self.anteriores[(defi["codigo"], ant["version"])] = vieja
            ins = self._crear_instruccion(defi, defi["version"], defi["pasos"], defi["dias"])
            self._publicar(ins, defi, defi["dias"])
            self._material(ins, defi, vigente=True)
            self.instr[defi["codigo"]] = ins
            self.guardar()
        self.cuenta["instrucciones"] = len(self.instr)

    # ------------------------------------------------------------------ consultas y fuentes

    def _fragmento(self, doc: Documento, respuesta: str) -> str:
        """Trozo del documento que más se parece a la respuesta (para la cita)."""
        palabras = {w for w in re.findall(r"\w{4,}", respuesta.lower())}
        if doc.id not in self._fragmentos:
            trozos = list(self.bd.scalars(
                select(Fragmento.texto).where(Fragmento.documento_id == doc.id).order_by(Fragmento.orden)).all())
            # Al arrancar, la pregunta frecuente se indexa en segundo plano y quizá aún no tiene
            # fragmentos: se usan los párrafos de su texto (crear_desde_texto lo guarda).
            if not trozos and doc.contenido_texto:
                trozos = [t.strip() for t in doc.contenido_texto.split("\n\n") if t.strip()]
            self._fragmentos[doc.id] = trozos
        mejor, puntos = "", -1
        for texto in self._fragmentos[doc.id]:
            p = len(palabras & set(re.findall(r"\w{4,}", texto.lower())))
            if p > puntos:
                mejor, puntos = texto, p
        return (mejor or doc.descripcion or doc.titulo)[:300]

    def fuente(self, n: int, doc: Documento, respuesta: str, paso: Paso | None = None) -> dict[str, Any]:
        """Cita con el formato de servicios/consulta (la URL se firma al leerla)."""
        autor = self.bd.get(Usuario, doc.autor_id) if doc.autor_id else None
        validador = self.bd.get(Usuario, doc.validador_id) if doc.validador_id else None
        codigo = None
        if doc.origen == "instruccion" and doc.origen_id:
            ins = self.bd.get(Instruccion, doc.origen_id)
            codigo = ins.codigo if ins else None
        return {
            "n": n, "documento_id": doc.id, "titulo": doc.titulo, "tipo": doc.tipo, "version": doc.version,
            "paso": paso.orden if paso else None, "paso_id": paso.id if paso else None, "codigo": codigo,
            "pagina": 1 if doc.tipo == "pdf" else None, "hoja": None, "diapositiva": None,
            "autor": autor.nombre if autor else None, "validador": validador.nombre if validador else None,
            "origen": doc.origen, "origen_id": doc.origen_id,
            "fragmento": (paso.texto or "")[:300] if paso else self._fragmento(doc, respuesta),
            "similitud": round(self.rnd.uniform(0.52, 0.81), 3), "url": None,
        }

    def consulta(self, usuario: Usuario, cuando: datetime, pregunta: str, respuesta: str,
                 fuentes: list[dict[str, Any]], con_respaldo: bool = True, laguna_id: int | None = None,
                 tarea_id: int | None = None, paso_id: int | None = None, ejecucion_id: int | None = None,
                 modo: str = "normal", valoracion: int | None = None) -> Consulta:
        modelo = ajustes().llm_modelo_chat
        duracion = self.rnd.randint(1400, 6200)
        c = Consulta(usuario_id=usuario.id, pregunta=pregunta, respuesta=respuesta, modo=modo, fuentes=fuentes,
                     con_respaldo=con_respaldo, laguna_id=laguna_id, tarea_id=tarea_id, paso_id=paso_id,
                     ejecucion_id=ejecucion_id, modelo=modelo, duracion_ms=duracion, valoracion=valoracion,
                     creada=cuando)
        self.bd.add(c)
        self.xapi(cuando, usuario, "pregunto", "consulta", c, pregunta[:200],
                  resultado={"con_respaldo": con_respaldo, "fuentes": len(fuentes),
                             "citadas": [1] if fuentes and con_respaldo else [], "duracion_ms": duracion,
                             "laguna_id": laguna_id},
                  contexto={"modo": modo, "tarea_id": tarea_id, "paso_id": paso_id, "ejecucion_id": ejecucion_id,
                            "modelo": modelo})
        self.cuenta["consultas"] += 1
        return c

    def _doc_por_clave(self, clave: str) -> Documento | None:
        if clave.startswith("it:"):
            ins = self.instr.get(clave[3:])
            return self.bd.get(Documento, ins.documento_id) if ins and ins.documento_id else None
        if clave.startswith("faq:"):
            ap = self.aps.get(clave[4:])
            return self.bd.get(Documento, ap.documento_id) if ap and ap.documento_id else None
        return self.docs.get(clave)

    # ------------------------------------------------------------------ 5. lagunas

    def lagunas(self) -> None:
        bd = self.bd
        try:
            vectores: list[Any] = list(llm.embeddings([lg["pregunta"] for lg in ACT.LAGUNAS]))
            if len(vectores) != len(ACT.LAGUNAS):
                raise ValueError(f"el modelo devolvió {len(vectores)} vectores para {len(ACT.LAGUNAS)} preguntas")
        except Exception as e:  # noqa: BLE001  (sin embeddings se agrupan por texto)
            log.warning("Lagunas sin embedding: %s", e)
            vectores = [None] * len(ACT.LAGUNAS)
        creadas: list[tuple[Laguna, list[Any], list[datetime], Tarea | None]] = []
        for definicion, vector in zip(ACT.LAGUNAS, vectores, strict=True):
            consultas = sorted(definicion["consultas"], key=lambda c: -c[1])
            fechas = [self.hace(dias) for _, dias, _ in consultas]
            tarea = self.tareas.get(definicion["tarea"]) if definicion["tarea"] else None
            ejemplos: list[str] = []
            for _, _, t in consultas:
                if t not in ejemplos:
                    ejemplos.append(t)
            lg = Laguna(pregunta=definicion["pregunta"], departamento_id=self.deps[definicion["departamento"]].id,
                        tarea_id=tarea.id if tarea else None, frecuencia=len(consultas), embedding=vector,
                        estado="abierta" if definicion.get("aportacion") else definicion["estado"],
                        ejemplos=ejemplos, primera_vez=min(fechas), ultima_vez=max(fechas))
            bd.add(lg)
            creadas.append((lg, consultas, fechas, tarea))
            if definicion.get("aportacion"):
                self.lagunas_de[definicion["aportacion"]] = lg
        bd.flush()
        for lg, consultas, fechas, tarea in creadas:
            for (quien, _, texto), cuando in zip(consultas, fechas, strict=True):
                self.consulta(self.personas[quien], cuando, texto, ACT.RESPUESTA_SIN_RESPALDO, [], con_respaldo=False,
                              laguna_id=lg.id, tarea_id=tarea.id if tarea else None)
        self.cuenta["lagunas"] = len(ACT.LAGUNAS)

    # ------------------------------------------------------------------ 6. modo planta

    def _instruccion_de(self, codigo: str, version: int | None) -> Instruccion:
        if version is None or self.instr[codigo].version == version:
            return self.instr[codigo]
        return self.anteriores[(codigo, version)]

    def ejecuciones(self) -> None:
        """Ejecuciones en el modo planta con sus pasos, sus consultas por paso y sus trazas."""
        bd = self.bd
        respaldo_doc = {"IT-061": "control"}  # versiones viejas sin documento: se citó el plan de control
        pendientes: list[dict[str, Any]] = []
        for plan in ACT.EJECUCIONES:
            ins = self._instruccion_de(plan["codigo"], plan.get("version"))
            pasos = sorted(ins.pasos, key=lambda p: p.orden)
            defi = self.definicion[plan["codigo"]]
            doc = bd.get(Documento, ins.documento_id) if ins.documento_id else None
            if doc is None and plan["codigo"] in respaldo_doc:
                doc = self.docs[respaldo_doc[plan["codigo"]]]
            comun = {
                "u": self.personas[plan["usuario"]], "ins": ins, "tarea": ins.tarea, "pasos": pasos, "doc": doc,
                "orden_def": {p["titulo"]: i for i, p in enumerate(defi["pasos"], start=1)},
                "banco": ACT.PREGUNTAS_PASO.get(plan["codigo"], {}),
            }
            for k, fila in enumerate(plan["filas"]):
                dias, n, n_crit, minutos = fila[:4]
                estado = fila[4] if len(fila) > 4 else "completada"
                inicio = self.hace(dias, self.rnd.uniform(6, 15))
                duracion = timedelta(minutes=minutos)
                ej = Ejecucion(usuario_id=comun["u"].id, tarea_id=ins.tarea_id, instruccion_id=ins.id, estado=estado,
                               inicio=inicio, fin=inicio + duracion, consultas=n, consultas_criticos=n_crit)
                bd.add(ej)
                pendientes.append({**comun, "k": k, "ej": ej, "n": n, "n_crit": n_crit, "duracion": duracion,
                                   "hechos": len(pasos) if estado == "completada" else max(1, len(pasos) // 3)})
        bd.flush()  # los ids de todas las ejecuciones en una sola ida a la base
        for e in pendientes:
            self._detalle_ejecucion(e)
            self.cuenta["ejecuciones"] += 1
        self.volcar()

    def _reparto(self, e: dict[str, Any]) -> Counter[int]:
        """Consultas por paso: las críticas en los pasos críticos y el resto en los demás pasos hechos."""
        pasos, ej = e["pasos"], e["ej"]
        criticos = [p for p in pasos if p.es_critico] or pasos
        alcanzados = pasos[: e["hechos"] + (0 if ej.estado == "completada" else 1)]
        normales = [p for p in alcanzados if not p.es_critico] or pasos
        reparto: Counter[int] = Counter()
        for j in range(e["n_crit"]):
            reparto[criticos[j % len(criticos)].id] += 1
        for j in range(e["n"] - e["n_crit"]):
            reparto[normales[(j + e["k"]) % len(normales)].id] += 1
        return reparto

    def _detalle_ejecucion(self, e: dict[str, Any]) -> None:
        u, ins, tarea, pasos, doc, ej = e["u"], e["ins"], e["tarea"], e["pasos"], e["doc"], e["ej"]
        reparto = self._reparto(e)
        ctx = {"ejecucion_id": ej.id, "tarea_id": tarea.id, "instruccion_id": ins.id, "version": ins.version,
               "codigo": ins.codigo}
        self.xapi(ej.inicio, u, "inicio", "tarea", tarea.id, tarea.nombre, contexto=ctx)
        tramo = e["duracion"] / len(pasos)
        for i, p in enumerate(pasos):
            hecho = i < e["hechos"]
            confirmado = ej.inicio + tramo * (i + 1) if hecho else None
            n_paso = reparto[p.id]
            self.bd.add(EjecucionPaso(ejecucion_id=ej.id, paso_id=p.id, confirmado_en=confirmado,
                                      critico_confirmado=bool(p.es_critico and hecho), consultas=n_paso))
            preguntas = e["banco"].get(e["orden_def"].get(p.titulo, p.orden)) or [
                (f"¿Qué hay que hacer en el paso {p.orden}?", f"{p.titulo}. {(p.texto or '')[:160]} [1]")]
            for j in range(n_paso):
                pregunta, respuesta = preguntas[(j + e["k"]) % len(preguntas)]
                cuando = ej.inicio + tramo * (i + (j + 1) / (n_paso + 1))
                fuentes = [self.fuente(1, doc, respuesta, p if doc.id == ins.documento_id else None)] if doc else []
                self.consulta(u, cuando, pregunta, respuesta, fuentes, tarea_id=tarea.id, paso_id=p.id,
                              ejecucion_id=ej.id, modo="planta", valoracion=1 if self.rnd.random() < 0.6 else None)
            if hecho:
                self.xapi(confirmado, u, "confirmo", "paso", p.id, p.titulo,
                          resultado={"completion": True, "critico": p.es_critico,
                                     "critico_confirmado": bool(p.es_critico), "consultas": n_paso},
                          contexto={**ctx, "orden": p.orden})
        segundos = int(e["duracion"].total_seconds())
        if ej.estado == "completada":
            self.xapi(ej.fin, u, "completo", "tarea", tarea.id, tarea.nombre,
                      resultado={"completion": True, "consultas": ej.consultas,
                                 "consultas_criticos": ej.consultas_criticos, "duracion": segundos}, contexto=ctx)
        else:
            self.xapi(ej.fin, u, "abandono", "tarea", tarea.id, tarea.nombre,
                      resultado={"completion": False, "pasos_confirmados": e["hechos"], "consultas": ej.consultas,
                                 "duracion": segundos}, contexto=ctx)

    # ------------------------------------------------------------------ 7. formación y evaluación

    def microlecciones_vistas(self) -> None:
        for usuario, codigo, indices, dias in ACT.VISTAS:
            u = self.personas[usuario]
            ins = self.instr[codigo]
            lecciones = self.bd.scalars(select(Microleccion).where(Microleccion.instruccion_id == ins.id)
                                        .order_by(Microleccion.orden)).all()
            primera = self.hace(dias, self.rnd.uniform(6, 12))
            for k, i in enumerate(indices):
                m = lecciones[i]
                cuando = primera + timedelta(minutes=6 * k + self.rnd.randint(1, 4))
                self.bd.add(MicroleccionVista(usuario_id=u.id, microleccion_id=m.id, completada_en=cuando))
                self.xapi(cuando, u, "vio", "microleccion", m, m.titulo, resultado={"completion": True},
                          contexto={"tarea_id": ins.tarea_id, "instruccion_id": ins.id, "version": ins.version,
                                    "orden": m.orden})

    def intentos(self) -> None:
        bd = self.bd
        umbral = float((self.empresa.config_iluo or {}).get("umbral_cuestionario", 0.8)) if self.empresa else 0.8
        aprobadas: dict[int, list[PreguntaEval]] = {}
        for usuario, codigo, version, dias, aciertos, total in ACT.INTENTOS:
            u = self.personas[usuario]
            ins = self._instruccion_de(codigo, version)
            if ins.id not in aprobadas:
                aprobadas[ins.id] = list(bd.scalars(select(PreguntaEval).where(
                    PreguntaEval.instruccion_id == ins.id, PreguntaEval.estado == "aprobada").order_by(PreguntaEval.id)))
            preguntas = aprobadas[ins.id]
            total = len(preguntas) or total
            aciertos = min(aciertos, total)
            fallos = set(self.rnd.sample(range(total), total - aciertos))
            respuestas = {}
            for i, p in enumerate(preguntas):
                respuestas[str(p.id)] = (p.correcta + 1) % len(p.opciones) if i in fallos else p.correcta
            puntuacion = aciertos / total
            aprobado = puntuacion + 1e-9 >= umbral
            cuando = self.hace(dias, self.rnd.uniform(9, 16))
            it = IntentoEval(usuario_id=u.id, instruccion_id=ins.id, respuestas=respuestas, aciertos=aciertos,
                             total=total, puntuacion=puntuacion, aprobado=aprobado, creado=cuando)
            bd.add(it)
            self.xapi(cuando, u, "aprobo" if aprobado else "suspendio", "cuestionario", ins.id,
                      f"Cuestionario · {ins.tarea.nombre} (v{ins.version})",
                      resultado={"score": round(puntuacion, 4), "success": aprobado, "aciertos": aciertos,
                                 "total": total},
                      contexto={"tarea_id": ins.tarea_id, "instruccion_id": ins.id, "intento_id": it})
            self.cuenta["intentos"] += 1

    def observaciones(self) -> None:
        bd = self.bd
        for o in ACT.OBSERVACIONES:
            evaluador, u = self.personas[o["evaluador"]], self.personas[o["usuario"]]
            ins = self._instruccion_de(o["codigo"], o.get("version"))
            fallos = set(o.get("fallos", []))
            lista = [{"paso_id": p.id, "orden": p.orden, "texto": p.titulo, "critico": p.es_critico,
                      "ok": p.orden not in fallos, "nota": o["notas"].get(p.orden)} for p in ins.pasos]
            cuando = self.hace(o["dias"], self.rnd.uniform(7, 13))
            obs = Observacion(evaluador_id=evaluador.id, usuario_id=u.id, tarea_id=ins.tarea_id,
                              instruccion_id=ins.id, lista=lista, aprobada=o["aprobada"], comentario=o["comentario"],
                              creada=cuando)
            bd.add(obs)
            ok = sum(1 for x in lista if x["ok"])
            self.xapi(cuando, evaluador, "observo", "observacion", obs, f"{u.nombre} · {ins.tarea.nombre}",
                      resultado={"success": obs.aprobada, "pasos": len(lista), "pasos_ok": ok,
                                 "score": round(ok / len(lista), 4)},
                      contexto={"usuario_id": u.id, "tarea_id": ins.tarea_id, "instruccion_id": ins.id})
            self.cuenta["observaciones"] += 1

    def niveles_iluo(self) -> None:
        """Niveles con fechas y caducidades. Las evidencias se calculan con servicios/iluo.evaluar."""
        bd = self.bd
        try:
            from cidia.servicios import iluo as servicio_iluo
        except ImportError:
            servicio_iluo = None  # type: ignore[assignment]
        letras = ["", "I", "L", "U", "O"]
        meses = int((self.empresa.config_iluo or {}).get("meses_validez", 12)) if self.empresa else 12
        filas = {(f.usuario_id, f.tarea_id): f for f in bd.scalars(select(NivelIluo)).all()}
        for usuario, codigo, nivel, dias, formador, reevaluar in ACT.ILUO:
            u, tarea = self.personas[usuario], self.tareas[codigo]
            desde = self.hace(dias, self.rnd.uniform(9, 15))
            historico = dias > ACT.DIAS_IMPLANTACION
            fila = filas.get((u.id, tarea.id))
            if fila is None:
                fila = NivelIluo(usuario_id=u.id, tarea_id=tarea.id)
                bd.add(fila)
            fila.nivel = nivel
            fila.desde = desde
            fila.caduca = (servicio_iluo.sumar_meses(desde, meses) if hasattr(servicio_iluo, "sumar_meses")
                           else desde + timedelta(days=round(365 * meses / 12)))
            fila.requiere_reevaluacion = reevaluar
            fila.formador_validado = bool(formador)
            fila.formador_validado_por_id = self.personas[formador].id if formador else None
            datos: dict[str, Any] = {"historial": [{"tipo": "importado" if historico else "subida", "fecha": _iso(desde),
                                                    "nivel_anterior": 0 if historico else nivel - 1, "nivel": nivel}]}
            if historico:
                datos["origen"] = "Matriz de competencias en papel, anterior a CidIA"
            if formador:
                validador = self.personas[formador]
                datos["formador"] = {"por_id": validador.id, "por": validador.nombre, "fecha": _iso(desde)}
            if reevaluar:
                publicada = self.instr[codigo].publicada_en
                datos["historial"].append({"tipo": "reevaluacion", "fecha": _iso(publicada), "nivel": nivel})
            fila.evidencias = datos
            if servicio_iluo is not None and hasattr(servicio_iluo, "evaluar"):
                try:
                    ev = servicio_iluo.evaluar(bd, u.id, tarea, fila)
                    fila.evidencias = {**datos, **ev.a_dict(), "calculado": ev.nivel, "actualizado": _iso(self.base)}
                except Exception as e:  # noqa: BLE001
                    log.warning("No se pudieron calcular las evidencias ILUO de %s en %s: %s", usuario, codigo, e)
            if not historico:
                self.xapi(desde, u, "certifico", "tarea", tarea.id, tarea.nombre,
                          resultado={"nivel": letras[nivel], "nivel_numero": nivel, "nivel_anterior": letras[nivel - 1],
                                     "success": True},
                          contexto={"usuario_id": u.id, "tarea_id": tarea.id, "motivo": "evidencias"})
            self.cuenta["niveles_iluo"] += 1
        self.volcar()

    # ------------------------------------------------------------------ 8. aportaciones

    def _audio(self, clave: str) -> tuple[str | None, float | None]:
        """Nota de voz sintética de la aportación (ruta y segundos), si viaja con el paquete."""
        origen = DIR_AUDIO / f"aportacion-{clave}.ogg"
        if not origen.is_file():
            return None, None
        destino = ajustes().dir_datos / CARPETA / "aportaciones" / origen.name
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origen, destino)
        return relativa(destino), duracion_ogg_opus(destino.read_bytes())

    def _validar_directo(self, ap: Aportacion, validador: Usuario) -> None:
        """Validación con el mismo resultado que servicios/aportaciones.validar (si el servicio no está)."""
        bd = self.bd
        autor = bd.get(Usuario, ap.autor_id)
        laguna = bd.get(Laguna, ap.laguna_id) if ap.laguna_id else None
        lineas = [f"Pregunta: {laguna.pregunta}"] if laguna else []
        lineas += [f"Problema: {ap.problema}", f"Causa: {ap.causa}", f"Solución: {ap.solucion}"]
        if ap.etiquetas:
            lineas.append("Etiquetas: " + ", ".join(ap.etiquetas))
        ap.estado, ap.validador_id = "validada", validador.id
        doc = documentos.crear_desde_texto(
            bd, titulo=ap.titulo, texto="\n\n".join(lineas), tipo="faq", departamento_id=ap.departamento_id,
            nivel_minimo=ap.nivel_minimo or 1, autor_id=ap.autor_id, validador_id=validador.id,
            subido_por_id=validador.id, origen="aportacion", origen_id=ap.id, en_segundo_plano=False,
            descripcion=f"Aportación de {autor.nombre} validada por {validador.nombre}.",
        )
        ap.documento_id = doc.id
        if laguna is not None:
            laguna.estado, laguna.aportacion_id = "resuelta", ap.id
        xapi.registrar(bd, _actor(validador), "valido", "aportacion", ap.id, ap.titulo,
                       resultado={"success": True, "response": "validada", "documento_id": doc.id},
                       contexto={"autor_id": ap.autor_id, "departamento_id": ap.departamento_id,
                                 "tarea_id": ap.tarea_id})

    def aportaciones(self) -> None:
        bd = self.bd
        for a in ACT.APORTACIONES:
            autor = self.personas[a["autor"]]
            cuando = self.base - timedelta(hours=a["horas"]) if "horas" in a else self.hace(a["dias"])
            tarea = self.tareas.get(a["tarea"]) if a.get("tarea") else None
            laguna = self.lagunas_de.get(a["clave"])
            audio, segundos = self._audio(a["clave"]) if a.get("transcripcion") else (None, None)
            ap = Aportacion(
                autor_id=autor.id, departamento_id=self.deps[a["departamento"]].id, tarea_id=tarea.id if tarea else None,
                laguna_id=laguna.id if laguna else None, texto_original=a.get("texto_original"), audio_ruta=audio,
                duracion_audio=segundos, transcripcion=a.get("transcripcion"),
                titulo=a["titulo"], problema=a["problema"], causa=a["causa"], solucion=a["solucion"],
                etiquetas=a["etiquetas"], nivel_minimo=a["nivel_minimo"], estado="pendiente", creada=cuando,
            )
            bd.add(ap)
            texto = a.get("texto_original")
            self.xapi(cuando, autor, "aporto", "aportacion", ap, _primera_frase(texto) if texto else "Nota de voz",
                      contexto={"via": "texto" if texto else "voz", "tarea_id": ap.tarea_id, "laguna_id": laguna,
                                "estado": "enviada"})
            self.aps[a["clave"]] = ap
            if a["estado"] == "validada":
                validador = self.personas[a["validador"]]
                fecha = self.hace(a["dias_validada"], self.rnd.uniform(9, 13))
                self.guardar()
                hecho = False
                with self.con_fecha(fecha):
                    try:
                        from cidia.servicios import aportaciones as servicio

                        servicio.validar(bd, _actor(validador), ap)
                        hecho = True
                    except Exception as e:  # noqa: BLE001  (incluye el servicio aún provisional)
                        log.warning("No se pudo validar la aportación con el servicio (%s); se valida directamente", e)
                        bd.rollback()
                        bd.refresh(ap)  # el servicio hace commit a mitad: quizá ya quedó validada
                        hecho = ap.estado == "validada" and ap.documento_id is not None
                    if not hecho:
                        self._validar_directo(ap, validador)
                if laguna is not None and laguna.estado != "resuelta":  # la laguna queda respondida
                    laguna.estado, laguna.aportacion_id = "resuelta", ap.id
                ap.validada_en = fecha
                doc = bd.get(Documento, ap.documento_id) if ap.documento_id else None
                if doc is not None:
                    bd.refresh(doc)
                    doc.creado = doc.actualizado = fecha
                    if doc.estado == "error":
                        self.avisos.append(f"«{doc.titulo}» no se pudo indexar: {doc.mensaje_estado}")
        self.guardar()
        self.cuenta["aportaciones"] = len(ACT.APORTACIONES)

    # ------------------------------------------------------------------ 9. consultas con respaldo

    def consultas_con_respaldo(self) -> None:
        alcances: dict[str, Any] = {}
        for usuario, dias, pregunta, respuesta, claves, valoracion in ACT.CONSULTAS:
            u = self.personas[usuario]
            alcance = alcances.setdefault(usuario, alcance_de(self.bd, _actor(u)))
            fuentes = []
            for clave in claves:
                doc = self._doc_por_clave(clave)
                # defensa: nunca se cita lo que esa persona no puede ver (aunque aún se esté indexando)
                if doc is not None and puede_ver(alcance, _como_listo(doc)):
                    fuentes.append(self.fuente(len(fuentes) + 1, doc, respuesta))
            self.consulta(u, self.hace(dias), pregunta, respuesta, fuentes, con_respaldo=bool(fuentes),
                          valoracion=valoracion)

    # ------------------------------------------------------------------ 10. cierre

    def marcar(self, estado: str) -> None:
        """Anota en empresa.config qué ha creado la semilla (lo usa `vaciar`) y si ya terminó.

        Se anota «en_curso» en el primer commit: si el servidor se reinicia a mitad de la siembra,
        el arranque sabe que esos datos son de la semilla y la repite desde cero.
        """
        assert self.empresa is not None
        self.empresa.config = {**(self.empresa.config or {}), "semilla": {
            "version": VERSION_SEMILLA, "estado": estado, "fecha": _iso(self.base), "usuarios": list(self.creados),
            "departamentos": list(self.deps_creados),
        }}

    def cerrar(self, origen_contrasena: str) -> dict[str, Any]:
        bd = self.bd
        assert self.empresa is not None
        self.volcar()
        self.marcar("completa")
        self.auditar(self.base, None, "sembrar_demo", "empresa", self.empresa.id, {
            "resumen": "Cargó los datos sintéticos de demostración (Metalúrgica Arlanza, empresa ficticia)",
            "recuento": dict(self.cuenta),
        })
        self.guardar()
        self.cuenta["xapi"] = bd.scalar(select(func.count(SentenciaXapi.id))) or 0
        return {"sembrado": True, **dict(self.cuenta), "contrasena_en": origen_contrasena, "avisos": self.avisos}


def vaciar(bd: Session) -> None:
    """Borra el contenido de demostración: actividad, conocimiento, cuentas y departamentos sembrados.

    Conserva empresa, niveles, modelos, auditoría y las cuentas que no creó la semilla. Solo para
    servidores de demostración (lo usa `sembrar(forzar=True)`): en una base con datos propios
    (`estado_base` = «con_datos») se niega, porque vaciaría todos sus documentos y su actividad.
    """
    if estado_base(bd) == "con_datos":
        raise RuntimeError("La base tiene datos propios: la semilla no la vacía.")
    emp = bd.scalar(select(Empresa).order_by(Empresa.id))
    marca = marca_semilla(bd)
    # Sin marca (siembras antiguas) se supone lo de siempre: las personas y departamentos de ORG, y
    # de las personas solo las que llevan el correo ficticio de la semilla.
    usuarios = marca["usuarios"] if "usuarios" in marca else [p[0] for p in ORG.PERSONAS]
    departamentos = marca["departamentos"] if "departamentos" in marca else [d["nombre"] for d in ORG.DEPARTAMENTOS]
    cuentas = Usuario.usuario.in_(usuarios)
    if "usuarios" not in marca:
        cuentas = cuentas & Usuario.email.ilike(f"%@{ORG.DOMINIO_CORREO}")
    # Con un motor externo (WeKnora) los documentos viven también allí: se retiran antes, para no
    # dejar conocimiento huérfano. El motor propio no lo necesita: sus fragmentos son una tabla más.
    for doc in bd.scalars(select(Documento).where(Documento.motor_id.is_not(None))).all():
        try:
            with bd.begin_nested():
                motor().borrar(bd, doc)
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo retirar «%s» del motor de conocimiento: %s", doc.titulo, e)
    # Sin RESTART IDENTITY: los ids nuevos no reutilizan los antiguos, así que nada de lo que se
    # conserva (historial de trabajos, auditoría, enlaces guardados) acaba apuntando a otra fila.
    bd.execute(text(f"TRUNCATE TABLE {', '.join(TABLAS_CONTENIDO)} CASCADE"))
    bd.execute(delete(Usuario).where(cuentas).execution_options(synchronize_session=False))
    bd.execute(delete(Departamento).where(Departamento.nombre.in_(departamentos))
               .execution_options(synchronize_session=False))
    if emp is not None:
        emp.config = {k: v for k, v in (emp.config or {}).items() if k != "semilla"}
    bd.add(Auditoria(usuario_nombre="Sistema", accion="restablecer_demo", entidad="empresa",
                     entidad_id=str(emp.id) if emp else None,
                     detalle={"resumen": "Vació el contenido de demostración para volver a sembrarlo"}))
    bd.commit()
    bd.expunge_all()
    shutil.rmtree(ajustes().dir_datos / CARPETA, ignore_errors=True)


def sembrar(bd: Session, forzar: bool = False, progreso: Callable[..., None] | None = None) -> dict[str, Any]:
    """Siembra los datos de demostración. Devuelve un resumen con los recuentos (sin la contraseña).

    Si la base ya está sembrada (marca de la semilla o su cuenta «ana») no hace nada, salvo con `forzar=True`.
    En una base con datos propios no hace nada nunca (ni con `forzar`). Si ya hay otra siembra en
    marcha (estado «ocupada»), tampoco: se espera a que termine. Hace commit por etapas.
    """
    with _cerrojo(bd.get_bind().engine) as libre:
        if not libre:
            log.warning("Ya hay otra siembra de los datos de demostración en marcha: no se empieza otra")
            return {"sembrado": False, "estado": "ocupada", "motivo": OCUPADA}
        return _sembrar(bd, forzar, progreso)


def _sembrar(bd: Session, forzar: bool, progreso: Callable[..., None] | None) -> dict[str, Any]:
    estado = estado_base(bd)
    if estado == "con_datos":
        log.warning("La base tiene datos propios: no se cargan los datos de demostración")
        return {"sembrado": False, "estado": estado,
                "motivo": "La base ya tiene datos propios (departamentos, personas o documentos). Los datos de "
                          "demostración solo se cargan en una base vacía."}
    if estado != "vacia" and not forzar:
        log.info("La base ya tiene datos de demostración: no se siembra de nuevo")
        motivo = (f"Ya existe el usuario «{USUARIO_TESTIGO}»." if estado == "sembrada" and ya_sembrado(bd) else
                  "La base ya tiene los datos de demostración." if estado == "sembrada" else
                  "La siembra anterior quedó a medias.")
        return {"sembrado": False, "estado": estado, "motivo": motivo}
    if estado != "vacia":
        vaciar(bd)
    s = _Semilla(bd, progreso)
    inicio = time.monotonic()
    contrasena, origen = contrasena_demo()
    cifrada = hash_contrasena(contrasena)
    log.info("Cuentas de demostración: la contraseña común está en %s", origen)
    s.progreso(2, "Creando la organización")
    s.organizacion(cifrada)
    s.personas_y_formaciones(cifrada)
    s.marcar("en_curso")
    s.guardar()
    s.progreso(8, "Indexando documentos")
    s.documentos()
    s.progreso(35, "Publicando instrucciones")
    s.instrucciones()
    s.progreso(65, "Generando actividad")
    s.lagunas()
    s.ejecuciones()
    s.microlecciones_vistas()
    s.intentos()
    s.observaciones()
    s.guardar()
    s.progreso(80, "Calculando niveles ILUO")
    s.niveles_iluo()
    s.guardar()
    s.progreso(88, "Validando aportaciones")
    s.aportaciones()
    s.consultas_con_respaldo()
    s.progreso(97, "Cerrando")
    resumen = s.cerrar(origen)
    resumen["segundos"] = round(time.monotonic() - inicio, 1)
    log.info("Semilla de demostración cargada en %.1f s: %s", resumen["segundos"],
             {k: v for k, v in resumen.items() if k not in ("avisos", "contrasena_en")})
    for aviso in s.avisos:
        log.warning("Semilla: %s", aviso)
    return resumen


# --------------------------------------------------------------------------- arranque


def _esperar_modelos(progreso: Callable[..., None], intentos: int = 240, pausa: float = 5.0) -> None:
    """Al arrancar con Docker, Ollama puede tardar en responder o el instalador puede estar aún
    descargando los modelos (arranca los servicios antes): se espera hasta ~20 minutos. Es un hilo
    de la cola de trabajos dormido, no retrasa nada más."""
    for i in range(intentos):
        try:
            llm.embeddings(["prueba"])
            return
        except Exception:  # noqa: BLE001
            progreso(1, "Esperando al modelo de búsqueda")
            if i == 0:
                log.info("La semilla espera a que responda el modelo de embeddings")
            time.sleep(pausa)
    log.warning("El modelo de embeddings no responde: los documentos quedarán con error de indexado "
                "(se pueden reindexar después desde Documentos)")


def _trabajo_sembrar(bd: Session, progreso: Callable[..., None], forzar: bool = False) -> dict[str, Any]:
    """Trabajo en segundo plano del arranque. Vuelve a mirar la base: pudo cambiar en la cola."""
    estado = estado_base(bd)
    if estado == "vacia" or (forzar and estado == "incompleta"):
        _esperar_modelos(progreso)
        return sembrar(bd, forzar=forzar, progreso=progreso)
    return {"sembrado": False, "estado": estado}


def sembrar_si_vacio() -> int | None:
    """La llama arranque.py (CIDIA_CREAR_SEMILLA=true). Si hace falta, encola la siembra en segundo
    plano y devuelve el id del trabajo; los errores se registran sin impedir el arranque.

    Siembra en una base vacía y repite desde cero una siembra que quedó a medias. Una base ya
    sembrada o con datos propios no se toca.
    """
    try:
        with sesion_bd() as bd:
            estado = estado_base(bd)
        if estado == "sembrada":
            log.info("Semilla: la base ya tiene datos de demostración")
            return None
        if estado == "con_datos":
            log.warning("Semilla: CIDIA_CREAR_SEMILLA=true, pero la base tiene datos propios: no se cargan los "
                        "datos de demostración")
            return None
        forzar = estado == "incompleta"
        if forzar:
            log.warning("Semilla: la siembra anterior quedó a medias (¿se reinició el servidor?): se repite desde cero")
        return trabajos.encolar("semilla_demo", _trabajo_sembrar, forzar, entidad="empresa")
    except Exception:  # noqa: BLE001
        log.exception("No se pudo preparar la semilla de demostración")
        return None


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m cidia.semilla",
                                     description="Datos sintéticos de demostración de CidIA (empresa ficticia).")
    parser.add_argument("--forzar", action="store_true", help="vacía el contenido de demostración y vuelve a sembrar")
    parser.add_argument("--exportar", metavar="DIR", help="solo escribe los documentos (Markdown y PDF) en DIR")
    args = parser.parse_args(argv)
    if args.exportar:
        n = exportar_documentos(Path(args.exportar))
        print(f"{n} documentos escritos en {args.exportar}")
        return 0
    from cidia.arranque import administrador_inicial, valores_por_defecto
    from cidia.db import inicializar_bd, motor_bd

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Antes de tocar el esquema: inicializar_bd altera la tabla de usuarios y, con otra siembra a
    # mitad de una etapa, esperaría a que terminase y dejaría esperando a todo el servidor.
    with _cerrojo(motor_bd()) as libre:
        if not libre:
            print(f"No se ha sembrado: {OCUPADA}")
            return 1
    inicializar_bd()
    valores_por_defecto()
    administrador_inicial()  # como al arrancar: la cuenta de CIDIA_ADMIN_CONTRASENA conserva su contraseña
    trabajos.modo_sincrono(True)  # el indexado termina antes de salir
    with sesion_bd() as bd:
        resumen = sembrar(bd, forzar=args.forzar)
    if not resumen.get("sembrado"):
        estado = resumen.get("estado")
        consejo = " Usa --forzar para empezar de cero." if estado in ("sembrada", "incompleta") else ""
        print(f"No se ha sembrado: {resumen.get('motivo')}{consejo}")
        return 1 if estado in ("con_datos", "ocupada") else 0
    print("Datos de demostración cargados:")
    for clave, valor in resumen.items():
        if clave not in ("sembrado", "avisos"):
            print(f"  {clave}: {valor}")
    for aviso in resumen.get("avisos", []):
        print(f"  aviso: {aviso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
