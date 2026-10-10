"""Recorrido completo de la demostración por la API, con los modelos falsos y su propia base.

El mismo guion que qa/recorrido_demo.py (que lo hace contra un gateway en marcha con los modelos
reales), de principio a fin y en una sola prueba, como lo vería el jurado:

  carmen (experta de Producción) sube el vídeo sintético de la brida B → borrador de 7 pasos con
  el 3 crítico → lo corrige y lo publica → aprueba las preguntas; pedro (operario) hace la tarea en
  modo planta con una pregunta por voz en el paso crítico y una foto → la repite hasta tres veces →
  aprueba el cuestionario; javier (jefe) ve la ejecución y lo observa en el puesto → el ILUO sube a
  U y el pasaporte de pedro lo refleja; marta aporta una solución por nota de voz, javier la valida
  y el copiloto se la cita a pedro.

Se mide el tiempo de cada paso y se imprime un resumen (se ve con `pytest -s`). Si no hay ffmpeg, la
instrucción se escribe a mano y el resto del recorrido sigue igual.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fabrica import cab
from sqlalchemy import select

from cidia.ia import asr
from cidia.modelos import Documento, Ejecucion, NivelIluo, SentenciaXapi, Tarea
from cidia.servicios import video

GATEWAY = Path(__file__).resolve().parents[1]
VIDEO_DEMO = GATEWAY.parents[1] / "datos-demo" / "video" / "brida-b-sintetico.mp4"
AUDIO_APORTACION = GATEWAY / "cidia" / "semilla_datos" / "audio" / "aportacion-prensa3.ogg"

# Lo que transcribe faster-whisper (base) del vídeo de la demostración, con sus erratas.
SEGMENTOS_BRIDA = [
    {"inicio": 0, "fin": 4, "texto": "Montaje de la brida B en la estación 2 de la línea A2."},
    {"inicio": 4.8, "fin": 11, "texto": "Paso 1. Preparo la brida B, una junta nueva y 4 tornillos E-10 con su arandela."},
    {"inicio": 11.8, "fin": 18, "texto": "Paso 2. Limpio el asiento y centro la junta. La junta nunca se reutiliza."},
    {"inicio": 19, "fin": 27, "texto": "Paso 3 y es crítico. Aprieto los 4 tornillos en cruza 25 Newton metro con la "
                                       "llave dinamométrica de media pulgada."},
    {"inicio": 27, "fin": 35, "texto": "Primero a 12 y luego a 25. Paso 4. Marco cada tornillo con el rotulador amarillo."},
    {"inicio": 36, "fin": 42, "texto": "Paso 5. Prueba de estanqueidad, tapacerrada, 3 bar durante un minuto."},
    {"inicio": 43, "fin": 48, "texto": "Paso 6. Reviso las marcas, la junta y que no hayar de babas."},
    {"inicio": 49, "fin": 55, "texto": "Paso 7. Registro el número de serie, pegó la etiqueta verde y al carro de salida."},
    {"inicio": 55, "fin": 58, "texto": "Brida B montada."},
]
NOTA_PRENSA = ("Después de cambiar el molde en la prensa 3, la prensa se queda parada con la alarma de falta de pieza "
               "y si fuerzas el ciclo se atasca. Es el sensor S4 de presencia de pieza, que se queda sucio de viruta "
               "y aceite. La solución es limpiar el sensor S4 con un trapo y alcohol y rearmar el ciclo.")
PREGUNTA_VOZ = "¿Qué llave tengo que usar para apretar los tornillos?"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6364f8ffbf1e000502027f3d0c2bb20000000049454e44ae426082"
)


class Cronometro:
    def __init__(self) -> None:
        self.pasos: list[tuple[str, float]] = []

    @contextmanager
    def paso(self, nombre: str) -> Iterator[None]:
        t0 = time.perf_counter()
        yield
        self.pasos.append((nombre, time.perf_counter() - t0))

    def resumen(self) -> str:
        ancho = max(len(n) for n, _ in self.pasos)
        filas = [f"  {n.ljust(ancho)}  {s:6.2f} s" for n, s in self.pasos]
        total = sum(s for _, s in self.pasos)
        return "\nRecorrido de la demostración (modelos falsos)\n" + "\n".join(filas) + f"\n  {'total'.ljust(ancho)}  {total:6.2f} s"


def _ffmpeg_disponible(monkeypatch: pytest.MonkeyPatch) -> bool:
    if not os.environ.get("CIDIA_FFMPEG"):
        locales = sorted((GATEWAY / ".herramientas").glob("*/bin/ffmpeg.exe")) + \
            sorted((GATEWAY / ".herramientas").glob("*/bin/ffmpeg"))
        if locales:
            monkeypatch.setenv("CIDIA_FFMPEG", str(locales[0]))
            monkeypatch.setenv("CIDIA_FFPROBE", str(locales[0].with_name(locales[0].name.replace("ffmpeg", "ffprobe"))))
    return VIDEO_DEMO.exists() and video.disponible()


def _transcripcion(segmentos: list[dict[str, Any]]):
    def transcribir(audio: Any, nombre: str = "audio.webm", con_marcas: bool = False, idioma: str | None = None):
        return {"texto": " ".join(s["texto"] for s in segmentos), "segmentos": segmentos,
                "duracion": segmentos[-1]["fin"]}
    return transcribir


def _sse(texto: str) -> list[tuple[str, dict[str, Any]]]:
    eventos = []
    for bloque in texto.strip().split("\n\n"):
        evento, datos = "message", ""
        for linea in bloque.splitlines():
            if linea.startswith("event:"):
                evento = linea[6:].strip()
            elif linea.startswith("data:"):
                datos += linea[5:].strip()
        if datos:
            eventos.append((evento, json.loads(datos)))
    return eventos


def _ok(r, codigo: int = 200) -> Any:
    assert r.status_code == codigo, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:400]}"
    return r.json()


def test_recorrido_completo_de_la_demo(cliente, bd, planta, ia, monkeypatch):
    crono = Cronometro()
    carmen, javier, pedro, marta = (cab(cliente, u) for u in ("carmen", "javier", "pedro", "marta"))
    sufijo = uuid.uuid4().hex[:6].upper()
    tarea = Tarea(puesto_id=planta.puestos["prod"].id, codigo=f"QA-{sufijo}", nombre=f"Montaje de la brida B ({sufijo})",
                  criticidad=3, nivel_minimo=1)
    bd.add(tarea)
    bd.commit()

    # 1-2. Captura del vídeo, borrador y publicación -------------------------------------------
    con_video = _ffmpeg_disponible(monkeypatch)
    if con_video:
        monkeypatch.setattr(asr, "transcribir", _transcripcion(SEGMENTOS_BRIDA))
        ia.json = {}  # el modelo no propone nada útil: mandan los pasos que dice la experta
        with crono.paso("Experta: sube el vídeo y se genera el borrador"):
            with VIDEO_DEMO.open("rb") as f:
                cap = _ok(cliente.post("/api/captura/video", headers=carmen,
                                       files={"fichero": (VIDEO_DEMO.name, f, "video/mp4")},
                                       data={"tarea_id": str(tarea.id)}))
            cap = _ok(cliente.get(f"/api/captura/{cap['id']}", headers=carmen))
            assert cap["estado"] == "borrador_listo", cap.get("mensaje")
            assert cap["origen_borrador"] == "pasos_narrados"
            ins_id = cap["instruccion_id"]
        with crono.paso("Experta: corrige el borrador"):
            ins = _ok(cliente.get(f"/api/instrucciones/{ins_id}", headers=carmen))
            assert len(ins["pasos"]) == 7 and ins["pasos"][2]["es_critico"]
            assert all(p["imagen_url"] for p in ins["pasos"])  # un fotograma por paso
            pasos = [{k: p.get(k) for k in ("id", "titulo", "texto", "es_critico", "es_seguridad", "criterio_aceptacion")}
                     for p in ins["pasos"]]
            pasos[2]["criterio_aceptacion"] = "Par de 25 N·m en los cuatro tornillos, en cruz."
            pasos[4]["es_seguridad"] = True
            ins = _ok(cliente.put(f"/api/instrucciones/{ins_id}", headers=carmen,
                                  json={"titulo": f"Montaje de la brida B ({sufijo})", "pasos": pasos}))
            assert ins["pasos_criticos"] == 1 and ins["estado"] == "borrador"
        monkeypatch.setattr(asr, "transcribir", ia.transcribir)  # vuelve la voz falsa de conftest
    else:
        with crono.paso("Experta: escribe la instrucción (sin ffmpeg)"):
            pasos = [{"titulo": s["texto"].split(". ", 1)[1][:80], "texto": s["texto"], "es_critico": i == 2}
                     for i, s in enumerate(SEGMENTOS_BRIDA[1:8])]
            ins_id = _ok(cliente.post("/api/instrucciones", headers=carmen,
                                      json={"tarea_id": tarea.id, "titulo": f"Montaje de la brida B ({sufijo})",
                                            "pasos": pasos}))["id"]
    with crono.paso("Experta: publica"):
        pub = _ok(cliente.post(f"/api/instrucciones/{ins_id}/publicar", headers=carmen))
        assert pub["estado"] == "publicada" and pub["version"] == 1
    assert bd.scalar(select(Documento).where(Documento.origen == "instruccion", Documento.origen_id == ins_id))

    # 3. Preguntas del cuestionario: el modelo falso no propone ninguna, así que las escribe ella.
    with crono.paso("Experta: prepara el cuestionario"):
        ins = _ok(cliente.get(f"/api/instrucciones/{ins_id}", headers=carmen))
        correctas: dict[int, str] = {}
        for enunciado, opciones, paso in (
            ("¿A qué par se aprietan los tornillos de la brida?", ["25 N·m", "12 N·m", "50 N·m"], 2),
            ("¿Se puede reutilizar la junta?", ["Nunca", "Sí, si está limpia", "Solo una vez"], 1),
        ):
            p = _ok(cliente.post("/api/evaluacion/preguntas", headers=carmen, json={
                "instruccion_id": ins_id, "enunciado": enunciado, "opciones": opciones, "correcta": 0,
                "paso_id": ins["pasos"][paso]["id"]}))
            assert p["estado"] == "aprobada"
            correctas[p["id"]] = opciones[0]

    # 4. Modo planta: pregunta por voz en el paso crítico, foto y fin --------------------------------
    with crono.paso("Aprendiz: abre la tarea en modo planta"):
        assert tarea.id in {t["id"] for t in _ok(cliente.get("/api/planta/tareas", headers=pedro))}
        ej = _ok(cliente.post("/api/planta/ejecuciones", headers=pedro, json={"tarea_id": tarea.id}))
    critico = next(p for p in ej["pasos"] if p["es_critico"])
    with crono.paso("Aprendiz: pregunta por voz en el paso crítico"):
        for p in ej["pasos"]:
            if p["id"] == critico["id"]:
                break
            _ok(cliente.post(f"/api/planta/ejecuciones/{ej['id']}/pasos/{p['id']}/confirmar", headers=pedro, json={}))
        ia.transcripcion = PREGUNTA_VOZ
        voz = _ok(cliente.post("/api/voz/transcribir", headers=pedro,
                               files={"audio": ("pregunta.webm", b"\x1aE\xdf\xa3" + b"\x00" * 4000, "audio/webm")}))
        assert voz["texto"] == PREGUNTA_VOZ
        ia.respuesta = "Usa la llave dinamométrica de media pulgada [1]."
        r = cliente.post(f"/api/planta/ejecuciones/{ej['id']}/preguntar", headers=pedro,
                         json={"pregunta": voz["texto"], "paso_id": critico["id"]})
        assert r.status_code == 200, r.text
        eventos = _sse(r.text)
        fin = next(d for e, d in eventos if e == "fin")
        fuentes = next(d["fuentes"] for e, d in eventos if e == "fuentes")
        assert fin["con_respaldo"] and any(f.get("paso_id") == critico["id"] or f.get("paso") for f in fuentes)
        assert "dinamométrica" in "".join(d["texto"] for e, d in eventos if e == "token")
    with crono.paso("Aprendiz: confirma los pasos, foto y termina"):
        sin_marca = cliente.post(f"/api/planta/ejecuciones/{ej['id']}/pasos/{critico['id']}/confirmar", headers=pedro,
                                 json={"critico_confirmado": False})
        assert sin_marca.status_code == 400  # un paso crítico no se confirma sin marcar la casilla
        for p in ej["pasos"]:
            _ok(cliente.post(f"/api/planta/ejecuciones/{ej['id']}/pasos/{p['id']}/confirmar", headers=pedro,
                             json={"critico_confirmado": p["es_critico"]}))
        foto = _ok(cliente.post(f"/api/planta/ejecuciones/{ej['id']}/foto", headers=pedro,
                                files={"imagen": ("resultado.png", PNG, "image/png")}))
        assert foto["foto_url"] and foto["estado"]
        resumen = _ok(cliente.post(f"/api/planta/ejecuciones/{ej['id']}/finalizar", headers=pedro))
        assert resumen["estado"] == "completada" and resumen["resumen"]["consultas_criticos"] == 1
    with crono.paso("Aprendiz: repite la tarea dos veces"):
        for _ in range(2):
            otra = _ok(cliente.post("/api/planta/ejecuciones", headers=pedro, json={"tarea_id": tarea.id}))
            for p in otra["pasos"]:
                _ok(cliente.post(f"/api/planta/ejecuciones/{otra['id']}/pasos/{p['id']}/confirmar", headers=pedro,
                                 json={"critico_confirmado": p["es_critico"]}))
            _ok(cliente.post(f"/api/planta/ejecuciones/{otra['id']}/finalizar", headers=pedro))
    assert bd.scalar(select(Ejecucion.consultas).where(Ejecucion.id == ej["id"])) == 1

    # 5. Cuestionario -------------------------------------------------------------------------
    with crono.paso("Aprendiz: aprueba el cuestionario"):
        cu = _ok(cliente.get(f"/api/evaluacion/cuestionario/{tarea.id}", headers=pedro))
        assert "correcta" not in json.dumps(cu)
        respuestas = {str(q["id"]): next(o["clave"] for o in q["opciones"] if o["texto"] == correctas[q["id"]])
                      for q in cu["preguntas"]}
        res = _ok(cliente.post(f"/api/evaluacion/cuestionario/{tarea.id}/responder", headers=pedro,
                               json={"instruccion_id": cu["instruccion"]["id"], "respuestas": respuestas}))
        assert res["aprobado"] and res["nivel"]["letra"] == "L"

    # 6. El jefe observa y el ILUO sube ------------------------------------------------------
    uid = planta.personas["pedro"].id
    with crono.paso("Jefe: revisa la ejecución y observa"):
        vista = _ok(cliente.get(f"/api/planta/ejecuciones/{ej['id']}", headers=javier))
        assert not vista["es_mia"] and vista["consultas_criticos"] == 1 and vista["historial"]
        plantilla = _ok(cliente.get("/api/evaluacion/observacion/plantilla", headers=javier,
                                    params={"usuario_id": uid, "tarea_id": tarea.id}))
        obs = _ok(cliente.post("/api/evaluacion/observaciones", headers=javier, json={
            "usuario_id": uid, "tarea_id": tarea.id, "instruccion_id": plantilla["instruccion"]["id"],
            "lista": [{"paso_id": x["paso_id"], "ok": True} for x in plantilla["lista"]], "aprobada": True,
            "comentario": "Monta la brida sin ayuda."}))
        assert obs["nivel"]["letra"] == "U"
    with crono.paso("ILUO y pasaporte"):
        celda = _ok(cliente.get(f"/api/progreso/iluo/{uid}/{tarea.id}", headers=javier))
        assert celda["letra"] == "U"
        yo = _ok(cliente.get("/api/progreso/yo", headers=pedro))
        fila = next(t for t in yo["tareas"] if t["tarea"]["id"] == tarea.id)
        assert fila["letra"] == "U" and fila["cuestionario_aprobado"]
        equipo = json.dumps(_ok(cliente.get("/api/progreso/equipo", headers=javier)), ensure_ascii=False)
        assert "Pedro Ruiz" in equipo
    nivel = bd.scalar(select(NivelIluo).where(NivelIluo.usuario_id == uid, NivelIluo.tarea_id == tarea.id))
    assert nivel.nivel == 3

    # 7. Aportación por voz, validación y cita ----------------------------------------------
    ia.transcripcion = NOTA_PRENSA
    ia.json = {"titulo": "Atasco de la prensa 3 tras el cambio de molde",
               "problema": "La prensa 3 se queda parada con alarma de falta de pieza y se atasca tras cambiar el molde.",
               "causa": "El sensor S4 de presencia de pieza se ensucia de viruta y aceite.",
               "solucion": "Limpiar el sensor S4 con un trapo y alcohol.\nRearmar el ciclo.",
               "etiquetas": ["prensa 3", "sensor S4"], "nivel_minimo": 3}
    with crono.paso("Empleada: aporta una solución por voz"):
        audio = AUDIO_APORTACION.read_bytes() if AUDIO_APORTACION.exists() else b"OggS" + b"\x00" * 4000
        ap = _ok(cliente.post("/api/aportaciones", headers=marta, files={"audio": ("nota.ogg", audio, "audio/ogg")},
                              data={"duracion": "20"}))
        ap = _ok(cliente.get(f"/api/aportaciones/{ap['id']}", headers=marta))
        assert ap["estado"] == "pendiente" and "S4" in (ap["solucion"] or "") + (ap["causa"] or "")
    with crono.paso("Jefe: valida la aportación"):
        bandeja = _ok(cliente.get("/api/aportaciones/pendientes", headers=javier))["aportaciones"]
        assert ap["id"] in {a["id"] for a in bandeja}
        val = _ok(cliente.post(f"/api/aportaciones/{ap['id']}/validar", headers=javier, json={"nivel_minimo": 1}))
        doc_id = val["documento"]["id"]
        assert val["aportacion"]["estado"] == "validada"
    doc = bd.get(Documento, doc_id)
    bd.refresh(doc)
    assert doc.estado == "listo" and doc.tipo == "faq" and doc.departamento_id == planta.deps["prod"].id
    with crono.paso("Copiloto: cita la solución validada"):
        ia.respuesta = "Limpia el sensor S4 con un trapo y alcohol y rearma el ciclo [1]."
        r = _ok(cliente.post("/api/consulta/simple", headers=pedro,
                             json={"pregunta": "La prensa 3 se ha atascado al cambiar el molde, ¿qué hago?"}))
        citada = [f for f in r["fuentes"] if f["documento_id"] == doc_id]
        assert citada and r["con_respaldo"], r["fuentes"]
        assert f"[{citada[0]['n']}]" in r["respuesta"]
        assert citada[0].get("autor") == "Marta Sanz" and citada[0].get("validador") == "Javier Martín"
    # Quien no es de Producción no la encuentra.
    otra = _ok(cliente.post("/api/consulta/simple", headers=cab(cliente, "luis"),
                            json={"pregunta": "La prensa 3 se ha atascado al cambiar el molde, ¿qué hago?"}))
    assert all(f["documento_id"] != doc_id for f in otra["fuentes"])

    # Todo queda en el registro xAPI.
    bd.expire_all()
    verbos = set(bd.scalars(select(SentenciaXapi.verbo)).all())
    esperados = {"publico", "inicio", "confirmo", "pregunto", "fotografio", "completo", "aprobo", "observo",
                 "certifico", "aporto", "valido"}
    assert esperados <= verbos, esperados - verbos
    if con_video:
        assert "capturo" in verbos
    print(crono.resumen())
