"""Pruebas de aportaciones desde la planta y lagunas.

Personas (ver fabrica.py): pedro y marta son empleados de Producción, javier es su jefe;
luis es empleado de Oficina técnica y ana su jefa; admin no tiene departamento.
Los modelos son falsos y deterministas (fixture `ia`); los trabajos se ejecutan en el acto.
"""

from __future__ import annotations

from typing import Any

import pytest
from fabrica import cab
from sqlalchemy import delete, select

from cidia.conocimiento import motor
from cidia.ia import llm
from cidia.modelos import Aportacion, Documento, Laguna, SentenciaXapi
from cidia.permisos import alcance_de
from cidia.seguridad import Actor
from cidia.servicios import aportaciones as srv
from cidia.servicios import lagunas as srv_lagunas

RELATO = ("La prensa 3 se atascaba al cambiar de molde. El sensor S4 quedaba sucio después del cambio. "
          "Lo limpié con aire comprimido y reinicié el ciclo en modo manual.")

FICHA = {
    "titulo": "Atasco de la prensa 3 al cambiar de molde",
    "problema": "La prensa 3 se atasca al cambiar de molde.",
    "causa": "El sensor S4 queda sucio tras el cambio.",
    "solucion": "Limpiar el sensor S4 con aire y reiniciar el ciclo en modo manual.",
    "etiquetas": ["prensa 3", "sensor S4"],
    "nivel_minimo": 1,
}


@pytest.fixture(autouse=True)
def limpio(app, bd):
    """Cada prueba empieza sin aportaciones ni lagunas (`app` garantiza que existen las tablas)."""
    bd.execute(delete(Aportacion))
    bd.execute(delete(Laguna))
    bd.commit()


@pytest.fixture
def resueltas(monkeypatch) -> list[tuple[int, int]]:
    """Sustituye lagunas.resolver (lo implementa el módulo de consulta) y apunta las llamadas."""
    llamadas: list[tuple[int, int]] = []

    def resolver(bd, laguna_id, aportacion_id):
        llamadas.append((laguna_id, aportacion_id))
        lag = bd.get(Laguna, laguna_id)
        lag.estado, lag.aportacion_id = "resuelta", aportacion_id

    monkeypatch.setattr(srv_lagunas, "resolver", resolver)
    return llamadas


def _enviar(cliente, quien: str, **datos: Any) -> dict[str, Any]:
    r = cliente.post("/api/aportaciones", json={"texto": RELATO, **datos}, headers=cab(cliente, quien))
    assert r.status_code == 200, r.text
    return r.json()


def _laguna(bd, planta, dep: str, pregunta: str, frecuencia: int = 1, **extra: Any) -> Laguna:
    lag = Laguna(pregunta=pregunta, departamento_id=planta.deps[dep].id, frecuencia=frecuencia, **extra)
    bd.add(lag)
    bd.commit()
    return lag


# --------------------------------------------------------------------------- flujo completo


def test_flujo_completo_por_texto(cliente, bd, planta, ia, resueltas):
    ia.json = FICHA
    tarea = planta.tareas["prod"]
    ap = _enviar(cliente, "pedro", tarea_id=tarea.id)
    # el trabajo en segundo plano ya lo ha ordenado (en las pruebas es inmediato)
    assert ap["estado"] == "pendiente"
    assert ap["titulo"] == FICHA["titulo"] and ap["causa"] == FICHA["causa"]
    assert ap["etiquetas"] == ["prensa 3", "sensor S4"]
    assert ap["tarea"]["codigo"] == "IT-023" and ap["via"] == "texto"
    assert "nivel_minimo" not in ap and "departamento" not in ap  # etiquetas de acceso: solo quien gestiona
    prompt = ia.llamadas[-1]["mensajes"]
    assert prompt[0]["role"] == "system" and "JSON" in prompt[0]["content"]
    assert "sensor S4" in prompt[1]["content"] and "IT-023" in prompt[1]["content"]

    # el jefe de Producción la ve en su bandeja, con autor y etiquetas
    hj = cab(cliente, "javier")
    bandeja = cliente.get("/api/aportaciones/pendientes", headers=hj).json()
    assert [a["id"] for a in bandeja["aportaciones"]] == [ap["id"]]
    assert bandeja["resumen"]["pendientes"] == 1
    fila = bandeja["aportaciones"][0]
    assert fila["autor"]["nombre"] == "Pedro Ruiz" and fila["departamento"]["nombre"] == "Producción"
    assert fila["nivel_minimo"] == 1 and fila["nivel_nombre"] == "Operario"

    # edita en línea y valida
    r = cliente.put(f"/api/aportaciones/{ap['id']}", headers=hj,
                    json={"solucion": "Limpiar S4 con aire comprimido y reiniciar el ciclo en manual.",
                          "etiquetas": ["prensa 3", "sensor S4", "cambio de molde", "prensa 3"]})
    assert r.status_code == 200, r.text
    assert r.json()["etiquetas"] == ["prensa 3", "sensor S4", "cambio de molde"]
    r = cliente.post(f"/api/aportaciones/{ap['id']}/validar", headers=hj, json={})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["aportacion"]["estado"] == "validada" and res["aportacion"]["revisada_por"] == "Javier Martín"
    doc_id = res["documento"]["id"]
    assert res["documento"]["tipo"] == "faq" and res["documento"]["origen"] == "aportacion"
    assert res["documento"]["autor"] == "Pedro Ruiz" and res["documento"]["validador"] == "Javier Martín"
    assert res["documento"]["estado"] == "listo"  # indexado

    bd.expire_all()
    doc = bd.get(Documento, doc_id)
    assert doc.autor_id == planta.personas["pedro"].id
    assert doc.validador_id == planta.personas["javier"].id
    assert doc.departamento_id == planta.deps["prod"].id and doc.nivel_minimo == 1 and doc.origen_id == ap["id"]
    assert "Problema: La prensa 3" in doc.contenido_texto and "Solución: Limpiar S4" in doc.contenido_texto
    assert "Causa: El sensor S4" in doc.contenido_texto and "IT-023" in doc.contenido_texto

    # el motor propio la encuentra para Producción, pero no para Oficina técnica
    marta = Actor(sesion=None, usuario=planta.personas["marta"])  # type: ignore[arg-type]
    encontrados = motor().buscar(bd, "¿Qué hago si se atasca la prensa 3?", alcance_de(bd, marta), k=5)
    assert doc_id in [e.documento_id for e in encontrados[:2]]
    luis = Actor(sesion=None, usuario=planta.personas["luis"])  # type: ignore[arg-type]
    assert all(e.documento_id != doc_id for e in motor().buscar(bd, "atasco prensa 3 sensor S4", alcance_de(bd, luis)))

    # trazas xAPI: el jefe validó y el autor aportó con resultado
    sentencias = bd.scalars(select(SentenciaXapi).where(SentenciaXapi.objeto_tipo == "aportacion",
                                                        SentenciaXapi.objeto_id == str(ap["id"]))).all()
    valido = [s for s in sentencias if s.verbo == "valido"]
    aporto = [s for s in sentencias if s.verbo == "aporto" and s.resultado]
    assert valido and valido[0].actor_id == planta.personas["javier"].id
    assert aporto and aporto[0].actor_id == planta.personas["pedro"].id and aporto[0].resultado["success"] is True
    assert srv.contar_validadas(bd, planta.personas["pedro"].id) == 1
    assert srv.contar_validadas(bd, planta.personas["pedro"].id, tarea.id) == 1
    assert srv.validadas_por_persona(bd, planta.deps["prod"].id) == {planta.personas["pedro"].id: 1}

    # el autor ve el estado y lo publicado; ya no puede retirarla
    hp = cab(cliente, "pedro")
    mias = cliente.get("/api/aportaciones/mias", headers=hp).json()
    assert mias["resumen"]["validada"] == 1
    assert mias["aportaciones"][0]["documento"]["id"] == doc_id
    assert cliente.delete(f"/api/aportaciones/{ap['id']}", headers=hp).status_code == 409
    # no se valida dos veces
    assert cliente.post(f"/api/aportaciones/{ap['id']}/validar", headers=hj, json={}).status_code == 409
    assert resueltas == []  # no venía de una laguna


def test_flujo_por_nota_de_voz(cliente, bd, planta, ia):
    ia.transcripcion = ("Cuando la bobinadora pita tres veces hay que abrir el cuadro y rearmar el térmico "
                        "del motor 2.")

    def responder(mensajes):
        assert "bobinadora" in mensajes[1]["content"]  # el LLM recibe la transcripción
        return {"título": "Bobinadora pita tres veces", "Problema": "La bobinadora pita tres veces.",
                "Solución": ["Abrir el cuadro", "Rearmar el térmico del motor 2"], "etiquetas": "bobinadora, térmico",
                "nivel": "operario"}

    ia.json = responder
    h = cab(cliente, "pedro")
    r = cliente.post("/api/aportaciones", headers=h,
                     files={"audio": ("nota.webm", b"\x1aE\xdf\xa3audio-falso" * 50, "audio/webm")},
                     data={"tarea_id": str(planta.tareas["prod"].id), "duracion": "4.2"})
    assert r.status_code == 200, r.text
    ap = r.json()
    assert ap["estado"] == "pendiente" and ap["via"] == "voz"
    assert ap["transcripcion"] == ia.transcripcion
    assert ap["duracion_audio"] == 3.0  # la del servicio de voz manda sobre la del navegador
    assert ap["titulo"] == "Bobinadora pita tres veces"
    assert ap["solucion"] == "- Abrir el cuadro\n- Rearmar el térmico del motor 2"
    assert ap["etiquetas"] == ["bobinadora", "térmico"]
    # el audio se sirve con URL firmada (el autor y su jefe lo pueden escuchar)
    assert ap["audio_url"].startswith("/api/ficheros/")
    assert cliente.get(ap["audio_url"]).status_code == 200
    jefe = cliente.get(f"/api/aportaciones/{ap['id']}", headers=cab(cliente, "javier")).json()
    assert jefe["audio_url"] and jefe["transcripcion"] == ia.transcripcion

    # retirar la suya borra también el audio
    from cidia.ficheros import ruta_absoluta

    ruta = bd.get(Aportacion, ap["id"]).audio_ruta
    assert ruta_absoluta(ruta).exists() and ruta.endswith("/nota-de-voz.webm")
    assert cliente.delete(f"/api/aportaciones/{ap['id']}", headers=h).status_code == 200
    assert not ruta_absoluta(ruta).exists()
    assert not ruta_absoluta(ruta).parent.exists()  # tampoco queda su carpeta
    bd.expire_all()
    assert bd.get(Aportacion, ap["id"]) is None
    assert bd.scalar(select(SentenciaXapi).where(SentenciaXapi.verbo == "retiro",
                                                 SentenciaXapi.objeto_id == str(ap["id"]))) is not None


def test_nota_de_voz_vacia_o_sin_formato(cliente, planta):
    h = cab(cliente, "pedro")
    r = cliente.post("/api/aportaciones", headers=h, files={"audio": ("nota.webm", b"", "audio/webm")})
    assert r.status_code == 400
    r = cliente.post("/api/aportaciones", headers=h, files={"audio": ("nota.exe", b"MZ" * 20, "application/x-msdownload")})
    assert r.status_code == 400 and "formato" in r.json()["detail"]


def test_audio_sin_transcripcion_queda_para_escuchar(cliente, planta, ia, monkeypatch):
    from cidia.ia import asr

    def falla(*a, **k):
        raise asr.ErrorVoz("servicio de voz caído")

    monkeypatch.setattr(asr, "transcribir", falla)
    r = cliente.post("/api/aportaciones", headers=cab(cliente, "pedro"),
                     files={"audio": ("nota.ogg", b"OggS" + b"0" * 200, "audio/ogg")})
    ap = r.json()
    assert ap["estado"] == "pendiente" and ap["transcripcion"] is None
    assert ap["titulo"] == "Nota de voz sin transcribir" and not ap["solucion"]
    # sin solución no se puede validar: el jefe la escucha y la escribe
    hj = cab(cliente, "javier")
    assert cliente.post(f"/api/aportaciones/{ap['id']}/validar", headers=hj, json={}).status_code == 400
    r = cliente.post(f"/api/aportaciones/{ap['id']}/validar", headers=hj,
                     json={"problema": "Ruido en la prensa", "solucion": "Engrasar la guía."})
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- robustez con el LLM


def test_json_roto_usa_el_respaldo(cliente, planta, ia):
    def roto(mensajes):
        raise llm.ErrorModelo("El modelo no devolvió un JSON válido.")

    ia.json = roto
    ap = _enviar(cliente, "pedro")
    assert ap["estado"] == "pendiente"
    assert ap["titulo"] == "La prensa 3 se atascaba al cambiar de molde"
    assert ap["solucion"] == RELATO and not ap["problema"] and ap["etiquetas"] == []


@pytest.mark.parametrize("respuesta", [
    "esto no es un objeto",
    [],
    {"titulo": "...", "problema": "", "solucion": "..."},
    {"otra_cosa": 3},
])
def test_respuestas_inservibles_usan_el_respaldo(respuesta):
    ficha = srv.normalizar(respuesta, RELATO)
    assert ficha["titulo"] == "La prensa 3 se atascaba al cambiar de molde"
    assert ficha["solucion"] == RELATO and ficha["ordenada_por_ia"] is False


def test_normalizar_tolera_formatos_de_modelos_pequenos():
    relato = "El sensor S4 estaba sucio y la máquina no arranca. Hay que limpiar y rearmar."
    ficha = srv.normalizar({"ficha": {"Title": "Sensor sucio.", "problem": "Solución: no arranca", "cause": "Ninguna",
                                      "solution": {"paso1": "Limpiar", "paso2": "Rearmar"}, "tags": ["#S4", "s4", ""],
                                      "Nivel mínimo": "nivel 9"}}, relato, maximo_nivel=4)
    assert ficha["titulo"] == "Sensor sucio" and ficha["problema"] == "no arranca" and ficha["causa"] == ""
    assert ficha["solucion"] == "Limpiar\nRearmar" and ficha["etiquetas"] == ["S4"] and ficha["nivel_minimo"] == 4
    # sin solución pero con problema: la solución es el relato completo
    assert srv.normalizar({"problema": "Se atasca"}, RELATO)["solucion"] == RELATO
    assert srv.primera_frase("¿Qué pasa? Nada.") == "¿Qué pasa?"


def test_normalizar_descarta_lo_inventado():
    """Lo que no sale del relato no se publica: causa fuera, solución sustituida por el relato."""
    relato = ("pues nada que la bobinadora pitaba tres veces y se paraba, era el termico del motor dos que saltaba, "
              "abri el cuadro y lo rearme y listo")
    ficha = srv.normalizar({"titulo": "problema", "problema": "La bobinadora pitaba y se paraba.",
                            "causa": "Un fallo de calibración del variador de frecuencia.",
                            "solucion": "- Calibrar el variador\n- Sustituir el encoder",
                            "etiquetas": ["máquinas", "piezas", "bobinadora", "variador"]}, relato)
    assert ficha["causa"] == "" and ficha["solucion"] == relato
    assert ficha["etiquetas"] == ["bobinadora"]
    assert ficha["titulo"] == "La bobinadora pitaba y se paraba"
    # lo que viene de la tarea o de la pregunta también cuenta como respaldo
    ficha = srv.normalizar({"problema": "La bobinadora pitaba.", "solucion": "Rearmar el térmico.",
                            "etiquetas": ["IT-023"]}, relato, referencia="Tarea relacionada: IT-023 · Bobinado")
    assert ficha["etiquetas"] == ["IT-023"] and ficha["solucion"] == "Rearmar el térmico."


@pytest.mark.ia_real
def test_ordenar_con_el_modelo_real(bd):
    ficha = srv.ordenar(bd, RELATO)
    assert ficha["titulo"] and ficha["solucion"]
    assert 1 <= ficha["nivel_minimo"] <= 4


def test_texto_demasiado_corto_o_vacio(cliente, planta):
    h = cab(cliente, "pedro")
    assert cliente.post("/api/aportaciones", headers=h, json={"texto": "  hola "}).status_code == 400
    assert cliente.post("/api/aportaciones", headers=h, json={}).status_code == 400
    assert cliente.post("/api/aportaciones", headers=h, content=b"{no es json",
                        ).status_code == 400


# --------------------------------------------------------------------------- rechazo


def test_rechazo_con_motivo_obligatorio(cliente, planta, ia):
    ia.json = FICHA
    ap = _enviar(cliente, "pedro")
    hj = cab(cliente, "javier")
    assert cliente.post(f"/api/aportaciones/{ap['id']}/rechazar", headers=hj, json={}).status_code == 400
    assert cliente.post(f"/api/aportaciones/{ap['id']}/rechazar", headers=hj, json={"motivo": "  "}).status_code == 400
    r = cliente.post(f"/api/aportaciones/{ap['id']}/rechazar", headers=hj,
                     json={"motivo": "Ya está en la instrucción IT-023, paso 4."})
    assert r.status_code == 200 and r.json()["estado"] == "rechazada"
    mias = cliente.get("/api/aportaciones/mias", headers=cab(cliente, "pedro")).json()
    assert mias["aportaciones"][0]["motivo_rechazo"] == "Ya está en la instrucción IT-023, paso 4."
    assert mias["aportaciones"][0]["revisada_por"] == "Javier Martín"
    assert mias["resumen"]["rechazada"] == 1
    # ya revisada: ni se valida, ni se edita, ni se retira
    assert cliente.post(f"/api/aportaciones/{ap['id']}/validar", headers=hj, json={}).status_code == 409
    assert cliente.put(f"/api/aportaciones/{ap['id']}", headers=hj, json={"titulo": "x"}).status_code == 409
    assert cliente.delete(f"/api/aportaciones/{ap['id']}", headers=cab(cliente, "pedro")).status_code == 409
    assert cliente.get("/api/aportaciones/pendientes", headers=hj).json()["resumen"]["rechazadas_30d"] == 1


# --------------------------------------------------------------------------- permisos


def test_permisos_de_aportaciones(cliente, planta, ia):
    ia.json = FICHA
    ap = _enviar(cliente, "pedro")
    url = f"/api/aportaciones/{ap['id']}"

    # un empleado no valida, ni edita, ni ve la bandeja
    hm = cab(cliente, "marta")
    assert cliente.post(f"{url}/validar", headers=hm, json={}).status_code == 403
    assert cliente.post(f"{url}/rechazar", headers=hm, json={"motivo": "no me gusta"}).status_code == 403
    assert cliente.put(url, headers=hm, json={"titulo": "otro"}).status_code == 403
    assert cliente.get("/api/aportaciones/pendientes", headers=hm).status_code == 403
    # el autor solo ve las suyas: otra persona del mismo departamento no la ve ni la retira
    assert cliente.get(url, headers=hm).status_code == 404
    assert cliente.delete(url, headers=hm).status_code == 404
    assert cliente.get("/api/aportaciones/mias", headers=hm).json()["aportaciones"] == []
    assert len(cliente.get("/api/aportaciones/mias", headers=cab(cliente, "pedro")).json()["aportaciones"]) == 1

    # la jefa de otro departamento no la ve ni puede actuar sobre ella
    ha = cab(cliente, "ana")
    assert cliente.get("/api/aportaciones/pendientes", headers=ha).json()["aportaciones"] == []
    assert cliente.get(url, headers=ha).status_code == 404
    assert cliente.put(url, headers=ha, json={"titulo": "otro"}).status_code == 404
    assert cliente.post(f"{url}/validar", headers=ha, json={}).status_code == 404
    assert cliente.post(f"{url}/rechazar", headers=ha, json={"motivo": "fuera de mi área"}).status_code == 404

    # sin sesión de usuario no se aporta
    assert cliente.post("/api/aportaciones", json={"texto": RELATO}).status_code == 401
    assert cliente.post("/api/aportaciones", json={"texto": RELATO}, headers=cab(cliente, "invitado")).status_code == 401

    # la administración lo ve todo
    assert [a["id"] for a in cliente.get("/api/aportaciones/pendientes", headers=cab(cliente, "admin"))
            .json()["aportaciones"]] == [ap["id"]]


def test_tarea_de_otro_departamento(cliente, planta):
    h = cab(cliente, "pedro")
    r = cliente.post("/api/aportaciones", headers=h, json={"texto": RELATO, "tarea_id": planta.tareas["ot"].id})
    assert r.status_code == 400
    assert cliente.post("/api/aportaciones", headers=h, json={"texto": RELATO, "tarea_id": 999999}).status_code == 404
    ap = _enviar(cliente, "pedro")
    r = cliente.put(f"/api/aportaciones/{ap['id']}", headers=cab(cliente, "javier"),
                    json={"tarea_id": planta.tareas["ot"].id})
    assert r.status_code == 400
    r = cliente.put(f"/api/aportaciones/{ap['id']}", headers=cab(cliente, "javier"), json={"nivel_minimo": 9})
    assert r.status_code == 400


def test_jefe_no_valida_la_suya(cliente, planta, ia):
    ia.json = FICHA
    ap = _enviar(cliente, "javier")
    assert cliente.post(f"/api/aportaciones/{ap['id']}/validar", headers=cab(cliente, "javier"), json={}).status_code == 403
    r = cliente.post(f"/api/aportaciones/{ap['id']}/validar", headers=cab(cliente, "admin"), json={})
    assert r.status_code == 200, r.text


def test_opciones_y_resumen(cliente, planta, ia):
    op = cliente.get("/api/aportaciones/opciones", headers=cab(cliente, "pedro")).json()
    assert [t["codigo"] for t in op["tareas"]] == ["IT-023"] and "niveles" not in op
    op = cliente.get("/api/aportaciones/opciones", headers=cab(cliente, "javier")).json()
    assert [n["orden"] for n in op["niveles"]] == [1, 2, 3, 4]
    op = cliente.get("/api/aportaciones/opciones", headers=cab(cliente, "admin")).json()
    assert {t["codigo"] for t in op["tareas"]} >= {"IT-023", "IT-101"}

    ia.json = FICHA
    ap = _enviar(cliente, "carmen")
    hj = cab(cliente, "javier")
    cliente.post(f"/api/aportaciones/{ap['id']}/validar", headers=hj, json={})
    personas = cliente.get("/api/aportaciones/resumen", headers=hj).json()["personas"]
    assert personas[0]["nombre"] == "Carmen Díaz" and personas[0]["validadas"] == 1
    assert all(p["nombre"] != "Luis García" for p in personas)
    assert cliente.get("/api/aportaciones/resumen", headers=cab(cliente, "pedro")).status_code == 403


def test_rescate_de_aportaciones_atascadas(cliente, bd, planta):
    from datetime import timedelta

    from cidia.modelos import ahora

    ap = Aportacion(autor_id=planta.personas["pedro"].id, departamento_id=planta.deps["prod"].id,
                    texto_original=RELATO, estado="procesando", creada=ahora() - timedelta(hours=1))
    bd.add(ap)
    bd.commit()
    bandeja = cliente.get("/api/aportaciones/pendientes", headers=cab(cliente, "javier")).json()
    fila = next(a for a in bandeja["aportaciones"] if a["id"] == ap.id)
    assert fila["estado"] == "pendiente" and fila["solucion"] == RELATO


# --------------------------------------------------------------------------- lagunas


def test_aportar_respuesta_a_una_laguna(cliente, bd, planta, ia, resueltas):
    lag = _laguna(bd, planta, "prod", "¿Qué presión lleva el cilindro de la prensa 2?", 3,
                  tarea_id=planta.tareas["prod"].id)
    otra = _laguna(bd, planta, "ot", "¿Qué proveedor hace los utillajes de soldadura?", 2)
    ia.json = FICHA

    # se aporta enlazada a la laguna: hereda su tarea y el LLM recibe la pregunta
    ap = _enviar(cliente, "pedro", laguna_id=lag.id)
    assert ap["laguna"]["pregunta"] == lag.pregunta and ap["tarea"]["id"] == planta.tareas["prod"].id
    assert "cilindro de la prensa 2" in ia.llamadas[-1]["mensajes"][1]["content"]
    # una laguna de otro departamento no se puede responder
    r = cliente.post("/api/aportaciones", headers=cab(cliente, "pedro"), json={"texto": RELATO, "laguna_id": otra.id})
    assert r.status_code == 404

    # mientras está en revisión, las preguntas pendientes lo indican
    abiertas = cliente.get("/api/lagunas/abiertas-de-mi-departamento", headers=cab(cliente, "pedro")).json()["lagunas"]
    assert abiertas[0]["respuestas_en_revision"] == 1 and abiertas[0]["mi_respuesta"]["id"] == ap["id"]

    r = cliente.post(f"/api/aportaciones/{ap['id']}/validar", headers=cab(cliente, "javier"), json={})
    assert r.status_code == 200, r.text
    assert resueltas == [(lag.id, ap["id"])]
    bd.expire_all()
    doc = bd.get(Documento, r.json()["documento"]["id"])
    assert "Pregunta: ¿Qué presión lleva el cilindro de la prensa 2?" in doc.contenido_texto
    # resuelta: ya no aparece entre las pendientes y no admite más respuestas
    assert cliente.get("/api/lagunas/abiertas-de-mi-departamento", headers=cab(cliente, "pedro")).json()["lagunas"] == []
    r = cliente.post("/api/aportaciones", headers=cab(cliente, "marta"), json={"texto": RELATO, "laguna_id": lag.id})
    assert r.status_code == 409


def test_lagunas_visibles_por_departamento(cliente, bd, planta):
    a = _laguna(bd, planta, "prod", "¿Cómo se purga el circuito de refrigeración?", 2,
                ejemplos=[{"pregunta": "como purgo la refrigeracion", "usuario_id": 5, "fecha": "2026-10-01T10:00:00+00:00"},
                          "¿Cómo se purga el circuito de refrigeración?"])
    b = _laguna(bd, planta, "prod", "¿Qué presión lleva el cilindro de la prensa 2?", 5)
    c = _laguna(bd, planta, "ot", "¿Qué tolerancia tiene el utillaje U-7?", 1)
    _laguna(bd, planta, "prod", "¿Dónde está el manual viejo?", 9, estado="descartada")

    # jefe de Producción: las suyas, abiertas, las más frecuentes primero, con ejemplos sin datos personales
    hj = cab(cliente, "javier")
    datos = cliente.get("/api/lagunas", headers=hj).json()
    assert [g["id"] for g in datos["lagunas"]] == [b.id, a.id]
    assert datos["contadores"] == {"abierta": 2, "resuelta": 0, "descartada": 1}
    ej = next(g for g in datos["lagunas"] if g["id"] == a.id)["ejemplos"]
    assert ej[0] == {"pregunta": "¿Cómo se purga el circuito de refrigeración?", "fecha": None}
    assert ej[1]["pregunta"] == "como purgo la refrigeracion" and "usuario_id" not in ej[1]
    assert [g["frecuencia"] for g in cliente.get("/api/lagunas?estado=descartada", headers=hj).json()["lagunas"]] == [9]
    assert len(cliente.get("/api/lagunas?estado=todas&orden=reciente", headers=hj).json()["lagunas"]) == 3
    assert cliente.get("/api/lagunas?estado=rara", headers=hj).status_code == 400
    assert cliente.get("/api/lagunas?orden=rara", headers=hj).status_code == 400

    # jefa de Oficina técnica: solo la suya; administración: todas
    assert [g["id"] for g in cliente.get("/api/lagunas", headers=cab(cliente, "ana")).json()["lagunas"]] == [c.id]
    assert {g["id"] for g in cliente.get("/api/lagunas", headers=cab(cliente, "admin")).json()["lagunas"]} == {a.id, b.id, c.id}

    # empleados: no ven la gestión, pero sí las preguntas pendientes de su departamento (sin ejemplos)
    hp = cab(cliente, "pedro")
    assert cliente.get("/api/lagunas", headers=hp).status_code == 403
    pendientes = cliente.get("/api/lagunas/abiertas-de-mi-departamento", headers=hp).json()["lagunas"]
    assert [g["id"] for g in pendientes] == [b.id, a.id]
    assert all("ejemplos" not in g and "departamento" not in g for g in pendientes)
    hl = cab(cliente, "luis")
    assert [g["id"] for g in cliente.get("/api/lagunas/abiertas-de-mi-departamento", headers=hl).json()["lagunas"]] == [c.id]


def test_descartar_y_reabrir_lagunas(cliente, bd, planta):
    lag = _laguna(bd, planta, "prod", "¿Qué presión lleva el cilindro de la prensa 2?", 3)
    url = f"/api/lagunas/{lag.id}"
    # empleado: prohibido; jefa de otro departamento: no existe para ella
    assert cliente.post(f"{url}/descartar", headers=cab(cliente, "pedro")).status_code == 403
    assert cliente.post(f"{url}/descartar", headers=cab(cliente, "ana")).status_code == 404
    hj = cab(cliente, "javier")
    r = cliente.post(f"{url}/descartar", headers=hj)
    assert r.status_code == 200 and r.json()["estado"] == "descartada"
    assert cliente.post(f"{url}/descartar", headers=hj).status_code == 409
    assert cliente.get("/api/lagunas/abiertas-de-mi-departamento", headers=cab(cliente, "pedro")).json()["lagunas"] == []
    r = cliente.post(f"{url}/reabrir", headers=hj)
    assert r.status_code == 200 and r.json()["estado"] == "abierta"
    assert cliente.post(f"{url}/reabrir", headers=hj).status_code == 409
    assert cliente.post(f"{url}/reabrir", headers=cab(cliente, "ana")).status_code == 404
    from cidia.modelos import Auditoria

    acciones = [a.accion for a in bd.scalars(select(Auditoria).where(Auditoria.entidad == "laguna",
                                                                     Auditoria.entidad_id == str(lag.id)))]
    assert acciones == ["descartar_laguna", "reabrir_laguna"]


# --------------------------------------------------------------------------- seguridad y casos límite


def test_la_nota_se_guarda_siempre_como_audio(cliente, bd, planta, monkeypatch):
    """Una «nota» llamada .html no puede servirse como página web desde /api/ficheros (XSS)."""
    h = cab(cliente, "pedro")
    r = cliente.post("/api/aportaciones", headers=h,
                     files={"audio": ("nota.html", b"<script>alert(1)</script>" * 20, "audio/webm")})
    assert r.status_code == 200, r.text
    ap = r.json()
    assert bd.get(Aportacion, ap["id"]).audio_ruta.endswith("/nota-de-voz.webm")
    f = cliente.get(ap["audio_url"])
    assert f.status_code == 200 and "html" not in f.headers["content-type"]
    # sin extensión la deduce del tipo; con una de audio válida, la conserva
    r = cliente.post("/api/aportaciones", headers=h,
                     files={"audio": ("blob", b"OggS" + b"0" * 100, "audio/ogg;codecs=opus")})
    assert bd.get(Aportacion, r.json()["id"]).audio_ruta.endswith("/nota-de-voz.ogg")
    r = cliente.post("/api/aportaciones", headers=h,
                     files={"audio": ("Grabación.m4a", b"0" * 100, "application/octet-stream")})
    assert bd.get(Aportacion, r.json()["id"]).audio_ruta.endswith("/nota-de-voz.m4a")
    # demasiado grande: se rechaza antes de copiarla
    monkeypatch.setattr(srv, "MAX_AUDIO", 50)
    r = cliente.post("/api/aportaciones", headers=h, files={"audio": ("nota.webm", b"0" * 100, "audio/webm")})
    assert r.status_code == 413 and "grande" in r.json()["detail"]


def test_sin_departamento_no_se_cuela_en_otra_bandeja(cliente, bd, planta):
    from fabrica import CONTRASENA

    from cidia.modelos import Usuario
    from cidia.seguridad import hash_contrasena

    if bd.scalar(select(Usuario).where(Usuario.usuario == "sindep")) is None:
        bd.add(Usuario(usuario="sindep", nombre="Sin Departamento", rol="empleado",
                       hash_contrasena=hash_contrasena(CONTRASENA)))
        bd.commit()
    h = cab(cliente, "sindep")
    # ni con una tarea de Producción, ni respondiendo a una pregunta sin departamento
    r = cliente.post("/api/aportaciones", headers=h, json={"texto": RELATO, "tarea_id": planta.tareas["prod"].id})
    assert r.status_code == 400
    sin_dep = Laguna(pregunta="¿Dónde se piden los guantes nuevos?", departamento_id=None)
    bd.add(sin_dep)
    bd.commit()
    r = cliente.post("/api/aportaciones", headers=h, json={"texto": RELATO, "laguna_id": sin_dep.id})
    assert r.status_code == 404
    # sí puede aportar sin tarea: queda para la administración, no para el jefe de Producción
    ap = _enviar(cliente, "sindep")
    assert cliente.get("/api/aportaciones/pendientes", headers=cab(cliente, "javier")).json()["aportaciones"] == []
    admin = cliente.get("/api/aportaciones/pendientes", headers=cab(cliente, "admin")).json()["aportaciones"]
    assert ap["id"] in [a["id"] for a in admin]


def test_dos_respuestas_a_la_misma_laguna(cliente, bd, planta, ia, resueltas):
    """La laguna queda enlazada a la primera respuesta validada; la segunda también se publica."""
    lag = _laguna(bd, planta, "prod", "¿Qué presión lleva el cilindro de la prensa 2?", 2)
    ia.json = FICHA
    a1 = _enviar(cliente, "pedro", laguna_id=lag.id)
    a2 = _enviar(cliente, "marta", laguna_id=lag.id)
    hj = cab(cliente, "javier")
    assert cliente.post(f"/api/aportaciones/{a1['id']}/validar", headers=hj, json={}).status_code == 200
    r = cliente.post(f"/api/aportaciones/{a2['id']}/validar", headers=hj, json={})
    assert r.status_code == 200 and r.json()["documento"]["tipo"] == "faq"
    assert resueltas == [(lag.id, a1["id"])]
    bd.expire_all()
    assert bd.get(Laguna, lag.id).aportacion_id == a1["id"]


def test_el_procesado_no_pisa_un_rechazo_ni_una_retirada(bd, planta, monkeypatch):
    """Si mientras el modelo trabaja el jefe la rechaza o su autor la retira, el trabajo no escribe."""
    from cidia.db import nueva_sesion

    def nueva() -> Aportacion:
        ap = Aportacion(autor_id=planta.personas["pedro"].id, departamento_id=planta.deps["prod"].id,
                        texto_original=RELATO, estado="procesando")
        bd.add(ap)
        bd.commit()
        return ap

    ap = nueva()

    def rechazar_mientras(*a: Any, **k: Any) -> dict[str, Any]:
        with nueva_sesion() as otra:
            fila = otra.get(Aportacion, ap.id)
            fila.estado, fila.motivo_rechazo = "rechazada", "Está duplicada."
            otra.commit()
        return srv.respaldo(RELATO)

    monkeypatch.setattr(srv, "ordenar", rechazar_mientras)
    with nueva_sesion() as s:
        assert srv.procesar_trabajo(s, lambda *a: None, ap.id) == {"omitida": True}
        s.commit()
    bd.expire_all()
    assert bd.get(Aportacion, ap.id).estado == "rechazada"

    ap2 = nueva()

    def retirar_mientras(*a: Any, **k: Any) -> dict[str, Any]:
        with nueva_sesion() as otra:
            otra.delete(otra.get(Aportacion, ap2.id))
            otra.commit()
        return srv.respaldo(RELATO)

    monkeypatch.setattr(srv, "ordenar", retirar_mientras)
    with nueva_sesion() as s:
        assert srv.procesar_trabajo(s, lambda *a: None, ap2.id) == {"omitida": True}


def test_rechazo_sin_cuerpo_y_edicion_vacia(cliente, bd, planta, ia):
    from cidia.modelos import Auditoria

    ia.json = FICHA
    ap = _enviar(cliente, "pedro")
    url = f"/api/aportaciones/{ap['id']}"
    hj = cab(cliente, "javier")
    r = cliente.post(f"{url}/rechazar", headers=hj)  # sin cuerpo: aviso en castellano, no un 422
    assert r.status_code == 400 and "motivo" in r.json()["detail"]

    def auditorias() -> int:
        return len(bd.scalars(select(Auditoria).where(Auditoria.entidad == "aportacion",
                                                      Auditoria.entidad_id == str(ap["id"]))).all())

    antes = auditorias()
    assert cliente.put(url, headers=hj, json={}).status_code == 200
    assert auditorias() == antes  # un envío sin cambios no deja rastro
    assert cliente.put(url, headers=hj, json={"titulo": "  "}).status_code == 400
    assert cliente.put(url, headers=hj, json={"causa": "Polvo en el sensor S4."}).status_code == 200
    assert auditorias() == antes + 1


def test_caracter_nul_no_rompe_el_guardado(cliente, planta, ia):
    """PostgreSQL no admite NUL en un texto: se quita en vez de devolver un error 500."""
    ia.json = FICHA
    h = cab(cliente, "pedro")
    r = cliente.post("/api/aportaciones", headers=h, json={"texto": RELATO.replace("S4", "S4\x00")})
    assert r.status_code == 200, r.text
    ap = r.json()
    assert "\x00" not in ap["texto_original"] and "S4" in ap["texto_original"]
    hj = cab(cliente, "javier")
    r = cliente.put(f"/api/aportaciones/{ap['id']}", headers=hj, json={"causa": "Polvo\x00", "etiquetas": ["S4\x00"]})
    assert r.status_code == 200 and r.json()["causa"] == "Polvo" and r.json()["etiquetas"] == ["S4"]
    r = cliente.post(f"/api/aportaciones/{ap['id']}/rechazar", headers=hj, json={"motivo": "Ya documentado\x00."})
    assert r.status_code == 200 and r.json()["motivo_rechazo"] == "Ya documentado."


def test_invitado_y_sin_sesion_no_acceden(cliente, planta):
    hi = cab(cliente, "invitado")
    for ruta in ("/api/aportaciones/mias", "/api/aportaciones/opciones", "/api/aportaciones/pendientes",
                 "/api/aportaciones/resumen", "/api/aportaciones/1", "/api/lagunas",
                 "/api/lagunas/abiertas-de-mi-departamento"):
        assert cliente.get(ruta, headers=hi).status_code == 401, ruta
        assert cliente.get(ruta).status_code == 401, ruta
    assert cliente.post("/api/lagunas/1/descartar", headers=hi).status_code == 401
    assert cliente.delete("/api/aportaciones/1", headers=hi).status_code == 401
