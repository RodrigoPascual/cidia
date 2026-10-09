"""Espacio de trabajo: carpeta privada por persona, rutas seguras, cuotas y consola (ejecutor simulado)."""

from __future__ import annotations

import errno
import json
import os
import shutil
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fabrica import cab
from sqlalchemy import select

from cidia.config import ajustes
from cidia.modelos import SentenciaXapi
from cidia.servicios import espacio


def carpeta(usuario: str) -> Path:
    return ajustes().dir_datos / espacio.CARPETA_RAIZ / usuario


def escribir(cliente, h, ruta: str, contenido: str = "hola"):
    return cliente.put("/api/espacio/fichero", json={"ruta": ruta, "contenido": contenido}, headers=h)


def nombres(elementos: list[dict]) -> list[str]:
    return [e["nombre"] for e in elementos]


# --------------------------------------------------------------------------- acceso


def test_sin_sesion_o_invitado_401(cliente, planta):
    assert cliente.get("/api/espacio").status_code == 401
    h = cab(cliente, "invitado")
    for metodo, ruta, extra in (
        ("GET", "/api/espacio", {}),
        ("GET", "/api/espacio/fichero?ruta=a.txt", {}),
        ("PUT", "/api/espacio/fichero", {"json": {"ruta": "a.txt", "contenido": "x"}}),
        ("DELETE", "/api/espacio/fichero?ruta=a.txt", {}),
        ("POST", "/api/espacio/mover", {"json": {"origen": "a", "destino": "b"}}),
        ("POST", "/api/espacio/carpeta", {"json": {"ruta": "a"}}),
        ("POST", "/api/espacio/ejecutar", {"json": {"orden": "ls"}}),
        ("GET", "/api/espacio/ejecutor", {}),
    ):
        r = cliente.request(metodo, ruta, headers=h, **extra)
        assert r.status_code == 401, (metodo, ruta, r.text)
    r = cliente.post("/api/espacio/subir", files={"fichero": ("a.txt", b"x")}, headers=h)
    assert r.status_code == 401


def test_carpeta_se_crea_al_primer_uso(cliente, planta):
    h = cab(cliente, "luis")
    r = cliente.get("/api/espacio", headers=h)
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["carpeta"] == "luis"
    assert datos["cuota"] == espacio.CUOTA
    assert carpeta("luis").is_dir()


# --------------------------------------------------------------------------- ficheros


def test_escribir_leer_y_listar(cliente, planta):
    h = cab(cliente, "luis")
    r = escribir(cliente, h, "informes/marzo/resumen.md", "# Resumen\n\nTodo en orden.")
    assert r.status_code == 200, r.text
    assert r.json()["ruta"] == "informes/marzo/resumen.md"
    assert r.json()["vista"] == "markdown"

    r = cliente.get("/api/espacio/fichero", params={"ruta": "informes/marzo/resumen.md"}, headers=h)
    assert r.status_code == 200
    f = r.json()
    assert f["contenido"].startswith("# Resumen") and f["es_texto"] and not f["truncado"]
    assert "descargar=1" in f["url_descarga"]

    arbol = cliente.get("/api/espacio", headers=h).json()
    informes = next(e for e in arbol["elementos"] if e["nombre"] == "informes")
    assert informes["tipo"] == "carpeta"
    marzo = informes["hijos"][0]
    assert marzo["nombre"] == "marzo" and nombres(marzo["hijos"]) == ["resumen.md"]
    assert informes["tamano"] == marzo["tamano"] == f["tamano"] > 0
    assert arbol["uso"] >= f["tamano"]

    # la descarga firmada funciona y fuerza «guardar como»
    d = cliente.get(f["url_descarga"])
    assert d.status_code == 200 and d.content.startswith(b"# Resumen")
    assert "attachment" in d.headers.get("content-disposition", "")


def test_csv_imagen_y_binario(cliente, planta):
    h = cab(cliente, "luis")
    escribir(cliente, h, "datos/paradas.csv", "maquina;minutos\nprensa 3;12\n")
    f = cliente.get("/api/espacio/fichero", params={"ruta": "datos/paradas.csv"}, headers=h).json()
    assert f["vista"] == "csv" and "prensa 3" in f["contenido"]
    # imagen: sin contenido, con URL para <img>
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    r = cliente.post("/api/espacio/subir", data={"carpeta": "datos"}, files={"fichero": ("grafico.png", png, "image/png")},
                     headers=h)
    assert r.status_code == 200, r.text
    f = cliente.get("/api/espacio/fichero", params={"ruta": "datos/grafico.png"}, headers=h).json()
    assert f["vista"] == "imagen" and f["contenido"] is None and f["url"]
    r = cliente.get(f["url"])  # para <img>: en línea, sin «guardar como»
    assert r.status_code == 200 and r.content == png and "content-disposition" not in r.headers
    # HTML y SVG nunca tienen URL para abrir en la página (solo descarga)
    escribir(cliente, h, "datos/pagina.html", "<script>alert(1)</script>")
    f = cliente.get("/api/espacio/fichero", params={"ruta": "datos/pagina.html"}, headers=h).json()
    assert f["url"] is None and f["vista"] == "texto"


def test_subir_no_sustituye(cliente, planta):
    h = cab(cliente, "pedro")
    for _ in range(2):
        r = cliente.post("/api/espacio/subir", files={"fichero": ("parte.txt", b"hola")}, headers=h)
        assert r.status_code == 200, r.text
    arbol = cliente.get("/api/espacio", headers=h).json()
    assert {"parte.txt", "parte (2).txt"} <= set(nombres(arbol["elementos"]))
    r = cliente.post("/api/espacio/subir", data={"carpeta": "no-existe"}, files={"fichero": ("x.txt", b"x")}, headers=h)
    assert r.status_code == 404


def test_carpetas_mover_y_borrar(cliente, planta):
    h = cab(cliente, "marta")
    assert cliente.post("/api/espacio/carpeta", json={"ruta": "borradores"}, headers=h).status_code == 200
    assert cliente.post("/api/espacio/carpeta", json={"ruta": "borradores"}, headers=h).status_code == 409
    escribir(cliente, h, "borradores/a.txt", "uno")
    # renombrar
    r = cliente.post("/api/espacio/mover", json={"origen": "borradores/a.txt", "destino": "borradores/b.txt"}, headers=h)
    assert r.status_code == 200 and r.json()["ruta"] == "borradores/b.txt"
    # no sustituye
    escribir(cliente, h, "c.txt", "dos")
    r = cliente.post("/api/espacio/mover", json={"origen": "c.txt", "destino": "borradores/b.txt"}, headers=h)
    assert r.status_code == 409
    # una carpeta no puede ir dentro de sí misma
    r = cliente.post("/api/espacio/mover", json={"origen": "borradores", "destino": "borradores/sub/borradores"},
                     headers=h)
    assert r.status_code == 400
    # mover a otra carpeta (la crea)
    r = cliente.post("/api/espacio/mover", json={"origen": "c.txt", "destino": "archivo/c.txt"}, headers=h)
    assert r.status_code == 200
    # borrar fichero y carpeta con contenido
    assert cliente.delete("/api/espacio/fichero", params={"ruta": "archivo/c.txt"}, headers=h).status_code == 200
    assert cliente.delete("/api/espacio/fichero", params={"ruta": "borradores"}, headers=h).status_code == 200
    assert cliente.delete("/api/espacio/fichero", params={"ruta": "borradores"}, headers=h).status_code == 404
    assert not (carpeta("marta") / "borradores").exists()
    # la carpeta principal no se borra ni se mueve
    assert cliente.delete("/api/espacio/fichero", params={"ruta": ""}, headers=h).status_code == 400
    assert cliente.delete("/api/espacio/fichero", params={"ruta": "."}, headers=h).status_code == 400
    assert cliente.post("/api/espacio/mover", json={"origen": "", "destino": "x"}, headers=h).status_code == 400
    # xAPI de las acciones
    with __import__("cidia.db", fromlist=["nueva_sesion"]).nueva_sesion() as bd:
        verbos = set(bd.scalars(select(SentenciaXapi.verbo).where(
            SentenciaXapi.objeto_tipo == "espacio", SentenciaXapi.actor_id == planta.personas["marta"].id)).all())
    assert {"creo", "guardo", "movio", "borro"} <= verbos


# --------------------------------------------------------------------------- seguridad de rutas

# Salen de la carpeta: 400 siempre y en todas las operaciones.
RUTAS_FUERA = [
    "../secreto.txt",
    "../../etc/passwd",
    "a/../../secreto.txt",
    "/etc/passwd",
    "a/\x00b.txt",
]
# No salen, pero no son nombres portables (Windows): nunca valen para crear nada. En Linux, para
# leer, mover o borrar lo que ya existe se toman tal cual (son nombres literales dentro de la
# carpeta, que una orden pudo crear), así que ahí basta con que no existan (404).
RUTAS_NO_PORTABLES = [
    "..\\secreto.txt",
    "\\\\servidor\\compartida\\x",
    "C:/Windows/win.ini",
    "c:secreto.txt",
    "~/x.txt",
    "nombre:con-dos-puntos.txt",
]


@pytest.mark.parametrize("mala", RUTAS_FUERA + RUTAS_NO_PORTABLES)
def test_rutas_maliciosas(cliente, planta, mala):
    h = cab(cliente, "pedro")
    existente = {400} if os.name != "posix" or mala in RUTAS_FUERA else {400, 404}
    assert cliente.get("/api/espacio/fichero", params={"ruta": mala}, headers=h).status_code in existente
    assert escribir(cliente, h, mala).status_code == 400
    assert cliente.delete("/api/espacio/fichero", params={"ruta": mala}, headers=h).status_code in existente
    assert cliente.post("/api/espacio/carpeta", json={"ruta": mala}, headers=h).status_code == 400
    escribir(cliente, h, "propio.txt", "mío")
    assert cliente.post("/api/espacio/mover", json={"origen": "propio.txt", "destino": mala}, headers=h).status_code == 400
    r = cliente.post("/api/espacio/mover", json={"origen": mala, "destino": "x.txt"}, headers=h)
    assert r.status_code in existente
    r = cliente.post("/api/espacio/subir", data={"carpeta": mala}, files={"fichero": ("x.txt", b"x")}, headers=h)
    assert r.status_code in existente
    r = cliente.get("/api/espacio/fichero", params={"ruta": "propio.txt"}, headers=h)
    assert r.status_code == 200 and r.json()["contenido"] == "mío"  # lo propio sigue intacto


def test_descarga_firmada(cliente, planta):
    """Las descargas van por /api/espacio/descarga: firma propia y sin seguir enlaces hacia fuera."""
    escribir(cliente, cab(cliente, "admin"), "secreto.txt", "del admin")
    h = cab(cliente, "carmen")
    f = escribir(cliente, h, "informe.txt", "mío").json()
    url = f["url_descarga"]
    assert url.startswith("/api/espacio/descarga/carmen/informe.txt?") and "descargar=1" in url
    r = cliente.get(url)  # sin cabecera de sesión: la URL firmada basta (como en <a> o <img>)
    assert r.status_code == 200 and r.content == "mío".encode()
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["content-security-policy"] == "sandbox"
    # firma manipulada o caducada
    assert cliente.get(url.replace("firma=", "firma=0")).status_code == 403
    assert cliente.get(url.replace("exp=", "exp=1")).status_code == 403
    # la firma del espacio no vale en /api/ficheros (que sí sigue enlaces)
    consulta = url.split("?", 1)[1]
    assert cliente.get(f"/api/ficheros/{espacio.CARPETA_RAIZ}/carmen/informe.txt?{consulta}").status_code == 403
    # una orden sustituye el fichero ya firmado por un enlace a la carpeta de otro: deja de servirse
    p = carpeta("carmen") / "informe.txt"
    p.unlink()
    try:
        os.symlink(carpeta("admin") / "secreto.txt", p)
    except (OSError, NotImplementedError):
        pytest.skip("Este sistema no permite crear enlaces simbólicos")
    try:
        assert cliente.get(url).status_code == 404
    finally:
        p.unlink()


def test_nadie_ve_la_carpeta_de_otro(cliente, planta):
    escribir(cliente, cab(cliente, "ana"), "nominas.txt", "confidencial")
    h = cab(cliente, "luis")
    assert cliente.get("/api/espacio/fichero", params={"ruta": "nominas.txt"}, headers=h).status_code == 404
    assert cliente.get("/api/espacio/fichero", params={"ruta": "../ana/nominas.txt"}, headers=h).status_code == 400
    assert "nominas.txt" not in nombres(cliente.get("/api/espacio", headers=h).json()["elementos"])
    # ni por un nombre de subida con ruta
    r = cliente.post("/api/espacio/subir", files={"fichero": ("../ana/nominas.txt", b"pisado")}, headers=h)
    assert r.status_code == 200 and r.json()["ruta"] == "nominas.txt"  # se queda en la carpeta de Luis
    assert (carpeta("ana") / "nominas.txt").read_text(encoding="utf-8") == "confidencial"


def test_enlaces_simbolicos_no_salen(cliente, planta):
    """Una orden en la caja de arena podría crear enlaces: nunca llevan fuera de la carpeta."""
    h = cab(cliente, "javier")
    escribir(cliente, cab(cliente, "admin"), "clave.txt", "secreto del admin")
    raiz = carpeta("javier")
    raiz.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(carpeta("admin") / "clave.txt", raiz / "enlace.txt")
        os.symlink(carpeta("admin"), raiz / "enlace-carpeta", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Este sistema no permite crear enlaces simbólicos")
    assert cliente.get("/api/espacio/fichero", params={"ruta": "enlace.txt"}, headers=h).status_code == 400
    assert cliente.get("/api/espacio/fichero", params={"ruta": "enlace-carpeta/clave.txt"}, headers=h).status_code == 400
    assert escribir(cliente, h, "enlace-carpeta/nuevo.txt").status_code == 400
    assert escribir(cliente, h, "enlace.txt", "pisado").status_code == 400
    # el árbol los muestra como enlaces, sin entrar en ellos
    arbol = cliente.get("/api/espacio", headers=h).json()
    tipos = {e["nombre"]: e["tipo"] for e in arbol["elementos"]}
    assert tipos["enlace.txt"] == "enlace" and tipos["enlace-carpeta"] == "enlace"
    # borrar el enlace quita el enlace, no lo enlazado
    assert cliente.delete("/api/espacio/fichero", params={"ruta": "enlace-carpeta"}, headers=h).status_code == 200
    assert cliente.delete("/api/espacio/fichero", params={"ruta": "enlace.txt"}, headers=h).status_code == 200
    assert (carpeta("admin") / "clave.txt").read_text(encoding="utf-8") == "secreto del admin"


def _enlazar(destino: Path, enlace: Path, es_carpeta: bool = False) -> None:
    try:
        os.symlink(destino, enlace, target_is_directory=es_carpeta)
    except (OSError, NotImplementedError):
        pytest.skip("Este sistema no permite crear enlaces simbólicos")


def test_enlace_en_bucle(cliente, planta):
    """Un enlace que apunta a sí mismo (lo puede crear una orden) no rompe nada."""
    h = cab(cliente, "javier")
    raiz = carpeta("javier")
    raiz.mkdir(parents=True, exist_ok=True)
    _enlazar(raiz / "bucle", raiz / "bucle")
    try:
        assert cliente.get("/api/espacio/fichero", params={"ruta": "bucle"}, headers=h).status_code == 400
        assert escribir(cliente, h, "bucle/x.txt").status_code in (400, 404, 409)  # nunca se escribe
        r = cliente.get("/api/espacio", headers=h)
        assert r.status_code == 200
        assert {e["nombre"]: e["tipo"] for e in r.json()["elementos"]}["bucle"] == "enlace"
        assert cliente.delete("/api/espacio/fichero", params={"ruta": "bucle"}, headers=h).status_code == 200
    finally:
        if os.path.lexists(raiz / "bucle"):
            os.unlink(raiz / "bucle")


def test_temporales_ocultos_y_nombre_largo(cliente, planta):
    h = cab(cliente, "pedro")
    cliente.get("/api/espacio", headers=h)
    (carpeta("pedro") / ".cidia-0123456789.tmp").write_bytes(b"a medias")
    assert ".cidia-0123456789.tmp" not in nombres(cliente.get("/api/espacio", headers=h).json()["elementos"])
    # un nombre de 150 caracteres que ya existe: la copia « (2)» no pasa del máximo y se puede usar
    largo = "x" * 146 + ".txt"
    for _ in range(2):
        r = cliente.post("/api/espacio/subir", files={"fichero": (largo, b"hola")}, headers=h)
        assert r.status_code == 200, r.text
    copia = r.json()["ruta"]
    assert copia.endswith(" (2).txt") and len(copia) <= espacio.MAX_NOMBRE
    assert cliente.get("/api/espacio/fichero", params={"ruta": copia}, headers=h).status_code == 200
    assert cliente.delete("/api/espacio/fichero", params={"ruta": copia}, headers=h).status_code == 200


def test_errores_de_disco_claros(cliente, planta, monkeypatch):
    """Un problema del servidor (permisos de /datos, disco lleno) se explica, no es un 500 mudo."""
    h = cab(cliente, "pedro")

    def sin_permiso(*_a, **_k):
        raise PermissionError(errno.EACCES, "Permission denied", "/datos/generador-de-contenido/pedro")

    monkeypatch.setattr(espacio._Carpeta, "guardar", sin_permiso)
    r = escribir(cliente, h, "a.txt", "x")
    assert r.status_code == 500 and "permiso" in r.json()["detail"] and "/datos" not in r.json()["detail"]

    def lleno(*_a, **_k):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(espacio._Carpeta, "guardar", lleno)
    r = cliente.post("/api/espacio/subir", files={"fichero": ("b.txt", b"x")}, headers=h)
    assert r.status_code == 507 and "lleno" in r.json()["detail"]


@pytest.mark.skipif(os.name != "posix", reason="En Windows no se pueden crear esos nombres")
def test_nombres_creados_por_una_orden(cliente, planta):
    """Una orden puede crear nombres no portables (p. ej. con la hora): se ven, se leen, se
    descargan, se renombran y se borran. Los que no son UTF-8 no rompen la lista."""
    h = cab(cliente, "marta")
    raiz = carpeta("marta")
    (raiz / "turno 12:30").mkdir(parents=True, exist_ok=True)
    (raiz / "turno 12:30" / "informe?.txt").write_text("hola", encoding="utf-8")
    os.close(os.open(os.fsencode(raiz) + b"/mal\xff.txt", os.O_CREAT | os.O_WRONLY))
    r = cliente.get("/api/espacio", headers=h)
    assert r.status_code == 200, r.text
    turno = next(e for e in r.json()["elementos"] if e["nombre"] == "turno 12:30")
    f = turno["hijos"][0]
    assert f["ruta"] == "turno 12:30/informe?.txt"
    r = cliente.get("/api/espacio/fichero", params={"ruta": f["ruta"]}, headers=h)
    assert r.status_code == 200 and r.json()["contenido"] == "hola"
    assert cliente.get(f["url_descarga"]).content == b"hola"
    # se puede renombrar a un nombre portable (también dentro de su carpeta), pero no crear otro
    # que no lo sea
    destino = {"origen": f["ruta"], "destino": "turno 12:31.txt"}
    assert cliente.post("/api/espacio/mover", json=destino, headers=h).status_code == 400
    destino["destino"] = "turno 12:30/informe.txt"
    r = cliente.post("/api/espacio/mover", json=destino, headers=h)
    assert r.status_code == 200 and r.json()["ruta"] == "turno 12:30/informe.txt"
    assert escribir(cliente, h, "turno 12:30/notas.md", "# Notas").status_code == 200
    assert cliente.post("/api/espacio/carpeta", json={"ruta": "turno 12:30/a:b"}, headers=h).status_code == 400
    destino = {"origen": "turno 12:30/informe.txt", "destino": "informe.txt"}
    assert cliente.post("/api/espacio/mover", json=destino, headers=h).status_code == 200
    assert cliente.delete("/api/espacio/fichero", params={"ruta": "turno 12:30"}, headers=h).status_code == 200
    os.unlink(os.fsencode(raiz) + b"/mal\xff.txt")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="Sin FIFO en este sistema")
def test_fifo_no_bloquea(cliente, planta):
    """Una FIFO creada por una orden no deja colgado un hilo del servidor al abrirla."""
    h = cab(cliente, "luis")
    cliente.get("/api/espacio", headers=h)
    tubo = carpeta("luis") / "tubo.txt"
    os.mkfifo(tubo)
    try:
        e = next(x for x in cliente.get("/api/espacio", headers=h).json()["elementos"] if x["nombre"] == "tubo.txt")
        assert e["tipo"] == "especial" and "url_descarga" not in e
        assert cliente.get("/api/espacio/fichero", params={"ruta": "tubo.txt"}, headers=h).status_code == 400
    finally:
        tubo.unlink()


def test_en_linux_se_usan_descriptores():
    """En el servidor (Linux) la protección contra carreras con enlaces tiene que estar activa."""
    if sys.platform.startswith("linux"):
        assert espacio.CON_DESCRIPTORES
    else:
        assert not espacio.CON_DESCRIPTORES or os.name == "posix"


@pytest.mark.skipif(not espacio.CON_DESCRIPTORES, reason="Solo en Linux (descriptores con O_NOFOLLOW)")
@pytest.mark.parametrize("momento", ["tras_comprobar", "tras_abrir"])
def test_carrera_con_enlaces(cliente, planta, monkeypatch, momento):
    """Una orden de la caja de arena gana la carrera: después de que el gateway compruebe la ruta
    (o incluso después de abrir la carpeta, justo antes de operar) cambia una carpeta o un
    fichero por un enlace a la carpeta de otra persona. Ni se lee, ni se escribe, ni se mueve,
    ni se borra nada fuera de la propia carpeta. (Con rutas en lugar de descriptores, el
    momento «tras_abrir» filtra el fichero ajeno: así se comprobó que la prueba lo detecta.)"""
    escribir(cliente, cab(cliente, "admin"), "clave.txt", "secreto del admin")
    ajena = carpeta("admin")
    antes = sorted(p.name for p in ajena.iterdir())
    h = cab(cliente, "javier")
    cliente.get("/api/espacio", headers=h)
    raiz = carpeta("javier")
    pendiente: list = []

    def cambiar() -> None:
        while pendiente:
            pendiente.pop()()

    if momento == "tras_comprobar":
        real = espacio._real

        def real_y_cambio(r, trozos):
            p = real(r, trozos)
            cambiar()
            return p

        monkeypatch.setattr(espacio, "_real", real_y_cambio)
    else:
        abrir = espacio._Carpeta.__init__

        def abrir_y_cambio(self, *a, **k):
            abrir(self, *a, **k)
            cambiar()

        monkeypatch.setattr(espacio._Carpeta, "__init__", abrir_y_cambio)

    def limpiar() -> None:
        for n in ("informes", "x.txt"):
            if os.path.islink(raiz / n):
                os.unlink(raiz / n)
        for n in ("informes", "informes-antes"):
            shutil.rmtree(raiz / n, ignore_errors=True)
        (raiz / "informes").mkdir()
        (raiz / "x.txt").write_text("mío", encoding="utf-8")

    def carpeta_por_enlace() -> None:
        (raiz / "informes").rename(raiz / "informes-antes")
        os.symlink(ajena, raiz / "informes", target_is_directory=True)

    def fichero_por_enlace() -> None:
        os.unlink(raiz / "x.txt")
        os.symlink(ajena / "clave.txt", raiz / "x.txt")

    def nada_fuera(respuesta: bytes, caso: tuple) -> None:
        assert b"secreto" not in respuesta, caso
        assert sorted(p.name for p in ajena.iterdir()) == antes, caso
        assert (ajena / "clave.txt").read_text(encoding="utf-8") == "secreto del admin", caso
        for actual, _d, ficheros in os.walk(raiz):  # nada ajeno ha acabado en la carpeta de Javier
            for f in ficheros:
                p = Path(actual) / f
                assert p.is_symlink() or b"secreto" not in p.read_bytes(), (caso, p)

    casos = [
        ("GET", "/api/espacio/fichero", {"params": {"ruta": "informes/clave.txt"}}, carpeta_por_enlace),
        ("GET", "/api/espacio/fichero", {"params": {"ruta": "x.txt"}}, fichero_por_enlace),
        ("PUT", "/api/espacio/fichero", {"json": {"ruta": "informes/nuevo.txt", "contenido": "x"}}, carpeta_por_enlace),
        ("DELETE", "/api/espacio/fichero", {"params": {"ruta": "informes/clave.txt"}}, carpeta_por_enlace),
        ("POST", "/api/espacio/mover", {"json": {"origen": "informes/clave.txt", "destino": "robado.txt"}},
         carpeta_por_enlace),
        ("POST", "/api/espacio/mover", {"json": {"origen": "x.txt", "destino": "informes/x.txt"}}, carpeta_por_enlace),
        ("POST", "/api/espacio/carpeta", {"json": {"ruta": "informes/sub"}}, carpeta_por_enlace),
        ("POST", "/api/espacio/subir", {"data": {"carpeta": "informes"}, "files": {"fichero": ("y.txt", b"y")}},
         carpeta_por_enlace),
        ("PUT", "/api/espacio/fichero", {"json": {"ruta": "x.txt", "contenido": "nuevo"}}, fichero_por_enlace),
    ]
    for metodo, ruta, extra, cambio in casos:
        limpiar()
        pendiente.append(cambio)
        r = cliente.request(metodo, ruta, headers=h, **extra)
        assert r.status_code < 500, (metodo, ruta, r.status_code, r.text)
        nada_fuera(r.content, (metodo, ruta, extra))

    # descarga firmada de un fichero que cambia por un enlace mientras se comprueba
    limpiar()
    url = cliente.get("/api/espacio/fichero", params={"ruta": "x.txt"}, headers=h).json()["url_descarga"]
    pendiente.append(fichero_por_enlace)
    r = cliente.get(url)
    assert r.status_code == 404
    nada_fuera(r.content, ("descarga",))
    limpiar()


# --------------------------------------------------------------------------- cuotas y límites


def test_cuota_y_limites(cliente, planta, monkeypatch):
    h = cab(cliente, "carmen")
    cliente.get("/api/espacio", headers=h)  # crea la carpeta si aún no existe
    monkeypatch.setattr(espacio, "CUOTA", espacio.uso(carpeta("carmen")) + 1000)
    assert escribir(cliente, h, "a.txt", "x" * 600).status_code == 200
    r = escribir(cliente, h, "b.txt", "x" * 600)
    assert r.status_code == 413 and "límite" in r.json()["detail"]
    # sustituir un fichero cuenta lo que libera
    assert escribir(cliente, h, "a.txt", "y" * 900).status_code == 200
    r = cliente.post("/api/espacio/subir", files={"fichero": ("c.bin", b"z" * 500)}, headers=h)
    assert r.status_code == 413
    assert not [p for p in carpeta("carmen").iterdir() if p.name.startswith(".cidia-")]  # sin restos
    # límite por fichero
    monkeypatch.setattr(espacio, "CUOTA", 10 * espacio.MB)
    monkeypatch.setattr(espacio, "MAX_FICHERO", 2048)
    r = cliente.post("/api/espacio/subir", files={"fichero": ("grande.bin", b"z" * 4096)}, headers=h)
    assert r.status_code == 413 and "demasiado grande" in r.json()["detail"]
    # texto escrito de una vez
    monkeypatch.setattr(espacio, "MAX_TEXTO", 100)
    assert escribir(cliente, h, "largo.txt", "x" * 200).status_code == 413
    # lectura de texto recortada
    monkeypatch.setattr(espacio, "MAX_LECTURA", 10)
    f = cliente.get("/api/espacio/fichero", params={"ruta": "a.txt"}, headers=h).json()
    assert f["truncado"] and len(f["contenido"]) == 10


# --------------------------------------------------------------------------- consola (ejecutor simulado)


def _configurar(monkeypatch, responder) -> list[httpx.Request]:
    peticiones: list[httpx.Request] = []

    def manejador(p: httpx.Request) -> httpx.Response:
        peticiones.append(p)
        return responder(p)

    monkeypatch.setattr(ajustes(), "espacio_url", "http://espacio-trabajo:8090")
    monkeypatch.setattr(ajustes(), "espacio_secreto", "secreto-de-pruebas")
    monkeypatch.setattr(espacio, "_transporte", httpx.MockTransport(manejador))
    return peticiones


def test_ejecutar_sin_ejecutor(cliente, planta, monkeypatch):
    monkeypatch.setattr(ajustes(), "espacio_secreto", "")
    h = cab(cliente, "pedro")
    r = cliente.post("/api/espacio/ejecutar", json={"orden": "ls"}, headers=h)
    assert r.status_code == 503
    assert r.json()["detail"] == "El espacio de trabajo no está disponible en este servidor."
    assert cliente.get("/api/espacio/ejecutor", headers=h).json()["disponible"] is False


def test_ejecutar_con_ejecutor_simulado(cliente, planta, monkeypatch):
    def responder(p: httpx.Request) -> httpx.Response:
        if p.url.path == "/salud":
            return httpx.Response(200, json={"estado": "ok"})
        return httpx.Response(200, json={"codigo": 0, "salida": "hola\n", "recortada": False, "duracion": 0.8,
                                         "tiempo_agotado": False})

    peticiones = _configurar(monkeypatch, responder)
    h = cab(cliente, "pedro")
    assert cliente.get("/api/espacio/ejecutor", headers=h).json()["disponible"] is True
    r = cliente.post("/api/espacio/ejecutar", json={"orden": "echo hola", "tiempo_max": 30}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["codigo"] == 0 and r.json()["salida"] == "hola\n"
    p = peticiones[-1]
    assert p.url == httpx.URL("http://espacio-trabajo:8090/ejecutar")
    assert p.headers["x-espacio-secreto"] == "secreto-de-pruebas"
    cuerpo = json.loads(p.content)
    assert cuerpo["usuario"] == "pedro" and cuerpo["orden"] == "echo hola" and cuerpo["tiempo_max"] == 30
    assert 0 < cuerpo["limite_bytes"] <= espacio.CUOTA
    with __import__("cidia.db", fromlist=["nueva_sesion"]).nueva_sesion() as bd:
        fila = bd.scalars(select(SentenciaXapi).where(SentenciaXapi.verbo == "ejecuto")
                          .order_by(SentenciaXapi.momento.desc())).first()
    assert fila is not None and fila.actor_id == planta.personas["pedro"].id
    # validación de la orden y del tiempo
    assert cliente.post("/api/espacio/ejecutar", json={"orden": "  "}, headers=h).status_code == 400
    assert cliente.post("/api/espacio/ejecutar", json={"orden": "ls", "tiempo_max": 999}, headers=h).status_code == 422


def test_ejecutor_caido_o_secreto_mal(cliente, planta, monkeypatch):
    h = cab(cliente, "pedro")

    def caido(p: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión", request=p)

    _configurar(monkeypatch, caido)
    r = cliente.post("/api/espacio/ejecutar", json={"orden": "ls"}, headers=h)
    assert r.status_code == 503 and "no está disponible" in r.json()["detail"]
    assert cliente.get("/api/espacio/ejecutor", headers=h).json()["disponible"] is False

    _configurar(monkeypatch, lambda p: httpx.Response(401, json={"detail": "No autorizado."}))
    r = cliente.post("/api/espacio/ejecutar", json={"orden": "ls"}, headers=h)
    assert r.status_code == 503

    _configurar(monkeypatch, lambda p: httpx.Response(429, json={"detail": "El espacio de trabajo está ocupado."}))
    r = cliente.post("/api/espacio/ejecutar", json={"orden": "ls"}, headers=h)
    assert r.status_code == 429 and "ocupado" in r.json()["detail"]


def test_ejecutar_con_carpeta_llena(cliente, planta, monkeypatch):
    peticiones = _configurar(monkeypatch, lambda p: httpx.Response(200, json={"codigo": 0, "salida": ""}))
    h = cab(cliente, "luis")
    escribir(cliente, h, "lleno.txt", "x" * 100)
    monkeypatch.setattr(espacio, "CUOTA", espacio.uso(carpeta("luis")))
    r = cliente.post("/api/espacio/ejecutar", json={"orden": "ls"}, headers=h)
    assert r.status_code == 413
    assert not peticiones  # ni siquiera se llama al ejecutor


def test_nombre_de_carpeta_seguro(planta):
    u = planta.personas["luis"]
    assert espacio.carpeta_de(u) == "luis"
    for raro in ("Luis.García", "../x", ".oculto", "-guion", "a b", "user@empresa.com"):
        u2 = type(u)(id=99, usuario=raro, nombre="x")
        assert espacio.carpeta_de(u2) == "_u99", raro


# --------------------------------------------------------------------------- servicio ejecutor (sin Docker)


def _ejecutor():
    """Carga servidor/espacio-trabajo/ejecutor.py (no forma parte del paquete cidia)."""
    import importlib.util
    import sys

    nombre = "cidia_ejecutor_espacio"
    if nombre in sys.modules:
        return sys.modules[nombre]
    ruta = Path(__file__).resolve().parents[2] / "espacio-trabajo" / "ejecutor.py"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = m
    spec.loader.exec_module(m)
    return m


def _trama(canal: int, datos: bytes) -> bytes:
    return bytes([canal, 0, 0, 0]) + len(datos).to_bytes(4, "big") + datos


class DockerFalso:
    """Imita las llamadas a Docker del ejecutor. `segundos`: lo que «tarda» la orden."""

    def __init__(self, segundos: float = 0.0, codigo: int = 0, al_correr=None) -> None:
        self.segundos, self.codigo, self.al_correr = segundos, codigo, al_correr
        self.creados: list[tuple[str, dict]] = []
        self.borrados: list[str] = []
        self.matado = False
        self.inicio = 0.0

    def ping(self) -> bool:
        return True

    def existe_imagen(self, imagen: str) -> bool:
        return imagen == "cidia-sandbox:local"

    def crear(self, nombre: str, config: dict) -> str:
        self.creados.append((nombre, config))
        return "c1"

    def iniciar(self, cid: str) -> None:
        self.inicio = time.monotonic()

    def estado(self, cid: str) -> dict:
        if self.al_correr:
            self.al_correr()
        corriendo = not self.matado and time.monotonic() - self.inicio < self.segundos
        return {"Running": corriendo, "ExitCode": 137 if self.matado else self.codigo, "OOMKilled": False}

    def matar(self, cid: str) -> None:
        self.matado = True

    def esperar(self, cid: str, segundos: float = 15.0) -> None:
        pass

    def registros(self, cid: str) -> bytes:
        return _trama(1, b"hola\n") + _trama(2, "aviso: ñandú\n".encode())

    def borrar(self, cid: str) -> None:
        self.borrados.append(cid)

    def nuestros(self) -> list[str]:
        return ["resto-anterior"]


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Carpeta temporal propia dentro de los datos de prueba (el temporal del sistema puede no ser accesible)."""
    import shutil
    import uuid

    d = ajustes().dir_datos / "prueba-ejecutor" / uuid.uuid4().hex[:8]
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _config(m, tmp_path: Path):
    (tmp_path / "luis").mkdir(exist_ok=True)
    return m.Config(secreto="s" * 32, datos_host="/srv/cidia/datos/generador-de-contenido",
                    datos_local=str(tmp_path), puerto=0)


def test_ejecutor_contenedor_aislado(tmp_path):
    m = _ejecutor()
    c = m.config_contenedor(_config(m, tmp_path), "luis", "python3 informe.py", max_fichero=5 * m.MB)
    h = c["HostConfig"]
    assert c["Image"] == "cidia-sandbox:local" and c["Cmd"] == ["/bin/bash", "-c", "python3 informe.py"]
    assert c["User"] == "1000:1000" and c["WorkingDir"] == "/trabajo" and c["NetworkDisabled"] is True
    assert c["Labels"]["cidia.espacio"] == "1"
    assert h["NetworkMode"] == "none" and h["ReadonlyRootfs"] is True and h["Privileged"] is False
    assert h["CapDrop"] == ["ALL"] and h["SecurityOpt"] == ["no-new-privileges:true"]
    assert h["PidsLimit"] == 128 and h["Memory"] == h["MemorySwap"] == 256 * m.MB and h["NanoCpus"] == 500_000_000
    assert h["Tmpfs"] == {"/tmp": "rw,noexec,nosuid,nodev,size=64m"}
    assert {"Name": "fsize", "Soft": 5 * m.MB, "Hard": 5 * m.MB} in h["Ulimits"]
    assert h["Mounts"] == [{"Type": "bind", "Source": "/srv/cidia/datos/generador-de-contenido/luis",
                            "Target": "/trabajo", "ReadOnly": False, "BindOptions": {"Propagation": "rprivate"}}]
    assert "Binds" not in h and "Runtime" not in h


def test_ejecutor_valida_peticiones():
    m = _ejecutor()
    assert m.validar({"usuario": "luis", "orden": "ls", "tiempo_max": 30}) == ("luis", "ls", 30, None)
    malas = [
        {"usuario": "../etc", "orden": "ls"}, {"usuario": "Luis", "orden": "ls"}, {"usuario": "..", "orden": "ls"},
        {"usuario": "a/b", "orden": "ls"}, {"usuario": "luis", "orden": ""}, {"usuario": "luis", "orden": "a\x00b"},
        {"usuario": "luis", "orden": "x" * 10_001}, {"usuario": "luis", "orden": "ls", "tiempo_max": 121},
        {"usuario": "luis", "orden": "ls", "tiempo_max": 0}, {"usuario": "luis", "orden": "ls", "tiempo_max": "60"},
        {"usuario": "luis", "orden": "ls", "tiempo_max": True}, {"usuario": "luis", "orden": "ls", "limite_bytes": -1},
        ["no", "es", "un", "objeto"],
    ]
    for datos in malas:
        with pytest.raises(m.ErrorEspacio) as e:
            m.validar(datos)
        assert e.value.estado == 400, datos


def test_ejecutor_salida():
    m = _ejecutor()
    assert m.separar_registros(_trama(1, b"uno\n") + _trama(2, b"dos\n") + _trama(1, b"tres")) == "uno\ndos\ntres"
    assert m.separar_registros(b"sin multiplexar\n") == "sin multiplexar\n"
    texto, recortada = m.recortar("inicio\n" + "x" * 200_000 + "\nfinal")
    assert recortada and len(texto.encode()) <= m.MAX_SALIDA
    assert texto.startswith("inicio") and texto.endswith("final") and "recortada" in texto
    assert m.recortar("corto") == ("corto", False)


def test_ejecutor_http(tmp_path):
    m = _ejecutor()
    cfg = _config(m, tmp_path)
    docker = DockerFalso()
    srv = m.crear_servidor(cfg, docker, "127.0.0.1")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    sec = {"X-Espacio-Secreto": cfg.secreto}
    try:
        assert httpx.get(f"{url}/salud").status_code == 401
        assert httpx.get(f"{url}/salud", headers={"X-Espacio-Secreto": "otro" * 8}).status_code == 401
        assert httpx.get(f"{url}/salud", headers=sec).json() == {"estado": "ok"}
        assert httpx.post(f"{url}/ejecutar", json={"usuario": "luis", "orden": "ls"}).status_code == 401
        assert httpx.get(f"{url}/contenedores", headers=sec).status_code == 404
        assert httpx.post(f"{url}/otra", headers=sec, json={}).status_code == 404
        assert httpx.put(f"{url}/ejecutar", headers=sec, json={}).status_code == 501
        r = httpx.post(f"{url}/ejecutar", headers=sec, json={"usuario": "luis", "orden": "ls", "tiempo_max": 10})
        assert r.status_code == 200, r.text
        assert r.json()["codigo"] == 0 and r.json()["salida"] == "hola\naviso: ñandú\n"
        assert not r.json()["tiempo_agotado"]
        assert docker.borrados == ["c1"]  # el contenedor se borra siempre
        r = httpx.post(f"{url}/ejecutar", headers=sec, json={"usuario": "nadie", "orden": "ls"})
        assert r.status_code == 404 and "no existe" in r.json()["detail"]
        assert httpx.post(f"{url}/ejecutar", headers=sec, content=b"{no es json").status_code == 400
        assert m.Ejecutor(cfg, docker).limpiar_restos() == 1 and docker.borrados[-1] == "resto-anterior"
    finally:
        srv.shutdown()
        srv.server_close()


def test_ejecutor_tiempo_y_cuota(tmp_path):
    m = _ejecutor()
    cfg = _config(m, tmp_path)
    # tiempo agotado: se mata y se borra
    docker = DockerFalso(segundos=30)
    res = m.Ejecutor(cfg, docker).ejecutar("luis", "sleep 30", 1, None)
    assert res["tiempo_agotado"] and docker.matado and res["codigo"] == 137 and docker.borrados == ["c1"]

    # la orden llena la carpeta: se para por cuota
    def llenar() -> None:
        (tmp_path / "luis" / "grande.bin").write_bytes(b"x" * 5000)

    docker = DockerFalso(segundos=30, al_correr=llenar)
    res = m.Ejecutor(cfg, docker).ejecutar("luis", "dd ...", 20, 1000)
    assert res["cuota_superada"] and not res["tiempo_agotado"] and docker.borrados == ["c1"]
    # carpeta ya llena: ni se crea el contenedor
    docker = DockerFalso()
    with pytest.raises(m.ErrorEspacio) as e:
        m.Ejecutor(cfg, docker).ejecutar("luis", "ls", 10, 0)
    assert e.value.estado == 413 and not docker.creados


def test_ejecutor_nunca_sigue_como_root(monkeypatch):
    """Si arranca como root baja a 1000:1000 aunque no pueda leer el socket, y si no puede
    cambiar de usuario se para (nunca atiende peticiones como root)."""
    m = _ejecutor()
    llamadas: list[tuple[str, object]] = []

    class OsFalso:
        name = "posix"

        @staticmethod
        def geteuid() -> int:
            return 0

        @staticmethod
        def stat(_ruta: str):
            raise FileNotFoundError("sin socket")

        @staticmethod
        def setgroups(g: list[int]) -> None:
            llamadas.append(("grupos", g))

        @staticmethod
        def setgid(g: int) -> None:
            llamadas.append(("gid", g))

        @staticmethod
        def setuid(u: int) -> None:
            llamadas.append(("uid", u))

    monkeypatch.setattr(m, "os", OsFalso)
    cfg = m.Config(secreto="s" * 32, datos_host="/srv/cidia/datos/generador-de-contenido")
    m.bajar_privilegios(cfg)
    assert llamadas == [("grupos", []), ("gid", 1000), ("uid", 1000)]

    def no_puede(_u: int) -> None:
        raise PermissionError("Operation not permitted")

    monkeypatch.setattr(OsFalso, "setuid", staticmethod(no_puede))
    with pytest.raises(SystemExit):
        m.bajar_privilegios(cfg)
