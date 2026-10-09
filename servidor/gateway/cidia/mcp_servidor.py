"""Servidor MCP de CidIA: las herramientas del agente de la app, en /mcp (streamable HTTP).

Decisiones (ver docs/investigacion/04_stack_servidor_y_modelos.md §1):

* SDK oficial `mcp` 2.3 (`MCPServer`; `FastMCP` ya no existe en la 2.x). Transporte streamable
  HTTP **sin estado** (`stateless_http=True`) y con **respuestas JSON** (`json_response=True`):
  cada POST es independiente, sirve tanto a la era 2026-07-28 (la que usa la app dsh, sin
  `initialize`) como a la antigua, y permite varios procesos sin sesiones fijas.
* Autenticación: un `TokenVerifier` valida el mismo JWT de CidIA que usa la interfaz, contra la
  base de datos (`seguridad.actor_desde_token`: firma, caducidad, sesión no revocada, cuenta
  activa). Sin token o con uno no válido, 401 y no se ejecuta nada. Cada herramienta vuelve a
  cargar el actor de la petición con su propia sesión de BD y llama a los mismos servicios que
  la API: los permisos son los mismos por las tres entradas (/api, /v1, /mcp). Los invitados
  solo pueden buscar en lo público (con su límite de uso).
* Montaje: se añade la ruta `/mcp` a la app de FastAPI (no se monta la sub-app en «/», que
  taparía /app). El gestor del transporte (`session_manager.run()`) se registra con
  `cidia.vida.al_arrancar`; como cada gestor solo puede arrancarse una vez, si la app arranca de
  nuevo (pruebas) se reconstruye la sub-app con un gestor nuevo.
* Protección de Host (DNS rebinding): variable `CIDIA_MCP_HOSTS`. Por defecto «*», que **no**
  comprueba la cabecera Host. Es una decisión consciente: la autenticación es un token Bearer
  en cabecera (no hay cookies ni confianza por red), así que una web que haga DNS rebinding no
  puede usar /mcp sin el token; y el gateway se publica con nombres, IP y proxies distintos en
  cada empresa (Oracle, MSI, el proxy del plugin), que la lista blanca rompería con «421 Invalid
  Host header». Para restringirlo: `CIDIA_MCP_HOSTS=cidia.empresa.local,10.0.0.5` (se aceptan
  con y sin puerto) y, si un navegador envía `Origin`, `CIDIA_MCP_ORIGENES=https://...`.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import timedelta
from typing import Annotated, Any

import anyio
from fastapi import FastAPI, HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations
from pydantic import AnyHttpUrl, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from cidia import __version__, xapi
from cidia.config import ajustes
from cidia.db import nueva_sesion
from cidia.modelos import (
    Aportacion,
    Consulta,
    Departamento,
    Ejecucion,
    Formacion,
    Instruccion,
    IntentoEval,
    Laguna,
    NivelIluo,
    Puesto,
    Tarea,
    ahora,
)
from cidia.seguridad import Actor, actor_desde_token, limitar_invitado
from cidia.vida import al_arrancar

log = logging.getLogger("cidia.mcp")

MAX_LECTURA_AGENTE = 20_000  # caracteres de un fichero que se devuelven al agente
MAX_FRAGMENTO = 1200  # caracteres de cada fragmento encontrado

INSTRUCCIONES = (
    "Herramientas de CidIA, el copiloto de conocimiento de la planta. Antes de responder sobre "
    "procedimientos, máquinas o problemas, usa buscar_conocimiento y cita las fuentes como [1], [2]. "
    "Si no hay respaldo, dilo con claridad y apunta la duda con registrar_laguna. Para ver una "
    "instrucción de trabajo paso a paso usa listar_tareas y ver_instruccion. Si la persona cuenta "
    "cómo resolvió un problema, propón guardarlo con proponer_aportacion. Para crear informes, tablas "
    "o documentos usa el espacio de trabajo (espacio_*): es la carpeta privada de la persona en el "
    "servidor y ella lo descarga desde la app. Todo respeta los permisos de la persona."
)


# --------------------------------------------------------------------------- autenticación


def _verificar(token: str) -> AccessToken | None:
    """Valida el JWT de CidIA contra la BD. None si no es válido (el SDK responde 401)."""
    try:
        with nueva_sesion() as bd:
            actor = actor_desde_token(bd, token)
            sesion_id = actor.sesion.id
            expira = int(actor.sesion.expira.timestamp())
            sujeto = str(actor.id) if actor.id else f"invitado:{sesion_id}"
            tipo = "invitado" if actor.es_invitado else "usuario"
    except HTTPException:
        return None
    except Exception:  # noqa: BLE001  (BD caída...: se rechaza sin romper el servidor)
        log.exception("No se pudo validar el token de MCP")
        return None
    return AccessToken(token=token, client_id="cidia", scopes=[tipo], expires_at=expira, subject=sujeto,
                       claims={"sid": sesion_id, "tipo": tipo})


class VerificadorCidia(TokenVerifier):
    """Verificador de tokens del SDK MCP con las sesiones de CidIA."""

    async def verify_token(self, token: str) -> AccessToken | None:
        return await anyio.to_thread.run_sync(_verificar, token)


@contextmanager
def _sesion(requiere_usuario: bool = True) -> Iterator[tuple[Session, Actor]]:
    """Sesión de BD y actor de la petición MCP en curso. Convierte los errores de los servicios
    (HTTPException) en errores de herramienta con el mismo mensaje en castellano, y cualquier
    otro fallo en un mensaje genérico (el detalle queda en el registro, nunca va al agente)."""
    token = get_access_token()
    if token is None:
        raise ToolError("Falta la sesión de CidIA. Vuelve a iniciar sesión en la app.")
    with nueva_sesion() as bd:
        try:
            actor = actor_desde_token(bd, token.token)
        except HTTPException as e:
            raise ToolError(str(e.detail)) from None
        if requiere_usuario and actor.es_invitado:
            raise ToolError("Esta herramienta necesita iniciar sesión en CidIA. Sin sesión solo se puede "
                            "buscar en la información pública.")
        try:
            yield bd, actor
        except ToolError:
            bd.rollback()
            raise
        except HTTPException as e:
            bd.rollback()
            raise ToolError(str(e.detail)) from None
        except Exception:
            bd.rollback()
            log.exception("Fallo en una herramienta MCP")
            raise ToolError("Algo ha fallado en el servidor de CidIA. Inténtalo de nuevo dentro de un rato "
                            "y, si sigue fallando, díselo a la persona.") from None


def _xapi(bd: Session, actor: Actor, verbo: str, tipo: str, objeto_id: Any = None, nombre: str | None = None,
          resultado: dict[str, Any] | None = None, **contexto: Any) -> None:
    xapi.registrar(bd, actor, verbo, tipo, objeto_id, nombre, resultado=resultado, contexto={"via": "mcp", **contexto})


# --------------------------------------------------------------------------- servidor y herramientas


def _url_publica() -> str:
    url = (ajustes().url_publica or "").rstrip("/")
    return url if re.match(r"^https?://[^/\s]+", url) else "http://localhost:8080"


mcp: MCPServer[Any] = MCPServer(
    "cidia",
    title="CidIA",
    instructions=INSTRUCCIONES,
    version=__version__,
    token_verifier=VerificadorCidia(),
    # Solo servidor de recursos: valida nuestro propio token. Sin URL de recurso no se anuncian
    # metadatos OAuth (CidIA no es un servidor de autorización OAuth).
    auth=AuthSettings(issuer_url=AnyHttpUrl(_url_publica()), resource_server_url=None),
)

_LECTURA = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_ESCRITURA = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)


@mcp.tool(title="Buscar en el conocimiento de la empresa", annotations=_LECTURA)
def buscar_conocimiento(
    consulta: Annotated[str, Field(description="Qué buscar, con las palabras del trabajo: máquina, pieza, código, problema.")],
    k: Annotated[int, Field(description="Cuántos fragmentos devolver, de 1 a 10.")] = 5,
) -> dict[str, Any]:
    """Busca en la documentación, las instrucciones de trabajo y las soluciones validadas que esta
    persona puede ver. Devuelve fragmentos numerados con su fuente. Cítalos en la respuesta como
    [1], [2]... Si no hay resultados, di que no consta en la documentación."""
    from cidia.servicios import consulta as srv

    texto = (consulta or "").strip()[:2000]
    if not texto:
        raise ToolError("Escribe qué quieres buscar.")
    with _sesion(requiere_usuario=False) as (bd, actor):
        limitar_invitado(bd, actor)
        encontrados = srv.buscar(bd, actor, texto, max(1, min(10, int(k or 5))))
        resultados = []
        for n, e in enumerate(encontrados, start=1):
            meta = e.metadatos or {}
            cita = f"[{n}] {e.titulo}"
            if meta.get("paso"):
                cita += f", paso {meta['paso']}"
            if meta.get("pagina"):
                cita += f", página {meta['pagina']}"
            fragmento = e.texto if len(e.texto) <= MAX_FRAGMENTO else e.texto[:MAX_FRAGMENTO].rsplit(" ", 1)[0] + "…"
            resultados.append({"n": n, "cita": cita, "titulo": e.titulo, "texto": fragmento,
                               "documento_id": e.documento_id})
        _xapi(bd, actor, "pregunto", "busqueda", None, texto[:300], resultado={"resultados": len(resultados)})
        bd.commit()
    if not resultados:
        return {"consulta": texto, "resultados": [],
                "aviso": "No hay nada en la documentación que esta persona puede ver. Dilo así y no inventes."}
    return {"consulta": texto, "resultados": resultados,
            "aviso": "Responde solo con estos fragmentos y cita cada dato con su número, por ejemplo [1]."}


def _tarea_dict(t: Tarea, ins: Instruccion | None, nivel: NivelIluo | None) -> dict[str, Any]:
    from cidia.servicios import iluo

    n = nivel.nivel if nivel else 0
    return {
        "id": t.id,
        "codigo": t.codigo,
        "nombre": t.nombre,
        "puesto": t.puesto.nombre if t.puesto else None,
        "departamento": t.puesto.departamento.nombre if t.puesto and t.puesto.departamento else None,
        "criticidad": {1: "baja", 2: "media", 3: "alta"}.get(t.criticidad, "media"),
        "instruccion": {"codigo": ins.codigo, "version": ins.version, "titulo": ins.titulo} if ins else None,
        "mi_nivel_iluo": iluo.nivel_letra(n) or "sin iniciar",
    }


@mcp.tool(title="Mis tareas", annotations=_LECTURA)
def listar_tareas() -> dict[str, Any]:
    """Lista las tareas que esta persona puede ejecutar (las de su puesto y departamento y las de
    sus formaciones activas), con su instrucción publicada si la tiene y su nivel ILUO."""
    from cidia.servicios import planta

    with _sesion() as (bd, actor):
        acceso = planta.acceso_tareas(bd, actor)
        if not acceso:
            return {"tareas": [], "aviso": "Esta persona no tiene tareas asignadas."}
        tareas = bd.scalars(select(Tarea).where(Tarea.id.in_(list(acceso))).order_by(Tarea.codigo, Tarea.nombre)).all()
        vigentes = planta.instrucciones_vigentes(bd, acceso.keys())
        niveles = planta.niveles(bd, actor.id, acceso.keys())
        return {"tareas": [_tarea_dict(t, vigentes.get(t.id), niveles.get(t.id)) for t in tareas]}


def _buscar_tarea(bd: Session, actor: Actor, texto: str) -> Tarea | None:
    """Tarea visible para el actor por id, código de tarea, código de instrucción o nombre."""
    from cidia.servicios import planta

    acceso = planta.acceso_tareas(bd, actor)
    if not acceso:
        return None
    visibles = bd.scalars(select(Tarea).where(Tarea.id.in_(list(acceso)))).all()
    t = texto.strip().lower()
    if t.isdigit():
        for v in visibles:
            if v.id == int(t):
                return v
    for v in visibles:
        if v.codigo and v.codigo.lower() == t:
            return v
    codigos = {i.tarea_id for i in bd.scalars(
        select(Instruccion).where(Instruccion.tarea_id.in_(list(acceso)), func.lower(Instruccion.codigo) == t)
    )}
    for v in visibles:
        if v.id in codigos:
            return v
    parecidas = [v for v in visibles if t and t in v.nombre.lower()]
    return parecidas[0] if len(parecidas) >= 1 else None


@mcp.tool(title="Ver una instrucción de trabajo", annotations=_LECTURA)
def ver_instruccion(
    tarea: Annotated[str, Field(description="Código de la tarea o de la instrucción (p. ej. IT-023), su número o parte de su nombre.")],
) -> dict[str, Any]:
    """Devuelve la instrucción de trabajo publicada de una tarea, paso a paso, con los pasos
    críticos y de seguridad marcados, los riesgos y los EPI. Solo de tareas que esta persona
    puede ejecutar. Usa listar_tareas si no sabes el código."""
    from cidia.servicios import planta

    with _sesion() as (bd, actor):
        t = _buscar_tarea(bd, actor, tarea or "")
        if t is None:
            raise ToolError("No encuentro esa tarea entre las que puedes consultar. Usa listar_tareas para ver los códigos.")
        ins = planta.instruccion_vigente(bd, t.id)
        if ins is None:
            raise ToolError(f"La tarea «{t.nombre}» aún no tiene una instrucción publicada.")
        pasos = [{
            "n": i,
            "titulo": p.titulo,
            "texto": p.texto or "",
            "critico": p.es_critico,
            "seguridad": p.es_seguridad,
            "criterio_aceptacion": p.criterio_aceptacion,
        } for i, p in enumerate(ins.pasos, start=1)]
        _xapi(bd, actor, "vio", "instruccion", ins.id, ins.titulo, tarea_id=t.id)
        bd.commit()
        return {
            "tarea": t.nombre, "codigo_tarea": t.codigo, "codigo": ins.codigo, "version": ins.version,
            "titulo": ins.titulo, "resumen": ins.resumen, "riesgos": ins.riesgos or t.riesgos_prl,
            "epis": ins.epis, "herramientas": ins.herramientas, "pasos": pasos,
            "aviso": "Los pasos marcados como críticos o de seguridad no se pueden saltar.",
        }


@mcp.tool(title="Apuntar una duda sin respuesta", annotations=_ESCRITURA)
def registrar_laguna(
    pregunta: Annotated[str, Field(description="La pregunta que la documentación no responde, tal y como la haría un compañero.")],
) -> dict[str, Any]:
    """Apunta una pregunta que la documentación no responde para que los expertos del
    departamento la completen. Úsala cuando buscar_conocimiento no encuentre respaldo."""
    from cidia.servicios import lagunas

    texto = (pregunta or "").strip()
    if len(texto) < 5:
        raise ToolError("Escribe la pregunta completa.")
    with _sesion() as (bd, actor):
        lg = lagunas.registrar(bd, texto[:2000], actor.departamento_id)
        if lg is None:  # servicio provisional: se guarda tal cual
            lg = Laguna(pregunta=texto[:2000], departamento_id=actor.departamento_id, ejemplos=[texto[:2000]])
            bd.add(lg)
            bd.flush()
        _xapi(bd, actor, "senalo", "laguna", lg.id, texto[:300])
        bd.commit()
        return {"laguna_id": lg.id, "veces_preguntada": lg.frecuencia,
                "mensaje": "Pregunta apuntada. La verán los expertos y el jefe del departamento."}


def _procesar_propuesta(bd: Session, progreso: Any, aportacion_id: int, campos: dict[str, str]) -> dict[str, Any]:
    """Trabajo en segundo plano: el mismo procesado que una aportación escrita (título, etiquetas,
    nivel sugerido), conservando el problema, la causa y la solución que dio la persona."""
    from cidia.servicios import aportaciones

    resultado = aportaciones.procesar_trabajo(bd, progreso, aportacion_id) or {}
    ap = bd.get(Aportacion, aportacion_id)
    if ap is not None and ap.estado == "pendiente":
        for clave, valor in campos.items():
            if valor:
                setattr(ap, clave, valor)
        if not resultado.get("ordenada_por_ia") or not ap.titulo:  # sin ayuda del modelo: título propio
            ap.titulo = aportaciones.primera_frase(campos.get("problema") or campos.get("solucion") or "")
    return resultado


@mcp.tool(title="Proponer una aportación", annotations=_ESCRITURA)
def proponer_aportacion(
    problema: Annotated[str, Field(description="Qué pasaba, en una o dos frases.")],
    causa: Annotated[str, Field(description="Por qué pasaba. Vacío si no se sabe.")],
    solucion: Annotated[str, Field(description="Qué hay que hacer para resolverlo. Varios pasos, uno por línea.")],
) -> dict[str, Any]:
    """Guarda como aportación algo que esta persona ha resuelto (problema, causa y solución) para
    que su jefe lo valide y pase a ser conocimiento de la empresa. Pide confirmación a la persona
    antes de usarla y no inventes nada que no haya contado."""
    campos = {"problema": (problema or "").strip()[:4000], "causa": (causa or "").strip()[:4000],
              "solucion": (solucion or "").strip()[:4000]}
    if len(campos["problema"]) < 5 or len(campos["solucion"]) < 5:
        raise ToolError("Hacen falta al menos el problema y la solución.")
    with _sesion() as (bd, actor):
        texto = (f"Problema: {campos['problema']}\nCausa: {campos['causa'] or 'no se indica'}\n"
                 f"Solución: {campos['solucion']}")
        try:
            from cidia.servicios import aportaciones

            procesar = aportaciones.procesar_trabajo
            titulo = aportaciones.primera_frase(campos["problema"])
        except (ImportError, AttributeError):
            procesar, titulo = None, campos["problema"][:120]
        ap = Aportacion(
            autor_id=actor.id, departamento_id=actor.departamento_id, texto_original=texto, titulo=titulo[:300],
            problema=campos["problema"], causa=campos["causa"] or None, solucion=campos["solucion"],
            etiquetas=[], nivel_minimo=1, estado="procesando" if procesar else "pendiente",
        )
        bd.add(ap)
        bd.flush()
        _xapi(bd, actor, "aporto", "aportacion", ap.id, titulo[:300], estado="enviada")
        bd.commit()
        ap_id, autor_id = ap.id, actor.id
    if procesar is not None:
        from cidia import trabajos

        trabajos.encolar("procesar_aportacion", _procesar_propuesta, ap_id, campos, entidad="aportacion",
                         entidad_id=ap_id, usuario_id=autor_id)
    return {"aportacion_id": ap_id, "estado": "pendiente de validar",
            "mensaje": "Aportación enviada. Su jefe la revisará y, si la valida, la usará el copiloto."}


@mcp.tool(title="Mi progreso", annotations=_LECTURA)
def mi_progreso() -> dict[str, Any]:
    """Resumen del progreso de esta persona: nivel ILUO en cada tarea, ejecuciones completadas,
    cuestionarios aprobados, aportaciones y formaciones activas."""
    from cidia.servicios import iluo

    with _sesion() as (bd, actor):
        uid = actor.id
        filas = bd.execute(
            select(NivelIluo, Tarea).join(Tarea, Tarea.id == NivelIluo.tarea_id)
            .where(NivelIluo.usuario_id == uid).order_by(Tarea.codigo, Tarea.nombre)
        ).all()
        momento = ahora()
        tareas = [{
            "tarea": t.nombre, "codigo": t.codigo, "nivel": iluo.nivel_letra(n.nivel) or "sin iniciar",
            "significa": iluo.nivel_nombre(n.nivel) if hasattr(iluo, "nivel_nombre") else None,
            "caduca": n.caduca.date().isoformat() if n.caduca else None,
            "caducado": bool(n.caduca and n.caduca < momento),
            "requiere_reevaluacion": n.requiere_reevaluacion,
        } for n, t in filas]
        completadas = bd.scalar(select(func.count()).select_from(Ejecucion)
                                .where(Ejecucion.usuario_id == uid, Ejecucion.estado == "completada")) or 0
        aprobados = bd.scalar(select(func.count()).select_from(IntentoEval)
                              .where(IntentoEval.usuario_id == uid, IntentoEval.aprobado.is_(True))) or 0
        aportes = dict(bd.execute(select(Aportacion.estado, func.count()).where(Aportacion.autor_id == uid)
                                  .group_by(Aportacion.estado)).all())
        formaciones = bd.scalars(select(Departamento.nombre).join(Formacion, Formacion.departamento_id == Departamento.id)
                                 .where(Formacion.usuario_id == uid, Formacion.estado == "activa")).all()
        consultas = bd.scalar(select(func.count()).select_from(Consulta).where(
            Consulta.usuario_id == uid, Consulta.creada >= momento - timedelta(days=30))) or 0
        puesto = bd.get(Puesto, actor.usuario.puesto_id) if actor.usuario and actor.usuario.puesto_id else None
        return {
            "nombre": actor.nombre,
            "puesto": puesto.nombre if puesto else None,
            "tareas": tareas,
            "ejecuciones_completadas": completadas,
            "cuestionarios_aprobados": aprobados,
            "aportaciones": {"validadas": aportes.get("validada", 0),
                             "pendientes": aportes.get("pendiente", 0) + aportes.get("procesando", 0),
                             "rechazadas": aportes.get("rechazada", 0)},
            "formaciones_activas": list(formaciones),
            "consultas_ultimos_30_dias": consultas,
        }


# --------------------------------------------------------------------------- espacio de trabajo


def _ruta_agente(ruta: str | None) -> str:
    """Ruta que da el agente, relativa a su carpeta. Quita espacios y saltos de línea sueltos y
    acepta «/trabajo/...», que es como ve la carpeta desde espacio_ejecutar."""
    texto = (ruta or "").strip()
    if texto == "/trabajo" or texto.startswith("/trabajo/"):
        texto = texto[len("/trabajo"):].lstrip("/")
    return texto


@mcp.tool(title="Ver la carpeta de trabajo", annotations=_LECTURA)
def espacio_listar(
    ruta: Annotated[str, Field(description="Carpeta a listar, relativa a la carpeta de trabajo. Vacío para la principal.")] = "",
) -> dict[str, Any]:
    """Lista los ficheros y carpetas de la carpeta de trabajo de esta persona en el servidor
    (solo ella la ve). Las rutas son siempre relativas, por ejemplo informes/marzo."""
    from cidia.servicios import espacio

    with _sesion() as (bd, actor):
        return espacio.listar_carpeta(actor, _ruta_agente(ruta))


@mcp.tool(title="Leer un fichero de trabajo", annotations=_LECTURA)
def espacio_leer(
    ruta: Annotated[str, Field(description="Ruta del fichero, relativa a la carpeta de trabajo (p. ej. informes/resumen.md).")],
) -> dict[str, Any]:
    """Lee un fichero de texto de la carpeta de trabajo de esta persona (Markdown, CSV, código...).
    Si es muy largo, devuelve el principio y lo indica."""
    from cidia.servicios import espacio

    with _sesion() as (bd, actor):
        datos = espacio.leer(actor, _ruta_agente(ruta), limite=MAX_LECTURA_AGENTE * 4)
        if not datos["es_texto"]:
            return {"ruta": datos["ruta"], "tamano": datos["tamano"], "contenido": None,
                    "aviso": "No es un fichero de texto. La persona puede descargarlo desde la app."}
        contenido = datos["contenido"] or ""
        truncado = datos["truncado"] or len(contenido) > MAX_LECTURA_AGENTE
        return {"ruta": datos["ruta"], "tamano": datos["tamano"], "contenido": contenido[:MAX_LECTURA_AGENTE],
                "truncado": truncado}


@mcp.tool(title="Guardar un fichero de trabajo", annotations=_ESCRITURA)
def espacio_escribir(
    ruta: Annotated[str, Field(description="Ruta del fichero, relativa a la carpeta de trabajo (p. ej. informes/resumen.md).")],
    contenido: Annotated[str, Field(description="Texto completo del fichero.")],
) -> dict[str, Any]:
    """Crea o sustituye un fichero de texto en la carpeta de trabajo de esta persona (crea las
    carpetas que falten). Úsalo para informes en Markdown, tablas CSV, scripts... La persona lo
    verá y lo podrá descargar en la sección «Espacio de trabajo» de la app."""
    from cidia.servicios import espacio

    with _sesion() as (bd, actor):
        datos = espacio.escribir(actor, _ruta_agente(ruta), contenido)
        espacio.registrar(bd, actor, "guardo", datos["ruta"], via="mcp", resultado={"tamano": datos["tamano"]})
        bd.commit()
        return {"ruta": datos["ruta"], "tamano": datos["tamano"],
                "mensaje": "Guardado. La persona lo encontrará en «Espacio de trabajo»."}


@mcp.tool(title="Ejecutar una orden en el espacio de trabajo",
          annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False))
def espacio_ejecutar(
    orden: Annotated[str, Field(description="Orden de bash. Se ejecuta en la carpeta de trabajo (/trabajo). Ejemplo: python3 grafico.py")],
) -> dict[str, Any]:
    """Ejecuta una orden de bash en un contenedor aislado del servidor, sin red y con la carpeta
    de trabajo de esta persona en /trabajo (máximo 2 minutos). Tiene Python 3 con pandas,
    openpyxl, python-docx, matplotlib y reportlab para crear tablas, gráficos, Word y PDF.
    Devuelve el código de salida y lo que escribió la orden."""
    from cidia.servicios import espacio

    with _sesion() as (bd, actor):
        res = espacio.ejecutar(actor, orden, espacio.TIEMPO_MAX)
        espacio.registrar(bd, actor, "ejecuto", None, via="mcp", resultado={
            "codigo": res["codigo"], "duracion": res["duracion"], "orden": (orden or "")[:500]})
        bd.commit()
        avisos = []
        if res["tiempo_agotado"]:
            avisos.append("Se detuvo por superar el tiempo máximo.")
        if res["memoria_agotada"]:
            avisos.append("Se detuvo por falta de memoria.")
        if res["cuota_superada"]:
            avisos.append("Se detuvo porque la carpeta llegó a su límite de espacio.")
        if res["recortada"]:
            avisos.append("La salida era muy larga y se ha recortado.")
        return {"codigo_salida": res["codigo"], "salida": res["salida"], "duracion_s": round(res["duracion"], 1),
                "avisos": avisos}


# --------------------------------------------------------------------------- montaje en FastAPI


def _seguridad_transporte() -> TransportSecuritySettings:
    """Protección de Host según CIDIA_MCP_HOSTS (ver la cabecera del módulo)."""
    valor = os.environ.get("CIDIA_MCP_HOSTS", "*").strip()
    if valor in ("", "*"):
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    hosts: list[str] = []
    for h in (x.strip() for x in valor.split(",")):
        if not h:
            continue
        hosts.append(h)
        sin_puerto = not re.search(r":(\d+|\*)$", h)
        if sin_puerto:
            hosts.append(f"{h}:*")
    origenes = [o.strip() for o in os.environ.get("CIDIA_MCP_ORIGENES", "").split(",") if o.strip()]
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts,
                                     allowed_origins=origenes)


def _construir() -> Any:
    """Sub-app Starlette del transporte (crea también un gestor de sesiones nuevo)."""
    return mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=_seguridad_transporte(),
    )


class _PuertaMcp:
    """Aplicación ASGI de la ruta /mcp: delega en la sub-app vigente del SDK."""

    def __init__(self) -> None:
        self.app = _construir()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)

    @asynccontextmanager
    async def vida(self) -> AsyncIterator[None]:
        # Un gestor de sesiones solo arranca una vez: en cada arranque de la app se construye
        # la sub-app de nuevo (con su gestor y con la configuración de hosts vigente).
        self.app = _construir()
        async with mcp.session_manager.run():
            yield


def montar(app: FastAPI) -> None:
    """Añade POST /mcp a la app y registra el arranque del gestor del transporte."""
    puerta = _PuertaMcp()
    app.router.routes.append(Route("/mcp", endpoint=puerta, include_in_schema=False))
    al_arrancar(puerta.vida)
    log.info("Servidor MCP montado en /mcp")
