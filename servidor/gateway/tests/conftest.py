"""Infraestructura de pruebas del gateway.

Cada ejecución usa su propia base de datos (cidia_t_<CIDIA_TEST_BD>) en el PostgreSQL de
pruebas, que se recrea al empezar. La conexión base se lee de CIDIA_BASE_DATOS_URL (o del
fichero .env del gateway, que no se sube al repositorio).

Por defecto los modelos se sustituyen por versiones falsas y deterministas (fixture `ia`).
Las pruebas que necesitan los modelos reales llevan la marca `@pytest.mark.ia_real` y solo
se ejecutan con CIDIA_TEST_IA_REAL=1.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _leer_env() -> dict[str, str]:
    datos: dict[str, str] = {}
    f = RAIZ / ".env"
    if f.exists():
        for linea in f.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.strip().startswith("#"):
                k, v = linea.split("=", 1)
                datos[k.strip()] = v.strip()
    return datos


def _preparar_bd() -> None:
    env = _leer_env()
    base = os.environ.get("CIDIA_BASE_DATOS_URL") or env.get("CIDIA_BASE_DATOS_URL")
    if not base:
        raise RuntimeError("Falta CIDIA_BASE_DATOS_URL (o servidor/gateway/.env) para las pruebas")
    sufijo = re.sub(r"\W", "_", os.environ.get("CIDIA_TEST_BD", "general").lower())
    nombre = f"cidia_t_{sufijo}"
    from sqlalchemy import create_engine, text

    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n AND pid <> pg_backend_pid()"
        ), {"n": nombre})
        c.execute(text(f'DROP DATABASE IF EXISTS "{nombre}"'))
        c.execute(text(f'CREATE DATABASE "{nombre}"'))
    admin.dispose()
    url = base.rsplit("/", 1)[0] + "/" + nombre
    os.environ["CIDIA_BASE_DATOS_URL"] = url
    datos = RAIZ / "_datos_pruebas" / sufijo
    shutil.rmtree(datos, ignore_errors=True)
    datos.mkdir(parents=True, exist_ok=True)
    os.environ["CIDIA_DIR_DATOS"] = str(datos)
    os.environ.setdefault("CIDIA_SECRETO_JWT", "secreto-de-pruebas-" + "x" * 32)
    os.environ.setdefault("CIDIA_CREAR_SEMILLA", "false")
    for k in ("CIDIA_LLM_BASE_URL", "CIDIA_ASR_BASE_URL", "CIDIA_ESPACIO_URL", "CIDIA_ESPACIO_SECRETO"):
        if k in env and k not in os.environ:
            os.environ[k] = env[k]


_preparar_bd()

from cidia import trabajos  # noqa: E402
from cidia.db import inicializar_bd, nueva_sesion  # noqa: E402

trabajos.modo_sincrono(True)


def pytest_configure(config: Any) -> None:
    config.addinivalue_line("markers", "ia_real: necesita los modelos reales (CIDIA_TEST_IA_REAL=1)")


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    if os.environ.get("CIDIA_TEST_IA_REAL") == "1":
        return
    saltar = pytest.mark.skip(reason="modelos reales desactivados (CIDIA_TEST_IA_REAL=1 para activarlos)")
    for item in items:
        if "ia_real" in item.keywords:
            item.add_marker(saltar)


# --------------------------------------------------------------------------- modelos falsos

DIM = 256


def vector_falso(texto: str) -> list[float]:
    """Embedding determinista: bolsa de palabras con hashing (textos parecidos, vectores parecidos)."""
    v = [0.0] * DIM
    for palabra in re.findall(r"\w+", texto.lower()):
        if len(palabra) < 3:
            continue
        raiz = palabra[:6]
        h = int(hashlib.md5(raiz.encode()).hexdigest(), 16)
        v[h % DIM] += 1.0
    norma = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norma for x in v]


class IAFalsa:
    """Sustituye llm y asr. Configura las respuestas con .respuesta, .json y .transcripcion."""

    def __init__(self) -> None:
        self.respuesta = "Respuesta de prueba basada en la documentación [1]."
        self.json: Any = {}
        self.transcripcion = "Texto transcrito de prueba."
        self.llamadas: list[dict[str, Any]] = []

    def chat(self, mensajes: list[dict[str, Any]], modelo: str | None = None, bd: Any = None, *a: Any, **k: Any) -> str:
        self.llamadas.append({"tipo": "chat", "mensajes": mensajes, "modelo": modelo})
        return self.respuesta

    def chat_json(self, mensajes: list[dict[str, Any]], modelo: str | None = None, bd: Any = None, *a: Any, **k: Any) -> Any:
        self.llamadas.append({"tipo": "chat_json", "mensajes": mensajes, "modelo": modelo})
        return self.json(mensajes) if callable(self.json) else self.json

    async def chat_stream(self, mensajes: list[dict[str, Any]], modelo: str, *a: Any, **k: Any):
        self.llamadas.append({"tipo": "chat_stream", "mensajes": mensajes, "modelo": modelo})
        for trozo in re.findall(r"\S+\s*", self.respuesta):
            yield trozo

    def embeddings(self, textos: list[str], modelo: str | None = None) -> list[list[float]]:
        return [vector_falso(t) for t in textos]

    def transcribir(self, audio: Any, nombre: str = "audio.webm", con_marcas: bool = False, idioma: str | None = None,
                    **otros: Any) -> dict[str, Any]:
        self.llamadas.append({"tipo": "transcribir", **otros})
        return {"texto": self.transcripcion, "segmentos": [{"inicio": 0.0, "fin": 3.0, "texto": self.transcripcion}],
                "duracion": 3.0}


@pytest.fixture(autouse=True)
def ia(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> IAFalsa:
    falsa = IAFalsa()
    if "ia_real" in request.keywords:
        return falsa
    from cidia.ia import asr, llm

    monkeypatch.setattr(llm, "chat", falsa.chat)
    monkeypatch.setattr(llm, "chat_json", falsa.chat_json)
    monkeypatch.setattr(llm, "chat_stream", falsa.chat_stream)
    monkeypatch.setattr(llm, "embeddings", falsa.embeddings)
    monkeypatch.setattr(llm, "modelo_vision", lambda bd=None: "vision-falso")
    monkeypatch.setattr(asr, "transcribir", falsa.transcribir)
    return falsa


# --------------------------------------------------------------------------- app y BD


@pytest.fixture(scope="session")
def app():
    inicializar_bd()
    from cidia.main import app as aplicacion

    return aplicacion


@pytest.fixture(scope="module", autouse=True)
def bd_limpia_por_modulo():
    """Cada fichero de pruebas empieza con la base vacía (más los valores por defecto), igual
    que cuando se ejecuta solo: así la batería completa no depende del orden de los ficheros."""
    inicializar_bd()
    from sqlalchemy import text

    from cidia.arranque import valores_por_defecto
    from cidia.db import Base, motor_bd

    tablas = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with motor_bd().begin() as c:
        c.execute(text(f"TRUNCATE {tablas} RESTART IDENTITY CASCADE"))
    valores_por_defecto()
    yield


@pytest.fixture
def cliente(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture
def bd():
    s = nueva_sesion()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def planta(bd):
    """Empresa de ejemplo con departamentos, niveles, puestos, tareas y personas (ver fabrica.py)."""
    from fabrica import crear_planta

    return crear_planta(bd)
