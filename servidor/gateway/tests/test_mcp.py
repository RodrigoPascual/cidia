"""Servidor MCP (/mcp): autenticación con el token de CidIA, lista de herramientas y llamadas
con los permisos de cada persona (por la ruta antigua sin estado y por la moderna 2026-07-28)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fabrica import cab
from sqlalchemy import select

from cidia.config import ajustes
from cidia.modelos import Aportacion, Instruccion, Laguna, Paso, SentenciaXapi
from cidia.servicios import documentos, espacio

ACEPTA = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
HERRAMIENTAS = {
    "buscar_conocimiento", "listar_tareas", "ver_instruccion", "registrar_laguna", "proponer_aportacion",
    "mi_progreso", "espacio_listar", "espacio_leer", "espacio_escribir", "espacio_ejecutar",
}
VERSION_MODERNA = "2026-07-28"


def rpc(cliente, metodo: str, params: dict[str, Any] | None = None, cabeceras: dict[str, str] | None = None):
    cuerpo: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": metodo}
    if params is not None:
        cuerpo["params"] = params
    return cliente.post("/mcp", json=cuerpo, headers={**ACEPTA, **(cabeceras or {})})


def llamar(cliente, cabeceras: dict[str, str], herramienta: str, **argumentos: Any) -> tuple[bool, Any]:
    """Llama a una herramienta. Devuelve (es_error, datos): datos es el JSON devuelto o el texto del error."""
    r = rpc(cliente, "tools/call", {"name": herramienta, "arguments": argumentos}, cabeceras)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")  # json_response=True: sin SSE
    res = r.json()["result"]
    texto = "".join(c.get("text", "") for c in res.get("content", []))
    if res.get("isError"):
        return True, texto
    datos = res.get("structuredContent")
    if datos is None:
        datos = json.loads(texto)
    return False, datos


def _doc(bd, titulo, texto, dep, nivel=1, publico=False):
    return documentos.crear_desde_texto(bd, titulo, texto, departamento_id=dep.id if dep else None,
                                        nivel_minimo=nivel, es_formacion=False, es_publico=publico,
                                        en_segundo_plano=False)


# --------------------------------------------------------------------------- autenticación


def test_sin_token_401(cliente, planta):
    r = rpc(cliente, "tools/list")
    assert r.status_code == 401
    assert "bearer" in r.headers.get("www-authenticate", "").lower()


def test_token_no_valido_401(cliente, planta):
    r = rpc(cliente, "tools/list", cabeceras={"Authorization": "Bearer esto-no-es-un-token"})
    assert r.status_code == 401


def test_sesion_cerrada_401(cliente, planta):
    h = cab(cliente, "pedro")
    assert rpc(cliente, "tools/list", cabeceras=h).status_code == 200
    cliente.post("/api/auth/salir", headers=h)
    assert rpc(cliente, "tools/list", cabeceras=h).status_code == 401


def test_cualquier_host_por_defecto(cliente, planta):
    """CIDIA_MCP_HOSTS por defecto «*»: un Host que no es localhost no da 421."""
    h = {**cab(cliente, "pedro"), "Host": "cidia.planta.local:18700"}
    assert rpc(cliente, "tools/list", cabeceras=h).status_code == 200


def test_tools_list(cliente, planta):
    r = rpc(cliente, "tools/list", cabeceras=cab(cliente, "luis"))
    assert r.status_code == 200, r.text
    herramientas = {t["name"]: t for t in r.json()["result"]["tools"]}
    assert set(herramientas) == HERRAMIENTAS
    buscar = herramientas["buscar_conocimiento"]
    assert "documentación" in buscar["description"]
    assert set(buscar["inputSchema"]["properties"]) == {"consulta", "k"}
    assert buscar["inputSchema"]["properties"]["consulta"]["description"]


def test_ruta_moderna_2026(cliente, planta):
    """La app (dsh) habla 2026-07-28: sin initialize, con el sobre _meta y cabeceras de enrutado."""
    h = cab(cliente, "luis")
    meta = {"_meta": {"io.modelcontextprotocol/protocolVersion": VERSION_MODERNA,
                      "io.modelcontextprotocol/clientCapabilities": {}}}
    r = rpc(cliente, "tools/list", meta, {**h, "MCP-Protocol-Version": VERSION_MODERNA, "Mcp-Method": "tools/list"})
    assert r.status_code == 200, r.text
    assert HERRAMIENTAS <= {t["name"] for t in r.json()["result"]["tools"]}
    params = {"name": "mi_progreso", "arguments": {}, **meta}
    r = rpc(cliente, "tools/call", params, {**h, "MCP-Protocol-Version": VERSION_MODERNA, "Mcp-Method": "tools/call",
                                            "Mcp-Name": "mi_progreso"})
    assert r.status_code == 200, r.text
    assert not r.json()["result"].get("isError")
    assert r.json()["result"]["structuredContent"]["nombre"] == "Luis García"


# --------------------------------------------------------------------------- conocimiento y permisos


def test_buscar_respeta_departamentos(cliente, bd, planta, ia):
    prod, ot = planta.deps["prod"], planta.deps["ot"]
    _doc(bd, "Atasco en la prensa 3", "Si la prensa 3 se atasca al cambiar de molde, limpiar el sensor S4 con aire.", prod)
    _doc(bd, "Costes de utillaje", "Los costes del utillaje de soldadura dependen del proveedor.", ot, 3)
    _doc(bd, "Bienvenida y PRL", "Normas de prevención de riesgos para todo el personal de la planta.", None,
         publico=True)
    bd.commit()

    error, datos = llamar(cliente, cab(cliente, "pedro"), "buscar_conocimiento", consulta="se atasca la prensa 3")
    assert not error
    titulos = [r["titulo"] for r in datos["resultados"]]
    assert titulos[0] == "Atasco en la prensa 3"
    assert datos["resultados"][0]["cita"].startswith("[1] ")
    # Pedro (Producción) no encuentra lo de Oficina técnica, ni buscándolo a propósito
    _, datos = llamar(cliente, cab(cliente, "pedro"), "buscar_conocimiento", consulta="costes del utillaje proveedor")
    assert "Costes de utillaje" not in [r["titulo"] for r in datos["resultados"]]
    # Luis (Oficina técnica, nivel 1) no ve la prensa ni los costes (nivel 3)
    _, datos = llamar(cliente, cab(cliente, "luis"), "buscar_conocimiento", consulta="prensa 3 sensor S4 costes utillaje")
    assert not {"Atasco en la prensa 3", "Costes de utillaje"} & {r["titulo"] for r in datos["resultados"]}
    # Ana (jefa de Oficina técnica, nivel 3) sí ve los costes
    _, datos = llamar(cliente, cab(cliente, "ana"), "buscar_conocimiento", consulta="costes del utillaje proveedor")
    assert "Costes de utillaje" in [r["titulo"] for r in datos["resultados"]]
    # xAPI de la búsqueda, marcada como hecha por MCP
    fila = bd.scalars(select(SentenciaXapi).where(SentenciaXapi.objeto_tipo == "busqueda")
                      .order_by(SentenciaXapi.momento.desc())).first()
    assert fila is not None and fila.contexto == {"via": "mcp"}


@pytest.mark.ia_real
def test_buscar_con_modelos_reales(cliente, bd, planta):
    """Con el modelo de embeddings real: la búsqueda por significado llega por MCP."""
    _doc(bd, "Cambio de molde en la prensa 3", "Para cambiar el molde de la prensa 3 hay que parar la máquina, "
         "bloquearla con candado, soltar las cuatro bridas y sacar el molde con el puente grúa.", planta.deps["prod"])
    bd.commit()
    error, datos = llamar(cliente, cab(cliente, "pedro"), "buscar_conocimiento",
                          consulta="¿Qué pasos sigo para sustituir el útil de la prensa?", k=3)
    assert not error
    assert datos["resultados"] and datos["resultados"][0]["titulo"] == "Cambio de molde en la prensa 3"


def test_invitado_solo_publico(cliente, bd, planta):
    prod = planta.deps["prod"]
    _doc(bd, "Atasco en la prensa 3", "Si la prensa 3 se atasca, limpiar el sensor S4 con aire.", prod)
    _doc(bd, "Normas de la prensa para visitas", "Las visitas no pueden acercarse a la prensa 3.", None, publico=True)
    bd.commit()
    h = cab(cliente, "invitado")
    error, datos = llamar(cliente, h, "buscar_conocimiento", consulta="prensa 3")
    assert not error
    titulos = {r["titulo"] for r in datos["resultados"]}
    assert "Normas de la prensa para visitas" in titulos
    assert "Atasco en la prensa 3" not in titulos  # lo de Producción no es público
    # el resto de herramientas necesita sesión
    for herramienta, args in (
        ("listar_tareas", {}), ("mi_progreso", {}), ("ver_instruccion", {"tarea": "IT-023"}),
        ("registrar_laguna", {"pregunta": "¿Cómo se ajusta la prensa?"}),
        ("proponer_aportacion", {"problema": "La prensa se atasca.", "causa": "", "solucion": "Soplar el sensor."}),
        ("espacio_listar", {}), ("espacio_leer", {"ruta": "a.md"}),
        ("espacio_escribir", {"ruta": "a.md", "contenido": "x"}), ("espacio_ejecutar", {"orden": "ls"}),
    ):
        error, texto = llamar(cliente, h, herramienta, **args)
        assert error and "iniciar sesión" in texto, herramienta
    assert bd.scalar(select(Aportacion).where(Aportacion.autor_id.is_(None))) is None


def _instruccion(bd, planta, clave: str) -> Instruccion:
    tarea = planta.tareas[clave]
    ins = bd.scalar(select(Instruccion).where(Instruccion.tarea_id == tarea.id))
    if ins is None:
        ins = Instruccion(tarea_id=tarea.id, codigo=f"{tarea.codigo}-I", version=1, estado="publicada",
                          titulo=f"Instrucción de {tarea.nombre}", riesgos="Atrapamiento")
        ins.pasos = [Paso(orden=1, titulo="Preparar la brida", texto="Limpiar la superficie."),
                     Paso(orden=2, titulo="Apretar en cruz", texto="Par de 25 N·m.", es_critico=True)]
        bd.add(ins)
        bd.commit()
    return ins


def test_tareas_e_instruccion_con_permisos(cliente, bd, planta):
    _instruccion(bd, planta, "prod")
    _instruccion(bd, planta, "ot")
    hp = cab(cliente, "pedro")
    error, datos = llamar(cliente, hp, "listar_tareas")
    assert not error
    codigos = {t["codigo"] for t in datos["tareas"]}
    assert "IT-023" in codigos and "IT-101" not in codigos
    error, datos = llamar(cliente, hp, "ver_instruccion", tarea="IT-023")
    assert not error
    assert [p["titulo"] for p in datos["pasos"]] == ["Preparar la brida", "Apretar en cruz"]
    assert datos["pasos"][1]["critico"] is True
    # Pedro no puede ver la instrucción de Oficina técnica: como si no existiera
    error, texto = llamar(cliente, hp, "ver_instruccion", tarea="IT-101")
    assert error and "No encuentro esa tarea" in texto
    # Marta tiene una formación activa en Oficina técnica: ve las dos
    error, datos = llamar(cliente, cab(cliente, "marta"), "listar_tareas")
    assert {"IT-023", "IT-101"} <= {t["codigo"] for t in datos["tareas"]}
    # también por nombre
    error, datos = llamar(cliente, cab(cliente, "marta"), "ver_instruccion", tarea="utillaje de soldadura")
    assert not error and datos["codigo_tarea"] == "IT-101"


def test_laguna_y_aportacion(cliente, bd, planta, ia):
    h = cab(cliente, "pedro")
    error, datos = llamar(cliente, h, "registrar_laguna", pregunta="¿Qué par de apriete lleva la brida C?")
    assert not error
    lg = bd.get(Laguna, datos["laguna_id"])
    assert lg is not None and lg.departamento_id == planta.deps["prod"].id

    ia.json = {}  # el modelo no ayuda: se conserva lo que dio la persona
    error, datos = llamar(cliente, h, "proponer_aportacion", problema="La prensa 3 se atasca al cambiar de molde.",
                          causa="Polvo en el sensor S4.", solucion="Soplar el sensor S4 con aire antes de arrancar.")
    assert not error, datos
    bd.expire_all()
    ap = bd.get(Aportacion, datos["aportacion_id"])
    assert ap.autor_id == planta.personas["pedro"].id
    assert ap.departamento_id == planta.deps["prod"].id
    assert ap.estado == "pendiente"
    assert ap.problema == "La prensa 3 se atasca al cambiar de molde."
    assert ap.causa == "Polvo en el sensor S4."
    assert ap.solucion == "Soplar el sensor S4 con aire antes de arrancar."
    assert ap.titulo

    error, texto = llamar(cliente, h, "proponer_aportacion", problema="", causa="", solucion="")
    assert error and "problema y la solución" in texto


@pytest.mark.parametrize("respuesta", [
    "esto no es JSON",
    ["una lista", 3],
    {"titulo": "Atasco de la prensa 3 al cambiar de molde", "problema": "Otra cosa que no dijo",
     "causa": "Inventada", "solucion": "Inventada", "etiquetas": ["prensa", 7], "nivel_minimo": 9},
])
def test_aportacion_con_modelo_que_falla(cliente, bd, planta, ia, respuesta):
    """Un modelo pequeño que devuelve JSON roto o se inventa campos: se conserva lo que contó la persona."""
    ia.json = respuesta
    campos = {"problema": "La prensa 3 se atasca al cambiar de molde.", "causa": "Polvo en el sensor S4.",
              "solucion": "Soplar el sensor S4 con aire antes de arrancar."}
    error, datos = llamar(cliente, cab(cliente, "pedro"), "proponer_aportacion", **campos)
    assert not error, datos
    bd.expire_all()
    ap = bd.get(Aportacion, datos["aportacion_id"])
    assert ap.estado == "pendiente" and ap.titulo
    assert (ap.problema, ap.causa, ap.solucion) == (campos["problema"], campos["causa"], campos["solucion"])
    assert 1 <= ap.nivel_minimo <= 4


def test_mi_progreso(cliente, planta):
    error, datos = llamar(cliente, cab(cliente, "marta"), "mi_progreso")
    assert not error
    assert datos["nombre"] == "Marta Sanz"
    assert datos["formaciones_activas"] == ["Oficina técnica"]
    assert datos["ejecuciones_completadas"] == 0


# --------------------------------------------------------------------------- espacio de trabajo


def test_espacio_por_mcp(cliente, planta):
    h = cab(cliente, "carmen")
    error, datos = llamar(cliente, h, "espacio_escribir", ruta="informes/turno.md", contenido="# Turno\n\nSin incidencias.")
    assert not error and datos["ruta"] == "informes/turno.md"
    error, datos = llamar(cliente, h, "espacio_listar", ruta="informes")
    assert [e["nombre"] for e in datos["elementos"]] == ["turno.md"]
    error, datos = llamar(cliente, h, "espacio_leer", ruta="informes/turno.md")
    assert datos["contenido"].startswith("# Turno")
    # como la ve espacio_ejecutar (/trabajo/...) y con espacios sueltos, como las dan los modelos pequeños
    error, datos = llamar(cliente, h, "espacio_leer", ruta=" /trabajo/informes/turno.md\n")
    assert not error and datos["contenido"].startswith("# Turno")
    error, datos = llamar(cliente, h, "espacio_listar", ruta="/trabajo")
    assert not error and "informes" in [e["nombre"] for e in datos["elementos"]]
    # rutas peligrosas: error de herramienta, nunca fuera de la carpeta
    for mala in ("../pedro/x.md", "/etc/passwd", "informes/../../x", "/trabajo/../pedro/x.md", "/trabajox/a.md"):
        error, texto = llamar(cliente, h, "espacio_leer", ruta=mala)
        assert error and "Ruta no válida" in texto, mala
    # otra persona no ve el fichero de Carmen
    error, texto = llamar(cliente, cab(cliente, "pedro"), "espacio_leer", ruta="informes/turno.md")
    assert error and "No existe" in texto


def test_espacio_ejecutar_por_mcp(cliente, planta, monkeypatch):
    error, texto = llamar(cliente, cab(cliente, "pedro"), "espacio_ejecutar", orden="ls")
    # Sin consola: el agente sabe que no debe reintentar y qué puede hacer en su lugar.
    assert error and "no está disponible" in texto and "espacio_escribir" in texto

    monkeypatch.setattr(ajustes(), "espacio_url", "http://ejecutor:8090")
    monkeypatch.setattr(ajustes(), "espacio_secreto", "secreto-de-pruebas")

    tiempos: list[int] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(peticion.content)
        assert cuerpo["usuario"] == "pedro"
        tiempos.append(cuerpo["tiempo_max"])
        return httpx.Response(200, json={"codigo": 0, "salida": "informe.md\n", "recortada": False, "duracion": 0.4})

    monkeypatch.setattr(espacio, "_transporte", httpx.MockTransport(responder))
    error, datos = llamar(cliente, cab(cliente, "pedro"), "espacio_ejecutar", orden="ls")
    assert not error
    assert datos["codigo_salida"] == 0 and datos["salida"] == "informe.md\n"
    assert tiempos == [espacio.TIEMPO_MAX]  # el agente tiene los 2 minutos que anuncia la herramienta


def test_fallo_inesperado_en_castellano(cliente, planta, monkeypatch):
    """Un fallo interno llega al agente como un mensaje claro, sin detalles del servidor."""
    def roto(*_a, **_k):
        raise RuntimeError("detalle interno /datos/generador-de-contenido/carmen")

    monkeypatch.setattr(espacio, "listar_carpeta", roto)
    error, texto = llamar(cliente, cab(cliente, "carmen"), "espacio_listar")
    assert error and "Algo ha fallado" in texto and "/datos" not in texto


@pytest.mark.parametrize("valor,host,esperado", [
    ("cidia.local", "cidia.local", 200),
    ("cidia.local", "cidia.local:18700", 200),
    ("cidia.local", "otro.local:18700", 421),
])
def test_lista_de_hosts(valor, host, esperado, monkeypatch, app, planta):
    """Con CIDIA_MCP_HOSTS se activa la protección de Host del SDK (se aceptan con y sin puerto)."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CIDIA_MCP_HOSTS", valor)
    with TestClient(app) as c:  # la sub-app se reconstruye en cada arranque con la variable vigente
        r = rpc(c, "tools/list", cabeceras={**cab(c, "pedro"), "Host": host})
        assert r.status_code == esperado, r.text
