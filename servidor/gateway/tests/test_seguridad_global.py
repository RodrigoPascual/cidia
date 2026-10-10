"""Auditoría global de autorización y fugas de datos: TODAS las rutas de la app.

Batería parametrizada (con su propia base de datos: CIDIA_TEST_BD=e2e, nunca cidia_qa):

1. Inventario. Cada ruta de `app.routes` tiene declarado su nivel de acceso en ACCESO. Una ruta
   nueva sin declarar hace fallar la batería: hay que decidir quién puede usarla.
2. Autenticación y rol. Cada ruta se llama sin sesión, con sesión de invitado, con un empleado
   que no es experto (pedro), con una experta que no es jefa (carmen) y con un jefe (javier).
   Quien no llega al nivel recibe 401 o 403 antes de que se ejecute nada.
3. Robustez. Cada ruta, con la administración y con identificadores que no existen o fuera de
   rango, responde sin errores 500.
4. IDOR. Los objetos de una persona o de un departamento pedidos por otra persona (empleado de
   otro departamento, compañero sin permiso, jefe o experta de otro departamento, invitado)
   responden 403 o 404, y el objeto no cambia.
5. Fugas. Ninguna respuesta lleva hashes de contraseñas, el secreto de las firmas, rutas
   absolutas del servidor ni la respuesta correcta del cuestionario; los documentos sin permiso
   no aparecen ni en listas ni en búsquedas.
6. Ficheros: tipos peligrosos, recorridos de ruta, firmas manipuladas y límites de tamaño.
   Búsquedas con caracteres de SQL, de LIKE y de tsquery.
7. /v1 (compatible con OpenAI) y /mcp con tokens de invitado y de usuario.

Personas (tests/fabrica.py): ana (jefa y experta de Oficina técnica, nivel 3), luis (Oficina
técnica, nivel 1), marta (Producción, nivel 2, se forma en Oficina técnica), pedro (Producción,
nivel 1), javier (jefe de Producción), carmen (experta de Producción) y admin.
"""

from __future__ import annotations

import io
import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
import pytest
from conftest import IAFalsa
from fabrica import CONTRASENA, Planta, crear_planta
from fastapi.routing import APIRoute
from sqlalchemy import select
from starlette.routing import Route

from cidia import trabajos
from cidia.config import ajustes
from cidia.db import nueva_sesion
from cidia.ia import asr, llm
from cidia.modelos import (
    Aportacion,
    Captura,
    Consulta,
    Documento,
    Ejecucion,
    Instruccion,
    Laguna,
    Memoria,
    Microleccion,
    NivelIluo,
    Paso,
    PreguntaEval,
    Sesion,
    Tarea,
    Trabajo,
    Usuario,
    ahora,
)
from cidia.rutas import openai as rutas_openai
from cidia.seguridad import Actor, url_fichero
from cidia.servicios import documentos, espacio

# --------------------------------------------------------------------------- nivel de cada ruta
#
# publico: sin sesión · firma: URL firmada y caducable · sesion: también invitados ·
# usuario: sesión de empleado · experto: es_experto, jefe o admin · jefe: jefe o admin · admin.

ACCESO: dict[str, str] = {
    # web, documentación y salud
    "GET /": "publico", "GET /app": "publico", "GET /app/{ruta:path}": "publico",
    "GET /salud": "publico", "GET /api/sistema/info": "publico",
    "GET /api/openapi.json": "publico", "GET /api/docs": "publico", "GET /docs/oauth2-redirect": "publico",
    "GET /api/sistema/estado": "admin", "GET /api/trabajos/{trabajo_id}": "sesion",
    # sesión
    "POST /api/auth/login": "publico", "POST /api/auth/invitado": "publico",
    "GET /api/auth/yo": "sesion", "POST /api/auth/salir": "sesion", "POST /api/auth/contrasena": "usuario",
    # ficheros con URL firmada
    "GET /api/ficheros/{ruta:path}": "firma", "GET /api/espacio/descarga/{rel:path}": "firma",
    # copiloto
    "POST /api/consulta": "sesion", "POST /api/consulta/simple": "sesion",
    "POST /api/consulta/{consulta_id}/valoracion": "sesion", "GET /api/consulta/historial": "usuario",
    "POST /api/voz/transcribir": "usuario",
    "GET /api/memoria": "usuario", "PUT /api/memoria": "usuario", "POST /api/memoria": "usuario",
    "DELETE /api/memoria": "usuario", "DELETE /api/memoria/{memoria_id}": "usuario",
    "GET /api/inicio": "usuario", "GET /api/inicio/contadores": "usuario",
    # espacio de trabajo
    "GET /api/espacio": "usuario", "GET /api/espacio/fichero": "usuario", "PUT /api/espacio/fichero": "usuario",
    "DELETE /api/espacio/fichero": "usuario", "POST /api/espacio/subir": "usuario",
    "POST /api/espacio/mover": "usuario", "POST /api/espacio/carpeta": "usuario",
    "GET /api/espacio/ejecutor": "usuario", "POST /api/espacio/ejecutar": "usuario",
    # modo planta
    "GET /api/planta/tareas": "usuario", "POST /api/planta/ejecuciones": "usuario",
    "GET /api/planta/ejecuciones/{ejecucion_id}": "usuario",
    "POST /api/planta/ejecuciones/{ejecucion_id}/pasos/{paso_id}/confirmar": "usuario",
    "POST /api/planta/ejecuciones/{ejecucion_id}/preguntar": "usuario",
    "POST /api/planta/ejecuciones/{ejecucion_id}/foto": "usuario",
    "POST /api/planta/ejecuciones/{ejecucion_id}/finalizar": "usuario",
    "POST /api/planta/ejecuciones/{ejecucion_id}/abandonar": "usuario",
    # formación
    "GET /api/formacion/itinerario": "usuario", "GET /api/formacion/tareas/{tarea_id}": "usuario",
    "POST /api/formacion/microlecciones/{microleccion_id}/vista": "usuario",
    "POST /api/formacion/microlecciones/{microleccion_id}/responder": "usuario",
    "POST /api/formacion/tareas/{tarea_id}/generar": "experto",
    # evaluación
    "GET /api/evaluacion/pendientes": "usuario",
    "GET /api/evaluacion/preguntas": "experto", "POST /api/evaluacion/preguntas": "experto",
    "PUT /api/evaluacion/preguntas/{pregunta_id}": "experto",
    "DELETE /api/evaluacion/preguntas/{pregunta_id}": "experto",
    "POST /api/evaluacion/instrucciones/{instruccion_id}/generar-preguntas": "experto",
    "GET /api/evaluacion/cuestionario/{tarea_id}": "usuario",
    "POST /api/evaluacion/cuestionario/{tarea_id}/responder": "usuario",
    "GET /api/evaluacion/observacion/plantilla": "jefe", "POST /api/evaluacion/observaciones": "jefe",
    # aportaciones
    "POST /api/aportaciones": "usuario", "GET /api/aportaciones/mias": "usuario",
    "GET /api/aportaciones/opciones": "usuario", "GET /api/aportaciones/{aportacion_id}": "usuario",
    "DELETE /api/aportaciones/{aportacion_id}": "usuario",
    "GET /api/aportaciones/pendientes": "jefe", "GET /api/aportaciones/resumen": "jefe",
    "PUT /api/aportaciones/{aportacion_id}": "jefe", "POST /api/aportaciones/{aportacion_id}/validar": "jefe",
    "POST /api/aportaciones/{aportacion_id}/rechazar": "jefe",
    # captura
    "GET /api/captura": "experto", "POST /api/captura": "experto", "POST /api/captura/video": "experto",
    "POST /api/captura/audio": "experto", "POST /api/captura/entrevista": "experto",
    "GET /api/captura/{captura_id}": "experto", "DELETE /api/captura/{captura_id}": "experto",
    "POST /api/captura/{captura_id}/reintentar": "experto",
    "POST /api/captura/{captura_id}/entrevista/responder": "experto",
    "POST /api/captura/{captura_id}/entrevista/responder-audio": "experto",
    "POST /api/captura/{captura_id}/entrevista/finalizar": "experto",
    "PUT /api/captura/{captura_id}/ficha": "experto", "POST /api/captura/{captura_id}/ficha/publicar": "experto",
    # instrucciones
    "GET /api/instrucciones": "experto", "POST /api/instrucciones": "experto",
    "GET /api/instrucciones/tareas": "experto", "GET /api/instrucciones/{instruccion_id}": "experto",
    "PUT /api/instrucciones/{instruccion_id}": "experto", "DELETE /api/instrucciones/{instruccion_id}": "experto",
    "POST /api/instrucciones/{instruccion_id}/publicar": "experto",
    "POST /api/instrucciones/{instruccion_id}/nueva-version": "experto",
    "GET /api/instrucciones/{instruccion_id}/versiones": "experto",
    "GET /api/instrucciones/{instruccion_id}/diferencias": "experto",
    "POST /api/instrucciones/{instruccion_id}/pasos/{paso_id}/imagen": "experto",
    # lagunas
    "GET /api/lagunas": "jefe", "GET /api/lagunas/abiertas-de-mi-departamento": "usuario",
    "POST /api/lagunas/{laguna_id}/descartar": "jefe", "POST /api/lagunas/{laguna_id}/reabrir": "jefe",
    # progreso
    "GET /api/progreso/yo": "usuario", "GET /api/progreso/persona/{usuario_id}": "usuario",
    "GET /api/progreso/equipo": "jefe", "GET /api/progreso/planta": "admin",
    "GET /api/progreso/iluo/{usuario_id}/{tarea_id}": "usuario",
    "POST /api/progreso/iluo/{usuario_id}/{tarea_id}/formador": "usuario",
    "PUT /api/progreso/iluo/{usuario_id}/{tarea_id}": "jefe",
    # documentos (consola de conocimiento)
    "GET /api/documentos": "jefe", "POST /api/documentos": "jefe", "GET /api/documentos/opciones": "jefe",
    "POST /api/documentos/probar-busqueda": "jefe", "GET /api/documentos/{documento_id}": "jefe",
    "PATCH /api/documentos/{documento_id}": "jefe", "DELETE /api/documentos/{documento_id}": "jefe",
    "GET /api/documentos/{documento_id}/descarga": "jefe", "POST /api/documentos/{documento_id}/reindexar": "jefe",
    # administración (los jefes solo leen las personas de su departamento)
    "GET /api/admin/empleados": "jefe", "GET /api/admin/empleados/{usuario_id}": "jefe",
    "GET /api/admin/empleados/{usuario_id}/formaciones": "jefe",
    "POST /api/admin/empleados": "admin", "PUT /api/admin/empleados/{usuario_id}": "admin",
    "POST /api/admin/empleados/{usuario_id}/activar": "admin",
    "POST /api/admin/empleados/{usuario_id}/desactivar": "admin",
    "POST /api/admin/empleados/{usuario_id}/contrasena": "admin",
    "POST /api/admin/empleados/{usuario_id}/formaciones": "admin",
    "POST /api/admin/formaciones/{formacion_id}/completar": "admin",
    "POST /api/admin/formaciones/{formacion_id}/cancelar": "admin",
    "GET /api/admin/organizacion": "admin", "GET /api/admin/empresa": "admin", "PUT /api/admin/empresa": "admin",
    "POST /api/admin/departamentos": "admin", "PUT /api/admin/departamentos/{dep_id}": "admin",
    "DELETE /api/admin/departamentos/{dep_id}": "admin",
    "GET /api/admin/niveles": "admin", "POST /api/admin/niveles": "admin", "PUT /api/admin/niveles/orden": "admin",
    "PUT /api/admin/niveles/{nivel_id}": "admin", "DELETE /api/admin/niveles/{nivel_id}": "admin",
    "POST /api/admin/puestos": "admin", "PUT /api/admin/puestos/{puesto_id}": "admin",
    "DELETE /api/admin/puestos/{puesto_id}": "admin",
    "POST /api/admin/tareas": "admin", "PUT /api/admin/tareas/{tarea_id}": "admin",
    "DELETE /api/admin/tareas/{tarea_id}": "admin",
    "GET /api/admin/modelos": "admin", "POST /api/admin/modelos": "admin",
    "PUT /api/admin/modelos/{modelo_id}": "admin", "DELETE /api/admin/modelos/{modelo_id}": "admin",
    "GET /api/admin/xapi": "admin", "GET /api/admin/xapi/exportar": "admin", "GET /api/admin/auditoria": "admin",
    # agente de la app
    "GET /v1/models": "sesion", "POST /v1/chat/completions": "sesion",
    "POST /mcp": "sesion",
}

ORDEN = {"publico": 0, "firma": 0, "sesion": 1, "usuario": 2, "experto": 3, "jefe": 4, "admin": 5}
# Persona de la matriz → nivel más alto que alcanza (0 = sin sesión).
MATRIZ = {"anonimo": 0, "invitado": 1, "pedro": 2, "carmen": 3, "javier": 4}
SIN_ID = 987_654_321  # identificador que no existe (pero cabe en un INTEGER)
FUERA_DE_RANGO = 2**40  # no cabe en un INTEGER de PostgreSQL: no debe dar un 500

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6364f8ffbf1e000502027f3d0c2bb20000000049454e44ae426082"
)
ACEPTA_MCP = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rutas_de(app) -> set[str]:
    """«MÉTODO /ruta» de todas las rutas de la app, también las de los routers incluidos."""
    salida: set[str] = set()

    def recorrer(rutas: list[Any]) -> None:
        for r in rutas:
            if isinstance(r, APIRoute):
                salida.update(f"{m} {r.path}" for m in r.methods - {"HEAD", "OPTIONS"})
            elif hasattr(r, "original_router"):  # FastAPI ≥ 0.140 guarda los routers incluidos así
                recorrer(r.original_router.routes)
            elif hasattr(r, "routes") and not isinstance(r, Route):
                recorrer(r.routes)
            elif isinstance(r, Route):
                if r.path == "/mcp":
                    salida.add("POST /mcp")
                else:
                    salida.update(f"{m} {r.path}" for m in (r.methods or {"GET"}) - {"HEAD", "OPTIONS"})

    recorrer(app.routes)
    return salida


def _rellenar(ruta: str, valor: Any = 1) -> str:
    ruta = re.sub(r"\{\w+:path\}", "x", ruta)
    return re.sub(r"\{\w+\}", str(valor), ruta)


# --------------------------------------------------------------------------- escenario


@dataclass
class Escenario:
    p: Planta
    tarea: Tarea  # Producción, nivel 1, instrucción publicada
    ins: Instruccion
    tarea_ot3: Tarea  # Oficina técnica, nivel mínimo 3: luis no la puede abrir
    ins_ot3: Instruccion
    borrador: Instruccion  # borrador de Producción (de carmen)
    pregunta: PreguntaEval
    micro: Microleccion
    doc_prod: Documento
    doc_ot3: Documento
    doc_publico: Documento
    ejecucion_id: int
    consulta_id: int
    memoria_id: int
    aportacion_id: int
    laguna_id: int
    captura_id: int
    trabajo_id: int
    fichero_espacio: str  # fichero de pedro en su espacio de trabajo


def _ia_falsa(mp: pytest.MonkeyPatch) -> None:
    falsa = IAFalsa()
    for nombre in ("chat", "chat_json", "chat_stream", "embeddings"):
        mp.setattr(llm, nombre, getattr(falsa, nombre))
    mp.setattr(llm, "modelo_vision", lambda bd=None: "vision-falso")
    mp.setattr(asr, "transcribir", falsa.transcribir)


def _instruccion(bd, tarea: Tarea, estado: str = "publicada", autor: Usuario | None = None) -> Instruccion:
    ins = Instruccion(tarea_id=tarea.id, codigo=tarea.codigo, version=1, estado=estado, titulo=f"Instrucción {tarea.codigo}",
                      resumen="Montaje de prueba.", autor_id=autor.id if autor else None,
                      publicada_en=ahora() if estado == "publicada" else None)
    bd.add(ins)
    bd.flush()
    for i, (titulo, critico) in enumerate((("Preparar la brida", False), ("Apretar en cruz a 25 N·m", True),
                                           ("Comprobar el montaje", False)), start=1):
        bd.add(Paso(instruccion_id=ins.id, orden=i, titulo=titulo, texto=f"Texto del paso {i}.", es_critico=critico,
                    criterio_aceptacion="Par correcto." if critico else None))
    bd.commit()
    bd.refresh(ins)
    return ins


def _tarea(bd, p: Planta, dep: str, nivel: int = 1) -> Tarea:
    codigo = "S-" + uuid.uuid4().hex[:6].upper()
    t = Tarea(puesto_id=p.puestos[dep].id, codigo=codigo, nombre=f"Tarea de seguridad {codigo}", criticidad=3,
              nivel_minimo=nivel)
    bd.add(t)
    bd.commit()
    return t


def _doc(bd, titulo: str, texto: str, dep: Any, nivel: int = 1, publico: bool = False) -> Documento:
    return documentos.crear_desde_texto(bd, titulo, texto, departamento_id=dep.id if dep else None,
                                        nivel_minimo=nivel, es_formacion=False, es_publico=publico,
                                        en_segundo_plano=False)


@pytest.fixture(scope="module")
def c(app):
    """Un solo cliente para todo el módulo (la batería hace cientos de peticiones)."""
    from fastapi.testclient import TestClient

    with TestClient(app) as cliente:
        yield cliente


@pytest.fixture(scope="module")
def tokens(c, esc) -> dict[str, dict[str, str]]:
    salida: dict[str, dict[str, str]] = {"anonimo": {}}
    salida["invitado"] = {"Authorization": f"Bearer {c.post('/api/auth/invitado').json()['token']}"}
    for u in ("ana", "luis", "marta", "pedro", "javier", "carmen", "admin"):
        r = c.post("/api/auth/login", json={"usuario": u, "contrasena": CONTRASENA})
        assert r.status_code == 200, r.text
        salida[u] = {"Authorization": f"Bearer {r.json()['token']}"}
    return salida


@pytest.fixture(scope="module")
def esc(app) -> Escenario:
    """Datos de una planta con objetos de cada persona y de cada departamento."""
    trabajos.modo_sincrono(True)
    with pytest.MonkeyPatch.context() as mp, nueva_sesion() as bd:
        _ia_falsa(mp)
        p = crear_planta(bd)
        per = p.personas
        tarea = _tarea(bd, p, "prod")
        ins = _instruccion(bd, tarea, autor=per["carmen"])
        tarea_ot3 = _tarea(bd, p, "ot", nivel=3)
        ins_ot3 = _instruccion(bd, tarea_ot3, autor=per["ana"])
        borrador = _instruccion(bd, _tarea(bd, p, "prod"), estado="borrador", autor=per["carmen"])
        pregunta = PreguntaEval(instruccion_id=ins.id, paso_id=ins.pasos[1].id, enunciado="¿A qué par se aprieta?",
                                opciones=["10 N·m", "25 N·m", "50 N·m"], correcta=1, explicacion="25 N·m.",
                                estado="aprobada")
        micro = Microleccion(instruccion_id=ins.id, orden=1, titulo="El par de apriete", contenido="25 N·m en cruz.",
                             pregunta={"enunciado": "¿Par?", "opciones": ["10", "25", "50"], "correcta": 1,
                                       "explicacion": "25."})
        bd.add_all([pregunta, micro])
        doc_prod = _doc(bd, "Manual de la prensa de Producción", "La prensa de Producción se engrasa cada semana.",
                        p.deps["prod"])
        doc_ot3 = _doc(bd, "Costes secretos de utillaje", "El utillaje de soldadura cuesta 3.000 euros y lo aprueba "
                       "la dirección.", p.deps["ot"], nivel=3)
        doc_publico = _doc(bd, "Bienvenida pública", "Bienvenida a la planta y normas de prevención.", None,
                           publico=True)
        ej = Ejecucion(usuario_id=per["pedro"].id, tarea_id=tarea.id, instruccion_id=ins.id, estado="en_curso",
                       inicio=ahora())
        cons = Consulta(usuario_id=per["pedro"].id, pregunta="¿Cada cuánto se engrasa la prensa?", respuesta="Cada "
                        "semana [1].", modo="normal", fuentes=[{"n": 1, "documento_id": doc_prod.id,
                                                                "titulo": doc_prod.titulo}], con_respaldo=True)
        mem = Memoria(usuario_id=per["pedro"].id, contenido="Trabajo en el turno de noche.", origen="manual")
        ap = Aportacion(autor_id=per["pedro"].id, departamento_id=p.deps["prod"].id, texto_original="La prensa se "
                        "atasca: limpiar el sensor.", titulo="Atasco de la prensa", problema="Se atasca.",
                        solucion="Limpiar el sensor.", etiquetas=[], nivel_minimo=1, estado="pendiente")
        lag = Laguna(pregunta="¿Qué presión lleva el cilindro?", departamento_id=p.deps["prod"].id, frecuencia=3,
                     ejemplos=["¿Qué presión lleva el cilindro?"])
        cap = Captura(tipo="entrevista", autor_id=per["carmen"].id, tarea_id=tarea.id, titulo="Entrevista de carmen",
                      estado="en_curso", fase="conversando", conversacion=[
                          {"rol": "copiloto", "texto": "¿Qué herramientas usas?", "tema": "herramientas"}])
        bd.add_all([ej, cons, mem, ap, lag, cap])
        bd.flush()
        trab = Trabajo(tipo="microlecciones", estado="error", mensaje="Fallo interno en http://10.0.0.9:11434",
                       entidad="instruccion", entidad_id=ins.id, usuario_id=per["carmen"].id,
                       resultado={"microlecciones": 3})
        bd.add(trab)
        bd.add(NivelIluo(usuario_id=per["pedro"].id, tarea_id=tarea.id, nivel=1, desde=ahora()))
        bd.commit()
        pedro = Actor(sesion=None, usuario=per["pedro"])  # type: ignore[arg-type]
        espacio.escribir(pedro, "informes/privado.md", "# Informe privado de Pedro\n")
        return Escenario(p=p, tarea=tarea, ins=ins, tarea_ot3=tarea_ot3, ins_ot3=ins_ot3, borrador=borrador,
                         pregunta=pregunta, micro=micro, doc_prod=doc_prod, doc_ot3=doc_ot3, doc_publico=doc_publico,
                         ejecucion_id=ej.id, consulta_id=cons.id, memoria_id=mem.id, aportacion_id=ap.id,
                         laguna_id=lag.id, captura_id=cap.id, trabajo_id=trab.id,
                         fichero_espacio="informes/privado.md")


def _bd():
    s = nueva_sesion()
    s.expire_on_commit = False
    return s


# --------------------------------------------------------------------------- 1. inventario


def test_inventario_todas_las_rutas_declaradas(app):
    """Cada ruta de la app tiene su nivel de acceso declarado (y no sobran declaraciones)."""
    reales = rutas_de(app)
    sin_declarar = sorted(reales - set(ACCESO))
    sobran = sorted(set(ACCESO) - reales)
    assert not sin_declarar, f"Rutas nuevas sin nivel de acceso en ACCESO: {sin_declarar}"
    assert not sobran, f"Rutas declaradas que ya no existen: {sobran}"
    assert len(reales) >= 140


# --------------------------------------------------------------------------- 2. matriz de acceso


CASOS_MATRIZ = [(ruta, persona) for ruta, nivel in ACCESO.items() if nivel not in ("publico", "firma")
                for persona, alcanza in MATRIZ.items() if alcanza < ORDEN[nivel]]


@pytest.mark.parametrize("ruta,persona", CASOS_MATRIZ, ids=[f"{p}:{r}" for r, p in CASOS_MATRIZ])
def test_quien_no_llega_al_nivel_no_entra(c, tokens, ruta, persona):
    metodo, plantilla = ruta.split(" ", 1)
    url = _rellenar(plantilla)
    cab = dict(tokens[persona])
    if plantilla == "/mcp":
        cab.update(ACEPTA_MCP)
        r = c.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=cab)
    else:
        r = c.request(metodo, url, headers=cab)  # sin cuerpo: la autorización va antes que la validación
    esperado = 401 if MATRIZ[persona] < ORDEN["usuario"] else 403
    if ORDEN[ACCESO[ruta]] == ORDEN["sesion"]:
        esperado = 401
    assert r.status_code == esperado, f"{persona} → {ruta}: {r.status_code} {r.text[:200]}"
    assert "detail" in r.json() or plantilla == "/mcp"


def test_rutas_firmadas_sin_firma_valida(c, esc):
    rel = "documentos/x/inexistente.txt"
    for ruta in (f"/api/ficheros/{rel}", f"/api/espacio/descarga/pedro/{esc.fichero_espacio}"):
        assert c.get(ruta).status_code == 422  # faltan exp y firma
        assert c.get(ruta, params={"exp": int(time.time()) + 60, "firma": "0" * 32}).status_code == 403
        assert c.get(ruta, params={"exp": 1, "firma": "0" * 32}).status_code == 403


# --------------------------------------------------------------------------- 3. robustez


NO_EN_ROBUSTEZ = {"POST /api/auth/salir"}  # cerraría la sesión de la administración


@pytest.mark.parametrize("ruta", sorted(set(ACCESO) - NO_EN_ROBUSTEZ))
def test_sin_errores_500_con_ids_que_no_existen(c, tokens, esc, monkeypatch, ruta):
    """La administración llega a todas: con ids inexistentes o enormes y sin cuerpo, nunca un 500."""
    _ia_falsa(monkeypatch)
    monkeypatch.setattr(llm, "salud", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(asr, "salud", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(espacio, "estado_ejecutor", lambda: {"disponible": False})
    metodo, plantilla = ruta.split(" ", 1)
    cab = {**tokens["admin"], **(ACEPTA_MCP if plantilla == "/mcp" else {})}
    for valor in (SIN_ID, FUERA_DE_RANGO):
        r = c.request(metodo, _rellenar(plantilla, valor), headers=cab)
        assert r.status_code < 500, f"{ruta} con id {valor}: {r.status_code} {r.text[:300]}"


# --------------------------------------------------------------------------- 4. IDOR


def _casos_idor(e: Escenario) -> list[tuple[str, str, str, dict[str, Any] | None, tuple[str, ...]]]:
    """(descripción, método, url, cuerpo JSON, atacantes)."""
    ej, ins, t = e.ejecucion_id, e.ins.id, e.tarea.id
    paso = e.ins.pasos[1].id
    pedro = e.p.personas["pedro"].id
    otros = ("luis", "marta", "ana")  # otro departamento, compañero sin permiso, jefa de otro departamento
    return [
        # ejecución de pedro en Producción
        ("ver ejecución ajena", "GET", f"/api/planta/ejecuciones/{ej}", None, otros),
        ("confirmar paso ajeno", "POST", f"/api/planta/ejecuciones/{ej}/pasos/{paso}/confirmar",
         {"critico_confirmado": True}, (*otros, "javier")),
        ("preguntar en ejecución ajena", "POST", f"/api/planta/ejecuciones/{ej}/preguntar",
         {"pregunta": "¿Qué hago?", "paso_id": paso}, (*otros, "javier")),
        ("finalizar ejecución ajena", "POST", f"/api/planta/ejecuciones/{ej}/finalizar", None, (*otros, "javier")),
        ("abandonar ejecución ajena", "POST", f"/api/planta/ejecuciones/{ej}/abandonar", None, (*otros, "javier")),
        ("consulta con ejecución ajena", "POST", "/api/consulta/simple",
         {"pregunta": "¿Qué hago ahora?", "contexto": {"ejecucion_id": ej}}, otros),
        ("consulta con paso de otra tarea", "POST", "/api/consulta/simple",
         {"pregunta": "¿Qué hago ahora?", "contexto": {"paso_id": e.ins_ot3.pasos[0].id}}, ("luis", "pedro")),
        ("consulta con paso de un borrador", "POST", "/api/consulta/simple",
         {"pregunta": "¿Qué hago ahora?", "contexto": {"paso_id": e.borrador.pasos[0].id}}, ("pedro", "marta")),
        ("iniciar tarea de nivel superior", "POST", "/api/planta/ejecuciones", {"tarea_id": e.tarea_ot3.id},
         ("luis", "pedro")),
        ("iniciar tarea de otro departamento", "POST", "/api/planta/ejecuciones", {"tarea_id": t}, ("luis", "ana")),
        # consultas y memoria de pedro
        ("valorar consulta ajena", "POST", f"/api/consulta/{e.consulta_id}/valoracion", {"valor": -1},
         ("marta", "javier", "invitado")),
        ("borrar recuerdo ajeno", "DELETE", f"/api/memoria/{e.memoria_id}", None, ("marta", "javier", "admin")),
        # aportación pendiente de pedro (Producción)
        ("ver aportación ajena", "GET", f"/api/aportaciones/{e.aportacion_id}", None, otros),
        ("editar aportación de otro departamento", "PUT", f"/api/aportaciones/{e.aportacion_id}",
         {"titulo": "Cambiado"}, ("ana",)),
        ("validar aportación de otro departamento", "POST", f"/api/aportaciones/{e.aportacion_id}/validar", None,
         ("ana",)),
        ("rechazar aportación de otro departamento", "POST", f"/api/aportaciones/{e.aportacion_id}/rechazar",
         {"motivo": "No"}, ("ana",)),
        ("retirar aportación ajena", "DELETE", f"/api/aportaciones/{e.aportacion_id}", None,
         ("marta", "luis", "javier")),
        ("aportar a una laguna de otro departamento", "POST", "/api/aportaciones",
         {"texto": "La presión del cilindro es de 180 bar según el manual.", "laguna_id": e.laguna_id}, ("luis",)),
        ("aportar sobre una tarea de otro departamento", "POST", "/api/aportaciones",
         {"texto": "La brida se monta con cuidado y en cruz siempre.", "tarea_id": t}, ("luis",)),
        # captura (entrevista) de carmen
        ("ver captura ajena", "GET", f"/api/captura/{e.captura_id}", None, ("ana",)),
        ("responder entrevista ajena", "POST", f"/api/captura/{e.captura_id}/entrevista/responder",
         {"texto": "Con la llave"}, ("ana",)),
        ("finalizar entrevista ajena", "POST", f"/api/captura/{e.captura_id}/entrevista/finalizar", None, ("ana",)),
        ("editar ficha ajena", "PUT", f"/api/captura/{e.captura_id}/ficha", {"titulo": "X"}, ("ana",)),
        ("publicar ficha ajena", "POST", f"/api/captura/{e.captura_id}/ficha/publicar", None, ("ana",)),
        ("reintentar captura ajena", "POST", f"/api/captura/{e.captura_id}/reintentar", None, ("ana",)),
        ("borrar captura ajena", "DELETE", f"/api/captura/{e.captura_id}", None, ("ana",)),
        ("entrevista sobre tarea de otro departamento", "POST", "/api/captura/entrevista", {"tarea_id": t}, ("ana",)),
        # instrucciones de Producción gestionadas por una experta de Oficina técnica
        ("ver borrador de otro departamento", "GET", f"/api/instrucciones/{e.borrador.id}", None, ("ana",)),
        ("editar borrador de otro departamento", "PUT", f"/api/instrucciones/{e.borrador.id}", {"titulo": "X"},
         ("ana",)),
        ("publicar borrador de otro departamento", "POST", f"/api/instrucciones/{e.borrador.id}/publicar", None,
         ("ana",)),
        ("borrar borrador de otro departamento", "DELETE", f"/api/instrucciones/{e.borrador.id}", None, ("ana",)),
        ("nueva versión en otro departamento", "POST", f"/api/instrucciones/{ins}/nueva-version", None, ("ana",)),
        ("versiones de otro departamento", "GET", f"/api/instrucciones/{ins}/versiones", None, ("ana",)),
        ("diferencias de otro departamento", "GET", f"/api/instrucciones/{ins}/diferencias", None, ("ana",)),
        ("instrucción nueva en tarea de otro departamento", "POST", "/api/instrucciones",
         {"tarea_id": e.tarea_ot3.id, "titulo": "X"}, ("carmen",)),
        # preguntas del cuestionario de Producción
        ("listar preguntas de otro departamento", "GET", f"/api/evaluacion/preguntas?instruccion_id={ins}", None,
         ("ana",)),
        ("crear pregunta en otro departamento", "POST", "/api/evaluacion/preguntas",
         {"instruccion_id": ins, "enunciado": "¿X?", "opciones": ["a", "b"], "correcta": 0}, ("ana",)),
        ("cambiar pregunta de otro departamento", "PUT", f"/api/evaluacion/preguntas/{e.pregunta.id}",
         {"estado": "descartada"}, ("ana",)),
        ("borrar pregunta de otro departamento", "DELETE", f"/api/evaluacion/preguntas/{e.pregunta.id}", None,
         ("ana",)),
        ("generar preguntas en otro departamento", "POST", f"/api/evaluacion/instrucciones/{ins}/generar-preguntas",
         None, ("ana",)),
        ("cuestionario de otro departamento", "GET", f"/api/evaluacion/cuestionario/{t}", None, ("luis",)),
        ("cuestionario de nivel superior", "GET", f"/api/evaluacion/cuestionario/{e.tarea_ot3.id}", None, ("luis",)),
        ("responder cuestionario de otro departamento", "POST", f"/api/evaluacion/cuestionario/{t}/responder",
         {"respuestas": {str(e.pregunta.id): 1}}, ("luis",)),
        ("plantilla de observación de otro departamento", "GET",
         f"/api/evaluacion/observacion/plantilla?usuario_id={pedro}&tarea_id={t}", None, ("ana",)),
        ("observar a alguien de otro departamento", "POST", "/api/evaluacion/observaciones",
         {"usuario_id": pedro, "tarea_id": t, "lista": [], "aprobada": True}, ("ana",)),
        # formación
        ("tarea de formación de otro departamento", "GET", f"/api/formacion/tareas/{t}", None, ("luis",)),
        ("tarea de formación de nivel superior", "GET", f"/api/formacion/tareas/{e.tarea_ot3.id}", None, ("luis",)),
        ("ver micro-lección de otro departamento", "POST", f"/api/formacion/microlecciones/{e.micro.id}/vista",
         None, ("luis",)),
        ("responder micro-lección de otro departamento", "POST",
         f"/api/formacion/microlecciones/{e.micro.id}/responder", {"opcion": 1}, ("luis",)),
        ("regenerar micro-lecciones de otro departamento", "POST", f"/api/formacion/tareas/{t}/generar", None,
         ("ana",)),
        # lagunas de Producción
        ("descartar laguna de otro departamento", "POST", f"/api/lagunas/{e.laguna_id}/descartar", None, ("ana",)),
        ("reabrir laguna de otro departamento", "POST", f"/api/lagunas/{e.laguna_id}/reabrir", None, ("ana",)),
        # progreso de pedro
        ("progreso de otra persona", "GET", f"/api/progreso/persona/{pedro}", None, otros),
        ("celda ILUO de otra persona", "GET", f"/api/progreso/iluo/{pedro}/{t}", None, otros),
        ("validar formador sin ser jefe ni experto", "POST", f"/api/progreso/iluo/{pedro}/{t}/formador", None,
         ("marta", "luis", "ana")),
        ("ajustar ILUO de otro departamento", "PUT", f"/api/progreso/iluo/{pedro}/{t}",
         {"nivel": 4, "motivo": "Porque sí"}, ("ana",)),
        ("matriz de otro departamento", "GET", f"/api/progreso/equipo?departamento_id={e.p.deps['prod'].id}", None,
         ("ana",)),
        # personas
        ("ficha de persona de otro departamento", "GET", f"/api/admin/empleados/{pedro}", None, ("ana",)),
        ("formaciones de persona de otro departamento", "GET", f"/api/admin/empleados/{pedro}/formaciones", None,
         ("ana",)),
        ("lista de otro departamento", "GET", f"/api/admin/empleados?departamento_id={e.p.deps['prod'].id}", None,
         ("ana",)),
        # documentos
        ("ver documento de otro departamento", "GET", f"/api/documentos/{e.doc_ot3.id}", None, ("javier",)),
        ("descargar documento de otro departamento", "GET", f"/api/documentos/{e.doc_ot3.id}/descarga", None,
         ("javier",)),
        ("editar documento de otro departamento", "PATCH", f"/api/documentos/{e.doc_ot3.id}", {"es_publico": True},
         ("javier",)),
        ("reindexar documento de otro departamento", "POST", f"/api/documentos/{e.doc_ot3.id}/reindexar", None,
         ("javier",)),
        ("borrar documento de otro departamento", "DELETE", f"/api/documentos/{e.doc_ot3.id}", None, ("javier",)),
        ("editar documento público ajeno", "PATCH", f"/api/documentos/{e.doc_publico.id}", {"titulo": "X"},
         ("javier", "ana")),
        ("mover documento a otro departamento", "PATCH", f"/api/documentos/{e.doc_prod.id}",
         {"departamento_id": e.p.deps["ot"].id}, ("javier",)),
        ("buscar como otra persona", "POST", "/api/documentos/probar-busqueda",
         {"consulta": "costes", "como_usuario_id": e.p.personas["ana"].id}, ("javier",)),
        ("buscar como invitado sin ser admin", "POST", "/api/documentos/probar-busqueda",
         {"consulta": "costes", "como_invitado": True}, ("javier",)),
    ]


def test_idor_objetos_de_otra_persona_o_departamento(c, tokens, esc, monkeypatch):
    _ia_falsa(monkeypatch)
    fallos = []
    for desc, metodo, url, cuerpo, atacantes in _casos_idor(esc):
        for quien in atacantes:
            r = c.request(metodo, url, headers=tokens[quien], **({"json": cuerpo} if cuerpo is not None else {}))
            if r.status_code not in (401, 403, 404):
                fallos.append(f"{quien} · {desc}: {metodo} {url} → {r.status_code} {r.text[:160]}")
    assert not fallos, "Accesos indebidos:\n" + "\n".join(fallos)


def test_idor_no_cambia_nada(c, tokens, esc):
    """Tras todos los intentos, los objetos siguen como estaban."""
    with _bd() as bd:
        ej = bd.get(Ejecucion, esc.ejecucion_id)
        assert ej.estado == "en_curso" and (ej.consultas or 0) == 0
        assert not ej.pasos
        ap = bd.get(Aportacion, esc.aportacion_id)
        assert ap.estado == "pendiente" and ap.titulo == "Atasco de la prensa"
        assert bd.get(Consulta, esc.consulta_id).valoracion is None
        assert bd.get(Memoria, esc.memoria_id) is not None
        assert bd.get(Laguna, esc.laguna_id).estado == "abierta"
        assert bd.get(Captura, esc.captura_id) is not None
        assert bd.get(Instruccion, esc.borrador.id).estado == "borrador"
        assert bd.get(PreguntaEval, esc.pregunta.id).estado == "aprobada"
        d = bd.get(Documento, esc.doc_ot3.id)
        assert d is not None and not d.es_publico and d.departamento_id == esc.p.deps["ot"].id
        assert bd.get(Documento, esc.doc_publico.id).titulo == "Bienvenida pública"
        assert bd.get(Documento, esc.doc_prod.id).departamento_id == esc.p.deps["prod"].id
        fila = bd.scalar(select(NivelIluo).where(NivelIluo.usuario_id == esc.p.personas["pedro"].id,
                                                 NivelIluo.tarea_id == esc.tarea.id))
        assert fila.nivel == 1 and not fila.formador_validado


def test_trabajo_ajeno_no_da_detalles(c, tokens, esc):
    url = f"/api/trabajos/{esc.trabajo_id}"
    for quien in ("invitado", "pedro", "ana"):
        datos = c.get(url, headers=tokens[quien]).json()
        assert datos == {"id": esc.trabajo_id, "estado": "desconocido"}, quien
    propio = c.get(url, headers=tokens["carmen"]).json()
    assert propio["estado"] == "error" and "10.0.0.9" not in json.dumps(propio)  # sin detalles internos
    assert "10.0.0.9" in c.get(url, headers=tokens["admin"]).json()["mensaje"]


def test_listas_solo_con_lo_propio(c, tokens, esc):
    """Los filtros por departamento de las listas no sirven para mirar en otro departamento."""
    prod, ot = esc.p.deps["prod"].id, esc.p.deps["ot"].id
    docs = c.get("/api/documentos", params={"departamento_id": ot}, headers=tokens["javier"]).json()
    assert docs["documentos"] == []
    docs = c.get("/api/documentos", params={"texto": "Costes"}, headers=tokens["javier"]).json()
    assert docs["documentos"] == []
    lag = c.get("/api/lagunas", params={"departamento_id": prod}, headers=tokens["ana"]).json()
    assert all(x["id"] != esc.laguna_id for x in lag["lagunas"])
    abiertas = c.get("/api/lagunas/abiertas-de-mi-departamento", headers=tokens["luis"]).json()["lagunas"]
    assert all(x["id"] != esc.laguna_id for x in abiertas)
    pend = c.get("/api/aportaciones/pendientes", headers=tokens["ana"]).json()["aportaciones"]
    assert all(x["id"] != esc.aportacion_id for x in pend)
    mias = c.get("/api/aportaciones/mias", headers=tokens["marta"]).json()["aportaciones"]
    assert all(x["id"] != esc.aportacion_id for x in mias)
    resumen = c.get("/api/aportaciones/resumen", headers=tokens["ana"]).json()["personas"]
    assert all(x["usuario_id"] != esc.p.personas["pedro"].id for x in resumen)
    ins = c.get("/api/instrucciones", params={"departamento_id": prod}, headers=tokens["ana"]).json()
    assert all(x["tarea_id"] not in (esc.tarea.id, esc.borrador.tarea_id) for x in ins)
    capturas = c.get("/api/captura", headers=tokens["ana"]).json()
    assert all(x["id"] != esc.captura_id for x in capturas)
    hist = c.get("/api/consulta/historial", headers=tokens["marta"]).json()["elementos"]
    assert all(x["id"] != esc.consulta_id for x in hist)
    assert c.get("/api/memoria", headers=tokens["marta"]).json()["recuerdos"] == []
    planta = c.get("/api/planta/tareas", headers=tokens["luis"]).json()
    assert {x["id"] for x in planta} & {esc.tarea.id, esc.tarea_ot3.id} == set()
    itinerario = json.dumps(c.get("/api/formacion/itinerario", headers=tokens["luis"]).json(), ensure_ascii=False)
    assert esc.tarea.codigo not in itinerario and esc.tarea_ot3.codigo not in itinerario
    emp = c.get("/api/admin/empleados", headers=tokens["ana"]).json()["empleados"]
    assert {e["usuario"] for e in emp} == {"ana", "luis"}
    equipo = json.dumps(c.get("/api/progreso/equipo", headers=tokens["ana"]).json(), ensure_ascii=False)
    assert "Pedro Ruiz" not in equipo


def test_espacio_de_trabajo_aislado(c, tokens, esc):
    """Cada persona solo ve su carpeta: ni rutas relativas hacia fuera ni rutas absolutas."""
    propia = c.get("/api/espacio/fichero", params={"ruta": esc.fichero_espacio}, headers=tokens["pedro"])
    assert propia.status_code == 200 and "Pedro" in propia.json()["contenido"]
    intentos = ["../pedro/" + esc.fichero_espacio, "..\\pedro\\informes\\privado.md", "/etc/passwd",
                "C:/Windows/win.ini", "informes/../../pedro/" + esc.fichero_espacio, "%2e%2e/pedro/x",
                "\\\\servidor\\c$\\x", "informes/\x00.md"]
    for ruta in intentos:
        r = c.get("/api/espacio/fichero", params={"ruta": ruta}, headers=tokens["marta"])
        assert r.status_code in (400, 404), f"{ruta}: {r.status_code} {r.text[:120]}"
        assert "Pedro" not in r.text
        w = c.put("/api/espacio/fichero", json={"ruta": ruta, "contenido": "x"}, headers=tokens["marta"])
        assert w.status_code in (400, 404), f"escribir {ruta}: {w.status_code}"
    m = c.post("/api/espacio/mover", json={"origen": "../pedro/" + esc.fichero_espacio, "destino": "robado.md"},
               headers=tokens["marta"])
    assert m.status_code in (400, 404)
    assert "privado" not in json.dumps(c.get("/api/espacio", headers=tokens["marta"]).json())
    # Una URL firmada de pedro no vale para otro fichero ni para otra carpeta.
    arbol = c.get("/api/espacio", headers=tokens["pedro"]).json()
    url = next(x for x in _hojas(arbol) if x.get("nombre") == "privado.md")["url_descarga"]
    base, _, query = url.partition("?")
    assert c.get(url).status_code == 200
    assert c.get(base.replace("/pedro/", "/marta/") + "?" + query).status_code in (403, 404)
    assert c.get(base.replace("privado.md", "otro.md") + "?" + query).status_code == 403


def _hojas(nodo: Any) -> list[dict[str, Any]]:
    salida: list[dict[str, Any]] = []
    if isinstance(nodo, dict):
        if nodo.get("url_descarga"):
            salida.append(nodo)
        for v in nodo.values():
            salida.extend(_hojas(v))
    elif isinstance(nodo, list):
        for v in nodo:
            salida.extend(_hojas(v))
    return salida


# --------------------------------------------------------------------------- 5. fugas de datos


VALORES_GET = {"trabajo_id": "trabajo_id", "ejecucion_id": "ejecucion_id", "aportacion_id": "aportacion_id",
               "captura_id": "captura_id"}


def _url_real(plantilla: str, e: Escenario) -> str | None:
    ids = {
        "usuario_id": e.p.personas["pedro"].id, "tarea_id": e.tarea.id, "instruccion_id": e.ins.id,
        "documento_id": e.doc_prod.id, "aportacion_id": e.aportacion_id, "captura_id": e.captura_id,
        "ejecucion_id": e.ejecucion_id, "trabajo_id": e.trabajo_id, "consulta_id": e.consulta_id,
    }
    faltan = [n for n in re.findall(r"\{(\w+)(?::path)?\}", plantilla) if n not in ids]
    if faltan:
        return None
    url = re.sub(r"\{(\w+)\}", lambda m: str(ids[m.group(1)]), plantilla)
    extra = {
        "/api/espacio/fichero": f"?ruta={e.fichero_espacio}",
        "/api/evaluacion/preguntas": f"?instruccion_id={e.ins.id}",
        "/api/evaluacion/observacion/plantilla": f"?usuario_id={e.p.personas['pedro'].id}&tarea_id={e.tarea.id}",
    }
    return url + extra.get(plantilla, "")


def _prohibidos() -> list[str]:
    datos = ajustes().dir_datos.resolve()
    return ["$argon2", "hash_contrasena", ajustes().secreto_jwt, str(datos), datos.as_posix(),
            str(datos).replace("\\", "\\\\"), CONTRASENA]


def test_ninguna_respuesta_filtra_secretos(c, tokens, esc, monkeypatch):
    """Todas las rutas GET con datos reales, como cada persona: sin hashes, secretos ni rutas del servidor."""
    _ia_falsa(monkeypatch)
    monkeypatch.setattr(llm, "salud", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(asr, "salud", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(espacio, "estado_ejecutor", lambda: {"disponible": False})
    prohibidos = _prohibidos()
    fallos = []
    vistas = 0
    for ruta, nivel in sorted(ACCESO.items()):
        metodo, plantilla = ruta.split(" ", 1)
        if metodo != "GET" or nivel == "firma" or plantilla.startswith(("/app", "/api/docs", "/docs")) or plantilla == "/":
            continue
        url = _url_real(plantilla, esc)
        if url is None:
            continue
        for quien in ("invitado", "pedro", "marta", "carmen", "javier", "ana", "admin"):
            r = c.get(url, headers=tokens[quien])
            if r.status_code >= 500:
                fallos.append(f"{quien} {url}: {r.status_code}")
                continue
            vistas += 1
            for p in prohibidos:
                if p and p in r.text:
                    fallos.append(f"{quien} {url}: contiene «{p[:20]}»")
    assert vistas > 200
    assert not fallos, "\n".join(fallos)


def test_el_aprendiz_nunca_ve_la_respuesta_correcta(c, tokens, esc):
    cu = c.get(f"/api/evaluacion/cuestionario/{esc.tarea.id}", headers=tokens["pedro"])
    assert cu.status_code == 200, cu.text
    assert "correcta" not in cu.text and "explicacion" not in cu.text
    opciones = cu.json()["preguntas"][0]["opciones"]
    assert all(set(o) == {"clave", "texto"} for o in opciones)
    # Las claves son opacas: no son la posición ni se repiten entre preguntas.
    assert all(not o["clave"].isdigit() for o in opciones)
    det = c.get(f"/api/formacion/tareas/{esc.tarea.id}", headers=tokens["pedro"])
    assert det.status_code == 200, det.text
    assert '"correcta"' not in det.text


def test_documentos_sin_permiso_no_aparecen_en_busquedas(c, tokens, esc, monkeypatch):
    """Ni el copiloto, ni la consola de búsqueda ni el MCP devuelven el documento de nivel 3."""
    _ia_falsa(monkeypatch)
    pregunta = "¿Cuánto cuesta el utillaje de soldadura y quién aprueba la compra?"
    for quien in ("invitado", "luis", "pedro", "javier"):
        r = c.post("/api/consulta/simple", json={"pregunta": pregunta}, headers=tokens[quien])
        assert r.status_code == 200, r.text
        assert all(f.get("documento_id") != esc.doc_ot3.id for f in r.json()["fuentes"]), quien
        assert "Costes secretos" not in r.text
    ok, datos = _mcp_llamar(c, tokens["luis"], "buscar_conocimiento", consulta=pregunta)
    assert not ok or all(x["documento_id"] != esc.doc_ot3.id for x in datos.get("resultados", []))
    r = c.post("/api/documentos/probar-busqueda", json={"consulta": pregunta}, headers=tokens["javier"])
    assert all(x["documento_id"] != esc.doc_ot3.id for x in r.json()["resultados"])
    # Quien sí tiene permiso lo encuentra (la prueba no pasa por no encontrar nada).
    r = c.post("/api/consulta/simple", json={"pregunta": pregunta}, headers=tokens["ana"])
    assert any(f.get("documento_id") == esc.doc_ot3.id for f in r.json()["fuentes"])


def test_historial_no_resucita_fuentes_sin_permiso(c, tokens, esc):
    """Si pedro ya no puede ver un documento que se citó, su historial lo oculta."""
    with _bd() as bd:
        d = bd.get(Documento, esc.doc_prod.id)
        d.departamento_id, d.es_publico = esc.p.deps["ot"].id, False
        bd.commit()
    try:
        hist = c.get("/api/consulta/historial", headers=tokens["pedro"]).json()["elementos"]
        fuentes = next(x for x in hist if x["id"] == esc.consulta_id)["fuentes"]
        assert fuentes and all(not f["disponible"] and f["documento_id"] is None for f in fuentes)
        assert "Manual de la prensa" not in json.dumps(hist, ensure_ascii=False)
    finally:
        with _bd() as bd:
            bd.get(Documento, esc.doc_prod.id).departamento_id = esc.p.deps["prod"].id
            bd.commit()


# --------------------------------------------------------------------------- 6. ficheros y límites


@pytest.mark.parametrize("nombre,contenido", [
    ("pagina.html", b"<script>alert(1)</script>"), ("dibujo.svg", b"<svg onload='alert(1)'/>"),
    ("programa.exe", b"MZ\x90\x00"), ("codigo.js", b"alert(1)"), ("sin_extension", b"hola"),
    ("doble.pdf.html", b"<script>alert(1)</script>"), ("punto.pdf.", b"%PDF-1.4"),
])
def test_documentos_rechazan_tipos_peligrosos(c, tokens, esc, nombre, contenido):
    r = c.post("/api/documentos", headers=tokens["javier"], files={"fichero": (nombre, contenido, "text/html")})
    assert r.status_code == 400, f"{nombre}: {r.status_code} {r.text[:200]}"


def test_ficheros_activos_se_sirven_como_descarga(c, esc):
    """Si algún HTML o SVG acabara en los datos, /api/ficheros nunca lo sirve como página."""
    carpeta = ajustes().dir_datos / "pruebas_seguridad"
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, tipo in (("ataque.html", "text/html"), ("ataque.svg", "image/svg+xml")):
        (carpeta / nombre).write_bytes(b"<script>alert(document.cookie)</script>")
        r = c.get(url_fichero(f"pruebas_seguridad/{nombre}"))
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/octet-stream"), nombre
        assert "attachment" in r.headers.get("content-disposition", "")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "sandbox" in r.headers["content-security-policy"]
    # Una firma de un fichero no sirve para recorrer hacia fuera de los datos.
    url = url_fichero("pruebas_seguridad/ataque.html")
    base, _, query = url.partition("?")
    for otra in ("pruebas_seguridad/../../.env", "..%2f..%2f.env", "pruebas_seguridad/ataque.svg"):
        assert c.get(f"/api/ficheros/{otra}?{query}").status_code in (400, 403, 404)


def test_espacio_sirve_html_y_svg_sin_ejecutar(c, tokens):
    for nombre in ("pagina.html", "dibujo.svg"):
        r = c.post("/api/espacio/subir", headers=tokens["luis"], data={"carpeta": "subidas"},
                   files={"fichero": (nombre, b"<script>alert(1)</script>", "text/html")})
        assert r.status_code == 200, r.text
    arbol = c.get("/api/espacio", headers=tokens["luis"]).json()
    for hoja in _hojas(arbol):
        if hoja.get("nombre") in ("pagina.html", "dibujo.svg"):
            r = c.get(hoja["url_descarga"].replace("descargar=1", "descargar=0"))
            assert r.status_code == 200
            assert r.headers["x-content-type-options"] == "nosniff"
            assert "sandbox" in r.headers.get("content-security-policy", "")
            if hoja["nombre"].endswith(".html"):
                assert "attachment" in r.headers.get("content-disposition", "")


def _ejecucion_propia(c, tokens, esc, quien: str = "pedro") -> int:
    r = c.post("/api/planta/ejecuciones", json={"tarea_id": esc.tarea.id}, headers=tokens[quien])
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.mark.parametrize("nombre,contenido,tipo", [
    ("foto.png", b"<html><script>alert(1)</script></html>", "image/png"),
    ("foto.svg", b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>", "image/svg+xml"),
    ("foto.png", b"", "image/png"),
    ("foto.gif", b"GIF89a\x01\x00\x01\x00", "image/gif"),
])
def test_foto_de_planta_solo_imagenes(c, tokens, esc, monkeypatch, nombre, contenido, tipo):
    _ia_falsa(monkeypatch)
    ej = _ejecucion_propia(c, tokens, esc)
    r = c.post(f"/api/planta/ejecuciones/{ej}/foto", headers=tokens["pedro"], files={"imagen": (nombre, contenido, tipo)})
    assert r.status_code == 400, r.text


def test_limites_de_tamano(c, tokens, esc, monkeypatch):
    _ia_falsa(monkeypatch)
    ej = _ejecucion_propia(c, tokens, esc)
    grande = PNG + b"\x00" * (25 * 1024 * 1024)
    r = c.post(f"/api/planta/ejecuciones/{ej}/foto", headers=tokens["pedro"], files={"imagen": ("f.png", grande, "image/png")})
    assert r.status_code == 413
    r = c.post("/api/voz/transcribir", headers=tokens["pedro"], files={"audio": ("v.webm", grande, "audio/webm")})
    assert r.status_code == 413
    del grande
    r = c.post("/api/voz/transcribir", headers=tokens["pedro"], files={"audio": ("v.png", PNG * 100, "image/png")})
    assert r.status_code == 400
    largo = "x" * 4001
    assert c.post("/api/consulta/simple", json={"pregunta": largo}, headers=tokens["invitado"]).status_code == 422
    hist = [{"rol": "usuario", "texto": "hola"}] * 51
    assert c.post("/api/consulta/simple", json={"pregunta": "hola", "historial": hist},
                  headers=tokens["pedro"]).status_code == 422
    assert c.post("/api/aportaciones", json={"texto": "y" * 8001}, headers=tokens["pedro"]).status_code == 400
    c.put("/api/memoria", json={"activa": True}, headers=tokens["luis"])
    assert c.post("/api/memoria", json={"contenido": "z" * 501}, headers=tokens["luis"]).status_code == 422
    pasos = [{"titulo": f"Paso {i}"} for i in range(61)]
    r = c.put(f"/api/instrucciones/{esc.borrador.id}", json={"pasos": pasos}, headers=tokens["carmen"])
    assert r.status_code == 400, r.text
    r = c.put("/api/espacio/fichero", json={"ruta": "grande.txt", "contenido": "w" * (5 * 1024 * 1024 + 1)},
              headers=tokens["luis"])
    assert r.status_code in (400, 413)


@pytest.mark.parametrize("texto", [
    "' OR 1=1 --", "%", "_", "%' OR '1'='1", "\\", "'); DROP TABLE documentos; --", "a\x00b",
    "!(& | :* <-> )", "costes:* & !bienvenida", "\"\"\"", "../../etc/passwd",
])
def test_busquedas_con_caracteres_especiales(c, tokens, esc, monkeypatch, texto):
    """Ningún texto de búsqueda rompe la consulta ni enseña lo que no se puede ver."""
    _ia_falsa(monkeypatch)
    for quien, url, params in (
        ("javier", "/api/documentos", {"texto": texto}),
        ("pedro", "/api/consulta/historial", {"q": texto}),
        ("ana", "/api/admin/empleados", {"texto": texto}),
        ("carmen", "/api/instrucciones", {"q": texto}),
    ):
        r = c.get(url, params=params, headers=tokens[quien])
        assert r.status_code < 500, f"{url} {texto!r}: {r.status_code}"
        assert "Costes secretos" not in r.text and "Pedro Ruiz" not in (r.text if quien == "ana" else "")
    for quien in ("invitado", "luis"):
        r = c.post("/api/consulta/simple", json={"pregunta": texto + " utillaje"}, headers=tokens[quien])
        assert r.status_code < 500, r.text
        assert all(f.get("documento_id") != esc.doc_ot3.id for f in r.json().get("fuentes", []))
    r = c.post("/api/documentos/probar-busqueda", json={"consulta": texto}, headers=tokens["javier"])
    assert r.status_code < 500
    with _bd() as bd:  # la tabla sigue ahí
        assert bd.get(Documento, esc.doc_ot3.id) is not None


# --------------------------------------------------------------------------- sesiones y tokens


def test_tokens_manipulados_o_caducados(c, tokens, esc):
    secreto = ajustes().secreto_jwt
    with _bd() as bd:
        sesion = bd.scalar(select(Sesion).where(Sesion.usuario_id == esc.p.personas["pedro"].id))
        sid = sesion.id
    falsos = {
        "sin firma (alg none)": jwt.encode({"sid": sid, "tipo": "usuario", "sub": "1", "exp": int(time.time()) + 600},
                                           key="", algorithm="none"),
        "otro secreto": jwt.encode({"sid": sid, "tipo": "usuario", "exp": int(time.time()) + 600}, "otro" * 10,
                                   algorithm="HS256"),
        "caducado": jwt.encode({"sid": sid, "tipo": "usuario", "exp": int(time.time()) - 10}, secreto,
                               algorithm="HS256"),
        "sesión inventada": jwt.encode({"sid": "no-existe", "tipo": "usuario", "exp": int(time.time()) + 600}, secreto,
                                       algorithm="HS256"),
        "basura": "esto.no.es-un-token",
    }
    for nombre, t in falsos.items():
        h = {"Authorization": f"Bearer {t}"}
        assert c.get("/api/auth/yo", headers=h).status_code == 401, nombre
        assert c.get("/v1/models", headers=h).status_code == 401, nombre
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={**h, **ACEPTA_MCP})
        assert r.status_code == 401, nombre


def test_el_token_de_invitado_no_se_convierte_en_usuario(c, tokens):
    """Cambiar el «tipo» o añadir «sub» a un token de invitado invalida la firma."""
    t = tokens["invitado"]["Authorization"].split()[1]
    carga = jwt.decode(t, options={"verify_signature": False})
    carga.update({"tipo": "usuario", "sub": "1"})
    cabecera, _, firma = t.rpartition(".")
    falso = jwt.encode(carga, "x" * 32, algorithm="HS256").rpartition(".")[0] + "." + firma
    assert c.get("/api/auth/yo", headers={"Authorization": f"Bearer {falso}"}).status_code == 401
    yo = c.get("/api/auth/yo", headers=tokens["invitado"]).json()
    assert yo["invitado"] is True and "id" not in yo


def test_cuenta_desactivada_y_sesion_cerrada(c, esc):
    h = {"Authorization": f"Bearer {c.post('/api/auth/login', json={'usuario': 'luis', 'contrasena': CONTRASENA}).json()['token']}"}
    assert c.get("/api/auth/yo", headers=h).status_code == 200
    assert c.post("/api/auth/salir", headers=h).status_code == 200
    assert c.get("/api/auth/yo", headers=h).status_code == 401
    assert c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                  headers={**h, **ACEPTA_MCP}).status_code == 401
    r = c.post("/api/auth/login", json={"usuario": "luis", "contrasena": "mala"})
    assert r.status_code == 401 and "token" not in r.json()
    r = c.post("/api/auth/login", json={"usuario": "no-existe' OR '1'='1", "contrasena": "x"})
    assert r.status_code == 401


def test_perfil_no_revela_datos_internos(c, tokens):
    yo = c.get("/api/auth/yo", headers=tokens["pedro"]).json()
    assert "hash_contrasena" not in yo and "departamento" not in yo and "nivel" not in yo
    lista = c.get("/api/admin/empleados", headers=tokens["admin"]).text
    assert "$argon2" not in lista and "hash" not in lista


# --------------------------------------------------------------------------- 7. /v1 y /mcp


class _Proveedor:
    def __init__(self) -> None:
        self.cuerpos: list[dict[str, Any]] = []

    def manejar(self, request: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(request.content)
        self.cuerpos.append(cuerpo)
        return httpx.Response(200, json={"id": "c1", "object": "chat.completion", "model": cuerpo["model"],
                                         "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hola"},
                                                      "finish_reason": "stop"}]})


def test_v1_invitado_limitado_y_sin_modelos_bloqueados(c, tokens, monkeypatch):
    prov = _Proveedor()
    monkeypatch.setattr(rutas_openai, "_cliente_http",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(prov.manejar)))
    h = tokens["invitado"]
    assert c.get("/v1/models").status_code == 401
    modelos = c.get("/v1/models", headers=h).json()["data"]
    assert modelos and all("ref" not in m for m in modelos)
    r = c.post("/v1/chat/completions", headers=h, json={
        "messages": [{"role": "user", "content": "Hola"}], "max_tokens": 100_000, "max_completion_tokens": 50_000,
        "n": 8, "tool_choice": "required"})
    assert r.status_code == 200, r.text
    enviado = prov.cuerpos[-1]
    assert enviado["max_tokens"] <= rutas_openai.MAX_TOKENS_INVITADO
    assert enviado["max_completion_tokens"] <= rutas_openai.MAX_TOKENS_INVITADO
    assert enviado["n"] == 1 and "tool_choice" not in enviado
    sin = c.post("/v1/chat/completions", headers=h, json={"messages": [{"role": "user", "content": "Hola"}]})
    assert sin.status_code == 200 and prov.cuerpos[-1]["max_tokens"] <= rutas_openai.MAX_TOKENS_INVITADO
    for modelo in ("gpt-4o", "claude-opus", "../../etc", "qwen3:235b"):
        r = c.post("/v1/chat/completions", headers=h, json={"model": modelo, "messages": [{"role": "user", "content": "x"}]})
        assert r.status_code == 403, f"{modelo}: {r.status_code}"
        assert r.json()["error"]["code"] == "modelo_no_permitido"
    assert len(prov.cuerpos) == 2  # los modelos no permitidos no llegan al proveedor
    for malo in ("no es json", "[]", '{"messages": []}', '{"messages": "hola"}'):
        r = c.post("/v1/chat/completions", headers={**h, "Content-Type": "application/json"}, content=malo)
        assert r.status_code == 400


def test_v1_limite_de_uso_del_invitado(c, monkeypatch):
    prov = _Proveedor()
    monkeypatch.setattr(rutas_openai, "_cliente_http",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(prov.manejar)))
    monkeypatch.setattr(ajustes(), "invitado_limite_hora", 2)
    h = {"Authorization": f"Bearer {c.post('/api/auth/invitado').json()['token']}"}
    cuerpo = {"messages": [{"role": "user", "content": "Hola"}]}
    estados = [c.post("/v1/chat/completions", headers=h, json=cuerpo).status_code for _ in range(3)]
    assert estados == [200, 200, 429]
    # Un token de invitado nuevo no comparte la cuenta, pero el que llegó al límite sigue bloqueado.
    assert c.post("/v1/chat/completions", headers=h, json=cuerpo).status_code == 429


def _mcp(c, cab: dict[str, str], metodo: str, params: dict[str, Any] | None = None) -> httpx.Response:
    cuerpo: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": metodo}
    if params is not None:
        cuerpo["params"] = params
    return c.post("/mcp", json=cuerpo, headers={**ACEPTA_MCP, **cab})


def _mcp_llamar(c, cab: dict[str, str], herramienta: str, **argumentos: Any) -> tuple[bool, Any]:
    """(correcto, datos o texto del error)."""
    r = _mcp(c, cab, "tools/call", {"name": herramienta, "arguments": argumentos})
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    texto = "".join(x.get("text", "") for x in res.get("content", []))
    if res.get("isError"):
        return False, texto
    return True, res.get("structuredContent") or json.loads(texto)


def test_mcp_sin_token_e_invitado(c, tokens, esc, monkeypatch):
    _ia_falsa(monkeypatch)
    assert _mcp(c, {}, "tools/list").status_code == 401
    inv = tokens["invitado"]
    assert _mcp(c, inv, "tools/list").status_code == 200
    ok, datos = _mcp_llamar(c, inv, "buscar_conocimiento", consulta="prensa utillaje bienvenida costes")
    assert ok
    ids = {x["documento_id"] for x in datos["resultados"]}
    assert ids <= {esc.doc_publico.id}, ids
    for herramienta, args in (("listar_tareas", {}), ("ver_instruccion", {"tarea": esc.tarea.codigo}),
                              ("mi_progreso", {}), ("registrar_laguna", {"pregunta": "¿Qué presión lleva?"}),
                              ("proponer_aportacion", {"problema": "Se atasca la prensa", "causa": "",
                                                       "solucion": "Limpiar el sensor"}),
                              ("espacio_listar", {}), ("espacio_leer", {"ruta": "x.md"}),
                              ("espacio_escribir", {"ruta": "x.md", "contenido": "x"}),
                              ("espacio_ejecutar", {"orden": "ls"})):
        ok, texto = _mcp_llamar(c, inv, herramienta, **args)
        assert not ok and "iniciar sesión" in texto, herramienta


def test_mcp_usuario_con_sus_permisos(c, tokens, esc, monkeypatch):
    _ia_falsa(monkeypatch)
    luis = tokens["luis"]
    ok, datos = _mcp_llamar(c, luis, "listar_tareas")
    assert ok and esc.tarea.id not in {t["id"] for t in datos["tareas"]}
    assert esc.tarea_ot3.id not in {t["id"] for t in datos["tareas"]}
    for tarea in (esc.tarea.codigo, esc.tarea_ot3.codigo, str(esc.tarea.id), str(esc.tarea_ot3.id)):
        ok, texto = _mcp_llamar(c, luis, "ver_instruccion", tarea=tarea)
        assert not ok and "No encuentro" in texto, tarea
    ok, datos = _mcp_llamar(c, luis, "buscar_conocimiento", consulta="costes utillaje soldadura prensa Producción")
    assert ok
    assert not {x["documento_id"] for x in datos["resultados"]} & {esc.doc_ot3.id, esc.doc_prod.id}
    # El espacio de trabajo por MCP tampoco sale de la carpeta propia.
    for ruta in ("../pedro/" + esc.fichero_espacio, "/trabajo/../pedro/" + esc.fichero_espacio, "/etc/passwd"):
        ok, texto = _mcp_llamar(c, luis, "espacio_leer", ruta=ruta)
        assert not ok and "Pedro" not in texto, ruta
    # La aportación propuesta es del departamento de quien la propone, no de otro.
    ok, datos = _mcp_llamar(c, luis, "proponer_aportacion", problema="El utillaje no centra la pieza",
                            causa="Topes gastados", solucion="Cambiar los topes del utillaje")
    assert ok
    with _bd() as bd:
        ap = bd.get(Aportacion, datos["aportacion_id"])
        assert ap.autor_id == esc.p.personas["luis"].id and ap.departamento_id == esc.p.deps["ot"].id
    # Los errores internos no se cuentan al agente.
    monkeypatch.setattr(espacio, "listar_carpeta", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("C:/secreto")))
    ok, texto = _mcp_llamar(c, luis, "espacio_listar")
    assert not ok and "secreto" not in texto
