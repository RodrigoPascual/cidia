"""Ejecutor del espacio de trabajo de CidIA.

Servicio HTTP mínimo (solo biblioteca estándar de Python) que escucha en la red interna de
Docker y sabe hacer UNA cosa: ejecutar una orden de bash de un usuario en un contenedor
efímero y aislado, con la carpeta de ese usuario montada en /trabajo, y devolver la salida.

    POST /ejecutar  {"usuario": "luis", "orden": "python3 informe.py", "tiempo_max": 60, "limite_bytes": 123}
         → {"codigo": 0, "salida": "...", "recortada": false, "duracion": 1.2, "tiempo_agotado": false,
            "memoria_agotada": false, "cuota_superada": false}
    GET  /salud     → 200 si Docker responde y la imagen de la caja de arena existe

Todas las peticiones exigen la cabecera X-Espacio-Secreto (ESPACIO_SECRETO). Cualquier otra
ruta u operación se rechaza. El cliente nunca elige imagen, montajes ni opciones del contenedor.

Por qué así: montar /var/run/docker.sock equivale a ser root en el servidor (que es compartido).
Por eso SOLO este servicio monta el socket (el gateway nunca), no publica puertos, y únicamente
crea, consulta y borra contenedores con la etiqueta cidia.espacio=1 y la imagen de la lista
blanca, siempre con esta configuración fija:

    --network none --read-only --tmpfs /tmp:size=64m,noexec,nosuid,nodev --cap-drop ALL
    --security-opt no-new-privileges --pids-limit 128 --memory 256m --memory-swap 256m
    --cpus 0.5 --user 1000:1000 --label cidia.espacio=1 --ulimit fsize=... --ulimit nofile=1024
    --mount type=bind,src=$ESPACIO_DATOS_HOST/<usuario>,dst=/trabajo

Mientras corre la orden se vigila el tiempo (máximo 120 s) y el espacio que ocupa la carpeta del
usuario (para que una orden no llene el disco); si se pasa, se mata el contenedor. Al terminar se
recoge la salida (recortada a 64 KB) y el código, y el contenedor se borra siempre.

Variables de entorno:
    ESPACIO_SECRETO       secreto compartido con el gateway (obligatorio, 16 caracteres o más)
    ESPACIO_DATOS_HOST    ruta EN EL HOST de generador-de-contenido/ (obligatoria, para el montaje)
    ESPACIO_DATOS_LOCAL   la misma carpeta vista dentro de este contenedor (/datos/generador-de-contenido)
    ESPACIO_IMAGEN        imagen de la caja de arena (cidia-sandbox:local): la única que se usa
    ESPACIO_PUERTO        8090
    ESPACIO_SIMULTANEAS   órdenes a la vez en todo el servidor (2)
    ESPACIO_MAX_MB        espacio máximo de una carpeta si el gateway no envía límite (500)
    ESPACIO_MAX_FICHEROS  ficheros como máximo en una carpeta (20000)
    ESPACIO_DOCKER_SOCKET /var/run/docker.sock
    ESPACIO_DOCKER_API    v1.41 (Docker 20.10 o posterior)
    ESPACIO_UID, ESPACIO_GID  usuario de la caja de arena y del propio ejecutor (1000:1000, el mismo
                          que el gateway: los ficheros de /trabajo tienen que ser de los dos)
    ESPACIO_RUNTIME       runtime de Docker para la caja de arena (vacío = el normal; «runsc» con gVisor)
"""

from __future__ import annotations

import hmac
import http.client
import json
import logging
import os
import re
import signal
import socket
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import quote, urlsplit

log = logging.getLogger("cidia.espacio")

MB = 1024 * 1024
TIEMPO_MAX = 120  # segundos
MAX_SALIDA = 64 * 1024  # bytes de salida que se devuelven
MAX_REGISTROS = 4 * MB  # bytes de registros que se leen de Docker como mucho
MAX_CUERPO = 64 * 1024  # cuerpo de una petición
MAX_ORDEN = 10_000  # caracteres de una orden
MAX_FICHERO = 100 * MB  # tamaño máximo de un fichero creado por una orden (ulimit fsize)
ETIQUETA = "cidia.espacio"
USUARIO = re.compile(r"^[a-z0-9._-]{1,64}$")


class ErrorEspacio(Exception):
    """Error con estado HTTP y mensaje en castellano para el gateway."""

    def __init__(self, estado: int, mensaje: str) -> None:
        super().__init__(mensaje)
        self.estado = estado
        self.mensaje = mensaje


# --------------------------------------------------------------------------- configuración


@dataclass
class Config:
    secreto: str
    datos_host: str
    datos_local: str = "/datos/generador-de-contenido"
    imagen: str = "cidia-sandbox:local"
    puerto: int = 8090
    simultaneas: int = 2
    max_bytes: int = 500 * MB
    max_ficheros: int = 20_000
    socket: str = "/var/run/docker.sock"
    api: str = "v1.41"
    uid: int = 1000
    gid: int = 1000
    runtime: str = ""

    @classmethod
    def desde_entorno(cls) -> Config:
        e = os.environ
        secreto = e.get("ESPACIO_SECRETO", "")
        if len(secreto) < 16:
            raise SystemExit("ESPACIO_SECRETO es obligatorio y debe tener al menos 16 caracteres.")
        host = e.get("ESPACIO_DATOS_HOST", "").rstrip("/")
        if not host.startswith("/") or "/../" in f"{host}/":
            raise SystemExit("ESPACIO_DATOS_HOST debe ser la ruta absoluta en el host de generador-de-contenido/.")
        api = e.get("ESPACIO_DOCKER_API", "v1.41")
        if not re.fullmatch(r"v1\.\d{2}", api):
            raise SystemExit("ESPACIO_DOCKER_API no es válida (ejemplo: v1.41).")
        return cls(
            secreto=secreto,
            datos_host=host,
            datos_local=e.get("ESPACIO_DATOS_LOCAL", "/datos/generador-de-contenido").rstrip("/"),
            imagen=e.get("ESPACIO_IMAGEN", "cidia-sandbox:local").strip(),
            puerto=int(e.get("ESPACIO_PUERTO", "8090")),
            simultaneas=max(1, int(e.get("ESPACIO_SIMULTANEAS", "2"))),
            max_bytes=int(e.get("ESPACIO_MAX_MB", "500")) * MB,
            max_ficheros=int(e.get("ESPACIO_MAX_FICHEROS", "20000")),
            socket=e.get("ESPACIO_DOCKER_SOCKET", "/var/run/docker.sock"),
            api=api,
            uid=int(e.get("ESPACIO_UID", "1000")),
            gid=int(e.get("ESPACIO_GID", "1000")),
            runtime=e.get("ESPACIO_RUNTIME", "").strip(),
        )


# --------------------------------------------------------------------------- cliente de Docker


class _ConexionUnix(http.client.HTTPConnection):
    """HTTP sobre el socket unix de Docker."""

    def __init__(self, ruta: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._ruta = ruta

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined]
        s.settimeout(self.timeout)
        s.connect(self._ruta)
        self.sock = s


class Docker:
    """Las pocas llamadas a la API de Docker que necesita el ejecutor (y ninguna más)."""

    def __init__(self, ruta_socket: str, api: str = "v1.41") -> None:
        self.ruta = ruta_socket
        self.api = api

    def _pedir(self, metodo: str, ruta: str, cuerpo: Any = None, timeout: float = 30.0,
               maximo: int = 2 * MB) -> tuple[int, bytes]:
        c = _ConexionUnix(self.ruta, timeout)
        try:
            datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
            cab = {"Content-Type": "application/json"} if datos is not None else {}
            c.request(metodo, f"/{self.api}{ruta}", body=datos, headers=cab)
            r = c.getresponse()
            return r.status, r.read(maximo)
        finally:
            c.close()

    @staticmethod
    def _mensaje(cuerpo: bytes) -> str:
        try:
            return str(json.loads(cuerpo).get("message", ""))[:300]
        except (ValueError, AttributeError):
            return cuerpo[:300].decode("utf-8", "replace")

    def ping(self) -> bool:
        try:
            return self._pedir("GET", "/_ping", timeout=5)[0] == 200
        except OSError:
            return False

    def existe_imagen(self, imagen: str) -> bool:
        try:
            return self._pedir("GET", f"/images/{quote(imagen, safe='')}/json", timeout=10)[0] == 200
        except OSError:
            return False

    def crear(self, nombre: str, config: dict[str, Any]) -> str:
        st, cuerpo = self._pedir("POST", f"/containers/create?name={quote(nombre)}", config)
        if st == 404:
            raise ErrorEspacio(503, "Falta la imagen de la caja de arena en el servidor. Avisa a la administración.")
        if st != 201:
            log.error("Docker no creó el contenedor (%s): %s", st, self._mensaje(cuerpo))
            raise ErrorEspacio(503, "No se ha podido preparar el contenedor de trabajo.")
        return str(json.loads(cuerpo)["Id"])

    def iniciar(self, cid: str) -> None:
        st, cuerpo = self._pedir("POST", f"/containers/{cid}/start")
        if st not in (204, 304):
            log.error("Docker no arrancó el contenedor (%s): %s", st, self._mensaje(cuerpo))
            raise ErrorEspacio(503, "No se ha podido arrancar el contenedor de trabajo.")

    def estado(self, cid: str) -> dict[str, Any]:
        st, cuerpo = self._pedir("GET", f"/containers/{cid}/json")
        if st != 200:
            return {"Running": False}
        return dict(json.loads(cuerpo).get("State") or {})

    def matar(self, cid: str) -> None:
        self._pedir("POST", f"/containers/{cid}/kill")

    def esperar(self, cid: str, segundos: float = 15.0) -> None:
        try:
            self._pedir("POST", f"/containers/{cid}/wait?condition=not-running", timeout=segundos)
        except OSError:
            pass

    def registros(self, cid: str) -> bytes:
        st, cuerpo = self._pedir("GET", f"/containers/{cid}/logs?stdout=true&stderr=true", maximo=MAX_REGISTROS)
        return cuerpo if st == 200 else b""

    def borrar(self, cid: str) -> None:
        self._pedir("DELETE", f"/containers/{cid}?force=true&v=true")

    def nuestros(self) -> list[str]:
        filtro = quote(json.dumps({"label": [f"{ETIQUETA}=1"]}))
        st, cuerpo = self._pedir("GET", f"/containers/json?all=true&filters={filtro}")
        return [c["Id"] for c in json.loads(cuerpo)] if st == 200 else []


# --------------------------------------------------------------------------- utilidades


def validar(datos: Any) -> tuple[str, str, int, int | None]:
    """Comprueba la petición. Devuelve (usuario, orden, tiempo_max, limite_bytes)."""
    if not isinstance(datos, dict):
        raise ErrorEspacio(400, "Petición no válida.")
    usuario, orden = datos.get("usuario"), datos.get("orden")
    tiempo, limite = datos.get("tiempo_max", 60), datos.get("limite_bytes")
    if not isinstance(usuario, str) or not USUARIO.fullmatch(usuario) or usuario in (".", ".."):
        raise ErrorEspacio(400, "Usuario no válido.")
    if not isinstance(orden, str) or not orden.strip() or len(orden) > MAX_ORDEN or "\x00" in orden:
        raise ErrorEspacio(400, "Orden no válida.")
    if isinstance(tiempo, bool) or not isinstance(tiempo, int) or not 1 <= tiempo <= TIEMPO_MAX:
        raise ErrorEspacio(400, f"El tiempo máximo debe estar entre 1 y {TIEMPO_MAX} segundos.")
    if limite is not None and (isinstance(limite, bool) or not isinstance(limite, int) or limite < 0):
        raise ErrorEspacio(400, "Límite de espacio no válido.")
    return usuario, orden, tiempo, limite


def config_contenedor(cfg: Config, usuario: str, orden: str, max_fichero: int = MAX_FICHERO) -> dict[str, Any]:
    """Configuración fija del contenedor: sin red, solo lectura, sin privilegios y con límites."""
    fsize = max(1, int(max_fichero))
    config: dict[str, Any] = {
        "Image": cfg.imagen,
        "Cmd": ["/bin/bash", "-c", orden],
        "User": f"{cfg.uid}:{cfg.gid}",
        "WorkingDir": "/trabajo",
        "Env": [
            "HOME=/tmp", "MPLCONFIGDIR=/tmp/.matplotlib", "MPLBACKEND=Agg", "PYTHONDONTWRITEBYTECODE=1",
            "PYTHONUNBUFFERED=1", "LANG=C.UTF-8", "LC_ALL=C.UTF-8",
        ],
        "Labels": {ETIQUETA: "1", f"{ETIQUETA}.usuario": usuario},
        "NetworkDisabled": True,
        "AttachStdin": False, "AttachStdout": False, "AttachStderr": False, "Tty": False, "OpenStdin": False,
        "StopTimeout": 1,
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "Privileged": False,
            "PidsLimit": 128,
            "Memory": 256 * MB,
            "MemorySwap": 256 * MB,
            "NanoCpus": 500_000_000,
            "Ulimits": [{"Name": "fsize", "Soft": fsize, "Hard": fsize},
                        {"Name": "nofile", "Soft": 1024, "Hard": 1024}],
            "Mounts": [{"Type": "bind", "Source": f"{cfg.datos_host}/{usuario}", "Target": "/trabajo",
                        "ReadOnly": False, "BindOptions": {"Propagation": "rprivate"}}],
            "LogConfig": {"Type": "json-file", "Config": {"max-size": "2m", "max-file": "1"}},
            "AutoRemove": False,
            "RestartPolicy": {"Name": "no"},
        },
    }
    if cfg.runtime:  # p. ej. gVisor (runsc), si el servidor lo tiene instalado
        config["HostConfig"]["Runtime"] = cfg.runtime
    return config


def separar_registros(bruto: bytes) -> str:
    """Une stdout y stderr del flujo multiplexado de Docker (cabeceras de 8 bytes) en orden."""
    if len(bruto) >= 8 and bruto[0] in (0, 1, 2) and bruto[1:4] == b"\x00\x00\x00":
        partes, i = [], 0
        while i + 8 <= len(bruto):
            tam = int.from_bytes(bruto[i + 4:i + 8], "big")
            partes.append(bruto[i + 8:i + 8 + tam])
            i += 8 + tam
        bruto = b"".join(partes)
    return bruto.decode("utf-8", errors="replace")


def recortar(texto: str, maximo: int = MAX_SALIDA) -> tuple[str, bool]:
    """Deja como mucho `maximo` bytes: el principio y, sobre todo, el final (donde están los errores)."""
    datos = texto.encode("utf-8")
    if len(datos) <= maximo:
        return texto, False
    cabeza = datos[: maximo // 4].decode("utf-8", "ignore")
    cola = datos[-(maximo - maximo // 4 - 64):].decode("utf-8", "ignore")
    return f"{cabeza}\n[… salida recortada …]\n{cola}", True


def medir(ruta: str, max_bytes: int, max_ficheros: int) -> tuple[int, int, bool]:
    """(bytes, ficheros, excedido) de una carpeta sin seguir enlaces. Para en cuanto se excede."""
    total = n = 0
    for actual, _dirs, ficheros in os.walk(ruta):
        for f in ficheros:
            n += 1
            try:
                total += os.lstat(os.path.join(actual, f)).st_size
            except OSError:
                pass
            if total > max_bytes or n > max_ficheros:
                return total, n, True
    return total, n, False


# --------------------------------------------------------------------------- ejecución


class Ejecutor:
    def __init__(self, cfg: Config, docker: Docker) -> None:
        self.cfg = cfg
        self.docker = docker
        self._plazas = threading.BoundedSemaphore(cfg.simultaneas)
        self._en_marcha: set[str] = set()
        self._cerrojo = threading.Lock()

    def ejecutar(self, usuario: str, orden: str, tiempo_max: int, limite_bytes: int | None) -> dict[str, Any]:
        local = os.path.join(self.cfg.datos_local, usuario)
        if os.path.islink(local) or not os.path.isdir(local):
            raise ErrorEspacio(404, "La carpeta de trabajo del usuario no existe.")
        limite = self.cfg.max_bytes if limite_bytes is None else min(limite_bytes, self.cfg.max_bytes)
        usado, _, excedido = medir(local, self.cfg.max_bytes, self.cfg.max_ficheros)
        if excedido or limite <= 0:
            raise ErrorEspacio(413, "La carpeta de trabajo está llena. Borra algo antes de seguir.")
        tope = usado + limite  # bytes que puede llegar a ocupar la carpeta durante la orden

        with self._cerrojo:
            if usuario in self._en_marcha:
                raise ErrorEspacio(429, "Ya hay una orden en marcha en tu espacio. Espera a que termine.")
            if not self._plazas.acquire(blocking=False):
                raise ErrorEspacio(429, "El espacio de trabajo está ocupado con otras órdenes. Inténtalo en unos segundos.")
            self._en_marcha.add(usuario)
        try:
            return self._en_contenedor(usuario, orden, tiempo_max, local, tope, min(limite, MAX_FICHERO))
        finally:
            with self._cerrojo:
                self._en_marcha.discard(usuario)
            self._plazas.release()

    def _en_contenedor(self, usuario: str, orden: str, tiempo_max: int, local: str, tope: int,
                       max_fichero: int) -> dict[str, Any]:
        nombre = f"cidia-espacio-{usuario}-{uuid.uuid4().hex[:10]}"
        cid = self.docker.crear(nombre, config_contenedor(self.cfg, usuario, orden, max_fichero))
        inicio = time.monotonic()
        tiempo_agotado = cuota_superada = False
        try:
            self.docker.iniciar(cid)
            ultima_medida = inicio
            while True:
                estado = self.docker.estado(cid)
                if not estado.get("Running"):
                    break
                ahora = time.monotonic()
                if ahora - inicio > tiempo_max:
                    tiempo_agotado = True
                    self.docker.matar(cid)
                    break
                if ahora - ultima_medida >= 1.5:
                    ultima_medida = ahora
                    if medir(local, tope, self.cfg.max_ficheros)[2]:
                        cuota_superada = True
                        self.docker.matar(cid)
                        break
                time.sleep(0.25)
            duracion = time.monotonic() - inicio
            self.docker.esperar(cid)
            estado = self.docker.estado(cid)
            salida, recortada = recortar(separar_registros(self.docker.registros(cid)))
        finally:
            try:
                self.docker.borrar(cid)
            except OSError as e:
                log.error("No se pudo borrar el contenedor %s: %s", cid[:12], e)
        codigo = estado.get("ExitCode")
        log.info("Orden de %s: código %s en %.1f s (%d caracteres)%s%s", usuario, codigo, duracion, len(orden),
                 " · tiempo agotado" if tiempo_agotado else "", " · cuota superada" if cuota_superada else "")
        return {
            "codigo": codigo if isinstance(codigo, int) else None,
            "salida": salida,
            "recortada": recortada,
            "duracion": round(duracion, 2),
            "tiempo_agotado": tiempo_agotado,
            "memoria_agotada": bool(estado.get("OOMKilled")),
            "cuota_superada": cuota_superada,
        }

    def limpiar_restos(self) -> int:
        """Al arrancar: borra contenedores nuestros que quedaron de una caída anterior."""
        n = 0
        try:
            for cid in self.docker.nuestros():
                self.docker.borrar(cid)
                n += 1
        except OSError as e:
            log.warning("No se pudieron revisar los contenedores anteriores: %s", e)
        return n


# --------------------------------------------------------------------------- servidor HTTP


class Manejador(BaseHTTPRequestHandler):
    server_version = "cidia-espacio"
    sys_version = ""
    timeout = 30  # segundos para recibir la petición (HTTP/1.0: una petición por conexión)

    @property
    def ejecutor(self) -> Ejecutor:
        return self.server.ejecutor  # type: ignore[attr-defined]

    def log_message(self, formato: str, *args: Any) -> None:  # sin cabeceras ni cuerpos en el registro
        log.debug("%s %s", self.address_string(), formato % args)

    def _responder(self, estado: int, datos: dict[str, Any]) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _autorizado(self) -> bool:
        recibido = self.headers.get("X-Espacio-Secreto", "")
        if hmac.compare_digest(recibido.encode(), self.ejecutor.cfg.secreto.encode()):
            return True
        self._responder(401, {"detail": "No autorizado."})
        return False

    def do_GET(self) -> None:  # noqa: N802
        if not self._autorizado():
            return
        if urlsplit(self.path).path != "/salud":
            self._responder(404, {"detail": "No existe."})
            return
        d = self.ejecutor.docker
        if not d.ping():
            self._responder(503, {"estado": "error", "detail": "Docker no responde."})
        elif not d.existe_imagen(self.ejecutor.cfg.imagen):
            self._responder(503, {"estado": "error", "detail": "Falta la imagen de la caja de arena."})
        else:
            self._responder(200, {"estado": "ok"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._autorizado():
            return
        if urlsplit(self.path).path != "/ejecutar":
            self._responder(404, {"detail": "No existe."})
            return
        try:
            largo = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            largo = -1
        if not 0 < largo <= MAX_CUERPO:
            self._responder(413 if largo > MAX_CUERPO else 400, {"detail": "Petición no válida."})
            return
        try:
            datos = json.loads(self.rfile.read(largo))
            res = self.ejecutor.ejecutar(*validar(datos))
        except ValueError:
            self._responder(400, {"detail": "Petición no válida."})
        except ErrorEspacio as e:
            self._responder(e.estado, {"detail": e.mensaje})
        except (OSError, http.client.HTTPException) as e:
            log.error("Docker no responde: %s", e)
            self._responder(503, {"detail": "El espacio de trabajo no está disponible en este servidor."})
        else:
            self._responder(200, res)


def crear_servidor(cfg: Config, docker: Docker, direccion: str = "0.0.0.0") -> ThreadingHTTPServer:
    servidor = ThreadingHTTPServer((direccion, cfg.puerto), Manejador)
    servidor.daemon_threads = True
    servidor.ejecutor = Ejecutor(cfg, docker)  # type: ignore[attr-defined]
    return servidor


def preparar_carpeta(cfg: Config) -> None:
    """Si Docker creó generador-de-contenido/ como root (no existía en el host), se la da a
    1000:1000 para que el gateway pueda crear dentro las carpetas de cada persona."""
    if os.name != "posix" or os.geteuid() != 0:
        return
    try:
        os.makedirs(cfg.datos_local, exist_ok=True)
        if os.stat(cfg.datos_local).st_uid == 0:
            os.chown(cfg.datos_local, cfg.uid, cfg.gid)
    except OSError as e:
        log.warning("No se pudo preparar %s: %s", cfg.datos_local, e)


def bajar_privilegios(cfg: Config) -> None:
    """Si arranca como root: pasa a 1000:1000 conservando el grupo del socket de Docker.

    Nunca sigue como root: si no puede leer el socket, baja igualmente (sin ese grupo, /salud
    dirá que Docker no responde) y si no puede cambiar de usuario, el proceso termina."""
    if os.name != "posix" or os.geteuid() != 0:
        return
    try:
        grupos = [os.stat(cfg.socket).st_gid]
    except OSError as e:
        log.warning("No se puede leer el socket de Docker (%s): se sigue sin su grupo", e)
        grupos = []
    try:
        os.setgroups(grupos)
        os.setgid(cfg.gid)
        os.setuid(cfg.uid)
    except OSError as e:
        raise SystemExit(f"No se han podido reducir los privilegios a {cfg.uid}:{cfg.gid}: {e}") from None
    log.info("Privilegios reducidos a %s:%s (grupos %s)", cfg.uid, cfg.gid, grupos)


def principal() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = Config.desde_entorno()
    docker = Docker(cfg.socket, cfg.api)
    preparar_carpeta(cfg)
    bajar_privilegios(cfg)
    servidor = crear_servidor(cfg, docker)
    restos = servidor.ejecutor.limpiar_restos()  # type: ignore[attr-defined]
    if restos:
        log.info("Borrados %d contenedores de trabajo que quedaron de antes", restos)
    if not docker.ping():
        log.warning("Docker no responde en %s", cfg.socket)
    elif not docker.existe_imagen(cfg.imagen):
        log.warning("Falta la imagen %s: constrúyela con servidor/espacio-trabajo/README.md", cfg.imagen)

    def parar(*_: Any) -> None:
        threading.Thread(target=servidor.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, parar)
    signal.signal(signal.SIGINT, parar)
    log.info("Ejecutor del espacio de trabajo escuchando en el puerto %s (imagen %s)", cfg.puerto, cfg.imagen)
    servidor.serve_forever()
    servidor.server_close()


if __name__ == "__main__":
    try:
        principal()
    except SystemExit as e:
        if e.code and not isinstance(e.code, int):
            print(f"Error de configuración: {e.code}", file=sys.stderr)
            sys.exit(2)
        raise
