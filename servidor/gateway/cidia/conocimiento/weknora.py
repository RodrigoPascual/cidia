"""Motor de conocimiento WeKnora (perfil opcional), siempre detrás del gateway.

Organización en WeKnora (docs/arquitectura.md §4 y docs/investigacion/03_weknora_integracion.md):

* Una base de conocimiento por departamento (id en `Departamento.weknora_kb_id`) y una base
  «Público» (id en `Empresa.config['weknora_kb_publico']`).
* Cada documento lleva la etiqueta de su nivel mínimo (`n1`…`n4`) y, si es material de
  formación, también `formacion`. Los públicos van a la base «Público» con la etiqueta
  `publico`. Los que no tienen departamento ni son públicos van a «Público» sin esa etiqueta:
  solo los encuentra la administración, que busca sin etiquetas.
* `buscar()` lanza una búsqueda por cada elemento del alcance (base + etiquetas permitidas),
  fusiona las listas con RRF y vuelve a filtrar cada resultado contra la base de datos con
  `permisos.puede_ver` (defensa en profundidad: un error de etiquetado no abre nada).

Los fragmentos que genera WeKnora se copian, sin vector, en la tabla `fragmentos`: así la
consola de documentos los enseña igual que con el motor propio y se conservan los metadatos
de cada parte (página, paso de una instrucción...). Las claves internas llevan el prefijo `wk_`.

La API key solo la tiene el gateway (cabecera X-API-Key). Sin WeKnora disponible, cada
operación falla con un `ErrorWeKnora` cuyo mensaje se puede mostrar tal cual.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cidia.config import ajustes
from cidia.conocimiento.base import Encontrado, MotorConocimiento, fusion_rrf
from cidia.conocimiento.extraccion import extraer
from cidia.conocimiento.pgvector import metadatos_documento
from cidia.ia import llm
from cidia.modelos import Departamento, Documento, Empresa, Fragmento, Nivel
from cidia.permisos import Alcance, puede_ver

log = logging.getLogger("cidia.weknora")

MAX_POR_DOCUMENTO = 3
MAX_MANUAL = 200_000  # caracteres que admite /knowledge/manual; más largo se sube como fichero .md
MAX_FRAGMENTOS = 5000  # fragmentos que se copian como mucho por documento
ETIQUETA_FORMACION = "formacion"
ETIQUETA_PUBLICO = "publico"
CLAVE_KB_PUBLICO = "weknora_kb_publico"
CLAVE_MODELO_EMB = "weknora_modelo_embeddings"
PREFIJO_META = "wk_"
# Extensiones que WeKnora v0.8.2 admite al subir un fichero (supportedImportFileExtensions en
# internal/application/service/knowledge_util.go). El resto se extrae en local y se sube como texto.
EXT_WEKNORA = {"pdf", "txt", "docx", "doc", "md", "markdown", "csv", "xlsx", "xls", "pptx", "ppt", "json",
               "png", "jpg", "jpeg", "gif", "mp3", "wav", "m4a", "flac", "ogg"}
COLORES = {"publico": "#1f8a70", "formacion": "#2f6fbf", "n1": "#8a93a0", "n2": "#d97a00", "n3": "#c8442f", "n4": "#1f2328"}


class ErrorWeKnora(RuntimeError):
    """Fallo al hablar con WeKnora, con un mensaje pensado para mostrarse a quien administra."""


def etiqueta_nivel(n: int) -> str:
    return f"n{max(1, int(n))}"


@dataclass
class Ambito:
    """Una búsqueda en WeKnora: una base y, si procede, las etiquetas permitidas en ella."""

    base: str
    etiquetas: list[str] | None
    descripcion: str


# --------------------------------------------------------------------------- cliente HTTP


def _json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except ValueError:
        return {}


def _mensaje(datos: Any) -> str:
    """Saca el mensaje de error de las dos formas que usa WeKnora."""
    if isinstance(datos, dict):
        err = datos.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("details") or err.get("code") or "sin detalle")
        if err:
            return str(err)
        if datos.get("message"):
            return str(datos["message"])
    return "sin detalle"


class ClienteWeKnora:
    """Cliente síncrono de la API REST de WeKnora (base .../api/v1)."""

    def __init__(self, url: str, api_key: str, transporte: httpx.BaseTransport | None = None,
                 timeout: float = 60.0) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key or ""
        self.http = httpx.Client(base_url=self.url, timeout=timeout, transport=transporte,
                                 headers={"X-API-Key": self.api_key, "Accept-Language": "es-ES"})

    def comprobar_clave(self) -> None:
        if not self.api_key:
            raise ErrorWeKnora("Falta la API key de WeKnora (CIDIA_WEKNORA_API_KEY). "
                               "Genérala con servidor/weknora/inicializar.py y reinicia el gateway.")

    def pedir(self, metodo: str, ruta: str, *, aceptar: tuple[int, ...] = (), **kw: Any) -> tuple[int, Any]:
        """Hace una petición y devuelve (estado, json). Los estados de `aceptar` no se tratan como error."""
        self.comprobar_clave()
        try:
            r = self.http.request(metodo, ruta, **kw)
        except httpx.TimeoutException as e:
            raise ErrorWeKnora(f"WeKnora no ha respondido a tiempo ({self.url}).") from e
        except httpx.HTTPError as e:
            raise ErrorWeKnora(f"No se puede conectar con WeKnora en {self.url}. "
                               "Comprueba que el servicio está levantado (perfil weknora del despliegue).") from e
        datos = _json(r)
        if r.status_code in aceptar:
            return r.status_code, datos
        if r.status_code == 401:
            raise ErrorWeKnora("WeKnora ha rechazado la API key del gateway. "
                               "Vuelve a generarla con servidor/weknora/inicializar.py.")
        if r.status_code == 403:
            raise ErrorWeKnora(f"La API key del gateway no tiene permiso en WeKnora para esta operación ({_mensaje(datos)}).")
        if r.status_code >= 400:
            raise ErrorWeKnora(f"WeKnora ha devuelto un error {r.status_code}: {_mensaje(datos)}")
        return r.status_code, datos

    def raiz(self) -> str:
        """URL del servicio sin el prefijo /api/vN (allí está /health)."""
        return re.sub(r"/api/v\d+$", "", self.url)


# --------------------------------------------------------------------------- utilidades


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[#*_>`|]", " ", texto or "")).strip().lower()


def _meta_de_parte(texto: str, partes: list[tuple[str, dict[str, Any]]] | None) -> dict[str, Any]:
    """Metadatos de la parte original (página, paso...) en la que empieza un fragmento de WeKnora."""
    if not partes:
        return {}
    contenido = _normalizar(texto)
    for largo in (60, 25):
        sonda = contenido[:largo]
        if len(sonda) < 12:
            continue
        for parte, meta in partes:
            if meta and sonda in _normalizar(parte):
                return dict(meta)
    return {}


def _coseno(a: list[float], b: list[float]) -> float | None:
    if not a or not b or len(a) != len(b):
        return None
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb:
        return None
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)


def _empresa(bd: Session) -> Empresa:
    e = bd.scalar(select(Empresa).order_by(Empresa.id))
    if e is None:
        e = Empresa(nombre="Mi empresa", config={}, config_iluo={})
        bd.add(e)
        bd.flush()
    return e


def _guardar_config(bd: Session, clave: str, valor: Any) -> None:
    e = _empresa(bd)
    e.config = {**(e.config or {}), clave: valor}  # se reasigna para que SQLAlchemy vea el cambio
    bd.flush()


# --------------------------------------------------------------------------- motor


class MotorWeKnora(MotorConocimiento):
    nombre = "weknora"

    def __init__(self, url: str | None = None, api_key: str | None = None,
                 transporte: httpx.BaseTransport | None = None, espera_max: float = 900.0,
                 intervalo: float = 2.0) -> None:
        a = ajustes()
        self.cliente = ClienteWeKnora(url or a.weknora_url, a.weknora_api_key if api_key is None else api_key,
                                      transporte)
        self.espera_max = espera_max  # segundos que se espera a que WeKnora procese un documento
        self.intervalo = intervalo
        self._cerrojo = threading.RLock()
        self._bases: dict[Any, str] = {}  # departamento_id | "publico" -> id de base
        self._etiquetas: dict[str, dict[str, str]] = {}  # base -> {nombre: id}
        self._refresco: dict[str, float] = {}  # base -> momento de la última lectura de etiquetas
        self._modelo_emb: str | None = None

    # ------------------------------------------------------------------ bases y etiquetas

    def _modelo_embeddings(self, bd: Session) -> str:
        """Id del modelo de embeddings en WeKnora (el configurado en CidIA si está dado de alta)."""
        if self._modelo_emb:
            return self._modelo_emb
        guardado = (_empresa(bd).config or {}).get(CLAVE_MODELO_EMB)
        if guardado:
            self._modelo_emb = str(guardado)
            return self._modelo_emb
        _, datos = self.cliente.pedir("GET", "/models")
        modelos = [m for m in (datos.get("data") or []) if m.get("type") == "Embedding"]
        if not modelos:
            raise ErrorWeKnora("WeKnora no tiene ningún modelo de embeddings dado de alta. "
                               "Ejecuta servidor/weknora/inicializar.py.")
        elegido = next((m for m in modelos if m.get("name") == ajustes().llm_modelo_embeddings), modelos[0])
        self._modelo_emb = str(elegido["id"])
        _guardar_config(bd, CLAVE_MODELO_EMB, self._modelo_emb)
        return self._modelo_emb

    def _crear_base(self, bd: Session, nombre: str, descripcion: str) -> str:
        cuerpo = {
            "name": nombre,
            "description": descripcion,
            "type": "document",
            "embedding_model_id": self._modelo_embeddings(bd),
            # Mismo tamaño de fragmento que el motor propio (caracteres).
            "chunking_config": {"chunk_size": 900, "chunk_overlap": 150, "separators": ["\n\n", "\n", ". "]},
            "indexing_strategy": {"vector_enabled": True, "keyword_enabled": True,
                                  "wiki_enabled": False, "graph_enabled": False},
            "vlm_config": {"enabled": False},
            "asr_config": {"enabled": False},
        }
        _, datos = self.cliente.pedir("POST", "/knowledge-bases", json=cuerpo)
        kb = (datos.get("data") or {}).get("id")
        if not kb:
            raise ErrorWeKnora(f"WeKnora no ha devuelto el id de la base «{nombre}».")
        log.info("Creada en WeKnora la base «%s» (%s)", nombre, kb)
        return str(kb)

    def base_departamento(self, bd: Session, dep: Departamento) -> str:
        """Id de la base del departamento; la crea si aún no existe."""
        with self._cerrojo:
            # Manda la BD (inicializar.py puede haberla cambiado); la caché cubre la base recién
            # creada por otro hilo cuya transacción aún no se ha confirmado.
            kb = dep.weknora_kb_id or self._bases.get(dep.id)
            if not kb:
                kb = self._crear_base(bd, dep.nombre, f"Conocimiento del departamento {dep.nombre} (CidIA).")
            if dep.weknora_kb_id != kb:
                dep.weknora_kb_id = kb
                bd.flush()
            self._bases[dep.id] = kb
            return kb

    def base_publica(self, bd: Session, crear: bool = True) -> str | None:
        """Id de la base «Público» (la crea si hace falta y `crear`)."""
        with self._cerrojo:
            guardada = (_empresa(bd).config or {}).get(CLAVE_KB_PUBLICO)
            kb = guardada or self._bases.get("publico")  # manda la BD, como en base_departamento
            if not kb and crear:
                kb = self._crear_base(bd, "Público", "Documentos públicos y generales de la empresa (CidIA).")
            if kb and kb != guardada and crear:
                _guardar_config(bd, CLAVE_KB_PUBLICO, kb)
            if kb:
                self._bases["publico"] = str(kb)
            return str(kb) if kb else None

    def _leer_etiquetas(self, kb: str) -> dict[str, str]:
        _, datos = self.cliente.pedir("GET", f"/knowledge-bases/{kb}/tags", params={"page": 1, "page_size": 100})
        pagina = datos.get("data") or {}
        lista = pagina.get("data") if isinstance(pagina, dict) else pagina
        etiquetas = {str(t["name"]): str(t["id"]) for t in (lista or []) if t.get("name") and t.get("id")}
        self._etiquetas[kb] = etiquetas
        self._refresco[kb] = time.monotonic()
        return etiquetas

    def etiqueta(self, kb: str, nombre: str, crear: bool = True) -> str | None:
        """Id de la etiqueta `nombre` en la base `kb` (la crea si falta y `crear`)."""
        with self._cerrojo:
            conocidas = self._etiquetas.get(kb)
            if conocidas is None or (nombre not in conocidas and
                                     (crear or time.monotonic() - self._refresco.get(kb, 0) > 60)):
                conocidas = self._leer_etiquetas(kb)
            if nombre in conocidas:
                return conocidas[nombre]
            if not crear:
                return None
            orden = int(nombre[1:]) if re.fullmatch(r"n\d+", nombre) else (90 if nombre == ETIQUETA_FORMACION else 99)
            estado, datos = self.cliente.pedir(
                "POST", f"/knowledge-bases/{kb}/tags", aceptar=(409,),
                json={"name": nombre, "color": COLORES.get(nombre, "#5b6573"), "sort_order": orden},
            )
            if estado == 409:  # otro proceso la acaba de crear
                return self._leer_etiquetas(kb).get(nombre)
            tid = str((datos.get("data") or {}).get("id") or "")
            if not tid:
                raise ErrorWeKnora(f"WeKnora no ha devuelto el id de la etiqueta «{nombre}».")
            conocidas[nombre] = tid
            return tid

    def destino(self, bd: Session, doc: Documento) -> tuple[str, list[str]]:
        """Base y nombres de etiqueta que le corresponden a un documento según sus permisos."""
        if doc.es_publico:
            return self.base_publica(bd) or "", [ETIQUETA_PUBLICO]
        nombres = [etiqueta_nivel(doc.nivel_minimo or 1)]
        if doc.es_formacion:
            nombres.append(ETIQUETA_FORMACION)
        dep = bd.get(Departamento, doc.departamento_id) if doc.departamento_id else None
        if dep is None:  # sin departamento ni público: solo lo verá la administración
            return self.base_publica(bd) or "", nombres
        return self.base_departamento(bd, dep), nombres

    def preparar_bases(self, bd: Session, modelo_embeddings_id: str | None = None) -> dict[str, Any]:
        """Crea la base «Público», una por departamento y sus etiquetas (lo usa inicializar.py)."""
        if modelo_embeddings_id:
            self._modelo_emb = modelo_embeddings_id
            _guardar_config(bd, CLAVE_MODELO_EMB, modelo_embeddings_id)
        niveles = [n for (n,) in bd.execute(select(Nivel.orden).order_by(Nivel.orden)).all()] or [1, 2, 3, 4]
        publico = self.base_publica(bd)
        assert publico
        for nombre in [ETIQUETA_PUBLICO] + [etiqueta_nivel(n) for n in niveles]:
            self.etiqueta(publico, nombre)
        salida: dict[str, Any] = {"publico": publico, "departamentos": {}}
        for dep in bd.scalars(select(Departamento).order_by(Departamento.nombre)).all():
            kb = self.base_departamento(bd, dep)
            for nombre in [etiqueta_nivel(n) for n in niveles] + [ETIQUETA_FORMACION]:
                self.etiqueta(kb, nombre)
            salida["departamentos"][dep.nombre] = kb
        return salida

    # ------------------------------------------------------------------ indexado

    def indexar(
        self,
        bd: Session,
        doc: Documento,
        texto: str | None = None,
        partes: list[tuple[str, dict[str, Any]]] | None = None,
    ) -> int:
        kb, nombres = self.destino(bd, doc)
        ids_etiquetas = [t for t in (self.etiqueta(kb, n) for n in nombres) if t]
        if doc.motor_id:  # reindexado: fuera la versión anterior
            self._borrar_conocimiento(doc.motor_id)
            doc.motor_id = None
        if partes is None and texto is None and not doc.ruta_fichero:
            texto = doc.contenido_texto or ""
        ruta = ajustes().dir_datos / (doc.ruta_fichero or "")
        if partes is None and texto is None and ruta.suffix.lower().lstrip(".") not in EXT_WEKNORA:
            # Formato que WeKnora no acepta (p. ej. .log): se extrae el texto aquí y se sube como texto.
            if not ruta.is_file():
                raise ErrorWeKnora("No se encuentra en el servidor el fichero original del documento.")
            partes = extraer(ruta)
        locales: list[tuple[str, dict[str, Any]]] | None
        if partes is not None or texto is not None:
            locales = partes if partes is not None else [(texto or "", {})]
            contenido = "\n\n".join(t.strip() for t, _ in locales if t and t.strip())
            if not contenido:
                bd.execute(delete(Fragmento).where(Fragmento.documento_id == doc.id))
                return 0
            conocimiento = self._subir_texto(kb, doc, contenido, ids_etiquetas)
        else:
            if not ruta.is_file():
                raise ErrorWeKnora("No se encuentra en el servidor el fichero original del documento.")
            conocimiento = self._subir_fichero(bd, kb, doc, ruta, ids_etiquetas)
            locales = self._partes_locales(doc, ruta)
        kid = str(conocimiento.get("id") or "")
        if not kid:
            raise ErrorWeKnora("WeKnora no ha devuelto el id del conocimiento creado.")
        doc.motor_id = kid
        bd.flush()  # aunque falle la espera, queda anotado para poder borrarlo después
        self._esperar(kid)
        return self._copiar_fragmentos(bd, doc, kid, locales)

    def _subir_texto(self, kb: str, doc: Documento, contenido: str, etiquetas: list[str]) -> dict[str, Any]:
        if len(contenido) <= MAX_MANUAL:
            # status «publish»: un borrador (valor por defecto) no se indexa.
            _, datos = self.cliente.pedir("POST", f"/knowledge-bases/{kb}/knowledge/manual", json={
                "title": doc.titulo, "content": contenido, "status": "publish", "tag_ids": etiquetas, "channel": "api",
            })
            return datos.get("data") or {}
        _, datos = self.cliente.pedir(
            "POST", f"/knowledge-bases/{kb}/knowledge/file",
            files={"file": (f"documento-{doc.id}.md", contenido.encode("utf-8"), "text/markdown")},
            data=self._campos_subida(doc, etiquetas, f"{doc.titulo}.md"),
        )
        return datos.get("data") or {}

    def _campos_subida(self, doc: Documento, etiquetas: list[str], nombre: str) -> dict[str, str]:
        return {
            "fileName": nombre,
            "tag_ids": ",".join(etiquetas),
            "metadata": json.dumps({"cidia_documento_id": str(doc.id)}),
            "channel": "api",
        }

    def _subir_fichero(self, bd: Session, kb: str, doc: Documento, ruta: Path, etiquetas: list[str]) -> dict[str, Any]:
        nombre = doc.nombre_fichero or ruta.name
        with ruta.open("rb") as f:
            estado, datos = self.cliente.pedir(
                "POST", f"/knowledge-bases/{kb}/knowledge/file", aceptar=(409,),
                files={"file": (nombre, f, doc.mime or "application/octet-stream")},
                data=self._campos_subida(doc, etiquetas, nombre),
            )
        conocimiento = datos.get("data") or {}
        if estado != 409:
            return conocimiento
        # El mismo fichero ya estaba en esa base: si no lo usa otro documento, se adopta.
        existente = str(conocimiento.get("id") or "")
        otro = bd.scalar(select(Documento).where(Documento.motor_id == existente, Documento.id != doc.id)) \
            if existente else None
        if otro is not None:
            raise ErrorWeKnora(f"Este mismo fichero ya está indexado como «{otro.titulo}». Borra uno de los dos.")
        if not existente:
            raise ErrorWeKnora("WeKnora dice que el fichero está repetido pero no indica cuál es.")
        self.cliente.pedir("PUT", "/knowledge/tags", json={"updates": {existente: etiquetas}, "kb_id": kb})
        return conocimiento

    def _partes_locales(self, doc: Documento, ruta: Path) -> list[tuple[str, dict[str, Any]]] | None:
        """Texto por página, hoja o diapositiva (solo para recuperar esos metadatos)."""
        if doc.tipo not in ("pdf", "office"):
            return None
        try:
            return extraer(ruta)
        except Exception:  # noqa: BLE001
            log.warning("No se ha podido leer en local %s para sus metadatos", ruta.name)
            return None

    def _esperar(self, kid: str) -> dict[str, Any]:
        """Espera a que WeKnora termine de trocear e indexar el conocimiento."""
        limite = time.monotonic() + self.espera_max
        while True:
            _, datos = self.cliente.pedir("GET", f"/knowledge/{kid}")
            k = datos.get("data") or {}
            estado = k.get("parse_status")
            # «finalizing»: ya se puede buscar por vector; solo faltan resúmenes o preguntas generadas.
            if estado in ("completed", "finalizing"):
                return k
            if estado == "failed":
                raise ErrorWeKnora("WeKnora no ha podido procesar el documento: "
                                   f"{k.get('error_message') or 'sin detalle'}")
            if estado in ("cancelled", "deleting"):
                raise ErrorWeKnora("WeKnora ha cancelado el procesado del documento.")
            if time.monotonic() >= limite:
                raise ErrorWeKnora(f"WeKnora sigue procesando el documento tras {int(self.espera_max)} s. "
                                   "Vuelve a indexarlo más tarde.")
            time.sleep(self.intervalo)

    def _copiar_fragmentos(self, bd: Session, doc: Documento, kid: str,
                           partes: list[tuple[str, dict[str, Any]]] | None) -> int:
        trozos: list[dict[str, Any]] = []
        pagina = 1
        while len(trozos) < MAX_FRAGMENTOS:
            _, datos = self.cliente.pedir("GET", f"/chunks/{kid}", params={"page": pagina, "page_size": 100})
            lote = datos.get("data") or []
            trozos.extend(lote)
            if not lote or len(trozos) >= int(datos.get("total") or 0):
                break
            pagina += 1
        bd.execute(delete(Fragmento).where(Fragmento.documento_id == doc.id))
        trozos.sort(key=lambda c: c.get("chunk_index") or 0)
        n = 0
        for c in trozos:
            texto = (c.get("content") or "").strip()
            if not texto:
                continue
            meta = _meta_de_parte(texto, partes)
            meta.update({"wk_chunk_id": str(c.get("id")), "wk_indice": c.get("chunk_index", n)})
            bd.add(Fragmento(documento_id=doc.id, orden=n, texto=texto, embedding=None, metadatos=meta))
            n += 1
        bd.flush()
        return n

    def _borrar_conocimiento(self, kid: str) -> None:
        # El borrado en WeKnora es asíncrono; un 404 significa que ya no estaba.
        self.cliente.pedir("DELETE", f"/knowledge/{kid}", aceptar=(404,))

    def borrar(self, bd: Session, doc: Documento) -> None:
        if doc.motor_id:
            self._borrar_conocimiento(doc.motor_id)
            doc.motor_id = None
        bd.execute(delete(Fragmento).where(Fragmento.documento_id == doc.id))

    def reetiquetar(self, bd: Session, doc: Documento) -> bool:
        """Ajusta las etiquetas tras cambiar nivel, formación o público.

        Devuelve False si el documento tiene que cambiar de base (otro departamento o
        público): eso exige volver a indexarlo, y lo decide quien llama.
        """
        if not doc.motor_id:
            return False
        kb, nombres = self.destino(bd, doc)
        estado, datos = self.cliente.pedir("GET", f"/knowledge/{doc.motor_id}", aceptar=(404,))
        if estado == 404 or (datos.get("data") or {}).get("knowledge_base_id") != kb:
            return False
        ids = [t for t in (self.etiqueta(kb, n) for n in nombres) if t]
        self.cliente.pedir("PUT", "/knowledge/tags", json={"updates": {doc.motor_id: ids}, "kb_id": kb})
        return True

    # ------------------------------------------------------------------ búsqueda

    def ambitos(self, bd: Session, alcance: Alcance) -> list[Ambito]:
        """Bases y etiquetas en las que puede buscar un alcance (sin crear nada)."""
        salida: list[Ambito] = []
        publica = self.base_publica(bd, crear=False)
        if alcance.todo:
            for dep in bd.scalars(select(Departamento).where(Departamento.weknora_kb_id.is_not(None))
                                  .order_by(Departamento.nombre)).all():
                salida.append(Ambito(str(dep.weknora_kb_id), None, f"{dep.nombre} · todo"))
            if publica:
                salida.append(Ambito(publica, None, "Público · todo"))
            return salida
        if alcance.publico and publica:
            tid = self.etiqueta(publica, ETIQUETA_PUBLICO, crear=False)
            if tid:
                salida.append(Ambito(publica, [tid], "Público"))
        for e in alcance.elementos:
            dep = bd.get(Departamento, e.departamento_id)
            if dep is None or not dep.weknora_kb_id:
                continue  # aún no hay nada indexado de ese departamento
            kb = str(dep.weknora_kb_id)
            nombres = [ETIQUETA_FORMACION] if e.solo_formacion else [etiqueta_nivel(i) for i in range(1, e.nivel_max + 1)]
            ids = [t for t in (self.etiqueta(kb, n, crear=False) for n in nombres) if t]
            if ids:
                salida.append(Ambito(kb, ids, f"{dep.nombre} · {', '.join(nombres)}"))
        return salida

    def buscar(self, bd: Session, consulta: str, alcance: Alcance, k: int = 6) -> list[Encontrado]:
        consulta = (consulta or "").strip()
        if not consulta:
            return []
        self.cliente.comprobar_clave()  # sin clave no se responde «no hay nada»: se avisa
        listas: list[list[dict[str, Any]]] = []
        for amb in self.ambitos(bd, alcance):
            cuerpo: dict[str, Any] = {"query": consulta, "knowledge_base_ids": [amb.base]}
            if amb.etiquetas is not None:
                cuerpo["tag_ids"] = amb.etiquetas
            _, datos = self.cliente.pedir("POST", "/knowledge-search", json=cuerpo)
            listas.append([r for r in (datos.get("data") or []) if r.get("id")])
        if not listas:
            return []
        unicos: dict[str, dict[str, Any]] = {}
        for lista in listas:
            for r in lista:
                unicos.setdefault(str(r["id"]), r)
        puntos = fusion_rrf(listas, clave=lambda r: str(r["id"]))
        orden = sorted(puntos, key=puntos.get, reverse=True)  # type: ignore[arg-type]
        kids = {str(unicos[c].get("knowledge_id")) for c in orden}
        docs = {d.motor_id: d for d in bd.scalars(select(Documento).where(Documento.motor_id.in_(kids))).all()}
        # Defensa en profundidad: cada resultado se vuelve a comprobar contra la BD.
        elegidos: list[tuple[str, dict[str, Any], Documento]] = []
        por_doc: dict[int, int] = {}
        for cid in orden:
            r = unicos[cid]
            d = docs.get(str(r.get("knowledge_id")))
            if d is None or not puede_ver(alcance, d):
                continue
            if por_doc.get(d.id, 0) >= MAX_POR_DOCUMENTO:
                continue
            por_doc[d.id] = por_doc.get(d.id, 0) + 1
            elegidos.append((cid, r, d))
            if len(elegidos) >= k:
                break
        if not elegidos:
            return []
        locales = {
            str((f.metadatos or {}).get("wk_chunk_id")): f
            for f in bd.scalars(select(Fragmento).where(
                Fragmento.documento_id.in_({d.id for _, _, d in elegidos}),
                Fragmento.metadatos["wk_chunk_id"].astext.in_([c for c, _, _ in elegidos]),
            )).all()
        }
        sims = self._similitudes(consulta, [f"{d.titulo}\n{r.get('content') or ''}" for _, r, d in elegidos])
        salida: list[Encontrado] = []
        for (cid, r, d), sim in zip(elegidos, sims, strict=True):
            local = locales.get(cid)
            meta = {k: v for k, v in (local.metadatos if local else {}).items() if not k.startswith(PREFIJO_META)}
            meta.update(metadatos_documento(bd, d))
            meta["coincidencia_texto"] = r.get("match_type") == 1
            meta["puntuacion_motor"] = r.get("score")
            salida.append(Encontrado(
                documento_id=d.id,
                titulo=d.titulo,
                texto=(r.get("content") or "").strip(),
                puntuacion=puntos[cid],
                similitud=sim,
                metadatos=meta,
                fragmento_id=local.id if local else cid,
            ))
        return salida

    def _similitudes(self, consulta: str, textos: list[str]) -> list[float | None]:
        """Similitud semántica de cada resultado con la pregunta, en la misma escala que el
        motor propio (la puntuación de WeKnora depende de si hay reranker y no sirve de umbral)."""
        try:
            q = llm.embedding_consulta(consulta)
            vectores = llm.embeddings(textos)
        except Exception:  # noqa: BLE001
            log.warning("No se ha podido calcular la similitud de los resultados de WeKnora", exc_info=True)
            return [None] * len(textos)
        return [_coseno(q, v) for v in vectores]

    # ------------------------------------------------------------------ salud

    def salud(self) -> dict[str, Any]:
        base = {"motor": self.nombre, "url": self.cliente.url}
        try:
            r = self.cliente.http.get(self.cliente.raiz() + "/health", timeout=5)
        except httpx.HTTPError:
            return {**base, "ok": False, "error": f"No se puede conectar con WeKnora en {self.cliente.url}."}
        if r.status_code != 200:
            return {**base, "ok": False, "error": f"WeKnora responde con el estado {r.status_code}."}
        try:
            _, datos = self.cliente.pedir("GET", "/knowledge-bases")
        except ErrorWeKnora as e:
            return {**base, "ok": False, "error": str(e)}
        lista = datos.get("data")
        return {**base, "ok": True, "bases": len(lista) if isinstance(lista, list) else None}
