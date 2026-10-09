"""Pruebas de la captura: vídeo (con un vídeo sintético y ffmpeg), nota de voz, entrevista guiada y permisos.

ffmpeg: se usa CIDIA_FFMPEG/CIDIA_FFPROBE si están definidas; si no, la compilación LGPL de
servidor/gateway/.herramientas/ (ignorada por git) o, en su defecto, la del PATH. Si no hay
ninguna, las pruebas de vídeo se saltan.
"""

from __future__ import annotations

import itertools
import os
import subprocess
from pathlib import Path

import pytest
from fabrica import CONTRASENA, cab
from sqlalchemy import select

from cidia.config import ajustes
from cidia.modelos import Captura, Documento, Fragmento, Paso, Tarea, Usuario
from cidia.seguridad import hash_contrasena
from cidia.servicios import captura, video
from cidia.servicios.captura_prompts import GUION

RAIZ = Path(__file__).resolve().parents[1]
_contador = itertools.count(1)


def nueva_tarea(bd, planta, dep: str = "prod", nivel: int = 1) -> Tarea:
    """Cada prueba usa su propia tarea (la base de datos se comparte en toda la sesión)."""
    n = next(_contador)
    t = Tarea(puesto_id=planta.puestos[dep].id, codigo=f"CAP-T{n:03d}", nombre=f"Tarea capturada {n}",
              nivel_minimo=nivel)
    bd.add(t)
    bd.commit()
    return t


@pytest.fixture
def ffmpeg(monkeypatch):
    if not os.environ.get("CIDIA_FFMPEG"):
        locales = sorted((RAIZ / ".herramientas").glob("*/bin/ffmpeg.exe")) + sorted((RAIZ / ".herramientas").glob("*/bin/ffmpeg"))
        if locales:
            monkeypatch.setenv("CIDIA_FFMPEG", str(locales[0]))
            monkeypatch.setenv("CIDIA_FFPROBE", str(locales[0].with_name(locales[0].name.replace("ffmpeg", "ffprobe"))))
    if not video.disponible():
        pytest.skip("ffmpeg no está disponible")
    return os.environ.get("CIDIA_FFMPEG") or "ffmpeg"


def video_sintetico(ffmpeg: str, nombre: str) -> Path:
    """12 s: rojo, azul y carta de ajuste (dos cambios de plano, en 4 s y 8 s) con un pitido de fondo.
    Se genera en la carpeta de datos de las pruebas (tmp_path no siempre es accesible en Windows)."""
    destino = ajustes().dir_datos / "videos_sinteticos" / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=320x240:r=15:d=4",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=15:d=4",
            "-f", "lavfi", "-i", "testsrc=s=320x240:r=15:d=4",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a",
            "-c:v", "libvpx", "-b:v", "300k", "-c:a", "libopus", "-shortest", str(destino),
        ], check=True, capture_output=True, timeout=120)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        pytest.skip(f"No se ha podido generar el vídeo de prueba: {e}")
    return destino


@pytest.fixture
def ganchos(monkeypatch):
    from cidia.servicios import evaluacion, formacion, iluo

    monkeypatch.setattr(iluo, "marcar_reevaluacion", lambda bd, tarea_id: 0)
    monkeypatch.setattr(formacion, "encolar_generacion", lambda iid: None)
    monkeypatch.setattr(evaluacion, "encolar_generacion", lambda iid: None)


PROPUESTA = {
    "titulo": "Montaje de la brida B",
    "resumen": "Cómo montar la brida B en la línea 2.",
    "riesgos": ["Atrapamiento de manos"],
    "epis": ["Guantes", "Gafas"],
    "herramientas": ["Llave dinamométrica"],
    "pasos": [
        {"titulo": "Limpiar la brida", "texto": "Limpia la superficie de apoyo.", "t_inicio": 0, "t_fin": 4},
        {"titulo": "Apretar los tornillos", "texto": "Aprieta en cruz.", "es_critico": True,
         "criterio_aceptacion": "Par de 25 N·m", "t_inicio": "00:04", "t_fin": 8},
        {"titulo": "Comprobar fugas", "texto": "Prueba de presión.", "es_seguridad": "true", "t_inicio": 8, "t_fin": 12},
    ],
}


def _fichero(bd, ruta: str | None) -> Path:
    assert ruta
    return ajustes().dir_datos / ruta


# --------------------------------------------------------------------------- vídeo


def test_video_con_propuesta_del_modelo(cliente, bd, planta, ia, ffmpeg, ganchos):
    t = nueva_tarea(bd, planta, "prod")
    v = video_sintetico(ffmpeg, "montaje.webm")
    ia.transcripcion = "Primero limpio la brida. Después aprieto los tornillos en cruz."
    ia.json = PROPUESTA
    ia.respuesta = "Limpia con un trapo seco la superficie roja de apoyo de la brida."  # visión
    h = cab(cliente, "carmen")
    with v.open("rb") as f:
        r = cliente.post("/api/captura/video", headers=h, data={"tarea_id": str(t.id), "titulo": "Brida B"},
                         files={"fichero": ("montaje.webm", f, "video/webm")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["estado"] == "borrador_listo", d["mensaje"]
    assert d["progreso"] == 100 and d["fase"] == "listo" and d["origen_borrador"] == "modelo"
    assert d["borrador"] == {"tipo": "instruccion", "id": d["instruccion_id"], "version": 1, "estado": "borrador"}
    assert d["miniatura_url"] and [f["clave"] for f in d["fases"]][:2] == ["subiendo", "extrayendo_audio"]

    det = cliente.get(f"/api/captura/{d['id']}", headers=h).json()
    assert det["duracion"] == pytest.approx(12, abs=0.5)
    assert [round(e["t"]) for e in det["escenas"]] == [4, 8]
    assert det["transcripcion"]["texto"].startswith("Primero") and det["original_url"]

    ins = cliente.get(f"/api/instrucciones/{d['instruccion_id']}", headers=h).json()
    assert ins["estado"] == "borrador" and ins["titulo"] == "Montaje de la brida B" and ins["codigo"] == t.codigo
    assert ins["autor"]["nombre"] == "Carmen Díaz" and ins["video_url"] and ins["captura_id"] == d["id"]
    assert ins["riesgos"] == "Atrapamiento de manos" and ins["epis"] == "Guantes\nGafas"
    pasos = ins["pasos"]
    assert [p["titulo"] for p in pasos] == ["Limpiar la brida", "Apretar los tornillos", "Comprobar fugas"]
    assert pasos[1]["es_critico"] and pasos[2]["es_seguridad"] and pasos[1]["criterio_aceptacion"] == "Par de 25 N·m"
    assert [(p["t_inicio"], p["t_fin"]) for p in pasos] == [(0, 4), (4, 8), (8, 12)]
    assert pasos[0]["texto"] == ia.respuesta  # mejorado con el fotograma
    assert all(p["imagen_url"] and p["clip_url"] for p in pasos)
    clip = cliente.get(pasos[1]["clip_url"])
    assert clip.status_code == 200 and len(clip.content) > 1000
    bd.expire_all()
    for p in bd.scalars(select(Paso).where(Paso.instruccion_id == ins["id"])).all():
        assert _fichero(bd, p.imagen_ruta).stat().st_size > 0
        assert video.info(_fichero(bd, p.clip_ruta))["duracion"] == pytest.approx(4, abs=0.6)
    assert not (_fichero(bd, bd.get(Captura, d["id"]).ruta_original).parent / "audio.wav").exists()


def test_video_sin_tarea_y_modelo_inservible(cliente, bd, planta, ia, ffmpeg):
    v = video_sintetico(ffmpeg, "sin_tarea.webm")
    ia.transcripcion = "Coloco la pieza en el utillaje y cierro las mordazas."
    ia.json = "esto no es lo que se pidió"
    ia.respuesta = "ok"  # la visión no aporta nada válido: se queda el texto
    h = cab(cliente, "carmen")
    with v.open("rb") as f:
        r = cliente.post("/api/captura/video", headers=h, data={"titulo": "Cambio de utillaje"},
                         files={"fichero": ("sin_tarea.webm", f, "video/webm")})
    d = r.json()
    assert d["estado"] == "borrador_listo", d["mensaje"]
    assert d["origen_borrador"] == "segmentos" and d["tarea"]["nombre"] == "Cambio de utillaje"
    ins = cliente.get(f"/api/instrucciones/{d['instruccion_id']}", headers=h).json()
    # Plan B: un paso por tramo entre cambios de plano, con lo dicho en cada tramo.
    assert len(ins["pasos"]) == 3
    assert ins["pasos"][0]["texto"] == ia.transcripcion and ins["pasos"][0]["titulo"].startswith("Coloco la pieza")
    assert ins["pasos"][1]["titulo"] == "Paso 2" and ins["pasos"][1]["clip_url"]
    assert ins["tarea"]["departamento"] == "Producción" and ins["tarea"]["codigo"]


def test_video_danado_queda_en_error(cliente, bd, planta):
    h = cab(cliente, "carmen")
    r = cliente.post("/api/captura/video", headers=h, files={"fichero": ("roto.mp4", b"no soy un video", "video/mp4")})
    assert r.status_code == 200
    d = r.json()
    assert d["estado"] == "error" and d["mensaje"]
    assert cliente.post(f"/api/captura/{d['id']}/reintentar", headers=h).json()["estado"] == "error"
    assert cliente.delete(f"/api/captura/{d['id']}", headers=h).status_code == 200
    assert cliente.get(f"/api/captura/{d['id']}", headers=h).status_code == 404


def test_post_api_captura_es_la_subida_de_video(cliente, planta):
    """POST /api/captura (forma corta del encargo) equivale a POST /api/captura/video."""
    h = cab(cliente, "carmen")
    r = cliente.post("/api/captura", headers=h, files={"fichero": ("roto.mp4", b"no soy un video", "video/mp4")})
    assert r.status_code == 200, r.text
    assert r.json()["tipo"] == "video" and r.json()["estado"] == "error"
    assert cliente.delete(f"/api/captura/{r.json()['id']}", headers=h).status_code == 200
    r = cliente.post("/api/captura", headers=cab(cliente, "pedro"),
                     files={"fichero": ("v.mp4", b"x", "video/mp4")})
    assert r.status_code == 403


def test_captura_sin_fichero_no_sale_de_la_carpeta_de_datos():
    """Sin fichero, ruta_absoluta("") sería la carpeta de datos y el trabajo escribiría en la de encima."""
    with pytest.raises(captura.ErrorCaptura):
        captura._original(Captura(tipo="video", ruta_original=None))
    with pytest.raises(captura.ErrorCaptura):
        captura._original(Captura(tipo="audio", ruta_original="capturas/no-existe/nota.webm"))


def test_errores_del_modelo_no_filtran_direcciones_internas():
    from cidia.ia import llm

    msg = captura._mensaje_error(llm.ErrorModelo("No se puede contactar con el modelo: http://10.0.0.5:11434/v1"))
    assert "http" not in msg and "10.0.0.5" not in msg and msg
    assert captura._mensaje_error(captura.ErrorCaptura("Texto claro.")) == "Texto claro."


def test_tipos_de_fichero(cliente, planta):
    h = cab(cliente, "carmen")
    r = cliente.post("/api/captura/video", headers=h, files={"fichero": ("notas.txt", b"hola", "text/plain")})
    assert r.status_code == 400
    r = cliente.post("/api/captura/audio", headers=h, files={"fichero": ("informe.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 400
    r = cliente.post("/api/captura/audio", headers=h, files={"fichero": ("vacio.webm", b"", "audio/webm")})
    assert r.status_code == 400
    # La administración no tiene departamento: debe elegir la tarea.
    r = cliente.post("/api/captura/audio", headers=cab(cliente, "admin"),
                     files={"fichero": ("nota.webm", b"audio", "audio/webm")})
    assert r.status_code == 400


def test_fichero_disfrazado_se_guarda_con_extension_segura(cliente, bd, planta, ia):
    """Un «.html» o «.svg» declarado como vídeo o audio no puede acabar servido como página web
    (se ejecutaría en el mismo origen que la interfaz): se guarda con extensión de vídeo o audio."""
    h = cab(cliente, "carmen")
    pagina = b"<html><script>alert(1)</script></html>"
    d = cliente.post("/api/captura/video", headers=h, files={"fichero": ("pagina.html", pagina, "video/mp4")}).json()
    ia.transcripcion = "Nota sobre la prensa."
    n = cliente.post("/api/captura/audio", headers=h,
                     files={"fichero": ("dibujo.svg", b"<svg onload='alert(1)'/>", "audio/webm")}).json()
    bd.expire_all()
    assert bd.get(Captura, d["id"]).ruta_original.endswith(".mp4")
    assert Path(bd.get(Captura, n["id"]).ruta_original).suffix in captura.EXT_AUDIO
    for cid in (d["id"], n["id"]):
        url = cliente.get(f"/api/captura/{cid}", headers=h).json()["original_url"]
        tipo = cliente.get(url).headers["content-type"]
        assert tipo.startswith(("video/", "audio/")), tipo


# --------------------------------------------------------------------------- nota de voz


def test_nota_de_voz_y_publicacion_de_la_ficha(cliente, bd, planta, ia):
    t = nueva_tarea(bd, planta, "prod", nivel=2)
    ia.transcripcion = "Cuando la prensa tres se atasca, casi siempre es el sensor S4 sucio. Se limpia con alcohol."
    ia.json = {"titulo": "Atasco de la prensa 3", "etiquetas": ["Prensa", "sensor s4"],
               "contenido": "## Causa\n\nEl sensor S4 está sucio.\n\n## Solución\n\nLímpialo con alcohol isopropílico."}
    h = cab(cliente, "carmen")
    r = cliente.post("/api/captura/audio", headers=h, data={"tarea_id": str(t.id)},
                     files={"fichero": ("nota.webm", b"audio-falso", "audio/webm")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["estado"] == "borrador_listo" and d["borrador"]["tipo"] == "ficha" and d["borrador"]["estado"] == "borrador"
    assert d["duracion"] == 3.0
    det = cliente.get(f"/api/captura/{d['id']}", headers=h).json()
    ficha = det["ficha"]
    assert ficha["titulo"] == "Atasco de la prensa 3" and ficha["etiquetas"] == ["prensa", "sensor s4"]
    assert "sensor S4" in ficha["contenido"] and ficha["publicada"] is False

    r = cliente.put(f"/api/captura/{d['id']}/ficha", headers=h,
                    json={"titulo": "Atasco de la prensa 3 (sensor S4)", "etiquetas": ["prensa", "sensor", "prensa"]})
    assert r.status_code == 200 and r.json()["ficha"]["etiquetas"] == ["prensa", "sensor"]
    assert cliente.put(f"/api/captura/{d['id']}/ficha", headers=h, json={"titulo": ""}).status_code == 400

    # Otro experto de otro departamento no la publica.
    assert cliente.post(f"/api/captura/{d['id']}/ficha/publicar", headers=cab(cliente, "ana")).status_code == 403
    r = cliente.post(f"/api/captura/{d['id']}/ficha/publicar", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["ficha"]["publicada"] is True and r.json()["borrador"]["estado"] == "publicada"
    bd.expire_all()
    doc = bd.get(Documento, d["documento_id"])
    assert doc.tipo == "ficha" and doc.estado == "listo" and doc.validador_id == planta.personas["carmen"].id
    assert doc.departamento_id == planta.deps["prod"].id and doc.nivel_minimo == 2 and doc.es_formacion
    texto = " ".join(f.texto for f in bd.scalars(select(Fragmento).where(Fragmento.documento_id == doc.id)).all())
    assert "isopropílico" in texto and "Etiquetas: prensa, sensor" in texto
    assert cliente.post(f"/api/captura/{d['id']}/ficha/publicar", headers=h).status_code == 409
    assert cliente.put(f"/api/captura/{d['id']}/ficha", headers=h, json={"titulo": "Otro"}).status_code == 409
    # Al borrar la captura, la ficha publicada se conserva.
    assert cliente.delete(f"/api/captura/{d['id']}", headers=h).status_code == 200
    bd.expire_all()
    assert bd.get(Documento, d["documento_id"]) is not None


def test_nota_de_voz_sin_modelo_usa_la_transcripcion(cliente, bd, planta, ia):
    ia.transcripcion = "Antes de arrancar la línea reviso la presión del aire."
    ia.json = None
    h = cab(cliente, "carmen")
    d = cliente.post("/api/captura/audio", headers=h, files={"fichero": ("nota.ogg", b"audio", "audio/ogg")}).json()
    assert d["estado"] == "borrador_listo"
    ficha = cliente.get(f"/api/captura/{d['id']}", headers=h).json()["ficha"]
    assert ficha["titulo"] == "Antes de arrancar la línea reviso la presión"  # primera frase
    assert d["titulo"] == ficha["titulo"]  # la captura sin título toma el de la ficha
    assert ia.transcripcion in ficha["contenido"]
    # Si se borra la captura, la ficha en borrador desaparece con ella.
    assert cliente.delete(f"/api/captura/{d['id']}", headers=h).status_code == 200
    bd.expire_all()
    assert bd.get(Documento, d["documento_id"]) is None


def test_ficha_con_respuesta_estructurada_del_modelo(cliente, planta, ia):
    """Modelos pequeños: el contenido llega como objeto con listas y las etiquetas como texto."""
    ia.transcripcion = "Si la prensa se atasca, limpia el sensor S4 con alcohol y revísalo en cada turno."
    ia.json = {"titulo": "Atasco de la prensa", "etiquetas": "Prensa, sensor S4, prensa",
               "contenido": {"Causa": "El sensor S4 está sucio.",
                             "Trucos": ["Límpialo con alcohol", "Revísalo en cada turno"]}}
    h = cab(cliente, "carmen")
    d = cliente.post("/api/captura/audio", headers=h, files={"fichero": ("n.webm", b"a", "audio/webm")}).json()
    ficha = cliente.get(f"/api/captura/{d['id']}", headers=h).json()["ficha"]
    assert ficha["contenido"].startswith("## Causa\n\nEl sensor S4 está sucio.")
    assert "## Trucos\n\n- Límpialo con alcohol\n- Revísalo en cada turno" in ficha["contenido"]
    assert ficha["etiquetas"] == ["prensa", "sensor s4"]
    # Si el «contenido» es JSON de verdad (el modelo se ha liado), se usa la transcripción.
    ia.json = {"titulo": "X", "contenido": '{"seccion": "algo raro que no es markdown"}'}
    d = cliente.post("/api/captura/audio", headers=h, files={"fichero": ("n.webm", b"a", "audio/webm")}).json()
    ficha = cliente.get(f"/api/captura/{d['id']}", headers=h).json()["ficha"]
    assert ia.transcripcion in ficha["contenido"]


def test_ficha_envuelta_y_con_claves_en_ingles(cliente, planta, ia):
    """Modelos pequeños: {"ficha": {"title", "content", "tags"}} en vez de lo pedido."""
    ia.transcripcion = "La prensa dos pierde presión si la junta tórica está gastada."
    ia.json = {"ficha": {"title": "Pérdida de presión en la prensa 2", "content": "## Causa\n\nJunta tórica gastada.",
                         "tags": ["Prensa", "junta"]}}
    h = cab(cliente, "carmen")
    d = cliente.post("/api/captura/audio", headers=h, files={"fichero": ("n.webm", b"a", "audio/webm")}).json()
    ficha = cliente.get(f"/api/captura/{d['id']}", headers=h).json()["ficha"]
    assert ficha["titulo"] == "Pérdida de presión en la prensa 2" and ficha["etiquetas"] == ["prensa", "junta"]
    assert ficha["contenido"].startswith("## Causa") and d["origen_borrador"] == "modelo"


def test_ficha_de_otro_departamento_no_se_toca(cliente, bd, planta, ia):
    """Si la autora cambia de departamento, su ficha en borrador sigue siendo del anterior: ya no la
    edita ni la publica (la administración sí)."""
    u = bd.scalar(select(Usuario).where(Usuario.usuario == "experta_movil"))
    if u is None:
        u = Usuario(usuario="experta_movil", nombre="Experta que cambia", rol="empleado", es_experto=True,
                    nivel_id=planta.niveles[2].id, hash_contrasena=hash_contrasena(CONTRASENA))
        bd.add(u)
    u.departamento_id = planta.deps["prod"].id
    bd.commit()
    ia.transcripcion = "Para cambiar el molde, calienta antes la placa diez minutos."
    ia.json = None
    h = cab(cliente, "experta_movil")
    d = cliente.post("/api/captura/audio", headers=h, files={"fichero": ("n.webm", b"a", "audio/webm")}).json()
    assert d["estado"] == "borrador_listo"
    assert cliente.put(f"/api/captura/{d['id']}/ficha", headers=h, json={"titulo": "Cambio de molde"}).status_code == 200
    u.departamento_id = planta.deps["ot"].id
    bd.commit()
    assert cliente.put(f"/api/captura/{d['id']}/ficha", headers=h, json={"titulo": "Mío"}).status_code == 403
    assert cliente.post(f"/api/captura/{d['id']}/ficha/publicar", headers=h).status_code == 403
    # Lo capturado es de Producción: la jefa de Oficina técnica (departamento actual de la autora) no
    # lo ve; el jefe de Producción y la administración sí, y pueden revisarlo.
    ha = cab(cliente, "ana")
    assert cliente.get(f"/api/captura/{d['id']}", headers=ha).status_code == 403
    assert cliente.put(f"/api/captura/{d['id']}/ficha", headers=ha, json={"titulo": "X"}).status_code == 403
    hj = cab(cliente, "javier")
    assert cliente.get(f"/api/captura/{d['id']}", headers=hj).status_code == 200
    assert cliente.put(f"/api/captura/{d['id']}/ficha", headers=hj, json={"titulo": "Cambio de molde"}).status_code == 200
    assert cliente.get(f"/api/captura/{d['id']}", headers=cab(cliente, "admin")).status_code == 200


def test_nota_de_voz_sin_voz(cliente, planta, ia):
    ia.transcripcion = ""
    d = cliente.post("/api/captura/audio", headers=cab(cliente, "carmen"),
                     files={"fichero": ("nota.webm", b"silencio", "audio/webm")}).json()
    assert d["estado"] == "error" and "No se ha entendido" in d["mensaje"]


# --------------------------------------------------------------------------- entrevista guiada


def _ultima(d: dict) -> dict:
    return d["conversacion"][-1]


def test_entrevista_guiada_hasta_la_ficha(cliente, bd, planta, ia):
    t = nueva_tarea(bd, planta, "prod")
    h = cab(cliente, "carmen")
    r = cliente.post("/api/captura/entrevista", headers=h, json={"tarea_id": t.id})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["estado"] == "en_curso" and len(d["conversacion"]) == 1
    assert t.nombre in _ultima(d)["texto"] and _ultima(d)["rol"] == "copiloto"
    assert d["entrevista"]["temas"][0]["estado"] == "actual" and d["entrevista"]["terminada"] is False
    cid = d["id"]
    ruta = f"/api/captura/{cid}/entrevista/responder"

    # El modelo pide una repregunta: se acepta una vez por tema.
    ia.json = {"repreguntar": True, "pregunta": "¿Y cada cuánto se hace?"}
    d = cliente.post(ruta, headers=h, json={"texto": "Sirve para montar la brida B en la línea 2."}).json()
    assert _ultima(d)["texto"] == "¿Y cada cuánto se hace?" and _ultima(d)["tema"] == "objetivo"
    d = cliente.post(ruta, headers=h, json={"texto": "Una vez por turno."}).json()
    assert _ultima(d)["tema"] == "preparacion" and _ultima(d)["texto"] == GUION[1].pregunta
    assert d["progreso"] == int(100 / len(GUION))

    # Pregunta adaptada del modelo para el tema siguiente (se le añade el «¿» si falta).
    ia.json = {"repreguntar": False, "pregunta": "Y con la llave preparada, por dónde empiezas?"}
    d = cliente.post(ruta, headers=h, json={"texto": "Llave dinamométrica, guantes y la brida limpia."}).json()
    assert _ultima(d)["tema"] == "pasos" and _ultima(d)["texto"].startswith("¿Y con la llave")

    # Saltar una pregunta no llama al modelo y deja el tema como saltado.
    llamadas = len(ia.llamadas)
    d = cliente.post(ruta, headers=h, json={"saltar": True}).json()
    assert len(ia.llamadas) == llamadas and _ultima(d)["tema"] == "puntos_criticos"
    assert {x["clave"]: x["estado"] for x in d["entrevista"]["temas"]}["pasos"] == "saltado"

    # Respuesta por voz.
    ia.transcripcion = "El apriete en cruz es lo más crítico."
    ia.json = "basura"  # el modelo falla: se usa la pregunta del guion
    r = cliente.post(f"/api/captura/{cid}/entrevista/responder-audio", headers=h,
                     files={"fichero": ("respuesta.webm", b"voz", "audio/webm")})
    assert r.status_code == 200, r.text
    d = r.json()
    voz = d["conversacion"][-2]
    assert voz["rol"] == "experto" and voz["voz"] is True and voz["texto"] == ia.transcripcion
    assert _ultima(d)["tema"] == "errores"

    # Otras personas no pueden responder (ni ver, si no son su jefe).
    assert cliente.post(ruta, headers=cab(cliente, "ana"), json={"texto": "x"}).status_code == 403
    assert cliente.get(f"/api/captura/{cid}", headers=cab(cliente, "javier")).status_code == 200
    assert cliente.post(ruta, headers=cab(cliente, "javier"), json={"texto": "x"}).status_code == 403
    assert cliente.post(ruta, headers=h, json={"texto": "   "}).status_code == 400

    while not d["entrevista"]["terminada"]:
        d = cliente.post(ruta, headers=h, json={"texto": "Respuesta de prueba con detalle."}).json()
    assert _ultima(d)["tema"] == "fin" and d["progreso"] == 100
    d = cliente.post(ruta, headers=h, json={"texto": "Un apunte final."}).json()
    assert _ultima(d)["tema"] == "fin" and d["estado"] == "en_curso"

    ia.json = {"titulo": "Montaje de la brida B: claves", "etiquetas": ["brida"],
               "contenido": "## Para qué sirve\n\nMontar la brida B.\n\n## Puntos críticos\n\nEl apriete en cruz."}
    r = cliente.post(f"/api/captura/{cid}/entrevista/finalizar", headers=h, json={"generar": "ficha"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["estado"] == "borrador_listo" and d["ficha"]["titulo"] == "Montaje de la brida B: claves"
    bd.expire_all()
    cap = bd.get(Captura, cid)
    assert cap.conversacion[0]["rol"] == "copiloto" and len(cap.conversacion) > 10
    # El texto que recibe el modelo va ordenado por temas.
    peticion = ia.llamadas[-1]["mensajes"][-1]["content"]
    assert "[Objetivo]" in peticion and "El apriete en cruz es lo más crítico." in peticion
    assert cliente.post(ruta, headers=h, json={"texto": "tarde"}).status_code == 409


def test_entrevista_genera_borrador_de_instruccion(cliente, bd, planta, ia):
    h = cab(cliente, "carmen")
    d = cliente.post("/api/captura/entrevista", headers=h, json={"tema": "Cambio de bobina"}).json()
    cid = d["id"]
    assert cliente.post(f"/api/captura/{cid}/entrevista/finalizar", headers=h).status_code == 400  # sin respuestas
    ia.json = {"repreguntar": False, "pregunta": "¿Qué preparas?"}
    ruta = f"/api/captura/{cid}/entrevista/responder"
    cliente.post(ruta, headers=h, json={"texto": "Se cambia la bobina cuando se acaba."})
    cliente.post(ruta, headers=h, json={"texto": "Carro elevador y guantes."})
    cliente.post(ruta, headers=h, json={"texto": "Paro la línea. Quito la bobina vacía. Pongo la nueva y la enhebro."})
    ia.json = "nada útil"  # plan B: los pasos salen de la respuesta sobre los pasos
    r = cliente.post(f"/api/captura/{cid}/entrevista/finalizar", headers=h, json={"generar": "instruccion"})
    d = r.json()
    assert d["estado"] == "borrador_listo", d["mensaje"]
    assert d["borrador"]["tipo"] == "instruccion" and d["tarea"]["nombre"] == "Cambio de bobina"
    ins = cliente.get(f"/api/instrucciones/{d['instruccion_id']}", headers=h).json()
    assert [p["texto"] for p in ins["pasos"]] == ["Paro la línea.", "Quito la bobina vacía.", "Pongo la nueva y la enhebro."]
    assert ins["resumen"] == "Se cambia la bobina cuando se acaba." and ins["herramientas"] == "Carro elevador y guantes."
    bd.expire_all()
    assert bd.get(Tarea, d["tarea"]["id"]).puesto.departamento_id == planta.deps["prod"].id
    # Terminar otra vez (doble clic) no genera un segundo borrador.
    assert cliente.post(f"/api/captura/{cid}/entrevista/finalizar", headers=h,
                        json={"generar": "instruccion"}).status_code == 409


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"
)


def test_borrar_captura_limpia_las_imagenes_del_borrador(cliente, bd, planta, ia):
    """Al borrar la captura se borra su borrador y también las imágenes subidas a mano al revisarlo."""
    h = cab(cliente, "carmen")
    d = cliente.post("/api/captura/entrevista", headers=h, json={"tema": "Purga del compresor"}).json()
    ia.json = {"repreguntar": False, "pregunta": "¿Qué preparas?"}
    cliente.post(f"/api/captura/{d['id']}/entrevista/responder", headers=h, json={"texto": "Purgo el compresor los lunes."})
    ia.json = {"titulo": "Purga del compresor", "pasos": [{"titulo": "Abrir la válvula de purga"}]}
    d = cliente.post(f"/api/captura/{d['id']}/entrevista/finalizar", headers=h, json={"generar": "instruccion"}).json()
    assert d["estado"] == "borrador_listo", d["mensaje"]
    ins = cliente.get(f"/api/instrucciones/{d['instruccion_id']}", headers=h).json()
    r = cliente.post(f"/api/instrucciones/{ins['id']}/pasos/{ins['pasos'][0]['id']}/imagen", headers=h,
                     files={"fichero": ("foto.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    bd.expire_all()
    imagen = ajustes().dir_datos / bd.get(Paso, ins["pasos"][0]["id"]).imagen_ruta
    assert imagen.exists()
    assert cliente.delete(f"/api/captura/{d['id']}", headers=h).status_code == 200
    assert cliente.get(f"/api/instrucciones/{ins['id']}", headers=h).status_code == 404
    assert not imagen.parent.exists()


def test_entrevista_no_repite_la_misma_pregunta(bd, ia):
    """Si el modelo devuelve como «repregunta» la pregunta que ya se hizo, se sigue con el guion."""
    primera = captura.prompts.primera_pregunta("Montaje")
    conversacion = [captura._mensaje("copiloto", primera, "objetivo"),
                    captura._mensaje("experto", "Sirve para montar la brida.", "objetivo")]
    ia.json = {"repreguntar": True, "pregunta": primera.upper()}
    siguiente = captura.siguiente_pregunta(bd, "Montaje", conversacion, False)
    assert siguiente["tema"] == "preparacion" and siguiente["texto"] == GUION[1].pregunta
    ia.json = {"repreguntar": True, "pregunta": "¿Cada cuánto se hace?"}
    assert captura.siguiente_pregunta(bd, "Montaje", conversacion, False)["texto"] == "¿Cada cuánto se hace?"


def test_vision_deja_de_intentarlo_si_el_modelo_falla(monkeypatch, bd):
    """Sin modelo de visión operativo no se espera el tiempo máximo en cada uno de los pasos."""
    from cidia.ia import llm

    carpeta = ajustes().dir_datos / "vision_prueba"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "p.jpg").write_bytes(b"\xff\xd8\xff\xe0imagen")
    llamadas = []

    def falla(*a, **k):
        llamadas.append(1)
        raise llm.ErrorModelo("No se puede contactar con el modelo")

    monkeypatch.setattr(llm, "chat", falla)
    pasos = [{"titulo": f"Paso {i}", "texto": "Texto", "imagen_ruta": "vision_prueba/p.jpg"} for i in range(6)]
    assert captura.mejorar_con_vision(bd, pasos) is False
    assert len(llamadas) == 2 and all(p["texto"] == "Texto" for p in pasos)


# --------------------------------------------------------------------------- permisos y listados


def test_permisos_de_captura(cliente, bd, planta, ia):
    t_ot = nueva_tarea(bd, planta, "ot")
    # Empleados sin la marca de experto.
    for persona in ("luis", "pedro", "marta"):
        hp = cab(cliente, persona)
        assert cliente.get("/api/captura", headers=hp).status_code == 403
        assert cliente.post("/api/captura/entrevista", headers=hp, json={"tema": "x"}).status_code == 403
        r = cliente.post("/api/captura/audio", headers=hp, files={"fichero": ("n.webm", b"a", "audio/webm")})
        assert r.status_code == 403
    assert cliente.get("/api/captura").status_code == 401
    hi = cab(cliente, "invitado")
    assert cliente.get("/api/captura", headers=hi).status_code == 401
    assert cliente.post("/api/captura/entrevista", headers=hi, json={"tema": "x"}).status_code == 401
    # Experta de Producción con una tarea de Oficina técnica.
    hc = cab(cliente, "carmen")
    assert cliente.post("/api/captura/entrevista", headers=hc, json={"tarea_id": t_ot.id}).status_code == 403
    r = cliente.post("/api/captura/audio", headers=hc, data={"tarea_id": str(t_ot.id)},
                     files={"fichero": ("n.webm", b"a", "audio/webm")})
    assert r.status_code == 403
    assert cliente.post("/api/captura/entrevista", headers=hc, json={}).status_code == 400

    # Las capturas son de quien las hace: otra experta (otro departamento) no las ve ni las borra.
    ia.transcripcion = "Nota de Carmen."
    ia.json = None
    d = cliente.post("/api/captura/audio", headers=hc, files={"fichero": ("n.webm", b"a", "audio/webm")}).json()
    ha = cab(cliente, "ana")
    assert cliente.get(f"/api/captura/{d['id']}", headers=ha).status_code == 403
    assert cliente.delete(f"/api/captura/{d['id']}", headers=ha).status_code == 403
    assert cliente.put(f"/api/captura/{d['id']}/ficha", headers=ha, json={"titulo": "x"}).status_code == 403
    assert d["id"] not in {c["id"] for c in cliente.get("/api/captura", headers=ha).json()}
    assert d["id"] in {c["id"] for c in cliente.get("/api/captura", headers=hc).json()}
    assert cliente.get(f"/api/captura/{d['id']}", headers=cab(cliente, "admin")).status_code == 200
    assert cliente.get(f"/api/captura/{d['id']}", headers=hc).json()["autor"]["nombre"] == "Carmen Díaz"

    # Un jefe sin departamento no ve las capturas de quien tampoco lo tiene (la administración).
    if bd.scalar(select(Usuario).where(Usuario.usuario == "jefe_suelto")) is None:
        bd.add(Usuario(usuario="jefe_suelto", nombre="Jefe sin departamento", rol="jefe",
                       hash_contrasena=hash_contrasena(CONTRASENA)))
        bd.commit()
    de_admin = cliente.post("/api/captura/entrevista", headers=cab(cliente, "admin"), json={"tarea_id": t_ot.id}).json()
    hs = cab(cliente, "jefe_suelto")
    assert cliente.get(f"/api/captura/{de_admin['id']}", headers=hs).status_code == 403
    assert cliente.delete(f"/api/captura/{de_admin['id']}", headers=hs).status_code == 403


# --------------------------------------------------------------------------- piezas sin API


def test_normalizar_propuesta():
    p = captura.normalizar_propuesta({"pasos": [{"titulo": "A", "t_inicio": "0:05", "t_fin": "0:09"},
                                                 {"texto": "Aprieta bien la tuerca. Luego sigue.", "t_inicio": 9}]}, 20.0)
    assert p and p["pasos"][0]["t_inicio"] == 5.0 and p["pasos"][0]["t_fin"] == 9.0
    assert p["pasos"][1]["titulo"] == "Aprieta bien la tuerca" and p["pasos"][1]["t_fin"] == 20.0
    # Tiempos sin sentido → reparto uniforme.
    q = captura.normalizar_propuesta({"pasos": [{"titulo": "A", "t_inicio": 50}, {"titulo": "B", "t_inicio": 1}]}, 10.0)
    assert [(x["t_inicio"], x["t_fin"]) for x in q["pasos"]] == [(0.0, 5.0), (5.0, 10.0)]
    # Respuesta envuelta en otro objeto y pasos numerados como claves.
    r = captura.normalizar_propuesta({"instruccion": {"titulo": "T", "pasos": {"1": {"titulo": "A"}, "2": {"titulo": "B"}}}}, 10.0)
    assert r and r["titulo"] == "T" and [x["titulo"] for x in r["pasos"]] == ["A", "B"]
    # Basura.
    assert captura.normalizar_propuesta("texto", 10) is None
    assert captura.normalizar_propuesta({"pasos": []}, 10) is None
    assert captura.normalizar_propuesta({"pasos": [{"titulo": "X"}] * 4}, 10) is None


def test_propuesta_con_claves_en_ingles_y_titulos_repetidos():
    """Modelos diminutos: claves en inglés, texto como lista de frases y el mismo título en todos."""
    p = captura.normalizar_propuesta({"title": "Cambio de filtro", "tools": ["Llave"], "steps": [
        {"title": "Paso", "text": ["Afloja", "los tornillos."], "start": "0:00", "end": 4, "critical": "yes"},
        {"title": "Paso", "description": "Quita la tapa.", "start": 4},
        {"title": "Paso", "text": "Limpia el filtro.", "start": 8},
    ]}, 12.0)
    assert p and p["titulo"] == "Cambio de filtro" and p["herramientas"] == "Llave"
    assert [x["titulo"] for x in p["pasos"]] == ["Afloja los tornillos", "Quita la tapa", "Limpia el filtro"]
    assert p["pasos"][0]["texto"] == "Afloja los tornillos." and p["pasos"][0]["es_critico"]
    assert [(x["t_inicio"], x["t_fin"]) for x in p["pasos"]] == [(0.0, 4.0), (4.0, 8.0), (8.0, 12.0)]
    # Envuelta en otro objeto y en inglés.
    q = captura.normalizar_propuesta({"instruction": {"steps": [{"title": "A"}, {"title": "B"}]}}, None,
                                     con_tiempos=False)
    assert q and [x["titulo"] for x in q["pasos"]] == ["A", "B"]
    # El mismo título y el mismo texto en todos: atasco del modelo, se usa el plan B.
    assert captura.normalizar_propuesta({"pasos": [{"titulo": "Paso", "texto": "Igual."}] * 3}, 10) is None


def test_transcripcion_larga_llega_entera_al_modelo():
    """Un vídeo largo no se corta por el final: el modelo ve el principio y el final del vídeo."""
    from cidia.servicios import captura_prompts

    segmentos = [{"inicio": i * 3.0, "fin": i * 3.0 + 3, "texto": f"Frase número {i} con algo de detalle técnico."}
                 for i in range(800)]
    t = captura_prompts.transcripcion_compacta(segmentos, 9000)
    assert len(t) <= 9000
    assert t.startswith("[0.0-") and t.splitlines()[-1].startswith("[") and "-2400.0]" in t.splitlines()[-1]
    corta = captura_prompts.transcripcion_compacta(segmentos[:3], 9000)
    assert corta.splitlines()[1] == "[3.0-6.0] Frase número 1 con algo de detalle técnico."
    mensajes = captura_prompts.mensajes_pasos("T", 2400.0, segmentos, "", [{"t": float(i)} for i in range(200)])
    cortes = mensajes[1]["content"].split("Cambios de plano (segundos): ")[1].splitlines()[0].split(", ")
    assert len(cortes) == 80 and cortes[-1] == "197.0"


def test_borrador_por_segmentos_sin_escenas():
    segmentos = [{"inicio": i * 10.0, "fin": i * 10.0 + 9, "texto": f"Frase {i}."} for i in range(9)]
    b = captura.borrador_por_segmentos(segmentos, [], 90.0, "Tarea")
    assert len(b["pasos"]) == 3 and b["pasos"][0]["texto"].startswith("Frase 0.")
    assert b["pasos"][-1]["t_fin"] == 90.0
    vacio = captura.borrador_por_segmentos([], [], 0, "Nada")
    assert len(vacio["pasos"]) == 1


@pytest.mark.ia_real
def test_pasos_con_el_modelo_real(app, bd):
    """Con el modelo real (diminuto) la propuesta debe ser siempre utilizable (o caer al plan B)."""
    trans = {"texto": "", "segmentos": [
        {"inicio": 0.0, "fin": 5.0, "texto": "Primero me pongo los guantes y las gafas."},
        {"inicio": 5.0, "fin": 12.0, "texto": "Coloco la brida sobre el soporte y la centro con los pasadores."},
        {"inicio": 12.0, "fin": 20.0, "texto": "Aprieto los cuatro tornillos en cruz a veinticinco newton metro, esto es crítico."},
    ]}
    propuesta, origen = captura.proponer_pasos(bd, trans, [{"t": 5.0, "puntuacion": 20}, {"t": 12.0, "puntuacion": 30}],
                                               20.0, "Montaje de la brida B")
    assert origen in ("modelo", "segmentos") and propuesta["pasos"]
    assert all(0 <= p["t_inicio"] < p["t_fin"] <= 20.0 for p in propuesta["pasos"])
