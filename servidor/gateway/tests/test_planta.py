"""Pruebas del modo planta: tareas, ejecución paso a paso, preguntas en contexto, foto y permisos."""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any

import pytest
from fabrica import cab
from sqlalchemy import select

from cidia.config import ajustes
from cidia.ia import llm
from cidia.modelos import Consulta, Ejecucion, EjecucionPaso, Instruccion, Paso, SentenciaXapi, Tarea, ahora
from cidia.servicios import consulta, iluo

# PNG de 1x1 píxel: basta para guardar y enviar «imágenes» sin depender de ficheros externos.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

PASOS_EJEMPLO: list[dict[str, Any]] = [
    {"titulo": "Preparar la brida y los tornillos", "texto": "Coloca la brida B sobre el banco y comprueba que están los 4 tornillos M8."},
    {"titulo": "Apretar los 4 tornillos en cruz", "texto": "Usa la llave dinamométrica y aprieta en cruz.",
     "es_critico": True, "criterio_aceptacion": "Par de apriete de 25 N·m en los cuatro tornillos."},
    {"titulo": "Comprobar el montaje", "texto": "Revisa que la brida no tiene holgura.", "imagen": True},
]


def _imagen(nombre: str) -> str:
    """Crea una imagen de prueba en dir_datos y devuelve su ruta relativa."""
    carpeta = ajustes().dir_datos / "pruebas_planta"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / nombre).write_bytes(PNG)
    return f"pruebas_planta/{nombre}"


def crear_tarea_con_instruccion(bd, planta, dep: str = "prod", pasos: list[dict[str, Any]] | None = None,
                                nivel_minimo: int = 1, publicada: bool = True, version: int = 1) -> tuple[Tarea, Instruccion]:
    """Tarea nueva (código único) en el puesto del departamento `dep` con una instrucción y sus pasos."""
    codigo = "T-" + uuid.uuid4().hex[:6].upper()
    tarea = Tarea(puesto_id=planta.puestos[dep].id, codigo=codigo, nombre=f"Tarea de prueba {codigo}",
                  criticidad=3, nivel_minimo=nivel_minimo)
    bd.add(tarea)
    bd.flush()
    ins = Instruccion(tarea_id=tarea.id, codigo="IT-" + codigo[2:], version=version,
                      estado="publicada" if publicada else "borrador", titulo=f"Instrucción de {tarea.nombre}",
                      resumen="Montaje de prueba.", riesgos="Atrapamiento de manos.", epis="Guantes",
                      publicada_en=ahora() if publicada else None)
    bd.add(ins)
    bd.flush()
    for i, p in enumerate(pasos or PASOS_EJEMPLO, start=1):
        bd.add(Paso(instruccion_id=ins.id, orden=i, titulo=p["titulo"], texto=p.get("texto"),
                    es_critico=p.get("es_critico", False), es_seguridad=p.get("es_seguridad", False),
                    criterio_aceptacion=p.get("criterio_aceptacion"),
                    imagen_ruta=_imagen(f"{codigo}_{i}.png") if p.get("imagen") else None))
    bd.commit()
    bd.refresh(ins)
    return tarea, ins


def _sentencias(bd, verbo: str, ejecucion_id: int | None = None) -> list[SentenciaXapi]:
    bd.expire_all()
    filas = bd.scalars(select(SentenciaXapi).where(SentenciaXapi.verbo == verbo)).all()
    if ejecucion_id is None:
        return list(filas)
    return [s for s in filas if (s.contexto or {}).get("ejecucion_id") == ejecucion_id]


def _eventos(texto: str) -> list[tuple[str, Any]]:
    """Convierte un cuerpo SSE en [(evento, datos)]."""
    salida = []
    for bloque in texto.strip().split("\n\n"):
        evento, datos = "message", ""
        for linea in bloque.splitlines():
            if linea.startswith("event:"):
                evento = linea[6:].strip()
            elif linea.startswith("data:"):
                datos += linea[5:].strip()
        if datos:
            salida.append((evento, json.loads(datos)))
    return salida


@pytest.fixture
def recalculos(monkeypatch) -> list[tuple[int, int]]:
    """Registra las llamadas a iluo.recalcular (el módulo ILUO es de otro equipo)."""
    llamadas: list[tuple[int, int]] = []
    monkeypatch.setattr(iluo, "recalcular", lambda bd, usuario_id, tarea_id: llamadas.append((usuario_id, tarea_id)))
    return llamadas


# --------------------------------------------------------------------------- lista de tareas


def test_tareas_segun_departamento_nivel_y_formacion(cliente, bd, planta):
    t_prod, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    t_ot, _ = crear_tarea_con_instruccion(bd, planta, "ot")
    t_ot_n3, _ = crear_tarea_con_instruccion(bd, planta, "ot", nivel_minimo=3)
    t_borrador, _ = crear_tarea_con_instruccion(bd, planta, "prod", publicada=False)

    def ids(usuario: str) -> dict[int, dict[str, Any]]:
        r = cliente.get("/api/planta/tareas", headers=cab(cliente, usuario))
        assert r.status_code == 200, r.text
        return {t["id"]: t for t in r.json()}

    luis = ids("luis")  # Oficina técnica, nivel 1
    assert t_ot.id in luis and t_prod.id not in luis and t_ot_n3.id not in luis
    assert luis[t_ot.id]["origen"] == "puesto"
    assert luis[t_ot.id]["instruccion"]["pasos"] == 3 and luis[t_ot.id]["instruccion"]["pasos_criticos"] == 1
    assert luis[t_ot.id]["nivel"] == 0 and luis[t_ot.id]["nivel_letra"] == ""

    ana = ids("ana")  # jefa de Oficina técnica, nivel 3
    assert t_ot_n3.id in ana and t_prod.id not in ana

    marta = ids("marta")  # Producción con formación activa en Oficina técnica
    assert t_prod.id in marta and t_ot.id in marta and t_ot_n3.id in marta
    assert marta[t_ot.id]["origen"] == "formacion"
    assert t_borrador.id not in marta  # sin instrucción publicada no se ejecuta

    assert cliente.get("/api/planta/tareas", headers=cab(cliente, "invitado")).status_code == 401


# --------------------------------------------------------------------------- ejecución completa


def test_ejecucion_completa_con_paso_critico(cliente, bd, planta, recalculos):
    tarea, ins = crear_tarea_con_instruccion(bd, planta, "prod")
    h = cab(cliente, "pedro")
    r = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h)
    assert r.status_code == 200, r.text
    ej = r.json()
    assert ej["estado"] == "en_curso" and ej["reanudada"] is False
    assert ej["instruccion"]["codigo"] == ins.codigo and ej["total_pasos"] == 3 and ej["paso_actual"] == 0
    pasos = ej["pasos"]
    assert pasos[1]["es_critico"] is True
    assert pasos[2]["imagen_url"].startswith("/api/ficheros/") and "firma=" in pasos[2]["imagen_url"]
    assert cliente.get(pasos[2]["imagen_url"]).status_code == 200  # la URL firmada sirve el fichero
    assert (planta.personas["pedro"].id, tarea.id) in recalculos  # empezar cuenta para el nivel I

    # Volver a «Empezar» reanuda la misma ejecución.
    r2 = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    assert r2["id"] == ej["id"] and r2["reanudada"] is True

    base = f"/api/planta/ejecuciones/{ej['id']}"
    assert cliente.post(f"{base}/pasos/{pasos[0]['id']}/confirmar", json={}, headers=h).status_code == 200
    # Finalizar antes de tiempo: faltan pasos.
    r = cliente.post(f"{base}/finalizar", headers=h)
    assert r.status_code == 400 and "2, 3" in r.json()["detail"]
    # Paso crítico sin confirmación: rechazado.
    r = cliente.post(f"{base}/pasos/{pasos[1]['id']}/confirmar", json={"critico_confirmado": False}, headers=h)
    assert r.status_code == 400 and "crítico" in r.json()["detail"]
    r = cliente.post(f"{base}/pasos/{pasos[1]['id']}/confirmar", json={"critico_confirmado": True}, headers=h)
    assert r.status_code == 200 and r.json()["critico_confirmado"] is True
    r = cliente.post(f"{base}/pasos/{pasos[2]['id']}/confirmar", json={}, headers=h)
    assert r.json()["pasos_confirmados"] == 3

    # Un paso de otra instrucción no vale.
    _, otra = crear_tarea_con_instruccion(bd, planta, "prod")
    ajeno = otra.pasos[0].id
    assert cliente.post(f"{base}/pasos/{ajeno}/confirmar", json={}, headers=h).status_code == 404

    recalculos.clear()
    r = cliente.post(f"{base}/finalizar", headers=h)
    assert r.status_code == 200, r.text
    resumen = r.json()["resumen"]
    assert r.json()["estado"] == "completada"
    assert resumen["pasos"] == 3 and resumen["pasos_criticos"] == 1 and resumen["ejecuciones_completadas"] == 1
    assert resumen["consultas"] == 0 and resumen["duracion_s"] >= 0
    assert recalculos == [(planta.personas["pedro"].id, tarea.id)]

    bd.expire_all()
    fila = bd.get(Ejecucion, ej["id"])
    assert fila.estado == "completada" and fila.fin is not None
    assert len(_sentencias(bd, "confirmo", ej["id"])) == 3
    completo = _sentencias(bd, "completo", ej["id"])
    assert len(completo) == 1
    assert set(completo[0].resultado) >= {"consultas", "consultas_criticos", "duracion"}
    critico = bd.scalar(select(EjecucionPaso).where(EjecucionPaso.ejecucion_id == ej["id"],
                                                    EjecucionPaso.paso_id == pasos[1]["id"]))
    assert critico.critico_confirmado is True

    # Ya completada: no se puede tocar ni finalizar dos veces (ni cambiar la foto).
    assert cliente.post(f"{base}/finalizar", headers=h).status_code == 409
    assert cliente.post(f"{base}/foto", files={"imagen": ("r.png", PNG, "image/png")}, headers=h).status_code == 409
    lista = {t["id"]: t for t in cliente.get("/api/planta/tareas", headers=h).json()}
    assert lista[tarea.id]["ejecuciones_completadas"] == 1 and lista[tarea.id]["ejecucion_en_curso"] is None


def test_abandonar(cliente, bd, planta, recalculos):
    tarea, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    h = cab(cliente, "pedro")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    base = f"/api/planta/ejecuciones/{ej['id']}"
    r = cliente.post(f"{base}/abandonar", headers=h)
    assert r.status_code == 200 and r.json()["estado"] == "abandonada"
    assert cliente.post(f"{base}/pasos/{ej['pasos'][0]['id']}/confirmar", json={}, headers=h).status_code == 409
    assert len(_sentencias(bd, "abandono", ej["id"])) == 1
    # Una nueva ejecución empieza de cero.
    nueva = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    assert nueva["id"] != ej["id"] and nueva["reanudada"] is False


def test_tarea_sin_instruccion_publicada(cliente, bd, planta):
    tarea, _ = crear_tarea_con_instruccion(bd, planta, "prod", publicada=False)
    r = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=cab(cliente, "pedro"))
    assert r.status_code == 409


# --------------------------------------------------------------------------- preguntas en contexto


def test_preguntar_en_contexto_del_paso(cliente, bd, planta, monkeypatch, recalculos):
    llamadas: list[dict[str, Any]] = []

    async def falso(bd_, actor, pregunta, modo="normal", contexto=None, historial=None):
        llamadas.append({"pregunta": pregunta, "modo": modo, "contexto": contexto, "actor": actor.id})
        yield {"tipo": "fuentes", "fuentes": [{"n": 1, "titulo": "IT de prueba", "metadatos": {"paso": 2}}]}
        yield {"tipo": "token", "texto": "Usa la llave "}
        yield {"tipo": "token", "texto": "dinamométrica [1]."}
        yield {"tipo": "fin", "consulta_id": None, "con_respaldo": True, "laguna_id": None}

    monkeypatch.setattr(consulta, "responder_stream", falso)
    tarea, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    h = cab(cliente, "pedro")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    critico, normal = ej["pasos"][1], ej["pasos"][0]
    base = f"/api/planta/ejecuciones/{ej['id']}"

    r = cliente.post(f"{base}/preguntar", json={"pregunta": "¿Qué llave uso?", "paso_id": critico["id"]}, headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    eventos = _eventos(r.text)
    assert [e for e, _ in eventos] == ["fuentes", "token", "token", "fin"]
    assert "".join(d["texto"] for e, d in eventos if e == "token") == "Usa la llave dinamométrica [1]."
    assert llamadas[0]["modo"] == "planta"
    assert llamadas[0]["contexto"] == {"tarea_id": tarea.id, "paso_id": critico["id"], "ejecucion_id": ej["id"]}

    cliente.post(f"{base}/preguntar", json={"pregunta": "¿Y ahora?", "paso_id": normal["id"]}, headers=h)
    cliente.post(f"{base}/preguntar", json={"pregunta": "Pregunta general"}, headers=h)

    bd.expire_all()
    fila = bd.get(Ejecucion, ej["id"])
    assert fila.consultas == 3 and fila.consultas_criticos == 1
    por_paso = {ep.paso_id: ep.consultas for ep in bd.scalars(
        select(EjecucionPaso).where(EjecucionPaso.ejecucion_id == ej["id"]))}
    assert por_paso[critico["id"]] == 1 and por_paso[normal["id"]] == 1

    # Validaciones: pregunta vacía, paso ajeno, ejecución de otra persona.
    assert cliente.post(f"{base}/preguntar", json={"pregunta": "  "}, headers=h).status_code == 400
    _, otra = crear_tarea_con_instruccion(bd, planta, "prod")
    r = cliente.post(f"{base}/preguntar", json={"pregunta": "x", "paso_id": otra.pasos[0].id}, headers=h)
    assert r.status_code == 404
    r = cliente.post(f"{base}/preguntar", json={"pregunta": "x"}, headers=cab(cliente, "marta"))
    assert r.status_code == 404


def test_preguntar_si_el_copiloto_falla(cliente, bd, planta, monkeypatch, recalculos):
    async def roto(*a, **k):
        raise RuntimeError("modelo caído")
        yield {}  # pragma: no cover

    monkeypatch.setattr(consulta, "responder_stream", roto)
    tarea, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    h = cab(cliente, "pedro")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    r = cliente.post(f"/api/planta/ejecuciones/{ej['id']}/preguntar", json={"pregunta": "¿Qué hago?"}, headers=h)
    assert r.status_code == 200
    eventos = _eventos(r.text)
    assert eventos[-1][0] == "error" and "no ha podido" in eventos[-1][1]["mensaje"]
    # Aunque no hubo respuesta, la pregunta cuenta para la curva de autonomía.
    bd.expire_all()
    assert bd.get(Ejecucion, ej["id"]).consultas == 1


def test_preguntar_cuenta_antes_de_responder(cliente, bd, planta, monkeypatch, recalculos):
    """La pregunta queda contada (y guardada) antes de que empiece la respuesta: si la persona cierra
    la pantalla a mitad del streaming, la consulta en el paso crítico no se pierde."""
    from cidia.db import nueva_sesion

    vistas: list[tuple[int, int, int]] = []

    async def mira_y_responde(bd_, actor, pregunta, modo="normal", contexto=None, historial=None):
        with nueva_sesion() as otra:  # otra conexión: solo ve lo que ya está guardado
            fila = otra.get(Ejecucion, contexto["ejecucion_id"])
            ep = otra.scalar(select(EjecucionPaso).where(EjecucionPaso.ejecucion_id == fila.id,
                                                         EjecucionPaso.paso_id == contexto["paso_id"]))
            vistas.append((fila.consultas, fila.consultas_criticos, ep.consultas))
        yield {"tipo": "token", "texto": "Respuesta."}
        yield {"tipo": "fin", "consulta_id": None, "con_respaldo": False, "laguna_id": None}

    monkeypatch.setattr(consulta, "responder_stream", mira_y_responde)
    tarea, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    h = cab(cliente, "pedro")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    cliente.post(f"/api/planta/ejecuciones/{ej['id']}/preguntar",
                 json={"pregunta": "¿Qué par?", "paso_id": ej["pasos"][1]["id"]}, headers=h)
    assert vistas == [(1, 1, 1)]
    # Y una sola vez: el copiloto no vuelve a sumarla al terminar.
    bd.expire_all()
    fila = bd.get(Ejecucion, ej["id"])
    assert fila.consultas == 1 and fila.consultas_criticos == 1
    # Una ejecución terminada ya no admite preguntas (ni las cuenta).
    cliente.post(f"/api/planta/ejecuciones/{ej['id']}/abandonar", headers=h)
    r = cliente.post(f"/api/planta/ejecuciones/{ej['id']}/preguntar", json={"pregunta": "¿Y ahora?"}, headers=h)
    assert r.status_code == 409
    bd.expire_all()
    assert bd.get(Ejecucion, ej["id"]).consultas == 1


def test_preguntar_con_el_copiloto_real(cliente, bd, planta, ia, recalculos):
    """Integración con servicios/consulta.py (modelo falso): guarda la consulta con su paso y cuenta una vez."""
    ia.respuesta = "Usa la llave dinamométrica y aprieta en cruz."
    tarea, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    h = cab(cliente, "pedro")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    critico = ej["pasos"][1]
    r = cliente.post(f"/api/planta/ejecuciones/{ej['id']}/preguntar",
                     json={"pregunta": "¿Qué llave uso para apretar los tornillos?", "paso_id": critico["id"]}, headers=h)
    assert r.status_code == 200
    eventos = _eventos(r.text)
    assert eventos[-1][0] == "fin", eventos
    assert "llave dinamométrica" in "".join(d.get("texto", "") for e, d in eventos if e == "token")
    bd.expire_all()
    fila = bd.get(Ejecucion, ej["id"])
    assert fila.consultas == 1 and fila.consultas_criticos == 1
    guardada = bd.scalar(select(Consulta).where(Consulta.ejecucion_id == ej["id"]))
    assert guardada.paso_id == critico["id"] and guardada.modo == "planta" and guardada.tarea_id == tarea.id
    historial = cliente.get(f"/api/planta/ejecuciones/{ej['id']}", headers=h).json()["historial"]
    assert historial[0]["paso_id"] == critico["id"] and historial[0]["respuesta"]


# --------------------------------------------------------------------------- foto del resultado


def test_foto_sin_vision(cliente, bd, planta, monkeypatch, recalculos):
    monkeypatch.setattr(llm, "modelo_vision", lambda bd=None: None)
    tarea, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    h = cab(cliente, "pedro")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    r = cliente.post(f"/api/planta/ejecuciones/{ej['id']}/foto", files={"imagen": ("resultado.png", PNG, "image/png")},
                     headers=h)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["estado"] == "sin_vision" and v["revision_humana"] is True and v["coincide"] is None
    assert "persona" in v["mensaje"]
    assert cliente.get(v["foto_url"]).status_code == 200
    bd.expire_all()
    assert bd.get(Ejecucion, ej["id"]).foto_ruta
    assert len(_sentencias(bd, "fotografio")) >= 1
    # El veredicto se ve también al recargar la ejecución.
    assert cliente.get(f"/api/planta/ejecuciones/{ej['id']}", headers=h).json()["foto"]["estado"] == "sin_vision"
    # Un fichero que no es imagen se rechaza.
    r = cliente.post(f"/api/planta/ejecuciones/{ej['id']}/foto", files={"imagen": ("notas.txt", b"hola", "text/plain")},
                     headers=h)
    assert r.status_code == 400


def test_foto_con_vision(cliente, bd, planta, ia, recalculos):
    ia.json = {"coincide": "sí", "observaciones": "Los cuatro tornillos están puestos.", "confianza": 85}
    tarea, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    h = cab(cliente, "pedro")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    v = cliente.post(f"/api/planta/ejecuciones/{ej['id']}/foto", files={"imagen": ("r.png", PNG, "image/png")},
                     headers=h).json()
    assert v["estado"] == "comparada" and v["coincide"] is True and v["confianza"] == 0.85
    assert v["modelo"] == "vision-falso" and v["referencia_url"]
    partes = ia.llamadas[-1]["mensajes"][-1]["content"]
    assert sum(1 for p in partes if p.get("type") == "image_url") == 2  # referencia y foto


def test_foto_con_vision_y_json_roto(cliente, bd, planta, ia, recalculos):
    ia.json = {"texto": "no sé"}
    tarea, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    h = cab(cliente, "pedro")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    v = cliente.post(f"/api/planta/ejecuciones/{ej['id']}/foto", files={"imagen": ("r.png", PNG, "image/png")},
                     headers=h).json()
    assert v["estado"] == "error" and v["revision_humana"] is True


def test_veredicto_tolerante_con_modelos_pequenos():
    """Formas reales de responder de los modelos pequeños: anidado, en lista, sí/no como texto."""
    from cidia.servicios.planta import _veredicto_modelo

    v = _veredicto_modelo({"resultado": {"coincide": "Verdadero.", "observaciones": "Bien.", "confianza": "0.7"}})
    assert v == {"coincide": True, "observaciones": "Bien.", "confianza": 0.7}
    v = _veredicto_modelo([{"coincide": "no", "observaciones": "Falta un tornillo", "confianza": "alta"}])
    assert v["coincide"] is False and v["confianza"] is None
    assert _veredicto_modelo({"coincide": False, "confianza": 140})["confianza"] == 1.0
    for malo in ({"coincide": "puede"}, {"texto": "no sé"}, "coincide", []):
        with pytest.raises(ValueError):
            _veredicto_modelo(malo)


def test_foto_solo_imagenes_de_verdad(cliente, bd, planta, monkeypatch, recalculos):
    """Un SVG o un HTML disfrazado de imagen se serviría desde el mismo origen que la interfaz
    (podría robar la sesión): se decide por los bytes, no por el nombre ni el tipo declarado."""
    monkeypatch.setattr(llm, "modelo_vision", lambda bd=None: None)
    tarea, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    h = cab(cliente, "pedro")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    url = f"/api/planta/ejecuciones/{ej['id']}/foto"
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert cliente.post(url, files={"imagen": ("foto.svg", svg, "image/svg+xml")}, headers=h).status_code == 400
    html = b"<html><script>alert(1)</script></html>"
    r = cliente.post(url, files={"imagen": ("foto.html", html, "image/png")}, headers=h)
    assert r.status_code == 400 and "JPG" in r.json()["detail"]
    assert cliente.post(url, files={"imagen": ("vacia.jpg", b"", "image/jpeg")}, headers=h).status_code == 400
    # Una imagen buena con un nombre peligroso se guarda con un nombre fijo y su extensión real.
    r = cliente.post(url, files={"imagen": ("x.html", PNG, "image/png")}, headers=h)
    assert r.status_code == 200, r.text
    foto_url = r.json()["foto_url"]
    assert "resultado.png" in foto_url and ".html" not in foto_url
    servida = cliente.get(foto_url)
    assert servida.status_code == 200 and servida.headers["content-type"].startswith("image/png")
    # Sesión de otra persona: no puede subir fotos a esta ejecución.
    assert cliente.post(url, files={"imagen": ("r.png", PNG, "image/png")},
                        headers=cab(cliente, "javier")).status_code == 403


# --------------------------------------------------------------------------- permisos


def test_permisos_de_ejecucion(cliente, bd, planta, recalculos):
    tarea, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    t_ot, _ = crear_tarea_con_instruccion(bd, planta, "ot")
    # Luis (Oficina técnica) no puede ejecutar una tarea de Producción.
    r = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=cab(cliente, "luis"))
    assert r.status_code == 403
    # Pedro (Producción, sin formación) tampoco una de Oficina técnica.
    r = cliente.post("/api/planta/ejecuciones", json={"tarea_id": t_ot.id}, headers=cab(cliente, "pedro"))
    assert r.status_code == 403
    assert cliente.post("/api/planta/ejecuciones", json={"tarea_id": 999999},
                        headers=cab(cliente, "pedro")).status_code == 404
    # Identificadores fuera del rango de la BD: 404, no un error del servidor.
    assert cliente.post("/api/planta/ejecuciones", json={"tarea_id": 2**40},
                        headers=cab(cliente, "pedro")).status_code == 404
    assert cliente.get(f"/api/planta/ejecuciones/{2**40}", headers=cab(cliente, "pedro")).status_code == 404

    h = cab(cliente, "pedro")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    base = f"/api/planta/ejecuciones/{ej['id']}"
    paso = ej["pasos"][0]["id"]
    assert cliente.post(f"{base}/pasos/{2**40}/confirmar", json={}, headers=h).status_code == 404

    # Otra persona del mismo departamento: ni la ve ni la toca.
    hm = cab(cliente, "marta")
    assert cliente.get(base, headers=hm).status_code == 404
    assert cliente.post(f"{base}/pasos/{paso}/confirmar", json={}, headers=hm).status_code == 404
    assert cliente.post(f"{base}/finalizar", headers=hm).status_code == 404
    assert cliente.post(f"{base}/abandonar", headers=hm).status_code == 404
    assert cliente.post(f"{base}/foto", files={"imagen": ("r.png", PNG, "image/png")}, headers=hm).status_code == 404
    # La jefa de otro departamento tampoco.
    assert cliente.get(base, headers=cab(cliente, "ana")).status_code == 404
    # El jefe de Producción y la administración la ven, pero no pueden avanzar en ella.
    hj = cab(cliente, "javier")
    vista = cliente.get(base, headers=hj)
    assert vista.status_code == 200 and vista.json()["es_mia"] is False
    assert vista.json()["persona"]["nombre"] == "Pedro Ruiz"
    assert cliente.post(f"{base}/pasos/{paso}/confirmar", json={}, headers=hj).status_code == 403
    assert cliente.get(base, headers=cab(cliente, "admin")).status_code == 200
    # Sin sesión, nada.
    assert cliente.get(base).status_code == 401
    assert cliente.get(base, headers=cab(cliente, "invitado")).status_code == 401
    # La propia persona sí.
    assert cliente.get(base, headers=h).json()["es_mia"] is True


def test_formacion_activa_da_acceso_al_modo_planta(cliente, bd, planta, recalculos):
    t_ot, _ = crear_tarea_con_instruccion(bd, planta, "ot")
    r = cliente.post("/api/planta/ejecuciones", json={"tarea_id": t_ot.id}, headers=cab(cliente, "marta"))
    assert r.status_code == 200, r.text
    bd.expire_all()
    assert bd.scalar(select(Ejecucion).where(Ejecucion.id == r.json()["id"])).usuario_id == planta.personas["marta"].id


def test_supervision_de_quien_se_forma_en_otro_departamento(cliente, bd, planta, recalculos):
    """Marta (Producción) se forma en Oficina técnica: ven su ejecución su jefe (Javier) y la jefa del
    departamento en el que se forma (Ana); nadie más. Una tarea de Producción, Ana no la ve."""
    t_ot, _ = crear_tarea_con_instruccion(bd, planta, "ot")
    t_prod, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    hm = cab(cliente, "marta")
    ej_ot = cliente.post("/api/planta/ejecuciones", json={"tarea_id": t_ot.id}, headers=hm).json()
    ej_prod = cliente.post("/api/planta/ejecuciones", json={"tarea_id": t_prod.id}, headers=hm).json()
    ha, hj = cab(cliente, "ana"), cab(cliente, "javier")
    assert cliente.get(f"/api/planta/ejecuciones/{ej_ot['id']}", headers=ha).status_code == 200
    assert cliente.get(f"/api/planta/ejecuciones/{ej_ot['id']}", headers=hj).status_code == 200
    assert cliente.get(f"/api/planta/ejecuciones/{ej_prod['id']}", headers=ha).status_code == 404
    for quien in ("luis", "carmen", "pedro"):  # compañeros, expertos sin ser jefes...
        assert cliente.get(f"/api/planta/ejecuciones/{ej_ot['id']}", headers=cab(cliente, quien)).status_code == 404
    # Ver no es tocar.
    paso = ej_ot["pasos"][0]["id"]
    assert cliente.post(f"/api/planta/ejecuciones/{ej_ot['id']}/pasos/{paso}/confirmar", json={},
                        headers=ha).status_code == 403
    assert cliente.post(f"/api/planta/ejecuciones/{ej_ot['id']}/abandonar", headers=ha).status_code == 403


def test_historial_con_fuentes_refirmadas_y_filtradas(cliente, bd, planta, recalculos):
    """Las fuentes del historial se vuelven a firmar al leerlo, y solo las de documentos que puede
    ver quien mira: la jefa de Oficina técnica no puede abrir un documento de Producción que el
    copiloto citó a Marta (que es de Producción)."""
    from cidia.modelos import Documento

    t_ot, _ = crear_tarea_con_instruccion(bd, planta, "ot")
    hm = cab(cliente, "marta")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": t_ot.id}, headers=hm).json()
    docs = []
    for dep, titulo in (("ot", "Manual de utillajes"), ("prod", "Hoja de la línea 2")):
        d = Documento(titulo=titulo, tipo="imagen", departamento_id=planta.deps[dep].id, nivel_minimo=1,
                      es_formacion=True, estado="listo", ruta_fichero=_imagen(f"doc_{uuid.uuid4().hex[:6]}.png"),
                      nombre_fichero="doc.png")
        bd.add(d)
        docs.append(d)
    bd.flush()
    vieja = "/api/ficheros/otra/ruta.pdf?exp=1&firma=caducada"
    bd.add(Consulta(usuario_id=planta.personas["marta"].id, pregunta="¿Qué utillaje uso?", respuesta="El del manual [1].",
                    modo="planta", con_respaldo=True, tarea_id=t_ot.id, paso_id=ej["pasos"][0]["id"], ejecucion_id=ej["id"],
                    fuentes=[{"n": i + 1, "documento_id": d.id, "titulo": d.titulo, "fragmento": f"Fragmento {i + 1}.",
                              "url": vieja} for i, d in enumerate(docs)]))
    bd.commit()

    propias = cliente.get(f"/api/planta/ejecuciones/{ej['id']}", headers=hm).json()["historial"][0]["fuentes"]
    assert [f["disponible"] for f in propias] == [True, True] and propias[0]["fragmento"] == "Fragmento 1."
    assert propias[0]["url"] != vieja and cliente.get(propias[0]["url"]).status_code == 200
    jefa_ot = cliente.get(f"/api/planta/ejecuciones/{ej['id']}", headers=cab(cliente, "ana")).json()
    assert jefa_ot["contenido_restringido"] is False and jefa_ot["historial"][0]["respuesta"] == "El del manual [1]."
    fuentes = jefa_ot["historial"][0]["fuentes"]
    assert fuentes[0]["disponible"] is True
    assert fuentes[1] == {"n": 2, "documento_id": None, "titulo": "Documento no disponible", "fragmento": "", "url": None,
                          "disponible": False}


def test_supervisor_sin_acceso_a_la_tarea_no_ve_el_contenido(cliente, bd, planta, recalculos, monkeypatch):
    """El jefe de Marta (Producción) supervisa su ejecución de una tarea de Oficina técnica: ve el
    avance, las consultas por paso y su foto, pero no la instrucción de otro departamento (texto,
    criterios, imágenes, clips, riesgos) ni lo que respondió el copiloto."""
    monkeypatch.setattr(llm, "modelo_vision", lambda bd=None: None)
    t_ot, _ = crear_tarea_con_instruccion(bd, planta, "ot")
    hm = cab(cliente, "marta")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": t_ot.id}, headers=hm).json()
    base = f"/api/planta/ejecuciones/{ej['id']}"
    cliente.post(f"{base}/pasos/{ej['pasos'][0]['id']}/confirmar", json={}, headers=hm)
    cliente.post(f"{base}/foto", files={"imagen": ("r.png", PNG, "image/png")}, headers=hm)
    bd.add(Consulta(usuario_id=planta.personas["marta"].id, pregunta="¿Qué par?", respuesta="25 N·m según la IT [1].",
                    modo="planta", con_respaldo=True, tarea_id=t_ot.id, paso_id=ej["pasos"][1]["id"],
                    ejecucion_id=ej["id"], fuentes=[{"n": 1, "documento_id": None, "titulo": "IT", "fragmento": "25 N·m"}]))
    bd.commit()

    jefe = cliente.get(base, headers=cab(cliente, "javier")).json()
    assert jefe["contenido_restringido"] is True and jefe["es_mia"] is False
    assert jefe["pasos_confirmados"] == 1 and [p["titulo"] for p in jefe["pasos"]] == [p["titulo"] for p in ej["pasos"]]
    for p in jefe["pasos"]:
        assert p["texto"] is None and p["criterio_aceptacion"] is None and p["imagen_url"] is None and p["clip_url"] is None
    ins = jefe["instruccion"]
    assert ins["resumen"] is None and ins["riesgos"] is None and ins["epis"] is None and jefe["tarea"]["riesgos_prl"] is None
    h = jefe["historial"][0]
    assert h["pregunta"] == "¿Qué par?" and h["respuesta"] is None and h["fuentes"] == []
    assert jefe["foto"]["foto_url"] and jefe["foto"]["referencia_url"] is None
    # La propia persona, la jefa del departamento de la tarea y la administración lo ven todo.
    for quien in ("marta", "ana", "admin"):
        completo = cliente.get(base, headers=cab(cliente, quien)).json()
        assert completo["contenido_restringido"] is False
        assert completo["pasos"][2]["imagen_url"] and completo["historial"][0]["respuesta"]
        assert completo["foto"]["referencia_url"]


def test_nueva_version_cierra_la_ejecucion_anterior(cliente, bd, planta, recalculos):
    """Si se publica otra versión con una ejecución a medias, al empezar se abandona la vieja
    (con su sentencia xAPI) y se crea otra con la instrucción nueva."""
    tarea, v1 = crear_tarea_con_instruccion(bd, planta, "prod")
    h = cab(cliente, "pedro")
    vieja = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    v1.estado = "obsoleta"
    v2 = Instruccion(tarea_id=tarea.id, codigo=v1.codigo, version=2, estado="publicada", titulo=v1.titulo,
                     publicada_en=ahora())
    bd.add(v2)
    bd.flush()
    bd.add(Paso(instruccion_id=v2.id, orden=1, titulo="Paso único de la versión 2"))
    bd.commit()

    lista = {t["id"]: t for t in cliente.get("/api/planta/tareas", headers=h).json()}
    assert lista[tarea.id]["ejecucion_en_curso"]["misma_version"] is False
    nueva = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    assert nueva["id"] != vieja["id"] and nueva["instruccion"]["version"] == 2 and nueva["total_pasos"] == 1
    bd.expire_all()
    assert bd.get(Ejecucion, vieja["id"]).estado == "abandonada"
    abandono = _sentencias(bd, "abandono", vieja["id"])
    assert len(abandono) == 1 and abandono[0].resultado["motivo"] == "nueva_version"


def test_sin_acceso_a_la_tarea_no_se_puede_seguir(cliente, bd, planta, recalculos):
    """Si se cancela la formación a mitad de una ejecución, ya no suma evidencias: solo puede abandonarla."""
    from fabrica import _hash

    from cidia.modelos import Formacion, Usuario

    nombre = "temporal_" + uuid.uuid4().hex[:6]
    u = Usuario(usuario=nombre, nombre="Persona temporal", hash_contrasena=_hash(), rol="empleado",
                departamento_id=planta.deps["prod"].id, nivel_id=planta.niveles[1].id, puesto_id=planta.puestos["prod"].id)
    bd.add(u)
    bd.flush()
    form = Formacion(usuario_id=u.id, departamento_id=planta.deps["ot"].id, estado="activa")
    bd.add(form)
    bd.commit()
    t_ot, _ = crear_tarea_con_instruccion(bd, planta, "ot")
    h = cab(cliente, nombre)
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": t_ot.id}, headers=h).json()
    base = f"/api/planta/ejecuciones/{ej['id']}"
    assert cliente.post(f"{base}/pasos/{ej['pasos'][0]['id']}/confirmar", json={}, headers=h).status_code == 200

    form.estado = "cancelada"
    bd.commit()
    r = cliente.post(f"{base}/pasos/{ej['pasos'][1]['id']}/confirmar", json={"critico_confirmado": True}, headers=h)
    assert r.status_code == 403 and "acceso" in r.json()["detail"]
    assert cliente.post(f"{base}/preguntar", json={"pregunta": "¿Sigo?"}, headers=h).status_code == 403
    assert cliente.post(f"{base}/finalizar", headers=h).status_code == 403
    assert cliente.get(base, headers=h).status_code == 200  # la sigue viendo
    assert cliente.post(f"{base}/abandonar", headers=h).json()["estado"] == "abandonada"


# --------------------------------------------------------------------------- con el modelo real (CIDIA_TEST_IA_REAL=1)


def _png_color(color: tuple[int, int, int], lado: int = 64) -> bytes:
    """PNG de un solo color (sin dependencias) para probar la visión real."""
    import struct
    import zlib

    filas = b"".join(b"\x00" + bytes(color) * lado for _ in range(lado))

    def trozo(tipo: bytes, datos: bytes) -> bytes:
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)

    cabecera = struct.pack(">IIBBBBB", lado, lado, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", cabecera) + trozo(b"IDAT", zlib.compress(filas)) + trozo(b"IEND", b"")


@pytest.mark.ia_real
def test_foto_con_vision_real(cliente, bd, planta, monkeypatch, recalculos):
    import os

    modelo = os.environ.get("CIDIA_TEST_MODELO_VISION", "qwen3.5:0.8b")
    monkeypatch.setattr(llm, "modelo_vision", lambda bd=None: modelo)
    tarea, ins = crear_tarea_con_instruccion(bd, planta, "prod")
    referencia = ins.pasos[-1].imagen_ruta
    (ajustes().dir_datos / referencia).write_bytes(_png_color((200, 30, 30)))  # referencia roja
    h = cab(cliente, "pedro")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    v = cliente.post(f"/api/planta/ejecuciones/{ej['id']}/foto",
                     files={"imagen": ("azul.png", _png_color((30, 30, 200)), "image/png")}, headers=h).json()
    print(v)
    assert v["estado"] == "comparada" and v["coincide"] is False


# --------------------------------------------------------------------------- revisión de la foto por el jefe


def _ejecucion_con_foto(cliente, bd, planta, usuario: str = "pedro", dep: str = "prod",
                        completar: bool = True) -> tuple[dict[str, Any], dict[str, str]]:
    """Ejecución con todos los pasos confirmados, foto del resultado y (si `completar`) finalizada."""
    tarea, _ = crear_tarea_con_instruccion(bd, planta, dep)
    h = cab(cliente, usuario)
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    base = f"/api/planta/ejecuciones/{ej['id']}"
    for p in ej["pasos"]:
        r = cliente.post(f"{base}/pasos/{p['id']}/confirmar", json={"critico_confirmado": p["es_critico"]}, headers=h)
        assert r.status_code == 200, r.text
    assert cliente.post(f"{base}/foto", files={"imagen": ("r.png", PNG, "image/png")}, headers=h).status_code == 200
    if completar:
        assert cliente.post(f"{base}/finalizar", headers=h).status_code == 200
    return ej, h


def test_necesita_revision():
    from cidia.servicios.planta import necesita_revision

    assert necesita_revision({"estado": "sin_vision"}) and necesita_revision({"estado": "error"})
    assert necesita_revision({"estado": "sin_referencia"})
    assert necesita_revision({"estado": "comparada", "coincide": False, "confianza": 0.95})
    assert necesita_revision({"estado": "comparada", "coincide": True, "confianza": 0.4})  # duda
    assert not necesita_revision({"estado": "comparada", "coincide": True, "confianza": 0.9})
    assert not necesita_revision({"estado": "comparada", "coincide": True, "confianza": None})
    assert not necesita_revision(None)


def test_foto_con_dudas_del_modelo_queda_para_revision(cliente, bd, planta, ia, recalculos):
    ia.json = {"coincide": True, "observaciones": "Parece igual.", "confianza": 0.3}
    tarea, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    h = cab(cliente, "pedro")
    ej = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=h).json()
    v = cliente.post(f"/api/planta/ejecuciones/{ej['id']}/foto", files={"imagen": ("r.png", PNG, "image/png")},
                     headers=h).json()
    assert v["coincide"] is True and v["revision_humana"] is True and v["pendiente_revision"] is True
    assert "no está seguro" in v["mensaje"]
    ia.json = {"coincide": True, "observaciones": "Igual.", "confianza": 0.95}
    v = cliente.post(f"/api/planta/ejecuciones/{ej['id']}/foto", files={"imagen": ("r.png", PNG, "image/png")},
                     headers=h).json()
    assert v["revision_humana"] is False and v["pendiente_revision"] is False and v["revision"] is None


def test_el_jefe_revisa_la_foto(cliente, bd, planta, monkeypatch, recalculos):
    monkeypatch.setattr(llm, "modelo_vision", lambda bd=None: None)  # sin visión: la revisa una persona
    ej, h = _ejecucion_con_foto(cliente, bd, planta)
    base = f"/api/planta/ejecuciones/{ej['id']}"
    hj = cab(cliente, "javier")

    # La ve en su lista de pendientes y en la ejecución, con los botones de revisión.
    lista = cliente.get("/api/planta/revisiones", headers=hj)
    assert lista.status_code == 200, lista.text
    pend = {e["id"]: e for e in lista.json()["elementos"]}
    assert ej["id"] in pend and lista.json()["pendientes"] >= 1
    item = pend[ej["id"]]
    assert item["persona"]["nombre"] == "Pedro Ruiz" and item["pendiente"] is True
    assert item["foto"]["foto_url"] and item["foto"]["estado"] == "sin_vision"
    vista = cliente.get(base, headers=hj).json()
    assert vista["puede_revisar"] is True and vista["foto"]["pendiente_revision"] is True
    assert cliente.get(base, headers=h).json()["puede_revisar"] is False  # quien la hizo no se revisa

    # Quien no es jefe del departamento de la tarea no puede.
    assert cliente.get("/api/planta/revisiones", headers=h).status_code == 403
    assert cliente.get("/api/planta/revisiones", headers=cab(cliente, "carmen")).status_code == 403  # experta
    assert cliente.post(f"{base}/revision", json={"decision": "aprobada"}, headers=h).status_code == 403
    assert cliente.post(f"{base}/revision", json={"decision": "aprobada"},
                        headers=cab(cliente, "carmen")).status_code == 404  # no la supervisa: no existe
    assert cliente.post(f"{base}/revision", json={"decision": "aprobada"},
                        headers=cab(cliente, "ana")).status_code == 404  # otro departamento
    ajenas = cliente.get("/api/planta/revisiones", headers=cab(cliente, "ana")).json()["elementos"]
    assert ej["id"] not in {e["id"] for e in ajenas}
    assert cliente.post(f"{base}/revision", json={"decision": "quizás"}, headers=hj).status_code == 422

    # Rechazar exige explicar qué hay que corregir.
    r = cliente.post(f"{base}/revision", json={"decision": "rechazada", "comentario": " "}, headers=hj)
    assert r.status_code == 400 and "comentario" in r.json()["detail"]
    recalculos.clear()
    r = cliente.post(f"{base}/revision", json={"decision": "rechazada", "comentario": "Falta la marca de testigo."},
                     headers=hj)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["revision"]["estado"] == "rechazada" and v["revision"]["revisor"] == "Javier Martín"
    assert v["revision"]["comentario"] == "Falta la marca de testigo." and v["pendiente_revision"] is False
    assert recalculos == [(planta.personas["pedro"].id, ej["tarea"]["id"])]  # completada: se recalcula el ILUO
    rechazo = _sentencias(bd, "rechazo", ej["id"])
    assert len(rechazo) == 1 and rechazo[0].resultado["decision"] == "rechazada"
    assert rechazo[0].actor_id == planta.personas["javier"].id
    assert rechazo[0].contexto["usuario_id"] == planta.personas["pedro"].id

    # La persona ve la decisión y el comentario; ya no está entre las pendientes, sí entre las revisadas.
    propia = cliente.get(base, headers=h).json()["foto"]["revision"]
    assert propia["estado"] == "rechazada" and propia["comentario"] == "Falta la marca de testigo."
    assert ej["id"] not in {e["id"] for e in cliente.get("/api/planta/revisiones", headers=hj).json()["elementos"]}
    revisadas = cliente.get("/api/planta/revisiones?estado=revisadas", headers=hj).json()["elementos"]
    assert ej["id"] in {e["id"] for e in revisadas}

    # Puede cambiar de decisión (queda constancia de la anterior); la administración también revisa.
    r = cliente.post(f"{base}/revision", json={"decision": "aprobada"}, headers=cab(cliente, "admin"))
    assert r.status_code == 200 and r.json()["revision"]["estado"] == "aprobada"
    valido = _sentencias(bd, "valido", ej["id"])
    assert len(valido) == 1 and valido[0].resultado["decision_anterior"] == "rechazada"


def test_revision_de_quien_se_forma_en_otro_departamento(cliente, bd, planta, monkeypatch, recalculos):
    """Marta (Producción) se forma en Oficina técnica: su foto de una tarea de Oficina técnica la revisa
    Ana (jefa de ese departamento). Javier, su jefe, ve el avance pero no la instrucción: no la revisa."""
    monkeypatch.setattr(llm, "modelo_vision", lambda bd=None: None)
    ej, _ = _ejecucion_con_foto(cliente, bd, planta, usuario="marta", dep="ot", completar=False)
    base = f"/api/planta/ejecuciones/{ej['id']}"
    ha, hj = cab(cliente, "ana"), cab(cliente, "javier")
    assert ej["id"] in {e["id"] for e in cliente.get("/api/planta/revisiones", headers=ha).json()["elementos"]}
    assert ej["id"] not in {e["id"] for e in cliente.get("/api/planta/revisiones", headers=hj).json()["elementos"]}
    assert cliente.get(base, headers=hj).json()["puede_revisar"] is False
    assert cliente.post(f"{base}/revision", json={"decision": "aprobada"}, headers=hj).status_code == 403
    recalculos.clear()
    r = cliente.post(f"{base}/revision", json={"decision": "aprobada", "comentario": "Bien montado."}, headers=ha)
    assert r.status_code == 200 and r.json()["revision"]["estado"] == "aprobada"
    assert recalculos == []  # todavía en curso: el nivel se recalcula al finalizar
    # Una foto nueva vuelve a quedar pendiente de revisión.
    hm = cab(cliente, "marta")
    v = cliente.post(f"{base}/foto", files={"imagen": ("r.png", PNG, "image/png")}, headers=hm).json()
    assert v["revision"] is None and v["pendiente_revision"] is True
    # Una ejecución abandonada ya no se revisa.
    cliente.post(f"{base}/abandonar", headers=hm)
    assert cliente.post(f"{base}/revision", json={"decision": "aprobada"}, headers=ha).status_code == 409
    # Sin foto, tampoco.
    tarea, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    sin = cliente.post("/api/planta/ejecuciones", json={"tarea_id": tarea.id}, headers=cab(cliente, "pedro")).json()
    r = cliente.post(f"/api/planta/ejecuciones/{sin['id']}/revision", json={"decision": "aprobada"}, headers=hj)
    assert r.status_code == 409
