"""Pruebas de la API compatible con OpenAI (/v1): modelos permitidos, proxy con y sin streaming."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fabrica import cab
from sqlalchemy import select

from cidia.config import ajustes
from cidia.modelos import ModeloIA, SentenciaXapi
from cidia.rutas import openai as rutas_openai

SSE = (
    b'data: {"id":"c1","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hola"}}]}\n\n'
    b'data: {"id":"c1","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" mundo"}}]}\n\n'
    b"data: [DONE]\n\n"
)


class Proveedor:
    """Servidor de modelos falso: guarda lo que recibe y contesta con JSON o con SSE."""

    def __init__(self) -> None:
        self.peticiones: list[dict[str, Any]] = []
        self.estado = 200

    def manejar(self, request: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(request.content)
        self.peticiones.append({"url": str(request.url), "cuerpo": cuerpo,
                                "autorizacion": request.headers.get("authorization")})
        if self.estado != 200:
            return httpx.Response(self.estado, json={"error": {"message": "modelo caído", "type": "api_error"}})
        if cuerpo.get("stream"):
            return httpx.Response(200, content=SSE, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "id": "c1", "object": "chat.completion", "model": cuerpo["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hola"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 1, "total_tokens": 8},
        })

    @property
    def ultimo(self) -> dict[str, Any]:
        return self.peticiones[-1]["cuerpo"]


@pytest.fixture
def proveedor(monkeypatch) -> Proveedor:
    p = Proveedor()
    monkeypatch.setattr(rutas_openai, "_cliente_http",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(p.manejar)))
    return p


def _chat(cliente, h, **cuerpo):
    cuerpo.setdefault("messages", [{"role": "user", "content": "Hola"}])
    return cliente.post("/v1/chat/completions", json=cuerpo, headers=h)


def test_models_solo_permitidos(cliente, planta):
    r = cliente.get("/v1/models", headers=cab(cliente, "luis"))
    assert r.status_code == 200
    d = r.json()
    ids = [m["id"] for m in d["data"]]
    assert d["object"] == "list" and ajustes().llm_modelo_chat in ids
    assert "openai" not in ids and "deepseek" not in ids  # modelos en la nube bloqueados
    assert all(m["object"] == "model" for m in d["data"])
    assert any(m["default"] for m in d["data"])
    # También para invitados, pero no sin sesión.
    assert cliente.get("/v1/models", headers=cab(cliente, "invitado")).status_code == 200
    assert cliente.get("/v1/models").status_code == 401


def test_chat_sin_streaming(cliente, bd, planta, proveedor):
    h = cab(cliente, "luis")
    herramientas = [{"type": "function", "function": {"name": "leer", "parameters": {"type": "object"}}}]
    r = _chat(cliente, h, model=ajustes().llm_modelo_chat, tools=herramientas, tool_choice="auto", temperature=0.3)
    assert r.status_code == 200, r.text
    assert r.json()["choices"][0]["message"]["content"] == "Hola"
    enviado = proveedor.ultimo
    assert "tool_choice" not in enviado  # Ollama no lo admite
    assert enviado["tools"] == herramientas and enviado["temperature"] == 0.3
    assert enviado["model"] == ajustes().llm_modelo_chat
    assert enviado["reasoning_effort"] == "none"
    assert proveedor.peticiones[-1]["url"] == ajustes().llm_base_url.rstrip("/") + "/chat/completions"
    assert proveedor.peticiones[-1]["autorizacion"] == f"Bearer {ajustes().llm_api_key}"
    uso = bd.scalars(select(SentenciaXapi).where(SentenciaXapi.verbo == "uso_modelo")
                     .order_by(SentenciaXapi.momento.desc())).first()
    assert uso is not None and uso.actor_id == planta.personas["luis"].id
    assert uso.resultado["tokens"]["total_tokens"] == 8 and uso.resultado["herramientas"] == 1


def test_chat_streaming_transparente(cliente, planta, proveedor):
    h = cab(cliente, "pedro")
    with cliente.stream("POST", "/v1/chat/completions", headers=h,
                        json={"messages": [{"role": "user", "content": "Hola"}], "stream": True}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        contenido = r.read()
    assert contenido == SSE
    # Sin modelo: el predeterminado.
    assert proveedor.ultimo["model"] == ajustes().llm_modelo_chat and proveedor.ultimo["stream"] is True


def test_modelos_no_permitidos(cliente, planta, proveedor):
    h = cab(cliente, "luis")
    for modelo in ("openai", "gpt-4o", "inventado:7b"):
        r = _chat(cliente, h, model=modelo)
        assert r.status_code == 403, modelo
        assert "no está permitido" in r.json()["error"]["message"]
    r = _chat(cliente, h, model="openai", stream=True)
    assert r.status_code == 403
    assert proveedor.peticiones == []  # no se llega a llamar al proveedor
    assert cliente.post("/v1/chat/completions", json={"messages": []}, headers=h).status_code == 400
    assert cliente.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "x"}]}).status_code == 401


def test_modelo_por_nombre_visible_y_alias(cliente, bd, planta, proveedor):
    if not bd.scalar(select(ModeloIA).where(ModeloIA.ref == "rapido:1b")):
        bd.add(ModeloIA(nombre="Modelo rápido", ref="rapido:1b", tipo="chat", permitido=True))
        bd.commit()
    h = cab(cliente, "luis")
    assert _chat(cliente, h, model="Modelo rápido").status_code == 200
    assert proveedor.ultimo["model"] == "rapido:1b"
    assert _chat(cliente, h, model="cidia").status_code == 200
    assert proveedor.ultimo["model"] == ajustes().llm_modelo_chat
    ids = [m["id"] for m in cliente.get("/v1/models", headers=h).json()["data"]]
    assert "rapido:1b" in ids
    # Si la administración lo bloquea, deja de estar disponible.
    m = bd.scalar(select(ModeloIA).where(ModeloIA.ref == "rapido:1b"))
    m.permitido = False
    bd.commit()
    assert _chat(cliente, h, model="rapido:1b").status_code == 403
    assert "rapido:1b" not in [m["id"] for m in cliente.get("/v1/models", headers=h).json()["data"]]
    bd.delete(m)  # la tabla de modelos la comparten las pruebas de administración
    bd.commit()


def test_invitado_max_tokens_acotado(cliente, planta, proveedor):
    h = cab(cliente, "invitado")
    assert _chat(cliente, h, max_tokens=50000).status_code == 200
    assert proveedor.ultimo["max_tokens"] == rutas_openai.MAX_TOKENS_INVITADO
    assert _chat(cliente, h).status_code == 200
    assert proveedor.ultimo["max_tokens"] == rutas_openai.MAX_TOKENS_INVITADO
    assert _chat(cliente, h, max_tokens=100).status_code == 200
    assert proveedor.ultimo["max_tokens"] == 100
    # Valores raros no se cuelan: se cambian por el tope.
    assert _chat(cliente, h, max_tokens=True, max_completion_tokens="99999").status_code == 200
    assert proveedor.ultimo["max_tokens"] == rutas_openai.MAX_TOKENS_INVITADO
    assert proveedor.ultimo["max_completion_tokens"] == rutas_openai.MAX_TOKENS_INVITADO
    assert _chat(cliente, h, max_completion_tokens=50000).status_code == 200
    assert proveedor.ultimo["max_completion_tokens"] == rutas_openai.MAX_TOKENS_INVITADO
    # Varias respuestas a la vez multiplicarían el tope: una sola.
    assert _chat(cliente, h, n=8).status_code == 200
    assert proveedor.ultimo["n"] == 1
    # Un usuario con sesión no tiene esos topes.
    assert _chat(cliente, cab(cliente, "luis"), max_tokens=50000, n=2).status_code == 200
    assert proveedor.ultimo["max_tokens"] == 50000 and proveedor.ultimo["n"] == 2


def test_invitado_limite_de_uso(cliente, planta, proveedor, monkeypatch):
    monkeypatch.setattr(ajustes(), "invitado_limite_hora", 1)
    h = cab(cliente, "invitado")
    assert _chat(cliente, h).status_code == 200
    r = _chat(cliente, h)
    assert r.status_code == 429 and r.json()["error"]["type"] == "rate_limit_error"


MENSAJES_CON_IMAGEN = [{"role": "user", "content": [
    {"type": "text", "text": "¿Qué ves?"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
]}]


def test_imagenes_con_modelo_sin_vision(cliente, bd, planta, proveedor):
    fila = ModeloIA(nombre="Visión de pruebas", ref="vision-falso", tipo="vision", permitido=True, soporta_vision=True)
    bd.add(fila)
    bd.commit()
    try:
        r = _chat(cliente, cab(cliente, "luis"), messages=MENSAJES_CON_IMAGEN)
        assert r.status_code == 200
        # El predeterminado no tiene visión: se usa el modelo con visión permitido (en pruebas, «vision-falso»).
        assert proveedor.ultimo["model"] == "vision-falso"
        assert proveedor.ultimo["messages"] == MENSAJES_CON_IMAGEN  # la imagen viaja tal cual
    finally:  # la tabla de modelos la comparten las pruebas de administración
        bd.rollback()
        bd.delete(fila)
        bd.commit()


def test_imagenes_nunca_van_a_un_modelo_en_la_nube_bloqueado(cliente, bd, planta, proveedor, monkeypatch):
    from cidia.ia import llm

    # La administración marcó como permitido un modelo de nube con visión, pero la política no deja usar la nube.
    bd.add(ModeloIA(nombre="Visión en la nube", ref="nube-vision:cloud", tipo="vision", ubicacion="nube",
                    permitido=True, soporta_vision=True))
    bd.commit()
    monkeypatch.setattr(llm, "modelo_vision", lambda bd=None: "nube-vision:cloud")
    try:
        assert _chat(cliente, cab(cliente, "luis"), messages=MENSAJES_CON_IMAGEN).status_code == 200
        assert proveedor.ultimo["model"] == ajustes().llm_modelo_chat
        assert _chat(cliente, cab(cliente, "luis"), model="nube-vision:cloud").status_code == 403
    finally:
        fila = bd.scalar(select(ModeloIA).where(ModeloIA.ref == "nube-vision:cloud"))
        bd.delete(fila)
        bd.commit()


def test_errores_del_proveedor(cliente, planta, proveedor, monkeypatch):
    h = cab(cliente, "luis")
    proveedor.estado = 500
    r = _chat(cliente, h)
    assert r.status_code == 500 and r.json()["error"]["message"] == "modelo caído"
    r = _chat(cliente, h, stream=True)
    assert r.status_code == 500 and r.json()["error"]["message"] == "modelo caído"

    def caido(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión")

    monkeypatch.setattr(rutas_openai, "_cliente_http",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(caido)))
    for stream in (False, True):
        r = _chat(cliente, h, stream=stream)
        assert r.status_code == 502 and "no responde" in r.json()["error"]["message"]
