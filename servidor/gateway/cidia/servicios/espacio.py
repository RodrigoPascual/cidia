"""Espacio de trabajo del agente: la carpeta privada de cada persona en el servidor.

Cada usuario tiene `dir_datos/generador-de-contenido/<carpeta>/`, que se crea al primer uso.
Ahí deja el agente lo que genera (informes, tablas...) y ahí se ejecutan sus órdenes, en un
contenedor sin red que solo monta esa carpeta (servicio `espacio-trabajo`, ver
servidor/espacio-trabajo/README.md). Lo usan la API (`rutas/espacio.py`) y las herramientas
MCP (`mcp_servidor.py`), siempre con el actor de la petición: nadie elige la carpeta.

Seguridad de rutas: toda ruta que llega del cliente o del agente es relativa a la carpeta del
usuario. Se rechazan rutas absolutas, `..` y el carácter nulo; se resuelve la ruta real
(siguiendo enlaces) y se comprueba que sigue dentro. Pero una orden de la caja de arena puede
crear enlaces y cambiarlos EN CUALQUIER MOMENTO, también entre esa comprobación y el acceso
(carrera TOCTOU): cambiar un fichero por un enlace a /proc/self/environ o una carpeta por un
enlace a la de otra persona haría que el gateway leyera, escribiera, moviera o borrara fuera.
Por eso, en Linux, el acceso real se hace con descriptores (`_Carpeta`): se baja desde la raíz
del usuario nombre a nombre con O_NOFOLLOW y se opera sobre el último nombre relativo a su
carpeta (openat, mkdirat, renameat, unlinkat, rmtree con dir_fd). Un enlace en cualquier
tramo, aunque aparezca a mitad de la operación, la hace fallar. Las lecturas además usan
O_NONBLOCK y exigen un fichero normal (una FIFO dejaría colgado un hilo del servidor). Las
descargas tienen su propia URL firmada (/api/espacio/descarga) y se sirven desde el fichero ya
abierto. En Windows (solo desarrollo: allí no hay caja de arena) se trabaja con rutas.

Límites: cuota por usuario (CIDIA_ESPACIO_CUOTA_MB, 500 MB por defecto), tamaño por fichero
subido (CIDIA_ESPACIO_MAX_FICHERO_MB, 100 MB), texto escrito de una vez (5 MB) y lectura de
texto (512 KB para la interfaz; el agente pide menos).
"""

from __future__ import annotations

import errno
import logging
import mimetypes
import os
import re
import shutil
import stat
import threading
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import quote

import httpx
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from cidia import xapi
from cidia.config import ajustes
from cidia.ficheros import nombre_seguro
from cidia.modelos import Usuario
from cidia.seguridad import Actor, comprobar_firma, url_fichero

log = logging.getLogger("cidia.espacio")

MB = 1024 * 1024
CARPETA_RAIZ = "generador-de-contenido"
CUOTA = int(os.environ.get("CIDIA_ESPACIO_CUOTA_MB", "500")) * MB
MAX_FICHERO = int(os.environ.get("CIDIA_ESPACIO_MAX_FICHERO_MB", "100")) * MB
MAX_TEXTO = 5 * MB  # texto que se escribe de una vez
MAX_LECTURA = 512 * 1024  # texto que se devuelve para la vista previa
MAX_ELEMENTOS = 3000  # elementos como máximo en el árbol
MAX_PROFUNDIDAD = 12  # carpetas anidadas como máximo en una ruta
MAX_NOMBRE = 150  # caracteres de un nombre nuevo
MAX_ORDEN = 10_000  # caracteres de una orden
TIEMPO_MAX = 120  # segundos de una orden

# Solo falta la consola (el servicio espacio-trabajo): los ficheros siguen funcionando.
NO_DISPONIBLE = ("La consola para ejecutar órdenes no está disponible en este servidor. "
                 "Tus ficheros sí: puedes verlos, subirlos y descargarlos.")
_RELATIVA = "Ruta no válida: usa rutas relativas a tu carpeta (p. ej. informes/resumen.md)."
_TEMPORAL = ".cidia-"  # prefijo de los ficheros temporales del gateway (no se listan)

# Tipos de vista previa por extensión (la interfaz decide cómo mostrarlos).
_TEXTO = {
    ".txt", ".log", ".json", ".py", ".sh", ".xml", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".sql",
    ".js", ".ts", ".css", ".html", ".htm", ".svg", ".r", ".tex", ".ipynb", ".env", ".conf",
}
_MARKDOWN = {".md", ".markdown"}
_CSV = {".csv", ".tsv"}
# Imágenes que se pueden mostrar con <img>. SVG y HTML se ven como texto: abiertos en una
# pestaña podrían ejecutar código con el origen del servidor.
_IMAGEN = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_PDF = {".pdf"}

_NOMBRE_USUARIO = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_PROHIBIDOS = re.compile(r'[<>:"|?*\x00-\x1f\x7f]')

# Personas con una orden en marcha (una a la vez por persona).
_ocupados: set[int] = set()
_cerrojo = threading.Lock()

# Transporte HTTP del cliente del ejecutor. Las pruebas ponen aquí un httpx.MockTransport.
_transporte: httpx.BaseTransport | None = None

# Opciones de os.open (las que no existen en un sistema valen 0).
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORIO = getattr(os, "O_DIRECTORY", 0)
_NOBLOQUEA = getattr(os, "O_NONBLOCK", 0)
_BINARIO = getattr(os, "O_BINARY", 0)  # Windows: sin él, os.open traduce los saltos de línea

# ¿Se puede trabajar con descriptores? (Linux sí; Windows no). os.replace no figura en
# os.supports_dir_fd aunque admite src_dir_fd/dst_dir_fd igual que os.rename (renameat).
CON_DESCRIPTORES = (
    os.name == "posix" and bool(_NOFOLLOW and _DIRECTORIO)
    and {os.open, os.mkdir, os.rename, os.unlink, os.stat} <= os.supports_dir_fd
    and os.scandir in os.supports_fd and shutil.rmtree.avoids_symlink_attacks
)


# --------------------------------------------------------------------------- carpeta y rutas


def carpeta_de(usuario: Usuario) -> str:
    """Nombre de la carpeta de una persona: su usuario si es un nombre seguro ([a-z0-9._-],
    sin empezar por punto ni guion); si no, `_u<id>`. Los nombres de respaldo empiezan por
    «_» y un usuario válido nunca, así que no pueden coincidir."""
    nombre = (usuario.usuario or "").strip()
    if _NOMBRE_USUARIO.fullmatch(nombre):
        return nombre
    return f"_u{usuario.id}"


def _usuario(actor: Actor) -> Usuario:
    if actor.es_invitado or actor.usuario is None:
        raise HTTPException(401, "El espacio de trabajo necesita iniciar sesión.")
    return actor.usuario


@contextmanager
def _disco(no_existe: str = "No existe ese fichero o carpeta.") -> Iterator[None]:
    """Traduce los errores del sistema de ficheros a mensajes claros (nunca un 500 sin explicar)."""
    try:
        yield
    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(404, no_existe) from None
    except FileExistsError:
        raise HTTPException(409, "Ya existe un fichero o carpeta con ese nombre.") from None
    except IsADirectoryError:
        raise HTTPException(409, "Ya existe una carpeta con ese nombre.") from None
    except RecursionError:
        raise HTTPException(400, "Hay demasiadas carpetas anidadas para hacerlo desde aquí. "
                                 "Bórralas desde la consola (rm -rf).") from None
    except OSError as e:
        if e.errno in (errno.ELOOP, errno.ENOTDIR):
            raise HTTPException(400, "Ruta no válida: hay un enlace o un fichero donde debería haber una carpeta.") from None
        if e.errno == errno.ENAMETOOLONG:
            raise HTTPException(400, "El nombre es demasiado largo.") from None
        if e.errno == errno.EINVAL:
            raise HTTPException(400, "No se puede hacer eso con esa ruta.") from None
        if e.errno == errno.ENOTEMPTY:
            raise HTTPException(409, "Ya existe una carpeta con ese nombre y no está vacía.") from None
        if e.errno in (errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)):
            log.error("Sin espacio en el disco del espacio de trabajo: %s", e)
            raise HTTPException(507, "El disco del servidor está lleno. Avisa a la administración.") from None
        if e.errno in (errno.EACCES, errno.EPERM):
            log.error("Sin permiso en la carpeta del espacio de trabajo: %s", e)
            raise HTTPException(500, "El servidor no tiene permiso para usar la carpeta de trabajo. "
                                     "Avisa a la administración.") from None
        log.exception("Error de disco en el espacio de trabajo")
        raise HTTPException(500, "No se ha podido completar la operación en la carpeta de trabajo.") from None


def raiz(actor: Actor) -> Path:
    """Carpeta del usuario (resuelta). Se crea la primera vez."""
    base = (ajustes().dir_datos / CARPETA_RAIZ).resolve()
    r = base / carpeta_de(_usuario(actor))
    if r.is_symlink():  # nunca debería pasar: la crea el propio gateway
        raise HTTPException(500, "La carpeta del espacio de trabajo no es válida. Avisa a la administración.")
    with _disco():
        r.mkdir(parents=True, exist_ok=True)
    return r.resolve()


def _nombre_portable(p: str) -> None:
    """Un nombre que se va a crear tiene que poder descargarse en Windows. Lanza 400 si no."""
    if len(p) > MAX_NOMBRE or _PROHIBIDOS.search(p) or "\\" in p or p != p.strip() or p.endswith("."):
        raise HTTPException(400, f"El nombre «{p[:60]}» no es válido. Evita los caracteres < > : \" | ? * \\ "
                                 "y los puntos o espacios al final.")


def partes(ruta: str | None, existente: bool = False, nombres: bool = True) -> list[str]:
    """Valida una ruta relativa a la carpeta del usuario y la devuelve troceada (400 si no vale).

    Nunca se aceptan rutas absolutas, `..` ni el carácter nulo. Los nombres nuevos (escribir,
    crear una carpeta, destino de mover) además tienen que ser portables, porque se descargan en
    portátiles Windows: sin < > : " | ? * ni barra invertida, caracteres de control ni puntos o espacios al final
    (`nombres=False` deja esa comprobación para quien llama, ver `resolver`). Con
    `existente=True` (leer, descargar, mover o borrar algo que ya está) se aceptan en Linux, tal
    cual, los nombres que pudo crear una orden en la caja de arena (p. ej. «informe 12:30.pdf»);
    si no, la persona no podría ni verlos ni borrarlos desde la app.
    """
    laxa = existente and os.name == "posix"
    texto = ruta or ""
    if "\x00" in texto:
        raise HTTPException(400, "Ruta no válida.")
    if not laxa:
        texto = texto.strip().replace("\\", "/")
        if texto.startswith("~") or re.match(r"^[A-Za-z]:", texto):
            raise HTTPException(400, _RELATIVA)
    if texto.startswith("/"):
        raise HTTPException(400, _RELATIVA)
    trozos = [p for p in texto.split("/") if p not in ("", ".")]
    if len(trozos) > MAX_PROFUNDIDAD:
        raise HTTPException(400, "Ruta no válida: demasiadas carpetas anidadas.")
    for p in trozos:
        if p == "..":
            raise HTTPException(400, "Ruta no válida: no se puede salir de tu carpeta.")
        if not laxa and nombres:
            _nombre_portable(p)
    return trozos


def _dentro(r: Path, p: Path) -> bool:
    return p == r or r in p.parents


def _fuera() -> HTTPException:
    return HTTPException(400, "Ruta no válida: está fuera de tu carpeta.")


def _real(r: Path, trozos: Sequence[str]) -> Path:
    """Ruta real (enlaces resueltos) dentro de la carpeta `r`. Lanza 400 si sale de ella."""
    try:
        p = r.joinpath(*trozos).resolve()
    except (OSError, RuntimeError):  # bucle de enlaces (RuntimeError hasta Python 3.12)
        raise HTTPException(400, "Ruta no válida: hay un enlace que no lleva a ninguna parte.") from None
    if not _dentro(r, p):
        raise _fuera()
    return p


def resolver(r: Path, ruta: str | None, existente: bool = False) -> Path:
    """Ruta real dentro de la carpeta `r` (ver `partes`). Lanza 400 si no es segura.

    Para una ruta nueva, solo tienen que ser portables los nombres que se van a crear: en Linux,
    las carpetas que ya existen (quizá con un nombre que puso una orden) se aceptan tal cual,
    para poder guardar o renombrar dentro de ellas. Solo sirve para validar y dar mensajes
    claros: el acceso de verdad se hace con `_Carpeta`."""
    if existente:
        return _real(r, partes(ruta, existente=True))
    trozos = partes(ruta, nombres=False)
    actual = r
    for i, t in enumerate(trozos):
        actual = actual / t
        if os.name != "posix" or not os.path.lexists(actual):
            for nuevo in trozos[i:]:
                _nombre_portable(nuevo)
            break
    return _real(r, trozos)


def _trozos(r: Path, p: Path) -> tuple[str, ...]:
    return p.relative_to(r).parts if p != r else ()


def _lstat(p: Path) -> os.stat_result | None:
    try:
        return os.lstat(p)
    except FileNotFoundError:
        return None


# --------------------------------------------------------------------------- acceso al disco


def _bajar(fd: int, nombre: str, crear: bool) -> int:
    """Abre la subcarpeta `nombre` de la carpeta `fd` sin seguir enlaces (la crea si se pide)."""
    opciones = os.O_RDONLY | _DIRECTORIO | _NOFOLLOW | _CLOEXEC
    for intento in (1, 2):
        try:
            return os.open(nombre, opciones, dir_fd=fd)
        except FileNotFoundError:
            if not crear or intento == 2:
                raise HTTPException(404, "No existe esa carpeta.") from None
            with suppress(FileExistsError):
                os.mkdir(nombre, 0o775, dir_fd=fd)
        except OSError as e:
            if e.errno in (errno.ELOOP, errno.ENOTDIR):  # un enlace o un fichero
                raise HTTPException(400, f"Ruta no válida: «{nombre[:60]}» no es una carpeta de tu espacio.") from None
            raise
    raise AssertionError("inalcanzable")


class _Carpeta:
    """Una carpeta del espacio, abierta para operar con lo que contiene (ver la cabecera).

    En Linux guarda un descriptor obtenido bajando desde la raíz del usuario con O_NOFOLLOW, y
    todas las operaciones son relativas a él. En Windows guarda la ruta, ya comprobada.
    Uso: `with _Carpeta(r, ("informes", "marzo")) as c: c.estado("resumen.md")`.
    """

    def __init__(self, r: Path, trozos: Sequence[str] = (), crear: bool = False) -> None:
        self.raiz = r
        self.ruta = r.joinpath(*trozos)
        self.fd: int | None = None
        if not CON_DESCRIPTORES:
            if not _dentro(r, self.ruta.resolve()):
                raise _fuera()
            if crear:
                self.ruta.mkdir(parents=True, exist_ok=True)
            if self.ruta.is_symlink() or not _dentro(r, self.ruta.resolve()):
                raise _fuera()
            if not self.ruta.is_dir():
                if self.ruta.exists():
                    raise HTTPException(400, f"Ruta no válida: «{self.ruta.name[:60]}» no es una carpeta de tu espacio.")
                raise HTTPException(404, "No existe esa carpeta.")
            return
        fd = os.open(r, os.O_RDONLY | _DIRECTORIO | _CLOEXEC)
        try:
            for t in trozos:
                nuevo = _bajar(fd, t, crear)
                os.close(fd)
                fd = nuevo
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd

    def __enter__(self) -> _Carpeta:
        return self

    def __exit__(self, *_: Any) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _ruta(self, nombre: str) -> Path:  # solo sin descriptores
        return self.ruta / nombre

    def sub(self, nombre: str) -> _Carpeta:
        """Subcarpeta `nombre` (sin seguir enlaces)."""
        hija = _Carpeta.__new__(_Carpeta)
        hija.raiz, hija.ruta, hija.fd = self.raiz, self.ruta / nombre, None
        if self.fd is not None:
            hija.fd = _bajar(self.fd, nombre, False)
        elif hija.ruta.is_symlink() or not hija.ruta.is_dir():
            raise HTTPException(400, "No es una carpeta.")
        return hija

    def estado(self, nombre: str) -> os.stat_result | None:
        """Datos de `nombre` sin seguir enlaces (lstat); None si no existe."""
        try:
            if self.fd is not None:
                return os.stat(nombre, dir_fd=self.fd, follow_symlinks=False)
            return os.lstat(self._ruta(nombre))
        except FileNotFoundError:
            return None

    def entradas(self) -> list[os.DirEntry[str]]:
        with os.scandir(self.fd if self.fd is not None else self.ruta) as it:
            return list(it)

    def abrir(self, nombre: str, opciones: int, modo: int = 0o664) -> int:
        """os.open de `nombre` sin seguir enlaces (si es un enlace: OSError ELOOP)."""
        if self.fd is not None:
            return os.open(nombre, opciones | _NOFOLLOW | _CLOEXEC, modo, dir_fd=self.fd)
        p = self._ruta(nombre)
        if p.is_symlink():
            raise OSError(errno.ELOOP, "Es un enlace", str(p))
        return os.open(p, opciones | _BINARIO, modo)

    def crear(self, nombre: str) -> None:
        if self.fd is not None:
            os.mkdir(nombre, 0o775, dir_fd=self.fd)
        else:
            self._ruta(nombre).mkdir()

    def quitar(self, nombre: str, st: os.stat_result) -> None:
        """Borra `nombre`: un enlace (nunca lo enlazado), un fichero o una carpeta entera."""
        if stat.S_ISDIR(st.st_mode):
            if self.fd is not None:
                shutil.rmtree(nombre, dir_fd=self.fd)
            else:
                shutil.rmtree(self._ruta(nombre))
        elif self.fd is not None:
            os.unlink(nombre, dir_fd=self.fd)
        else:
            p = self._ruta(nombre)
            try:
                p.unlink()
            except (IsADirectoryError, PermissionError):  # enlace a carpeta en Windows
                os.rmdir(p)

    def renombrar(self, nombre: str, destino: _Carpeta, nuevo: str, sustituir: bool = False) -> None:
        mover = os.replace if sustituir else os.rename
        if self.fd is not None and destino.fd is not None:
            mover(nombre, nuevo, src_dir_fd=self.fd, dst_dir_fd=destino.fd)
        else:
            mover(self._ruta(nombre), destino._ruta(nuevo))

    def guardar(self, nombre: str, volcar: Callable[[BinaryIO], Any], sustituir: bool = True) -> None:
        """Escribe `nombre` de forma atómica: primero en un temporal oculto y luego lo renombra."""
        tmp = f"{_TEMPORAL}{uuid.uuid4().hex[:16]}.tmp"
        fd = self.abrir(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            with os.fdopen(fd, "wb") as f:
                volcar(f)
            self.renombrar(tmp, self, nombre, sustituir=sustituir)
        except BaseException:
            with suppress(OSError):
                if self.fd is not None:
                    os.unlink(tmp, dir_fd=self.fd)
                else:
                    self._ruta(tmp).unlink()
            raise


def _hijos(c: _Carpeta) -> list[tuple[str, os.stat_result]]:
    """(nombre, lstat) de lo que hay en `c`, carpetas primero. Omite los temporales del gateway
    y los nombres que no son UTF-8 válido (una orden puede crearlos; no se pueden enviar en JSON)."""
    filas = []
    for e in c.entradas():
        if e.name.startswith(_TEMPORAL):
            continue
        try:
            e.name.encode("utf-8")
            filas.append((e.name, e.stat(follow_symlinks=False)))
        except (UnicodeEncodeError, OSError):
            continue
    filas.sort(key=lambda x: (not stat.S_ISDIR(x[1].st_mode), x[0].lower()))
    return filas


def uso(r: Path) -> int:
    """Bytes ocupados por la carpeta (sin seguir enlaces). Solo cuenta, no abre nada: una carrera
    con una orden como mucho altera la cuenta. os.walk es iterativo (sin límite de anidamiento)
    y no mantiene un descriptor abierto por carpeta."""
    total = 0
    for actual, _dirs, ficheros in os.walk(r):
        for f in ficheros:
            with suppress(OSError):
                total += os.lstat(os.path.join(actual, f)).st_size
    return total


def _sin_espacio() -> HTTPException:
    return HTTPException(
        413, f"No queda espacio: tu carpeta ha llegado al límite de {CUOTA // MB} MB. Borra algo antes de seguir."
    )


def _comprobar_cuota(r: Path, nuevos: int, liberados: int = 0) -> None:
    if uso(r) - liberados + nuevos > CUOTA:
        raise _sin_espacio()


# --------------------------------------------------------------------------- descripción y descargas
#
# Los ficheros del espacio NO se sirven por /api/ficheros: ese servicio sigue los enlaces
# simbólicos y una orden en la caja de arena podría sustituir un fichero ya firmado por un
# enlace a otra carpeta. Se sirven por /api/espacio/descarga/<carpeta>/<ruta>, que abre el
# fichero sin seguir enlaces dentro de la carpeta de su dueño. La firma es la de
# seguridad.url_fichero, pero sobre «espacio:<carpeta>/<ruta>», así que no vale en /api/ficheros.

PREFIJO_FIRMA = "espacio:"


def url_descarga(carpeta: str, rel: str, descargar: bool = True) -> str:
    """URL firmada y caducable de un fichero del espacio (para <a>, <img> e <iframe>)."""
    firmada = f"{carpeta}/{rel}"
    consulta = (url_fichero(PREFIJO_FIRMA + firmada) or "").split("?", 1)[1]  # exp=...&firma=...
    url = f"/api/espacio/descarga/{quote(firmada)}?{consulta}"
    return f"{url}&descargar=1" if descargar else url


def vista(nombre: str) -> str | None:
    ext = Path(nombre).suffix.lower()
    if ext in _MARKDOWN:
        return "markdown"
    if ext in _CSV:
        return "csv"
    if ext in _IMAGEN:
        return "imagen"
    if ext in _PDF:
        return "pdf"
    if ext in _TEXTO or not ext:
        return "texto"
    return None


def _fecha(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _info(carpeta: str, rel: str, st: os.stat_result) -> dict[str, Any]:
    """Descripción de un elemento a partir de su lstat, con URL firmada si es un fichero.
    Tipos: carpeta, fichero, enlace o especial (FIFO, socket...: no se abren)."""
    modo = st.st_mode
    tipo = ("enlace" if stat.S_ISLNK(modo) else "carpeta" if stat.S_ISDIR(modo)
            else "fichero" if stat.S_ISREG(modo) else "especial")
    nombre = rel.rsplit("/", 1)[-1]
    datos: dict[str, Any] = {
        "nombre": nombre,
        "ruta": rel,
        "tipo": tipo,
        "tamano": st.st_size if tipo == "fichero" else 0,
        "modificado": _fecha(st.st_mtime),
    }
    if tipo == "fichero":
        v = vista(nombre)
        datos["vista"] = v
        datos["mime"] = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
        datos["url_descarga"] = url_descarga(carpeta, rel)
        # URL para mostrar en la página (solo imágenes y PDF: nada que pueda ejecutar código)
        datos["url"] = url_descarga(carpeta, rel, descargar=False) if v in ("imagen", "pdf") else None
    return datos


def abrir_descarga(rel: str, exp: int, firma: str) -> tuple[BinaryIO, str, os.stat_result]:
    """Fichero de una URL de descarga: firma válida, dentro de la carpeta de su dueño, abierto
    sin seguir enlaces y solo si es un fichero normal. Devuelve (fichero abierto, nombre, fstat)."""
    if not comprobar_firma(PREFIJO_FIRMA + rel, exp, firma):
        raise HTTPException(403, "Enlace caducado o no válido.")
    no_hay = HTTPException(404, "Fichero no encontrado.")
    carpeta, _, resto = rel.partition("/")
    if not (_NOMBRE_USUARIO.fullmatch(carpeta) or re.fullmatch(r"_u\d+", carpeta)) or not resto:
        raise no_hay
    r = (ajustes().dir_datos / CARPETA_RAIZ / carpeta).resolve()
    try:
        trozos = _trozos(r, resolver(r, resto, existente=True))
        if not trozos:
            raise no_hay
        with _Carpeta(r, trozos[:-1]) as c:
            fd = c.abrir(trozos[-1], os.O_RDONLY | _NOBLOQUEA)
    except (HTTPException, OSError):
        raise no_hay from None
    f = os.fdopen(fd, "rb")
    st = os.fstat(f.fileno())
    if not stat.S_ISREG(st.st_mode):
        f.close()
        raise no_hay
    return f, trozos[-1], st


def trozos_de(f: BinaryIO, total: int, bloque: int = 256 * 1024) -> Iterator[bytes]:
    """Contenido de un fichero abierto, en bloques y como mucho `total` bytes. Lo cierra al final."""
    try:
        quedan = total
        while quedan > 0 and (datos := f.read(min(bloque, quedan))):
            quedan -= len(datos)
            yield datos
    finally:
        f.close()


def disposicion(nombre: str) -> str:
    """Cabecera Content-Disposition de descarga (con el nombre codificado si no es ASCII)."""
    codificado = quote(nombre)
    if codificado != nombre:
        return f"attachment; filename*=utf-8''{codificado}"
    return f'attachment; filename="{nombre}"'


# --------------------------------------------------------------------------- operaciones


def _arbol(c: _Carpeta, carpeta: str, base: str, nivel: int, cuenta: list[int]) -> tuple[list[dict[str, Any]], int]:
    """Hijos de `c` (carpetas primero) y su tamaño total. No sigue enlaces."""
    elementos: list[dict[str, Any]] = []
    total = 0
    for nombre, st in _hijos(c):
        if cuenta[0] >= MAX_ELEMENTOS:
            break
        cuenta[0] += 1
        rel = f"{base}/{nombre}" if base else nombre
        item = _info(carpeta, rel, st)
        if item["tipo"] == "carpeta":
            hijos: list[dict[str, Any]] = []
            tam = 0
            if nivel < MAX_PROFUNDIDAD - 1:  # las rutas más profundas no se podrían usar
                try:
                    with c.sub(nombre) as hija:
                        hijos, tam = _arbol(hija, carpeta, rel, nivel + 1, cuenta)
                except (HTTPException, OSError):  # cambió mientras se leía
                    pass
            item["hijos"] = hijos
            item["tamano"] = tam
        total += item["tamano"]
        elementos.append(item)
    return elementos, total


def listar(actor: Actor) -> dict[str, Any]:
    """Árbol completo de la carpeta con tamaños, fechas y URL de descarga."""
    r = raiz(actor)
    cuenta = [0]
    with _disco(), _Carpeta(r) as c:
        elementos, _ = _arbol(c, r.name, "", 0, cuenta)
    a = ajustes()
    return {
        "carpeta": r.name,
        "elementos": elementos,
        "uso": uso(r),
        "cuota": CUOTA,
        "max_fichero": MAX_FICHERO,
        "incompleto": cuenta[0] >= MAX_ELEMENTOS,
        "ejecutor_configurado": bool(a.espacio_url and a.espacio_secreto),
    }


def listar_carpeta(actor: Actor, ruta: str | None = "") -> dict[str, Any]:
    """Contenido de una sola carpeta (sin bajar a las subcarpetas). Lo usa el agente."""
    r = raiz(actor)
    trozos = _trozos(r, resolver(r, ruta, existente=True))
    base = "/".join(trozos)
    elementos = []
    with _disco("No existe esa carpeta."), _Carpeta(r, trozos) as c:
        for nombre, st in _hijos(c)[:500]:
            item = _info(r.name, f"{base}/{nombre}" if base else nombre, st)
            elementos.append({k: item[k] for k in ("nombre", "ruta", "tipo", "tamano", "modificado")})
    return {"carpeta": base, "elementos": elementos, "uso": uso(r), "cuota": CUOTA}


def leer(actor: Actor, ruta: str, limite: int | None = None) -> dict[str, Any]:
    """Datos de un fichero y, si es texto, su contenido (hasta `limite` bytes, por defecto MAX_LECTURA)."""
    limite = limite or MAX_LECTURA
    r = raiz(actor)
    trozos = _trozos(r, resolver(r, ruta, existente=True))
    if not trozos:
        raise HTTPException(400, "Esa ruta es una carpeta, no un fichero.")
    no_es = HTTPException(400, "Ese elemento no es un fichero que se pueda abrir.")
    with _disco("No existe ese fichero."), _Carpeta(r, trozos[:-1]) as c:
        st = c.estado(trozos[-1])
        if st is None:
            raise HTTPException(404, "No existe ese fichero.")
        if stat.S_ISDIR(st.st_mode):
            raise HTTPException(400, "Esa ruta es una carpeta, no un fichero.")
        if not stat.S_ISREG(st.st_mode):
            raise no_es
        datos = _info(r.name, "/".join(trozos), st)
        datos.update(contenido=None, truncado=False, es_texto=False)
        if datos["vista"] in ("imagen", "pdf"):
            return datos
        # Sin seguir enlaces y sin bloquearse si entretanto lo cambian por una FIFO.
        with os.fdopen(c.abrir(trozos[-1], os.O_RDONLY | _NOBLOQUEA), "rb") as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                raise no_es
            bruto = f.read(limite + 1)
    if b"\x00" in bruto[:8192]:  # binario
        return datos
    datos["truncado"] = len(bruto) > limite
    datos["contenido"] = bruto[:limite].decode("utf-8", errors="replace")
    datos["es_texto"] = True
    return datos


def escribir(actor: Actor, ruta: str, contenido: str) -> dict[str, Any]:
    """Crea o sustituye un fichero de texto (UTF-8). Crea las carpetas que falten."""
    r = raiz(actor)
    p = resolver(r, ruta)
    trozos = _trozos(r, p)
    if not trozos:
        raise HTTPException(400, "Indica el nombre del fichero.")
    datos = (contenido or "").encode("utf-8")
    if len(datos) > MAX_TEXTO:
        raise HTTPException(413, f"El texto es demasiado largo (máximo {MAX_TEXTO // MB} MB).")
    with _disco():
        anterior = _lstat(p)
        if anterior is not None and stat.S_ISDIR(anterior.st_mode):
            raise HTTPException(409, "Ya existe una carpeta con ese nombre.")
        _comprobar_cuota(r, len(datos), anterior.st_size if anterior and stat.S_ISREG(anterior.st_mode) else 0)
        with _Carpeta(r, trozos[:-1], crear=True) as c:
            c.guardar(trozos[-1], lambda f: f.write(datos))
            st = c.estado(trozos[-1])
    if st is None:  # una orden lo borró en ese mismo instante
        raise HTTPException(409, "El fichero ha cambiado mientras se guardaba. Inténtalo de nuevo.")
    return _info(r.name, "/".join(trozos), st)


def _nombre_libre(c: _Carpeta, nombre: str) -> str:
    """`nombre` en `c`, o `nombre (2)`, `nombre (3)`... si ya existe (sin pasar de MAX_NOMBRE)."""
    base, ext = Path(nombre).stem, Path(nombre).suffix
    candidato, n = nombre, 2
    while c.estado(candidato) is not None:
        sufijo = f" ({n}){ext}"
        candidato = base[: MAX_NOMBRE - len(sufijo)].rstrip(" .") + sufijo
        n += 1
    return candidato


def subir(actor: Actor, carpeta: str | None, subida: UploadFile) -> dict[str, Any]:
    """Guarda un fichero subido en `carpeta` (sin sustituir: si existe, añade « (2)»)."""
    r = raiz(actor)
    trozos = _trozos(r, resolver(r, carpeta, existente=True))
    restante = CUOTA - uso(r)
    tam = 0

    def volcar(f: BinaryIO) -> None:
        nonlocal tam
        while bloque := subida.file.read(MB):
            tam += len(bloque)
            if tam > MAX_FICHERO:
                raise HTTPException(413, f"El fichero es demasiado grande (máximo {MAX_FICHERO // MB} MB).")
            if tam > restante:
                raise _sin_espacio()
            f.write(bloque)

    with _disco("No existe la carpeta de destino."), _Carpeta(r, trozos) as c:
        nombre = _nombre_libre(c, nombre_seguro(subida.filename or "fichero"))
        c.guardar(nombre, volcar, sustituir=False)
        st = c.estado(nombre)
    if st is None:
        raise HTTPException(409, "El fichero ha cambiado mientras se guardaba. Inténtalo de nuevo.")
    return _info(r.name, "/".join((*trozos, nombre)), st)


def borrar(actor: Actor, ruta: str) -> None:
    """Borra un fichero, un enlace (nunca lo enlazado) o una carpeta con todo su contenido."""
    r = raiz(actor)
    trozos = partes(ruta, existente=True)
    if not trozos:
        raise HTTPException(400, "No se puede borrar tu carpeta principal.")
    padre = _trozos(r, _real(r, trozos[:-1]))
    with _disco(), _Carpeta(r, padre) as c:
        st = c.estado(trozos[-1])
        if st is None:
            raise HTTPException(404, "No existe ese fichero o carpeta.")
        c.quitar(trozos[-1], st)


def mover(actor: Actor, origen: str, destino: str) -> dict[str, Any]:
    """Mueve o renombra un fichero, enlace o carpeta. No sustituye nada que ya exista."""
    r = raiz(actor)
    to = partes(origen, existente=True)
    if not to:
        raise HTTPException(400, "No se puede mover tu carpeta principal.")
    # El origen se toma tal cual dentro de su carpeta (resuelta): si es un enlace, se mueve el enlace.
    padre_o = _real(r, to[:-1])
    o = padre_o / to[-1]
    d = resolver(r, destino)
    td = _trozos(r, d)
    if not td:
        raise HTTPException(400, "Indica el nuevo nombre o la carpeta de destino.")
    with _disco("No existe lo que quieres mover."):
        st_o = _lstat(o)
        if st_o is None:
            raise HTTPException(404, "No existe lo que quieres mover.")
        if os.path.lexists(d):
            raise HTTPException(409, f"Ya existe «{d.name}» en el destino.")
        if stat.S_ISDIR(st_o.st_mode) and _dentro(o, d):
            raise HTTPException(400, "No se puede mover una carpeta dentro de sí misma.")
        with _Carpeta(r, _trozos(r, padre_o)) as co, _Carpeta(r, td[:-1], crear=True) as cd:
            if cd.estado(td[-1]) is not None:
                raise HTTPException(409, f"Ya existe «{td[-1]}» en el destino.")
            co.renombrar(to[-1], cd, td[-1])
            st = cd.estado(td[-1])
    if st is None:
        raise HTTPException(409, "Ha cambiado mientras se movía. Inténtalo de nuevo.")
    return _info(r.name, "/".join(td), st)


def crear_carpeta(actor: Actor, ruta: str) -> dict[str, Any]:
    r = raiz(actor)
    trozos = _trozos(r, resolver(r, ruta))
    if not trozos:
        raise HTTPException(400, "Indica el nombre de la carpeta.")
    with _disco(), _Carpeta(r, trozos[:-1], crear=True) as c:
        if c.estado(trozos[-1]) is not None:
            raise HTTPException(409, "Ya existe un fichero o carpeta con ese nombre.")
        c.crear(trozos[-1])
        st = c.estado(trozos[-1])
    if st is None:
        raise HTTPException(409, "La carpeta ha cambiado mientras se creaba. Inténtalo de nuevo.")
    return _info(r.name, "/".join(trozos), st)


# --------------------------------------------------------------------------- ejecutor


def _cliente(timeout: float) -> httpx.Client:
    return httpx.Client(timeout=timeout, transport=_transporte)


def _cabeceras() -> dict[str, str]:
    return {"X-Espacio-Secreto": ajustes().espacio_secreto}


def configurado() -> bool:
    a = ajustes()
    return bool(a.espacio_url and a.espacio_secreto)


def estado_ejecutor() -> dict[str, Any]:
    """¿Responde el servicio ejecutor? (para mostrar u ocultar la consola)."""
    if not configurado():
        return {"disponible": False, "mensaje": NO_DISPONIBLE}
    try:
        with _cliente(4.0) as c:
            res = c.get(f"{ajustes().espacio_url.rstrip('/')}/salud", headers=_cabeceras())
        ok = res.status_code == 200
    except httpx.HTTPError:
        ok = False
    return {"disponible": ok, "mensaje": None if ok else NO_DISPONIBLE, "tiempo_max": TIEMPO_MAX}


def ejecutar(actor: Actor, orden: str, tiempo_max: int = 60) -> dict[str, Any]:
    """Ejecuta una orden de bash en un contenedor efímero sin red con la carpeta del usuario
    montada en /trabajo. Devuelve código de salida, salida (recortada a 64 KB) y duración."""
    orden = (orden or "").strip()
    if not orden:
        raise HTTPException(400, "Escribe la orden que quieres ejecutar.")
    if len(orden) > MAX_ORDEN or "\x00" in orden:
        raise HTTPException(400, f"La orden es demasiado larga (máximo {MAX_ORDEN} caracteres).")
    tiempo_max = max(1, min(TIEMPO_MAX, int(tiempo_max or 60)))
    if not configurado():
        raise HTTPException(503, NO_DISPONIBLE)
    usuario = _usuario(actor)
    r = raiz(actor)
    restante = CUOTA - uso(r)
    if restante <= 0:
        raise _sin_espacio()
    with _cerrojo:
        if usuario.id in _ocupados:
            raise HTTPException(429, "Ya hay una orden en marcha en tu espacio. Espera a que termine.")
        _ocupados.add(usuario.id)
    try:
        with _cliente(tiempo_max + 30.0) as c:
            res = c.post(
                f"{ajustes().espacio_url.rstrip('/')}/ejecutar",
                headers=_cabeceras(),
                json={"usuario": r.name, "orden": orden, "tiempo_max": tiempo_max, "limite_bytes": restante},
            )
    except httpx.HTTPError as e:
        log.warning("El ejecutor del espacio de trabajo no responde: %s", e)
        raise HTTPException(503, NO_DISPONIBLE) from None
    finally:
        with _cerrojo:
            _ocupados.discard(usuario.id)
    if res.status_code in (401, 403):
        log.error("El ejecutor rechaza el secreto: revisa CIDIA_ESPACIO_SECRETO y ESPACIO_SECRETO")
        raise HTTPException(503, NO_DISPONIBLE)
    try:
        datos = res.json()
    except ValueError:
        datos = {}
    if not isinstance(datos, dict):
        datos = {}
    if res.status_code == 429:
        raise HTTPException(429, datos.get("detail") or "El espacio de trabajo está ocupado. Inténtalo en unos segundos.")
    if res.status_code >= 400:
        detalle = datos.get("detail") if isinstance(datos.get("detail"), str) else None
        raise HTTPException(502 if res.status_code >= 500 else 400, detalle or "No se ha podido ejecutar la orden.")
    codigo = datos.get("codigo")
    try:
        duracion = float(datos.get("duracion") or 0.0)
    except (TypeError, ValueError):
        duracion = 0.0
    return {
        "codigo": codigo if isinstance(codigo, int) and not isinstance(codigo, bool) else None,
        "salida": str(datos.get("salida") or ""),
        "recortada": bool(datos.get("recortada")),
        "duracion": duracion,
        "tiempo_agotado": bool(datos.get("tiempo_agotado")),
        "memoria_agotada": bool(datos.get("memoria_agotada")),
        "cuota_superada": bool(datos.get("cuota_superada")),
        "uso": uso(r),
        "cuota": CUOTA,
    }


# --------------------------------------------------------------------------- registro


def registrar(bd: Session, actor: Actor, verbo: str, ruta: str | None, via: str = "api",
              resultado: dict[str, Any] | None = None) -> None:
    """Sentencia xAPI de una acción en el espacio de trabajo. No hace commit."""
    nombre = (ruta or "").rsplit("/", 1)[-1] or "espacio de trabajo"
    xapi.registrar(bd, actor, verbo, "espacio", (ruta or "")[:100] or None, nombre[:300],
                   resultado=resultado, contexto={"via": via})
