"""Motor WeKnora contra un WeKnora falso en memoria (transporte httpx, sin red).

Comprueba la organización en bases y etiquetas, el indexado (texto, partes y ficheros), la
búsqueda por ámbitos con defensa en profundidad, el reetiquetado, el borrado, los mensajes
de error y la consola de documentos funcionando con este motor.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from fabrica import cab
from sqlalchemy import select, update

from cidia.config import ajustes
from cidia.conocimiento.weknora import ErrorWeKnora, MotorWeKnora
from cidia.modelos import Departamento, Documento, Empresa, Fragmento, Trabajo
from cidia.permisos import alcance_de
from cidia.rutas import documentos as rutas_documentos
from cidia.seguridad import Actor
from cidia.servicios import documentos

CLAVE = "sk-prueba"
URL = "http://weknora.prueba/api/v1"
# supportedImportFileExtensions de WeKnora v0.8.2 (internal/application/service/knowledge_util.go)
ADMITIDAS = {"pdf", "txt", "docx", "doc", "epub", "html", "htm", "mhtml", "md", "markdown", "xmind", "png", "jpg",
             "jpeg", "gif", "csv", "xlsx", "xls", "pptx", "ppt", "json", "mp3", "wav", "m4a", "flac", "ogg"}


class WeKnoraFalso:
    """Lo justo de la API de WeKnora v0.8.2 para el gateway (ver docs/investigacion/03)."""

    def __init__(self) -> None:
        self.bases: dict[str, dict[str, Any]] = {}  # id -> {nombre, etiquetas: {id: nombre}}
        self.conocimientos: dict[str, dict[str, Any]] = {}
        self.peticiones: list[tuple[str, str, Any]] = []
        self.modelos = [{"id": "emb-1", "name": "qwen3-embedding:0.6b", "type": "Embedding"},
                        {"id": "chat-1", "name": "qwen3:0.6b", "type": "KnowledgeQA"}]
        self.ignorar_filtros = False  # para probar la defensa en profundidad
        self.estado_final = "completed"
        self.transporte = httpx.MockTransport(self.manejar)

    # ------------------------------------------------------------------ utilidades

    @staticmethod
    def _id(prefijo: str) -> str:
        return f"{prefijo}-{uuid.uuid4().hex[:10]}"

    @staticmethod
    def _multipart(req: httpx.Request) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
        limite = req.headers["content-type"].split("boundary=")[1].encode()
        campos: dict[str, str] = {}
        ficheros: dict[str, tuple[str, bytes]] = {}
        for parte in req.content.split(b"--" + limite):
            if b"\r\n\r\n" not in parte:
                continue
            cabecera, _, valor = parte.partition(b"\r\n\r\n")
            valor = valor[:-2] if valor.endswith(b"\r\n") else valor
            nombre = re.search(rb'name="([^"]+)"', cabecera).group(1).decode()  # type: ignore[union-attr]
            fichero = re.search(rb'filename="([^"]*)"', cabecera)
            if fichero:
                ficheros[nombre] = (fichero.group(1).decode(), valor)
            else:
                campos[nombre] = valor.decode()
        return campos, ficheros

    def _ok(self, datos: Any = None, estado: int = 200, **extra: Any) -> httpx.Response:
        return httpx.Response(estado, json={"success": True, "data": datos, **extra})

    @staticmethod
    def _error(estado: int, mensaje: str) -> httpx.Response:
        return httpx.Response(estado, json={"success": False, "error": {"code": estado, "message": mensaje}})

    def _crear_conocimiento(self, kb: str, titulo: str, contenido: str, etiquetas: list[str],
                            hash_: str | None = None) -> dict[str, Any]:
        k = {"id": self._id("k"), "knowledge_base_id": kb, "title": titulo, "content": contenido,
             "tags": [t for t in etiquetas if t], "parse_status": "pending", "sondeos": 1, "hash": hash_}
        self.conocimientos[k["id"]] = k
        return k

    def _publico(self, k: dict[str, Any]) -> dict[str, Any]:
        return {c: v for c, v in k.items() if c not in ("content", "sondeos", "hash")}

    def _trozos(self, k: dict[str, Any]) -> list[dict[str, Any]]:
        partes = [p.strip() for p in re.split(r"\n\s*\n", k["content"]) if p.strip()]
        return [{"id": f"{k['id']}-c{i}", "content": p, "chunk_index": i, "knowledge_id": k["id"]}
                for i, p in enumerate(partes)]

    # ------------------------------------------------------------------ rutas

    def manejar(self, req: httpx.Request) -> httpx.Response:
        req.read()
        ruta = req.url.path
        if ruta == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if req.headers.get("x-api-key") != CLAVE:
            return httpx.Response(401, json={"error": "Unauthorized"})
        ruta = ruta.removeprefix("/api/v1")
        es_json = req.headers.get("content-type", "").startswith("application/json")
        cuerpo = json.loads(req.content) if es_json else None
        self.peticiones.append((req.method, ruta, cuerpo))
        m = req.method

        if (m, ruta) == ("GET", "/models"):
            return self._ok(self.modelos)
        if (m, ruta) == ("GET", "/knowledge-bases"):
            return self._ok([{"id": i, "name": b["nombre"]} for i, b in self.bases.items()])
        if (m, ruta) == ("POST", "/knowledge-bases"):
            assert cuerpo["embedding_model_id"] == "emb-1"
            kb = self._id("kb")
            self.bases[kb] = {"nombre": cuerpo["name"], "etiquetas": {}}
            return self._ok({"id": kb, "name": cuerpo["name"]}, 201)
        if g := re.fullmatch(r"/knowledge-bases/([^/]+)/tags", ruta):
            base = self.bases.get(g.group(1))
            if base is None:
                return self._error(404, "knowledge base not found")
            if m == "GET":
                lista = [{"id": i, "name": n} for i, n in base["etiquetas"].items()]
                return self._ok({"total": len(lista), "page": 1, "page_size": 100, "data": lista})
            tid = self._id("t")
            base["etiquetas"][tid] = cuerpo["name"]
            return self._ok({"id": tid, "name": cuerpo["name"], "seq_id": len(base["etiquetas"])})
        if g := re.fullmatch(r"/knowledge-bases/([^/]+)/knowledge/manual", ruta):
            assert cuerpo["status"] == "publish"
            k = self._crear_conocimiento(g.group(1), cuerpo["title"], cuerpo["content"], cuerpo["tag_ids"])
            return self._ok(self._publico(k))
        if g := re.fullmatch(r"/knowledge-bases/([^/]+)/knowledge/file", ruta):
            campos, ficheros = self._multipart(req)
            nombre, datos = ficheros["file"]
            if nombre.rsplit(".", 1)[-1].lower() not in ADMITIDAS:  # como validateImportFileType
                return self._error(400, f"不支持的文件类型: {nombre.rsplit('.', 1)[-1]}")
            h = hashlib.sha256(datos).hexdigest()
            repetido = next((k for k in self.conocimientos.values()
                             if k["knowledge_base_id"] == g.group(1) and k["hash"] == h), None)
            if repetido:
                return httpx.Response(409, json={"success": False, "message": "duplicate", "code": "duplicate_file",
                                                 "data": self._publico(repetido)})
            k = self._crear_conocimiento(g.group(1), nombre, datos.decode("utf-8", "ignore"),
                                         campos.get("tag_ids", "").split(","), h)
            k["metadata"] = campos.get("metadata")
            return self._ok(self._publico(k))
        if (m, ruta) == ("PUT", "/knowledge/tags"):
            for kid, etiquetas in cuerpo["updates"].items():
                self.conocimientos[kid]["tags"] = etiquetas
            return httpx.Response(200, json={"success": True})
        if g := re.fullmatch(r"/knowledge/([^/]+)", ruta):
            k = self.conocimientos.get(g.group(1))
            if k is None:
                return self._error(404, "knowledge not found")
            if m == "DELETE":
                del self.conocimientos[k["id"]]
                return self._ok({"task_id": "t1"}, message="Delete task submitted")
            if k["sondeos"] > 0:  # la primera consulta encuentra el documento aún procesándose
                k["sondeos"] -= 1
                k["parse_status"] = "processing"
            else:
                k["parse_status"] = self.estado_final
                k["error_message"] = "no se ha podido leer" if self.estado_final == "failed" else ""
            return self._ok(self._publico(k))
        if g := re.fullmatch(r"/chunks/([^/]+)", ruta):
            trozos = self._trozos(self.conocimientos[g.group(1)])
            pagina, tam = int(req.url.params["page"]), int(req.url.params["page_size"])
            return self._ok(trozos[(pagina - 1) * tam: pagina * tam], total=len(trozos))
        if (m, ruta) == ("POST", "/knowledge-search"):
            return self._ok(self._buscar(cuerpo))
        return self._error(404, f"ruta no simulada: {m} {ruta}")

    def _buscar(self, cuerpo: dict[str, Any]) -> list[dict[str, Any]]:
        palabras = [p for p in re.findall(r"\w+", cuerpo["query"].lower()) if len(p) >= 3]
        resultados = []
        for k in self.conocimientos.values():
            if k["parse_status"] not in ("completed", "finalizing"):
                continue
            if not self.ignorar_filtros:
                if k["knowledge_base_id"] not in cuerpo["knowledge_base_ids"]:
                    continue
                if cuerpo.get("tag_ids") and not set(cuerpo["tag_ids"]) & set(k["tags"]):
                    continue
            for t in self._trozos(k):
                puntos = sum(t["content"].lower().count(p) for p in palabras)
                if puntos:
                    resultados.append({"id": t["id"], "content": t["content"], "score": float(puntos),
                                       "knowledge_id": k["id"], "knowledge_title": k["title"],
                                       "knowledge_base_id": k["knowledge_base_id"],
                                       "chunk_index": t["chunk_index"], "match_type": 1})
        return sorted(resultados, key=lambda r: -r["score"])[:10]

    # ------------------------------------------------------------------ consultas para las pruebas

    def busquedas(self) -> list[dict[str, Any]]:
        return [c for m, r, c in self.peticiones if (m, r) == ("POST", "/knowledge-search")]

    def nombres_etiquetas(self, k: dict[str, Any]) -> set[str]:
        return {self.bases[k["knowledge_base_id"]]["etiquetas"][t] for t in k["tags"]}

    def base_de(self, nombre: str) -> str:
        return next(i for i, b in self.bases.items() if b["nombre"] == nombre)


# --------------------------------------------------------------------------- fixtures


def _olvidar_weknora(bd) -> None:
    """Borra de la BD los ids de bases y modelos de un WeKnora anterior."""
    bd.execute(update(Departamento).values(weknora_kb_id=None))
    for e in bd.scalars(select(Empresa)).all():
        e.config = {c: v for c, v in (e.config or {}).items() if not c.startswith("weknora_")}
    bd.commit()


@pytest.fixture
def wk(app, bd, planta, monkeypatch):
    """WeKnora falso + motor conectado a él, y servicios/rutas de documentos usando ese motor."""
    _olvidar_weknora(bd)
    falso = WeKnoraFalso()
    m = MotorWeKnora(url=URL, api_key=CLAVE, transporte=falso.transporte, intervalo=0)
    monkeypatch.setattr(documentos, "motor", lambda: m)
    monkeypatch.setattr(rutas_documentos, "motor", lambda: m)
    return falso, m


def _doc(bd, titulo: str, texto: str, dep=None, nivel: int = 1, formacion: bool = False, publico: bool = False,
         partes=None) -> Documento:
    d = documentos.crear_desde_texto(bd, titulo, texto, departamento_id=dep.id if dep else None, nivel_minimo=nivel,
                                     es_formacion=formacion, es_publico=publico, partes=partes,
                                     en_segundo_plano=False)
    bd.commit()
    return d


def _actor(planta, usuario: str) -> Actor:
    return Actor(sesion=None, usuario=planta.personas[usuario])  # type: ignore[arg-type]


# --------------------------------------------------------------------------- indexado


def test_indexar_crea_base_etiquetas_y_fragmentos(wk, bd, planta):
    falso, m = wk
    prod = planta.deps["prod"]
    d = _doc(bd, "Engrase del husillo", "Engrasar el husillo cada 40 horas.\n\nUsar grasa de litio EP2.",
             prod, nivel=2, formacion=True)
    assert d.estado == "listo" and d.fragmentos_n == 2 and d.motor_id in falso.conocimientos
    bd.refresh(prod)
    assert prod.weknora_kb_id and falso.bases[prod.weknora_kb_id]["nombre"] == "Producción"
    k = falso.conocimientos[d.motor_id]
    assert k["knowledge_base_id"] == prod.weknora_kb_id
    assert falso.nombres_etiquetas(k) == {"n2", "formacion"}
    # esperó a que WeKnora terminase (una consulta «processing» y otra «completed»)
    assert len([r for mt, r, _ in falso.peticiones if mt == "GET" and r == f"/knowledge/{d.motor_id}"]) == 2
    frags = bd.scalars(select(Fragmento).where(Fragmento.documento_id == d.id).order_by(Fragmento.orden)).all()
    assert [f.texto for f in frags] == ["Engrasar el husillo cada 40 horas.", "Usar grasa de litio EP2."]
    assert frags[0].embedding is None and frags[0].metadatos["wk_chunk_id"] == f"{d.motor_id}-c0"
    bd.expire_all()
    assert bd.scalar(select(Empresa)).config["weknora_modelo_embeddings"] == "emb-1"
    # un segundo documento reutiliza base, etiquetas y modelo
    _doc(bd, "Cambio de grasa", "Cambiar la grasa del husillo una vez al año.", prod, nivel=2)
    assert len(falso.bases) == 1 and len([p for p in falso.peticiones if p[1] == "/models"]) == 1


def test_publico_y_sin_departamento(wk, bd, planta):
    falso, m = wk
    pub = _doc(bd, "Bienvenida y PRL", "Normas de seguridad de la planta.", None, publico=True)
    general = _doc(bd, "Plan estratégico", "Documento solo para la administración.", None, nivel=4)
    bd.expire_all()
    kb_pub = bd.scalar(select(Empresa)).config["weknora_kb_publico"]
    assert falso.bases[kb_pub]["nombre"] == "Público"
    assert falso.nombres_etiquetas(falso.conocimientos[pub.motor_id]) == {"publico"}
    k = falso.conocimientos[general.motor_id]
    assert k["knowledge_base_id"] == kb_pub and falso.nombres_etiquetas(k) == {"n4"}
    # el invitado busca solo lo etiquetado «publico» y no encuentra el plan estratégico
    invitado = Actor(sesion=None, usuario=None)  # type: ignore[arg-type]
    res = m.buscar(bd, "documento normas seguridad plan", alcance_de(bd, invitado))
    assert {r.titulo for r in res} == {"Bienvenida y PRL"}
    assert all(b.get("tag_ids") for b in falso.busquedas())


def test_las_partes_conservan_sus_metadatos(wk, bd, planta):
    falso, m = wk
    d = _doc(bd, "IT-023 Montaje de la brida B", "", planta.deps["prod"], partes=[
        ("Limpiar el asiento de la brida con un trapo sin pelusa.", {"paso": 1, "paso_id": 11}),
        ("Apretar los tornillos de la brida en cruz a 25 Nm.", {"paso": 2, "paso_id": 12}),
    ])
    assert d.fragmentos_n == 2
    res = m.buscar(bd, "¿A cuánto aprieto los tornillos de la brida?", alcance_de(bd, _actor(planta, "pedro")))
    primero = res[0]
    assert primero.documento_id == d.id and primero.metadatos["paso"] == 2 and primero.metadatos["paso_id"] == 12
    assert primero.metadatos["tipo"] == "texto" and primero.metadatos["coincidencia_texto"] is True
    assert isinstance(primero.fragmento_id, int) and primero.similitud is not None and primero.puntuacion > 0


def test_subida_de_fichero_y_duplicado(wk, bd, planta, cliente):
    falso, m = wk
    h = cab(cliente, "javier")
    r = cliente.post("/api/documentos", headers=h, files={"fichero": ("atasco.txt", b"Prensa 3 atascada: limpiar S4.")},
                     data={"titulo": "Atasco prensa 3"})
    assert r.status_code == 201 and r.json()["estado"] == "listo", r.text
    k = falso.conocimientos[r.json()["motor_id"]]
    assert falso.nombres_etiquetas(k) == {"n1"} and f'"{r.json()["id"]}"' in k["metadata"]
    # el mismo fichero otra vez: WeKnora responde 409 y el gateway lo explica
    r2 = cliente.post("/api/documentos", headers=h, files={"fichero": ("copia.txt", b"Prensa 3 atascada: limpiar S4.")},
                      data={"titulo": "Copia"})
    assert r2.json()["estado"] == "error" and "Atasco prensa 3" in r2.json()["mensaje_estado"]


# --------------------------------------------------------------------------- búsqueda


def _juego_de_documentos(bd, planta) -> dict[str, Documento]:
    prod, ot = planta.deps["prod"], planta.deps["ot"]
    return {
        "prod1": _doc(bd, "Atasco de la prensa 3", "La prensa 3 se atasca: limpiar el sensor S4.", prod, 1),
        "prod3": _doc(bd, "Costes de la prensa 3", "La prensa 3 cuesta 900 euros al mes.", prod, 3),
        "ot_form": _doc(bd, "Iniciación: prensa 3 y utillajes", "Utillajes para la prensa 3.", ot, 1, formacion=True),
        "ot2": _doc(bd, "Diseño de utillaje para la prensa 3", "Diseño del utillaje de la prensa 3.", ot, 2),
        "pub": _doc(bd, "PRL de la prensa 3", "La prensa 3 exige guantes y gafas.", None, publico=True),
    }


def test_buscar_solo_en_los_ambitos_permitidos(wk, bd, planta):
    falso, m = wk
    docs = _juego_de_documentos(bd, planta)
    bd.refresh(planta.deps["ot"])
    kb_ot = planta.deps["ot"].weknora_kb_id

    falso.peticiones.clear()
    res = m.buscar(bd, "prensa 3", alcance_de(bd, _actor(planta, "pedro")), k=10)
    assert {r.documento_id for r in res} == {docs["prod1"].id, docs["pub"].id}
    busquedas = falso.busquedas()
    assert all(len(b["knowledge_base_ids"]) == 1 and b["tag_ids"] for b in busquedas)
    assert kb_ot not in {b["knowledge_base_ids"][0] for b in busquedas}
    etiquetas_prod = next(b["tag_ids"] for b in busquedas if b["knowledge_base_ids"][0] == planta.deps["prod"].weknora_kb_id)
    assert {falso.bases[planta.deps["prod"].weknora_kb_id]["etiquetas"][t] for t in etiquetas_prod} == {"n1"}

    # marta: nivel 2 en producción y formación activa en oficina técnica
    falso.peticiones.clear()
    res = m.buscar(bd, "prensa 3", alcance_de(bd, _actor(planta, "marta")), k=10)
    assert {r.documento_id for r in res} == {docs["prod1"].id, docs["ot_form"].id, docs["pub"].id}
    b_ot = next(b for b in falso.busquedas() if b["knowledge_base_ids"] == [kb_ot])
    assert {falso.bases[kb_ot]["etiquetas"][t] for t in b_ot["tag_ids"]} == {"formacion"}

    # la administración busca en todas las bases sin etiquetas
    falso.peticiones.clear()
    res = m.buscar(bd, "prensa 3", alcance_de(bd, _actor(planta, "admin")), k=20)
    assert {r.documento_id for r in res} >= set(d.id for d in docs.values())
    assert all("tag_ids" not in b for b in falso.busquedas()) and len(falso.busquedas()) == 3


def test_defensa_en_profundidad(wk, bd, planta):
    """Aunque WeKnora devolviera de más (etiquetas mal puestas), el gateway filtra con la BD."""
    falso, m = wk
    docs = _juego_de_documentos(bd, planta)
    falso.ignorar_filtros = True
    res = m.buscar(bd, "prensa 3", alcance_de(bd, _actor(planta, "pedro")), k=20)
    assert {r.documento_id for r in res} == {docs["prod1"].id, docs["pub"].id}
    # un documento que deja de estar listo tampoco sale
    docs["prod1"].estado = "error"
    bd.commit()
    res = m.buscar(bd, "prensa 3", alcance_de(bd, _actor(planta, "pedro")), k=20)
    assert {r.documento_id for r in res} == {docs["pub"].id}


def test_alcance_sin_bases_no_pregunta_a_weknora(wk, bd, planta):
    falso, m = wk
    assert m.buscar(bd, "prensa", alcance_de(bd, _actor(planta, "luis"))) == []
    assert falso.busquedas() == [] and m.buscar(bd, "   ", alcance_de(bd, _actor(planta, "admin"))) == []


# --------------------------------------------------------------------------- etiquetas y borrado


def test_reetiquetar_y_mover(wk, bd, planta):
    falso, m = wk
    d = _doc(bd, "Ajuste del tope", "Ajustar el tope de la prensa 5.", planta.deps["prod"], 1)
    d.nivel_minimo = 2
    d.es_formacion = True
    assert m.reetiquetar(bd, d) is True
    assert falso.nombres_etiquetas(falso.conocimientos[d.motor_id]) == {"n2", "formacion"}
    d.departamento_id = planta.deps["ot"].id
    assert m.reetiquetar(bd, d) is False  # cambia de base: hay que reindexar
    d.departamento_id = planta.deps["prod"].id
    d.es_publico = True
    assert m.reetiquetar(bd, d) is False
    bd.rollback()


def test_editar_y_borrar_desde_la_consola(wk, bd, planta, cliente):
    falso, m = wk
    h = cab(cliente, "admin")
    r = cliente.post("/api/documentos", headers=h, files={"fichero": ("tope.txt", b"Ajuste del tope de la prensa 5.")},
                     data={"departamento_id": str(planta.deps["prod"].id)})
    d = r.json()
    antiguo = d["motor_id"]
    # cambiar el nivel: se reetiqueta en su sitio
    r = cliente.patch(f"/api/documentos/{d['id']}", headers=h, json={"nivel_minimo": 3})
    assert r.status_code == 200 and r.json()["motor_id"] == antiguo
    assert falso.nombres_etiquetas(falso.conocimientos[antiguo]) == {"n3"}
    # moverlo a otro departamento: se reindexa en la base de destino
    r = cliente.patch(f"/api/documentos/{d['id']}", headers=h, json={"departamento_id": planta.deps["ot"].id})
    assert r.status_code == 200 and r.json()["estado"] == "listo"
    nuevo = r.json()["motor_id"]
    assert nuevo != antiguo and antiguo not in falso.conocimientos
    assert falso.bases[falso.conocimientos[nuevo]["knowledge_base_id"]]["nombre"] == "Oficina técnica"
    # la consola de búsqueda muestra los ámbitos consultados
    r = cliente.post("/api/documentos/probar-busqueda", headers=h, json={"consulta": "tope prensa 5"})
    assert r.json()["motor"] == "weknora" and r.json()["ambitos"]
    assert d["id"] in {x["documento_id"] for x in r.json()["resultados"]}
    det = cliente.get(f"/api/documentos/{d['id']}", headers=h).json()
    assert det["fragmentos_muestra"][0]["metadatos"]["wk_chunk_id"].startswith(nuevo)
    # borrar
    assert cliente.delete(f"/api/documentos/{d['id']}", headers=h).status_code == 200
    assert nuevo not in falso.conocimientos and ("DELETE", f"/knowledge/{nuevo}", None) in falso.peticiones


def test_preparar_bases(wk, bd, planta):
    falso, m = wk
    salida = m.preparar_bases(bd, modelo_embeddings_id="emb-1")
    bd.commit()
    assert set(salida["departamentos"]) >= {"Producción", "Oficina técnica"}
    kb_prod = salida["departamentos"]["Producción"]
    assert set(falso.bases[kb_prod]["etiquetas"].values()) >= {"n1", "n2", "n3", "n4", "formacion"}
    assert "publico" in falso.bases[salida["publico"]]["etiquetas"].values()
    # idempotente
    antes = len(falso.bases)
    m.preparar_bases(bd)
    assert len(falso.bases) == antes


# --------------------------------------------------------------------------- errores y salud


def test_errores_con_mensajes_claros(wk, bd, planta):
    falso, m = wk
    prod = planta.deps["prod"]

    sin_clave = MotorWeKnora(url=URL, api_key="", transporte=falso.transporte, intervalo=0)
    with pytest.raises(ErrorWeKnora, match="Falta la API key"):
        sin_clave.buscar(bd, "prensa", alcance_de(bd, _actor(planta, "admin")))

    clave_mala = MotorWeKnora(url=URL, api_key="sk-mala", transporte=falso.transporte, intervalo=0)
    with pytest.raises(ErrorWeKnora, match="rechazado la API key"):
        clave_mala.indexar(bd, Documento(id=0, titulo="x", tipo="texto", departamento_id=prod.id, nivel_minimo=1,
                                         es_formacion=False, es_publico=False), texto="hola")
    bd.rollback()

    def caido(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("conexión rechazada", request=req)

    sin_red = MotorWeKnora(url=URL, api_key=CLAVE, transporte=httpx.MockTransport(caido), intervalo=0)
    with pytest.raises(ErrorWeKnora, match="No se puede conectar con WeKnora"):
        sin_red.base_departamento(bd, prod)
    assert sin_red.salud()["ok"] is False and "No se puede conectar" in sin_red.salud()["error"]

    # el fallo de procesado en WeKnora llega al documento como estado de error legible
    falso.estado_final = "failed"
    d = _doc(bd, "Roto", "Texto que WeKnora no procesa.", prod)
    assert d.estado == "error" and "no ha podido procesar" in d.mensaje_estado

    # sin modelo de embeddings en WeKnora no se puede crear la base
    falso.estado_final = "completed"
    falso.modelos = []
    _olvidar_weknora(bd)
    otro = MotorWeKnora(url=URL, api_key=CLAVE, transporte=falso.transporte, intervalo=0)
    with pytest.raises(ErrorWeKnora, match="ningún modelo de embeddings"):
        otro.base_departamento(bd, prod)
    bd.rollback()


def test_espera_con_limite(wk, bd, planta):
    falso, _ = wk
    lento = MotorWeKnora(url=URL, api_key=CLAVE, transporte=falso.transporte, intervalo=0, espera_max=0)
    d = Documento(titulo="Lento", tipo="texto", departamento_id=planta.deps["prod"].id, nivel_minimo=1,
                  es_formacion=False, es_publico=False, estado="procesando")
    bd.add(d)
    bd.flush()
    with pytest.raises(ErrorWeKnora, match="sigue procesando"):
        lento.indexar(bd, d, texto="Texto que tarda en procesarse.")
    assert d.motor_id  # queda anotado para poder borrarlo después
    bd.rollback()


def test_salud(wk):
    falso, m = wk
    s = m.salud()
    assert s["ok"] is True and s["motor"] == "weknora" and s["url"] == URL and "sk-" not in str(s)


# --------------------------------------------------------------------------- revisión: casos límite


def test_formato_no_admitido_por_weknora_se_sube_como_texto(wk, bd, planta, cliente):
    """WeKnora rechaza p. ej. .log: el gateway extrae el texto en local y lo sube como texto."""
    falso, m = wk
    r = cliente.post("/api/documentos", headers=cab(cliente, "javier"),
                     files={"fichero": ("prensa.log", b"10:02 prensa 3 parada por atasco del sensor S4.")},
                     data={"titulo": "Registro de la prensa 3"})
    assert r.status_code == 201 and r.json()["estado"] == "listo", r.json().get("mensaje_estado")
    rutas = [ruta for _, ruta, _ in falso.peticiones]
    assert any(x.endswith("/knowledge/manual") for x in rutas) and not any(x.endswith("/knowledge/file") for x in rutas)
    assert "sensor S4" in falso.conocimientos[r.json()["motor_id"]]["content"]


def test_etiquetas_y_borrado_esperan_al_indexado(wk, bd, planta, cliente):
    """Con WeKnora, cambiar quién lo encuentra o borrar durante un indexado dejaría etiquetas
    antiguas o un conocimiento huérfano: se responde 409 hasta que termine."""
    falso, m = wk
    h = cab(cliente, "admin")
    d = cliente.post("/api/documentos", headers=h, files={"fichero": ("tope5.txt", b"Ajuste del tope de la prensa 5.")},
                     data={"departamento_id": str(planta.deps["prod"].id)}).json()
    t = Trabajo(tipo="indexar_documento", entidad="documento", entidad_id=d["id"], estado="en_curso")
    bd.add(t)
    bd.commit()
    try:
        r = cliente.patch(f"/api/documentos/{d['id']}", headers=h, json={"nivel_minimo": 2})
        assert r.status_code == 409 and "indexando" in r.json()["detail"]
        assert cliente.patch(f"/api/documentos/{d['id']}", headers=h, json={"titulo": "Tope de la prensa 5"}).status_code == 200
        assert cliente.delete(f"/api/documentos/{d['id']}", headers=h).status_code == 409
        assert d["motor_id"] in falso.conocimientos
    finally:
        t.estado = "completado"
        bd.commit()
    assert cliente.delete(f"/api/documentos/{d['id']}", headers=h).status_code == 200
    assert d["motor_id"] not in falso.conocimientos


def test_manda_la_base_guardada_en_la_bd(wk, bd, planta):
    """Si inicializar.py (otro proceso) cambia la base de un departamento, el motor no se queda
    con la que tenía en caché."""
    falso, m = wk
    prod = planta.deps["prod"]
    primera = m.base_departamento(bd, prod)
    publica = m.base_publica(bd)
    bd.commit()
    otra = m._crear_base(bd, "Producción (nueva)", "Base recreada")
    otra_publica = m._crear_base(bd, "Público (nueva)", "Base recreada")
    prod.weknora_kb_id = otra
    e = bd.scalar(select(Empresa))
    e.config = {**(e.config or {}), "weknora_kb_publico": otra_publica}
    bd.commit()
    assert m.base_departamento(bd, prod) == otra != primera
    assert m.base_publica(bd) == otra_publica != publica


# --------------------------------------------------------------------------- inicializar.py


def _inicializar():
    """Carga servidor/weknora/inicializar.py como módulo (no está en el paquete cidia)."""
    ruta = Path(__file__).resolve().parents[2] / "weknora" / "inicializar.py"
    spec = importlib.util.spec_from_file_location("inicializar_weknora", ruta)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_inicializar_espera_al_modelo_con_la_lista():
    """El estado del modelo se lee de GET /models: GET /models/{id} da 500 mientras se descarga."""
    ini = _inicializar()
    modelos: list[dict[str, Any]] = []
    sondeos = {"n": 0}

    def manejar(req: httpx.Request) -> httpx.Response:
        ruta = req.url.path.removeprefix("/api/v1")
        if (req.method, ruta) == ("GET", "/models"):
            if modelos:
                sondeos["n"] += 1
                if sondeos["n"] >= 2:
                    modelos[0]["status"] = "active"
            return httpx.Response(200, json={"success": True, "data": modelos})
        if (req.method, ruta) == ("POST", "/models"):
            modelos.append({"id": "m1", "name": json.loads(req.content)["name"], "type": "Embedding",
                            "status": "downloading"})
            return httpx.Response(201, json={"success": True, "data": {"id": "m1"}})
        if ruta.startswith("/models/"):
            return httpx.Response(500, json={"success": False, "error": {"message": "model is currently downloading"}})
        return httpx.Response(404, json={})

    http = httpx.Client(base_url=URL, transport=httpx.MockTransport(manejar))
    cuerpo = {"name": "qwen3-embedding:0.6b", "type": "Embedding", "source": "local"}
    # si no está en Ollama, no se da de alta (quedaría «activo» sin existir o intentaría descargarse)
    with pytest.raises(ini.Fallo, match="no está en Ollama"):
        ini.asegurar_modelo(http, cuerpo, 5, presentes={"qwen3:0.6b"}, intervalo=0)
    assert modelos == []
    assert ini.asegurar_modelo(http, cuerpo, 5, presentes={"qwen3-embedding:0.6b"}, intervalo=0) == "m1"
    assert modelos[0]["status"] == "active" and sondeos["n"] == 2
    # ya dado de alta: se reutiliza
    assert ini.asegurar_modelo(http, cuerpo, 5, presentes=None, intervalo=0) == "m1" and len(modelos) == 1


def test_inicializar_guarda_la_clave_sin_imprimirla(capsys):
    ini = _inicializar()
    # Carpeta propia dentro de los datos de prueba (el tmp_path de pytest no siempre es accesible).
    carpeta = ajustes().dir_datos / f"inicializar-{uuid.uuid4().hex[:8]}"
    fichero = carpeta / "secretos" / "cidia.env"
    fichero.parent.mkdir(parents=True)
    fichero.write_text("OTRA_VARIABLE=1\nCIDIA_WEKNORA_API_KEY=sk-vieja\n", encoding="utf-8")
    ini.guardar_clave(fichero, "sk-nueva-123", "env")
    texto = fichero.read_text(encoding="utf-8")
    assert "OTRA_VARIABLE=1" in texto and texto.count("CIDIA_WEKNORA_API_KEY=") == 1 and "sk-vieja" not in texto
    assert ini.leer_clave(fichero) == "sk-nueva-123"
    solo = carpeta / "clave.txt"
    ini.guardar_clave(solo, "sk-solo", "clave")
    assert ini.leer_clave(solo) == "sk-solo"
    assert sorted(p.name for p in fichero.parent.iterdir()) == ["cidia.env"]  # sin temporales
    salida = capsys.readouterr()
    assert "sk-" not in salida.out + salida.err
    if os.name != "nt":
        assert (fichero.stat().st_mode & 0o777) == 0o600
