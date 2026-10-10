"""Captura del conocimiento del experto: vídeo narrado, nota de voz y entrevista guiada.

* Vídeo: se sube (estado «subida») y un trabajo en segundo plano extrae el audio, lo transcribe con
  marcas de tiempo, detecta cambios de plano, pide al modelo los pasos (con plan B por segmentos si
  responde algo inservible), saca una imagen y un clip por paso y deja una instrucción en borrador
  (versión siguiente de la tarea, o de una tarea nueva). La fase y el progreso se guardan en la
  captura para que la interfaz los muestre en vivo.
* Nota de voz: transcripción → el modelo la ordena en una ficha (documento tipo «ficha» en
  borrador) → el experto la revisa y la publica (entonces se indexa).
* Entrevista guiada: el copiloto pregunta siguiendo un guion (objetivo, preparación, pasos, puntos
  críticos, errores, trucos, calidad), una pregunta cada vez y adaptándose a las respuestas. Al
  terminar se genera la ficha o un borrador de instrucción, igual que con la nota de voz.

Permisos: capturan los expertos, jefes y administración, sobre tareas de su departamento. Cada
captura es de quien la hace; la ven también los jefes de su departamento y la administración.
"""

from __future__ import annotations

import logging
import mimetypes
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from cidia import trabajos
from cidia.ficheros import guardar_subida, nombre_seguro, relativa, ruta_absoluta
from cidia.ia import asr, llm
from cidia.modelos import Captura, Documento, Instruccion, Paso, Puesto, Tarea, Trabajo, Usuario, ahora
from cidia.seguridad import Actor, url_fichero
from cidia.servicios import captura_prompts as prompts
from cidia.servicios import documentos, instrucciones, video
from cidia.xapi import auditar, registrar

log = logging.getLogger("cidia.captura")

EXT_VIDEO = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp", ".mpeg", ".mpg", ".wmv"}
EXT_AUDIO = {".webm", ".weba", ".ogg", ".oga", ".opus", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".mp4", ".amr", ".3gp"}
MAX_AUDIO_RESPUESTA = 25 * 1024 * 1024
MAX_AUDIO = 300 * 1024 * 1024  # nota de voz subida (unas horas de audio comprimido)

UMBRAL_ESCENAS = 10.0  # puntuación de scdet (0-100) para considerar un cambio de plano
MAX_PASOS = 30
MAX_CLIP = 90.0  # segundos como mucho por clip, para que sean ligeros
MAX_VISION = 15  # pasos que se describen con el modelo de visión
TRAMO_MINIMO = 3.0  # segundos mínimos de un paso del plan B
TRAMO_SIN_ESCENAS = 30.0  # sin cambios de plano, el plan B corta cada ~30 s respetando las frases
MAX_REPREGUNTAS = 1  # repreguntas por tema en la entrevista
MAX_MENSAJES = 150  # mensajes de una entrevista (el guion completo, con repreguntas, son unos 30)

FASES: dict[str, list[tuple[str, str]]] = {
    "video": [("subiendo", "Subiendo"), ("extrayendo_audio", "Extrayendo audio"), ("transcribiendo", "Transcribiendo"),
              ("detectando_pasos", "Detectando pasos"), ("generando_borrador", "Generando borrador"),
              ("recortando_clips", "Recortando clips"), ("listo", "Borrador listo")],
    "audio": [("subiendo", "Subiendo"), ("transcribiendo", "Transcribiendo"), ("generando_ficha", "Generando ficha"),
              ("listo", "Ficha lista")],
    "entrevista": [("conversando", "Entrevista"), ("generando_ficha", "Generando borrador"), ("listo", "Borrador listo")],
}


class ErrorCaptura(RuntimeError):
    """Problema del contenido capturado que se explica a la persona tal cual."""


# --------------------------------------------------------------------------- utilidades


# Valores de relleno que los modelos pequeños escriben en vez de dejar el campo vacío.
RELLENO = {"vacío", "vacio", "ninguno", "ninguna", "nada", "n/a", "na", "-", "...", "…", "no se dice",
           "no se menciona", "sin datos", "null", "none", "no aplica", "no hay", "desconocido", "mínimo", "minimo",
           "bajo", "riesgo mínimo", "riesgo minimo", "riesgos mínimos", "riesgos minimos", "sin riesgo",
           "sin riesgos", "no se indica", "no se indican"}
_MARCA_TIEMPO = re.compile(r"^\[\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\]\s*")
# Elementos de lista que no son nada: números o marcas de tiempo sueltas («4.6», «0:05», «12 s») e
# identificadores («riesgo_mínimo»), que los modelos diminutos copian del prompt.
_NO_ELEMENTO = re.compile(r"^(?:[\d\s.,:;\-–]+(?:s|seg|segundos)?|\w+_\w+(?:_\w+)*)$", re.I)
# Frases del resumen que hablan de segundos o de números de paso: el modelo repite los datos del
# prompt («los pasos clave están en 4.6 y 55.9 segundos») en lugar de decir para qué sirve la tarea.
_FRASE_DE_TIEMPOS = re.compile(r"\d+(?:[.,]\d+)?\s*(?:s|seg\.?|segundos)\b|\bpasos?\b[^.]*?\b\d+\b", re.I)


def _limpio(v: Any, maximo: int) -> str:
    if v is None or isinstance(v, (dict, list, bool)):  # «true» en un campo de texto tampoco es texto
        return ""
    t = re.sub(r"[ \t]+", " ", str(v)).strip()
    return "" if t.lower().strip(" .") in RELLENO else t[:maximo]


def _texto_libre(v: Any, maximo: int) -> str:
    """Texto del modelo; si llega como lista de frases (pasa con modelos pequeños), se unen."""
    if isinstance(v, list):
        v = " ".join(t for t in (_limpio(x, maximo) for x in v) if t)
    return _limpio(v, maximo)


def _lista(v: Any, maximo: int = 3000) -> str:
    """Lista o texto del modelo → texto con un elemento por línea (sin marcas de tiempo copiadas)."""
    if isinstance(v, bool):  # «"epis": true»
        return ""
    if isinstance(v, dict):  # {"1": "Guantes", "2": "Gafas"}
        v = list(v.values())
    elementos = v if isinstance(v, list) else str(v or "").splitlines()
    limpios = (_limpio(_MARCA_TIEMPO.sub("", _limpio(e, 300)), 300) for e in elementos)
    return "\n".join(dict.fromkeys(x for x in limpios if x and not _NO_ELEMENTO.match(x)))[:maximo]


def _resumen_limpio(v: Any) -> str:
    """Resumen sin las frases que solo repiten tiempos o números de paso."""
    texto = _texto_libre(v, 3000)
    frases = re.split(r"(?<=[.!?])\s+", texto)
    return " ".join(f for f in frases if f and not _FRASE_DE_TIEMPOS.search(f)).strip()


def _si(v: Any) -> bool:
    return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "sí", "si", "1", "yes", "verdadero"))


# Claves en inglés o sinónimas que los modelos pequeños escriben a veces en lugar de las pedidas.
_ALIAS_PROPUESTA = {"steps": "pasos", "title": "titulo", "summary": "resumen", "risks": "riesgos",
                    "ppe": "epis", "tools": "herramientas"}
_ALIAS_PASO = {"title": "titulo", "text": "texto", "description": "texto", "descripcion": "texto",
               "critical": "es_critico", "safety": "es_seguridad", "acceptance_criteria": "criterio_aceptacion",
               "criterio": "criterio_aceptacion", "start": "t_inicio", "end": "t_fin", "inicio": "t_inicio",
               "fin": "t_fin"}
_ALIAS_FICHA = {"title": "titulo", "content": "contenido", "texto": "contenido", "tags": "etiquetas",
                "keywords": "etiquetas"}


def _con_alias(d: dict[str, Any], alias: dict[str, str]) -> dict[str, Any]:
    """Copia de `d` con las claves sinónimas traducidas (sin pisar las que ya vienen bien)."""
    salida = dict(d)
    for clave, valor in d.items():
        destino = alias.get(str(clave).strip().lower())
        if destino and destino not in salida:
            salida[destino] = valor
    return salida


def _segundos(v: Any) -> float | None:
    """Número de segundos; admite también «mm:ss» (los modelos pequeños a veces lo devuelven así)."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v >= 0 else None
    m = re.fullmatch(r"\s*(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\s*", str(v))
    if m:
        return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    try:
        f = float(str(v).strip().rstrip("s"))
    except ValueError:
        return None
    return f if f >= 0 else None


_CORTES_TITULO = {"con", "para", "durante", "hasta", "sin", "en", "de", "desde", "sobre", "mediante", "por"}


def titulo_de(texto: str, palabras: int = 8) -> str:
    """Título corto a partir de la primera frase de un texto. Si la frase es larga, se corta por una
    coma o antes de una preposición («Aprieto los 4 tornillos en cruz con la llave…» → «Aprieto los
    4 tornillos»), no a mitad de una expresión."""
    frase = re.split(r"(?<=[.;:!?])\s+|\n", (texto or "").strip(), maxsplit=1)[0]
    trozos = frase.strip(" .,;:¡!¿?-").split()
    if not trozos:
        return ""
    if len(trozos) > palabras:
        coma = next((i for i, w in enumerate(trozos[:palabras]) if w.endswith(",") and i >= 1), None)
        if coma is not None:
            trozos = trozos[:coma + 1]
        else:
            corte = max((i for i in range(3, palabras + 1) if trozos[i].lower() in _CORTES_TITULO), default=None)
            trozos = trozos[:corte] if corte else trozos[:palabras]
    t = " ".join(trozos).rstrip(",;:")
    return t[0].upper() + t[1:]


def _fase(bd: Session, cap: Captura, fase: str, progreso: int, aviso: Any = None) -> None:
    """Guarda la fase y el progreso (con commit, para que la interfaz los vea mientras tanto)."""
    cap.fase = fase
    cap.progreso = max(0, min(100, int(progreso)))
    bd.commit()
    if aviso:
        aviso(cap.progreso, dict(FASES.get(cap.tipo, [])).get(fase, fase))


def _actor_de(usuario: Usuario | None) -> Actor | None:
    """Actor para registrar en nombre del autor desde un trabajo en segundo plano (sin sesión)."""
    return Actor(sesion=None, usuario=usuario) if usuario else None  # type: ignore[arg-type]


def _mensaje_error(e: Exception) -> str:
    if isinstance(e, HTTPException):
        return str(e.detail)
    if isinstance(e, (ErrorCaptura, video.ErrorVideo)):
        return str(e)[:400]
    if isinstance(e, llm.ErrorModelo):  # su texto puede llevar direcciones internas del servidor de modelos
        return "El modelo de IA no está disponible ahora mismo. Vuelve a intentarlo en unos minutos."
    if isinstance(e, asr.ErrorVoz):
        return "El servicio de voz no ha podido transcribir el audio. Vuelve a intentarlo en unos minutos."
    return "Ha ocurrido un error inesperado al procesar la captura. Vuelve a intentarlo."


def _comprobar_tipo(subida: UploadFile, extensiones: set[str], prefijo_mime: str, mensaje: str,
                    ext_defecto: str) -> None:
    """Admite el fichero por su extensión o, si no la trae, por su tipo MIME. En ese caso se guarda con
    una extensión de vídeo o audio: el nombre decide cómo se sirve después (/api/ficheros), y un
    «nota.html» declarado como vídeo se serviría como página web en el mismo origen que la interfaz."""
    nombre = Path(subida.filename or "")
    ext = nombre.suffix.lower()
    if ext in extensiones:
        return
    mime = (subida.content_type or "").split(";")[0].strip().lower()
    if not mime.startswith(prefijo_mime):
        raise HTTPException(400, mensaje)
    propia = mimetypes.guess_extension(mime) or ""
    subida.filename = (nombre.stem or "captura") + (propia if propia in extensiones else ext_defecto)


# --------------------------------------------------------------------------- permisos y consulta


def _trabajo_activo(bd: Session, cap: Captura) -> bool | None:
    """¿Sigue vivo el último trabajo de la captura? None si no tiene ninguno."""
    t = bd.scalar(select(Trabajo).where(Trabajo.entidad == "captura", Trabajo.entidad_id == cap.id)
                  .order_by(Trabajo.id.desc()).limit(1))
    return None if t is None else t.estado in ("pendiente", "en_curso")


def _corregir_interrumpida(bd: Session, cap: Captura) -> None:
    """Si su trabajo murió (p. ej., al reiniciar el servidor), la captura pasa a «error» para poder reintentarla."""
    if cap.estado in ("subida", "procesando") and _trabajo_activo(bd, cap) is False:
        cap.estado = "error"
        cap.mensaje = "El procesado se interrumpió (por ejemplo, al reiniciar el servidor). Pulsa «Reintentar»."
        bd.commit()


def departamento_de_captura(bd: Session, cap: Captura) -> int | None:
    """Departamento al que pertenece lo capturado: el de su tarea, el de su ficha o, si aún no tiene
    ninguna, el de su autor. No depende del departamento actual del autor (puede haber cambiado)."""
    if cap.tarea_id:
        tarea = bd.get(Tarea, cap.tarea_id)
        if tarea is not None:
            return instrucciones.departamento_de(tarea)
    if cap.documento_id:
        doc = bd.get(Documento, cap.documento_id)
        if doc is not None:
            return doc.departamento_id
    autor = bd.get(Usuario, cap.autor_id) if cap.autor_id else None
    return autor.departamento_id if autor else None


def obtener(bd: Session, actor: Actor, captura_id: int) -> Captura:
    cap = bd.get(Captura, captura_id)
    if cap is None:
        raise HTTPException(404, "La captura no existe.")
    # La ve su autor, la administración y el jefe del departamento de lo capturado. Un jefe sin
    # departamento no es jefe «del departamento» de nadie (None == None no cuenta).
    jefe_del_departamento = (cap.autor_id != actor.id and actor.es_jefe and actor.departamento_id is not None
                             and departamento_de_captura(bd, cap) == actor.departamento_id)
    if not (cap.autor_id == actor.id or actor.es_admin or jefe_del_departamento):
        raise HTTPException(403, "Esta captura es de otra persona.")
    _corregir_interrumpida(bd, cap)
    return cap


def _exigir_departamento(bd: Session, actor: Actor, cap: Captura) -> None:
    """Lo que genera borradores (reintentar, seguir o terminar una entrevista) exige poder gestionar
    el departamento de lo capturado. Si la autora se ha cambiado de departamento, ya no crea
    borradores en el anterior (igual que ya no edita ni publica su ficha)."""
    if not instrucciones.puede_gestionar(actor, departamento_de_captura(bd, cap)):
        raise HTTPException(403, "Esta captura es de otro departamento. Pide a su jefe que la revise.")


def _tarea_para(bd: Session, actor: Actor, tarea_id: int | None) -> Tarea | None:
    """Tarea elegida (comprobando que es de su departamento y que sigue activa). Sin tarea se creará
    una nueva en su departamento, así que hace falta que tenga uno."""
    if tarea_id:
        tarea = instrucciones.tarea_gestionable(bd, actor, tarea_id)
        if not tarea.activa:
            raise HTTPException(400, "Esa tarea está dada de baja. Elige otra o pide a la administración que la reactive.")
        return tarea
    if not actor.departamento_id:
        raise HTTPException(400, "Elige la tarea: tu usuario no pertenece a ningún departamento.")
    return None


def listar(bd: Session, actor: Actor) -> list[dict[str, Any]]:
    filas = bd.scalars(select(Captura).where(Captura.autor_id == actor.id).order_by(Captura.creada.desc()).limit(100)).all()
    for c in filas:
        _corregir_interrumpida(bd, c)
    return [a_dict(bd, c) for c in filas]


def _estado_borrador(bd: Session, cap: Captura) -> dict[str, Any] | None:
    """Qué ha producido la captura y en qué estado está (para «Revisar borrador»)."""
    if cap.instruccion_id:
        ins = bd.get(Instruccion, cap.instruccion_id)
        if ins:
            return {"tipo": "instruccion", "id": ins.id, "version": ins.version, "estado": ins.estado}
    if cap.documento_id:
        doc = bd.get(Documento, cap.documento_id)
        if doc:
            return {"tipo": "ficha", "id": doc.id, "estado": "borrador" if doc.estado == "borrador" else "publicada"}
    return None


def _tema_actual(conversacion: list[dict[str, Any]]) -> str:
    for m in reversed(conversacion):
        if m.get("rol") == "copiloto":
            return m.get("tema") or prompts.GUION[0].clave
    return prompts.GUION[0].clave


def _resumen_entrevista(conversacion: list[dict[str, Any]]) -> dict[str, Any]:
    actual = _tema_actual(conversacion)
    respuestas = [m for m in conversacion if m.get("rol") == "experto"]
    respondidos = {m.get("tema") for m in respuestas if not m.get("saltada")}
    saltados = {m.get("tema") for m in respuestas if m.get("saltada")} - respondidos
    temas = []
    for t in prompts.GUION:
        if t.clave == actual:
            estado = "actual"
        elif t.clave in respondidos:
            estado = "hecho"
        elif t.clave in saltados:
            estado = "saltado"
        else:
            estado = "pendiente"
        temas.append({"clave": t.clave, "titulo": t.titulo, "estado": estado})
    return {
        "temas": temas,
        "tema_actual": actual,
        "terminada": actual == "fin",
        "respuestas": sum(1 for m in conversacion if m.get("rol") == "experto" and (m.get("texto") or "").strip()),
    }


def _progreso_entrevista(conversacion: list[dict[str, Any]]) -> int:
    if _tema_actual(conversacion) == "fin":
        return 100
    hechos = {m.get("tema") for m in conversacion if m.get("rol") == "experto"} & set(prompts.TEMAS)
    return int(100 * len(hechos) / len(prompts.GUION))


def a_dict(bd: Session, cap: Captura, detalle: bool = False) -> dict[str, Any]:
    tarea = bd.get(Tarea, cap.tarea_id) if cap.tarea_id else None
    autor = bd.get(Usuario, cap.autor_id) if cap.autor_id else None
    fases = FASES.get(cap.tipo, [])
    resultado = cap.resultado or {}
    d: dict[str, Any] = {
        "id": cap.id,
        "tipo": cap.tipo,
        "titulo": cap.titulo,
        "autor": {"id": autor.id, "nombre": autor.nombre} if autor else None,
        "tarea": {"id": tarea.id, "codigo": tarea.codigo, "nombre": tarea.nombre} if tarea else None,
        "estado": cap.estado,
        "fase": cap.fase,
        "fase_texto": dict(fases).get(cap.fase or "", cap.fase),
        "fases": [{"clave": c, "texto": t} for c, t in fases],
        "progreso": cap.progreso,
        "mensaje": cap.mensaje,
        "duracion": cap.duracion,
        "creada": cap.creada.isoformat() if cap.creada else None,
        "actualizada": cap.actualizada.isoformat() if cap.actualizada else None,
        "instruccion_id": cap.instruccion_id,
        "documento_id": cap.documento_id,
        "miniatura_url": url_fichero(resultado.get("miniatura")),
        "origen_borrador": resultado.get("origen"),
        "borrador": _estado_borrador(bd, cap),
    }
    if cap.tipo == "entrevista":
        d["entrevista"] = _resumen_entrevista(cap.conversacion or [])
    if detalle:
        d["original_url"] = url_fichero(cap.ruta_original)
        d["transcripcion"] = cap.transcripcion
        d["escenas"] = cap.escenas
        d["conversacion"] = cap.conversacion or []
        d["ficha"] = None
        if cap.documento_id:
            doc = bd.get(Documento, cap.documento_id)
            if doc:
                d["ficha"] = {
                    "id": doc.id, "titulo": doc.titulo, "contenido": doc.contenido_texto or "",
                    "etiquetas": resultado.get("etiquetas", []), "estado": doc.estado,
                    "publicada": doc.estado != "borrador",
                    "departamento": doc.departamento.nombre if doc.departamento else None,
                    "validador": doc.validador.nombre if doc.validador else None,
                }
    return d


# --------------------------------------------------------------------------- alta de capturas


def _encolar(cap: Captura) -> None:
    funcion = {"video": procesar_video_trabajo, "audio": procesar_audio_trabajo,
               "entrevista": procesar_entrevista_trabajo}[cap.tipo]
    trabajos.encolar(f"captura_{cap.tipo}", funcion, cap.id, entidad="captura", entidad_id=cap.id,
                     usuario_id=cap.autor_id)


def _crear_desde_fichero(bd: Session, actor: Actor, tipo: str, subida: UploadFile, tarea_id: int | None,
                         titulo: str | None) -> Captura:
    tarea = _tarea_para(bd, actor, tarea_id)
    if tipo == "video":
        _comprobar_tipo(subida, EXT_VIDEO, "video/", "Sube un fichero de vídeo (MP4, MOV, WebM…).", ".mp4")
    else:
        _comprobar_tipo(subida, EXT_AUDIO, "audio/", "Sube un fichero de audio (WebM, OGG, MP3, WAV, M4A…).", ".webm")
    # La nota de voz se envía entera al servicio de voz (en memoria): sin límite propio admitiría
    # los 2 GB de un vídeo. Si se conoce el tamaño, se rechaza antes de escribir nada en disco.
    demasiado = (413, f"La nota de voz es demasiado grande (máximo {MAX_AUDIO // (1024 * 1024)} MB). "
                      "Si es una grabación muy larga, divídela en partes.")
    if tipo == "audio" and (getattr(subida, "size", None) or 0) > MAX_AUDIO:
        raise HTTPException(*demasiado)
    ruta, nombre, tam = guardar_subida(subida, "capturas")
    if tam == 0 or (tipo == "audio" and tam > MAX_AUDIO):
        shutil.rmtree(ruta_absoluta(ruta).parent, ignore_errors=True)
        if tam == 0:
            raise HTTPException(400, "El fichero está vacío.")
        raise HTTPException(*demasiado)
    cap = Captura(
        tipo=tipo, autor_id=actor.id, tarea_id=tarea.id if tarea else None,
        # Sin título ni tarea, lo pondrá el borrador (título de la propuesta o de la ficha).
        titulo=_limpio(titulo, 300) or (tarea.nombre if tarea else None),
        ruta_original=ruta, nombre_fichero=nombre, estado="subida", fase="subiendo", progreso=5,
    )
    bd.add(cap)
    bd.flush()
    registrar(bd, actor, "capturo", "captura", cap.id, cap.titulo, resultado={"tipo": tipo, "tamano": tam},
              contexto={"tarea_id": cap.tarea_id})
    bd.commit()
    _encolar(cap)
    bd.refresh(cap)
    return cap


def crear_video(bd: Session, actor: Actor, subida: UploadFile, tarea_id: int | None = None,
                titulo: str | None = None) -> Captura:
    return _crear_desde_fichero(bd, actor, "video", subida, tarea_id, titulo)


def crear_nota_voz(bd: Session, actor: Actor, subida: UploadFile, tarea_id: int | None = None,
                   titulo: str | None = None) -> Captura:
    return _crear_desde_fichero(bd, actor, "audio", subida, tarea_id, titulo)


def reintentar(bd: Session, actor: Actor, captura_id: int) -> Captura:
    cap = obtener(bd, actor, captura_id)
    _exigir_departamento(bd, actor, cap)  # el procesado crea el borrador en su departamento
    bd.refresh(cap, with_for_update=True)  # un doble clic no encola el procesado dos veces
    if cap.estado != "error":
        raise HTTPException(409, "Solo se puede reintentar una captura que ha fallado.")
    if cap.tipo == "entrevista":
        cap.estado, cap.fase, cap.progreso = "procesando", "generando_ficha", 10
    else:
        cap.estado, cap.fase, cap.progreso = "subida", "subiendo", 5
    cap.mensaje = None
    bd.commit()
    _encolar(cap)
    bd.refresh(cap)
    return cap


def borrar(bd: Session, actor: Actor, captura_id: int) -> None:
    """Borra la captura y lo que generó sin publicar (borrador de instrucción, ficha en borrador).
    Los ficheros se borran solo si ninguna instrucción (de ninguna versión) los usa ya."""
    cap = obtener(bd, actor, captura_id)
    if cap.estado in ("subida", "procesando") and _trabajo_activo(bd, cap):
        raise HTTPException(409, "Espera a que termine de procesarse antes de borrarla.")
    # Con la captura se borran sus borradores sin publicar, que son conocimiento del departamento de
    # su tarea: hace falta poder gestionarlo (p. ej., la autora que se ha cambiado de departamento
    # ya no borra el borrador que revisa su antiguo jefe).
    otro_departamento = HTTPException(403, "El borrador de esta captura es de otro departamento. "
                                           "Pide a su jefe que lo revise o lo borre.")
    imagenes: set[str] = set()
    if cap.instruccion_id:
        ins = bd.get(Instruccion, cap.instruccion_id)
        if ins is not None:
            instrucciones.bloquear_tarea(bd, ins.tarea_id)  # que nadie lo esté publicando a la vez
            bd.refresh(ins)
            if ins.estado in instrucciones.EDITABLES:
                if not instrucciones.puede_gestionar(actor, instrucciones.departamento_de(ins.tarea)):
                    raise otro_departamento
                imagenes = instrucciones.imagenes_propias(ins)  # las subidas a mano al revisar el borrador
                bd.delete(ins)
    if cap.documento_id:
        doc = bd.get(Documento, cap.documento_id)
        if doc is not None and doc.estado == "borrador":
            if not instrucciones.puede_gestionar(actor, doc.departamento_id):
                raise otro_departamento
            bd.delete(doc)
    carpeta = Path(cap.ruta_original).parent.as_posix() if cap.ruta_original else None
    auditar(bd, actor, "borrar_captura", "captura", cap.id, {"tipo": cap.tipo, "titulo": cap.titulo})
    registrar(bd, actor, "borro", "captura", cap.id, cap.titulo, resultado={"tipo": cap.tipo},
              contexto={"tarea_id": cap.tarea_id})
    bd.delete(cap)
    bd.flush()
    en_uso = carpeta is not None and bd.scalar(
        select(Paso.id).where(or_(Paso.imagen_ruta.startswith(carpeta + "/"), Paso.clip_ruta.startswith(carpeta + "/")))
        .limit(1)
    ) is not None
    en_uso = en_uso or (carpeta is not None and bd.scalar(
        select(Instruccion.id).where(Instruccion.video_ruta.startswith(carpeta + "/")).limit(1)) is not None)
    bd.commit()
    instrucciones.borrar_imagenes_sin_uso(bd, imagenes)
    if carpeta and not en_uso:
        try:
            shutil.rmtree(ruta_absoluta(carpeta), ignore_errors=True)
        except HTTPException:
            pass


# --------------------------------------------------------------------------- vídeo → borrador de instrucción


def _ajustar_tiempos(pasos: list[dict[str, Any]], dur: float | None) -> None:
    """Tiempos coherentes: dentro del vídeo, crecientes y con al menos 1 s por paso. Si los del
    modelo no tienen sentido se reparten de forma uniforme."""
    n = len(pasos)
    if not dur or dur <= 0:
        for p in pasos:
            p["t_inicio"] = p["t_fin"] = None
        return
    inicios = [p.get("t_inicio") for p in pasos]
    validos = all(t is not None and 0 <= t < dur for t in inicios) and all(
        inicios[i] < inicios[i + 1] for i in range(n - 1))  # type: ignore[operator]
    if not validos:
        for i, p in enumerate(pasos):
            p["t_inicio"] = dur * i / n
            p["t_fin"] = None
    for i, p in enumerate(pasos):
        siguiente = pasos[i + 1]["t_inicio"] if i + 1 < n else dur
        fin = p.get("t_fin")
        if fin is None or fin <= p["t_inicio"] or fin > dur:
            fin = siguiente
        if fin - p["t_inicio"] < 1.0:
            fin = min(dur, p["t_inicio"] + 1.0)
        p["t_inicio"], p["t_fin"] = round(p["t_inicio"], 2), round(fin, 2)


def normalizar_propuesta(datos: Any, dur: float | None, con_tiempos: bool = True) -> dict[str, Any] | None:
    """Valida y limpia la propuesta del modelo. Devuelve None si no sirve (y se usará el plan B)."""
    # Una lista con un único objeto que es la instrucción entera ([{"titulo": ..., "pasos": [...]}]),
    # no un paso: si no, saldría un único paso con el título de la tarea.
    if (isinstance(datos, list) and len(datos) == 1 and isinstance(datos[0], dict)
            and {"pasos", "steps"} & {str(k).strip().lower() for k in datos[0]}):
        datos = datos[0]
    if isinstance(datos, list):
        datos = {"pasos": datos}
    # Los modelos pequeños a veces envuelven la respuesta ({"instruccion": {...}}), usan claves en
    # inglés ({"steps": [...]}) o numeran los pasos como claves de un objeto ({"pasos": {"1": {...}}}).
    if isinstance(datos, dict):
        datos = _con_alias(datos, _ALIAS_PROPUESTA)
    if isinstance(datos, dict) and "pasos" not in datos and len(datos) == 1:
        interior = next(iter(datos.values()))
        if isinstance(interior, dict):
            interior = _con_alias(interior, _ALIAS_PROPUESTA)
            if "pasos" in interior:
                datos = interior
    if isinstance(datos, dict) and isinstance(datos.get("pasos"), dict):
        datos = {**datos, "pasos": list(datos["pasos"].values())}
    if not isinstance(datos, dict) or not isinstance(datos.get("pasos"), list):
        return None
    pasos: list[dict[str, Any]] = []
    for e in datos["pasos"][:MAX_PASOS]:
        if isinstance(e, str):
            e = {"titulo": e}
        if not isinstance(e, dict):
            continue
        e = _con_alias(e, _ALIAS_PASO)
        titulo = _limpio(e.get("titulo"), 200)
        texto = _texto_libre(e.get("texto"), 3000) or _texto_libre(e.get("descripcion"), 3000)
        if not titulo and not texto:
            continue
        pasos.append({
            "titulo": titulo or titulo_de(texto) or f"Paso {len(pasos) + 1}",
            "texto": texto,
            # Si el propio paso dice que es crítico, lo es aunque el modelo no lo marque.
            "es_critico": _si(e.get("es_critico")) or bool(_DICHO_CRITICO.search(f"{titulo} {texto}")),
            "es_seguridad": _si(e.get("es_seguridad")),
            "criterio_aceptacion": _limpio(e.get("criterio_aceptacion"), 1000),
            "t_inicio": _segundos(e.get("t_inicio")),
            "t_fin": _segundos(e.get("t_fin")),
        })
    if not pasos:
        return None
    titulos = [p["titulo"].lower() for p in pasos]
    if len(pasos) >= 3 and len(set(titulos)) == 1:
        textos = [p["texto"].lower() for p in pasos]
        if not all(textos) or len(set(textos)) < len(textos):
            return None  # el mismo paso repetido: el modelo se ha atascado
        for p in pasos:  # el mismo título genérico («Paso») en todos, pero cada uno con su texto
            p["titulo"] = titulo_de(p["texto"]) or p["titulo"]
    if con_tiempos:
        _ajustar_tiempos(pasos, dur)
    else:
        for p in pasos:
            p["t_inicio"] = p["t_fin"] = None
    return {
        "titulo": _limpio(datos.get("titulo"), 300),
        "resumen": _resumen_limpio(datos.get("resumen")),
        "riesgos": _lista(datos.get("riesgos")),
        "epis": _lista(datos.get("epis")),
        "herramientas": _lista(datos.get("herramientas")),
        "pasos": pasos,
    }


def borrador_por_segmentos(segmentos: list[dict[str, Any]], escenas: list[dict[str, Any]], dur: float | None,
                           titulo: str | None, desde: float = 0.0) -> dict[str, Any]:
    """Plan B sin modelo: un paso por tramo entre cambios de plano (o cada ~30 s si no los hay),
    con el texto dicho en ese tramo. Siempre produce un borrador editable. Con `desde`, solo cubre
    el vídeo a partir de ese segundo (para completar una propuesta que se queda corta)."""
    dur = dur or max((s.get("fin", 0.0) for s in segmentos), default=0.0)
    cortes: list[float] = [e["t"] for e in escenas if desde + TRAMO_MINIMO <= e.get("t", 0) <= dur - TRAMO_MINIMO]
    if not cortes and segmentos:
        inicio = desde
        for s in segmentos:
            if s["fin"] - inicio >= TRAMO_SIN_ESCENAS and s["fin"] <= dur - TRAMO_MINIMO:
                cortes.append(s["fin"])
                inicio = s["fin"]
    limpios: list[float] = []
    for c in sorted(cortes):
        if c - (limpios[-1] if limpios else desde) >= TRAMO_MINIMO:
            limpios.append(c)
    if len(limpios) >= MAX_PASOS:  # demasiados cortes: se queda con unos repartidos
        paso = len(limpios) / (MAX_PASOS - 1)
        limpios = [limpios[int(i * paso)] for i in range(MAX_PASOS - 1)]
    limites = [desde, *limpios, dur]
    pasos = []
    for i in range(len(limites) - 1):
        a, b = limites[i], limites[i + 1]
        texto = " ".join(s["texto"] for s in segmentos
                         if s.get("texto") and a <= (s["inicio"] + s["fin"]) / 2 < b).strip()
        pasos.append({"titulo": titulo_de(texto) or f"Paso {i + 1}", "texto": texto, "es_critico": False,
                      "es_seguridad": False, "criterio_aceptacion": "",
                      "t_inicio": round(a, 2) if dur else None, "t_fin": round(b, 2) if dur else None})
    completo = " ".join(s.get("texto", "") for s in segmentos).strip()
    frases = re.split(r"(?<=[.!?])\s+", completo)
    return {"titulo": titulo or "", "resumen": " ".join(frases[:2])[:600], "riesgos": "", "epis": "",
            "herramientas": "", "pasos": pasos}


# --- pasos nombrados en voz alta («Paso 1…», «Paso dos…», «tercer paso…»)

_CARDINALES = {"uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
               "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15}
_ORDINALES = {"primer": 1, "primero": 1, "segundo": 2, "tercer": 3, "tercero": 3, "cuarto": 4, "quinto": 5,
              "sexto": 6, "séptimo": 7, "septimo": 7, "octavo": 8, "noveno": 9, "décimo": 10, "decimo": 10}
_MARCA_PASO = re.compile(
    r"\b(?:paso\s+(?:n[úu]mero\s+)?(?P<n>\d{1,2}|" + "|".join(_CARDINALES) + r")"
    r"|(?P<o>" + "|".join(_ORDINALES) + r")\s+paso)\b[ \t]*[.,:;]?", re.I)
# «Paso 3 y es crítico.», «Paso 5, de seguridad:» → la marca del paso, que no forma parte de su texto.
_CLAUSULA_PASO = re.compile(r"^(?:y\s+|que\s+)?(?:este\s+)?(?:es\s+)?(?:un\s+paso\s+|muy\s+)?"
                            r"(?P<c>cr[ií]tico|importante|de\s+seguridad)\b\s*[.,:;!]*\s*", re.I)
_DICHO_CRITICO = re.compile(r"\b(?:es|son)\s+(?:un\s+|muy\s+)?(?:paso\s+|punto\s+)?cr[ií]tic[oa]s?\b"
                            r"|\bpunto\s+cr[ií]tico\b|\bpaso\s+cr[ií]tico\b", re.I)
_DICHO_SEGURIDAD = re.compile(r"\bpor\s+(?:tu\s+)?seguridad\b|\bpeligr", re.I)
AJUSTE_A_ESCENA = 1.5  # segundos: una marca dicha cerca de un cambio de plano empieza en el cambio


def _secuencia_de_pasos(marcas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """La secuencia más larga de marcas con números crecientes que empieza por el 1 o el 2 y avanza
    de uno en uno (o de dos, por si la transcripción se come una marca). Así un «paso 2 veces el
    trapo» suelto no parte un paso por la mitad."""
    mejor: list[list[dict[str, Any]]] = []
    for i, m in enumerate(marcas):
        previas = [mejor[j] for j in range(i) if mejor[j] and mejor[j][-1]["n"] < m["n"] <= mejor[j][-1]["n"] + 2]
        if previas:
            mejor.append(max(previas, key=len) + [m])
        else:
            mejor.append([m] if m["n"] <= 2 else [])
    return max(mejor, key=len, default=[])


def pasos_narrados(segmentos: list[dict[str, Any]], dur: float | None,
                   escenas: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Si el experto nombra los pasos al explicar («Paso 1. Preparo…», «Paso dos…»), los pasos salen
    de ahí: el texto de cada uno es lo que dice hasta el siguiente y empieza en el momento en que lo
    nombra (o en el cambio de plano más cercano). Es lo más fiel a lo que contó, así que manda sobre
    los pasos del modelo. Devuelve {intro, pasos} o None si no hay al menos 3 marcas seguidas."""
    utiles = [s for s in segmentos if str(s.get("texto") or "").strip()]
    plano, inicios, marcas = "", [], []
    for s in utiles:
        texto = str(s["texto"]).strip()
        base = len(plano)
        inicios.append(base)
        for m in _MARCA_PASO.finditer(texto):
            n = int(m.group("n")) if (m.group("n") or "").isdigit() else (
                _CARDINALES.get((m.group("n") or "").lower()) or _ORDINALES.get((m.group("o") or "").lower()))
            ini, fin = _segundos(s.get("inicio")), _segundos(s.get("fin"))
            t = None
            if ini is not None and fin is not None and fin >= ini:
                t = ini + (fin - ini) * m.start() / max(1, len(texto))
            marcas.append({"n": n, "t": t, "desde": base + m.start(), "hasta": base + m.end()})
        plano += texto + " "
    elegidas = _secuencia_de_pasos([m for m in marcas if m["n"]])
    if len(elegidas) < 3:
        return None
    cortes = [e["t"] for e in escenas or [] if isinstance(e.get("t"), (int, float))]
    pasos: list[dict[str, Any]] = []
    for i, m in enumerate(elegidas):
        siguiente = elegidas[i + 1]["desde"] if i + 1 < len(elegidas) else len(plano)
        texto = plano[m["hasta"]:siguiente].strip(" .,;:")
        critico = seguridad = False
        while (c := _CLAUSULA_PASO.match(texto)):
            palabra = c.group("c").lower()
            critico = critico or not palabra.startswith("de")
            seguridad = seguridad or palabra.startswith("de")
            texto = texto[c.end():]
        texto = texto.strip(" .,;:")
        texto = (texto[:1].upper() + texto[1:]) if texto else ""
        if texto and texto[-1] not in ".!?":
            texto += "."
        t = m["t"]
        if t is not None and cortes:
            cerca = min(cortes, key=lambda c: abs(c - t))
            t = cerca if abs(cerca - t) <= AJUSTE_A_ESCENA else t
        pasos.append({"titulo": titulo_de(texto) or f"Paso {i + 1}", "texto": texto[:3000],
                      "es_critico": critico or bool(_DICHO_CRITICO.search(texto)),
                      "es_seguridad": seguridad or bool(_DICHO_SEGURIDAD.search(texto)),
                      "criterio_aceptacion": "", "t_inicio": t, "t_fin": None})
    if dur and all(p["t_inicio"] is not None for p in pasos):
        for i, p in enumerate(pasos):
            p["t_fin"] = pasos[i + 1]["t_inicio"] if i + 1 < len(pasos) else dur
        _ajustar_tiempos(pasos, dur)
    else:
        for p in pasos:
            p["t_inicio"] = p["t_fin"] = None
    return {"intro": plano[:elegidas[0]["desde"]].strip(), "pasos": pasos[:MAX_PASOS]}


def _completar_final(propuesta: dict[str, Any], segmentos: list[dict[str, Any]], escenas: list[dict[str, Any]],
                     dur: float | None) -> int:
    """Los modelos pequeños a veces se quedan sin pasos a mitad del vídeo: lo que se dice después del
    último paso se añade como pasos del plan B (por cambios de plano). Devuelve cuántos añade."""
    pasos = propuesta["pasos"]
    fin = pasos[-1].get("t_fin") if pasos else None
    if not dur or fin is None or fin >= dur * 0.85:
        return 0
    resto = [s for s in segmentos if str(s.get("texto") or "").strip()
             and (float(s.get("inicio", 0)) + float(s.get("fin", 0))) / 2 >= fin]
    if sum(len(str(s["texto"])) for s in resto) < 40:
        return 0
    extra = [p for p in borrador_por_segmentos(resto, escenas, dur, None, desde=fin)["pasos"] if p["texto"]]
    for i, p in enumerate(extra):  # sin huecos: cada paso llega hasta el siguiente
        p["t_inicio"] = fin if i == 0 else p["t_inicio"]
        p["t_fin"] = extra[i + 1]["t_inicio"] if i + 1 < len(extra) else dur
        p["es_critico"] = bool(_DICHO_CRITICO.search(p["texto"]))
    pasos.extend(extra[:max(0, MAX_PASOS - len(pasos))])
    return len(extra)


def _frases(texto: str, n: int = 2) -> str:
    return " ".join(re.split(r"(?<=[.!?])\s+", (texto or "").strip())[:n])[:600]


def proponer_pasos(bd: Session, transcripcion: dict[str, Any], escenas: list[dict[str, Any]], dur: float,
                   nombre: str | None) -> tuple[dict[str, Any], str]:
    """Propuesta a partir de la transcripción y los cambios de plano. Devuelve (propuesta, origen):
    * «pasos_narrados»: el experto nombra los pasos en voz alta; los pasos salen de lo que dice y el
      modelo aporta los datos generales (título, herramientas, EPIs, riesgos) y las marcas.
    * «modelo»: los pasos del modelo (completados con el plan B si se quedan cortos).
    * «segmentos»: plan B sin modelo, un paso por tramo entre cambios de plano."""
    segmentos = [s for s in transcripcion.get("segmentos") or [] if isinstance(s, dict)]
    texto = transcripcion.get("texto") or ""
    propuesta: dict[str, Any] | None = None
    if texto.strip() or segmentos:
        try:
            datos = llm.chat_json(prompts.mensajes_pasos(nombre, dur, segmentos, texto, escenas), bd=bd)
            propuesta = normalizar_propuesta(datos, dur)
            if not propuesta:
                log.info("La propuesta del modelo no sirve; se usa el plan B")
        except Exception as e:  # noqa: BLE001  (cualquier fallo del modelo → plan B)
            log.warning("El modelo no ha propuesto pasos (%s); se usa el plan B", e)
    narrados = pasos_narrados(segmentos, dur, escenas)
    if narrados:
        pasos = narrados["pasos"]
        general = propuesta or {}
        if propuesta and len(propuesta["pasos"]) == len(pasos):  # mismos pasos: se suman sus marcas
            for p, m in zip(pasos, propuesta["pasos"], strict=True):
                p["es_critico"] = p["es_critico"] or m["es_critico"]
                p["es_seguridad"] = p["es_seguridad"] or m["es_seguridad"]
                p["criterio_aceptacion"] = p["criterio_aceptacion"] or m["criterio_aceptacion"]
        intro = narrados["intro"] if len(narrados["intro"]) >= 15 else ""
        return {"titulo": general.get("titulo") or (nombre or ""),
                "resumen": general.get("resumen") or intro or _frases(texto),
                "riesgos": general.get("riesgos", ""), "epis": general.get("epis", ""),
                "herramientas": general.get("herramientas", ""), "pasos": pasos}, "pasos_narrados"
    if propuesta:
        propuesta["titulo"] = propuesta["titulo"] or (nombre or "")
        propuesta["resumen"] = propuesta["resumen"] or _frases(texto)
        if _completar_final(propuesta, segmentos, escenas, dur):
            log.info("La propuesta del modelo no cubría el final del vídeo; se ha completado")
        return propuesta, "modelo"
    return borrador_por_segmentos(segmentos, escenas, dur, nombre), "segmentos"


def _texto_mejorado(respuesta: str, original: str) -> str | None:
    t = llm.limpiar(respuesta or "").strip().strip('"«»').strip()
    t = re.sub(r"^(texto( del paso)?|paso)\s*:\s*", "", t, flags=re.I).strip()
    if len(t) < 15 or t[:1] in "{[" or len(t) > max(1200, 3 * len(original) + 300):
        return None
    if re.search(r"\b(no puedo|lo siento|no veo ninguna imagen|as an ai)\b", t, re.I):
        return None
    return t if _conserva_lo_dicho(original, t) else None


def _conserva_lo_dicho(original: str, nuevo: str) -> bool:
    """¿Mantiene el texto reescrito lo que dijo el experto? Todas sus cifras (pares, presiones,
    cantidades) y al menos la mitad de sus palabras con contenido (se comparan por la raíz, para
    admitir el paso a imperativo: «aprieto» → «aprieta»). Los modelos de visión diminutos a veces
    describen la imagen y se olvidan del texto."""
    cifras = set(re.findall(r"\d+(?:[.,]\d+)?", original or ""))
    if not cifras <= set(re.findall(r"\d+(?:[.,]\d+)?", nuevo)):
        return False
    raices = {w[:5] for w in re.findall(r"[a-záéíóúñü]{5,}", (original or "").lower())}
    if not raices:
        return True
    nuevas = {w[:5] for w in re.findall(r"[a-záéíóúñü]{5,}", nuevo.lower())}
    return len(raices & nuevas) >= 0.5 * len(raices)


def mejorar_con_vision(bd: Session, pasos: list[dict[str, Any]]) -> bool:
    """Si hay un modelo con visión permitido, mejora el texto de cada paso con su fotograma.
    Si el modelo falla dos veces seguidas (no está cargado, no responde) se deja de intentar:
    cada intento fallido puede tardar todo el tiempo de espera del cliente."""
    try:
        modelo = llm.modelo_vision(bd)
    except Exception:  # noqa: BLE001
        return False
    if not modelo:
        return False
    usado = False
    fallos = 0
    for p in pasos[:MAX_VISION]:
        if not p.get("imagen_ruta"):
            continue
        try:
            r = llm.chat(prompts.mensajes_vision(p["titulo"], p.get("texto") or "", ruta_absoluta(p["imagen_ruta"])),
                         modelo=modelo, max_tokens=400)
            fallos = 0
        except Exception as e:  # noqa: BLE001
            log.warning("El modelo de visión no ha respondido: %s", e)
            fallos += 1
            if fallos >= 2:
                break
            continue
        nuevo = _texto_mejorado(r, p.get("texto") or "")
        if nuevo:
            p["texto"] = nuevo
            usado = True
    return usado


def _tarea_nueva(bd: Session, autor: Usuario | None, nombre: str) -> Tarea:
    """Tarea nueva en el departamento del autor (en su puesto si es de ese departamento)."""
    if autor is None or not autor.departamento_id:
        raise ErrorCaptura("No se puede crear la tarea: el autor no pertenece a ningún departamento.")
    dep = autor.departamento_id
    puesto = autor.puesto if autor.puesto and autor.puesto.departamento_id == dep else bd.scalar(
        select(Puesto).where(Puesto.departamento_id == dep).order_by(Puesto.id).limit(1))
    if puesto is None:
        puesto = Puesto(departamento_id=dep, nombre="General")
        bd.add(puesto)
        bd.flush()
    t = Tarea(puesto_id=puesto.id, nombre=(nombre or "Tarea capturada")[:200],
              descripcion="Creada a partir de una captura.", nivel_minimo=1)
    bd.add(t)
    bd.flush()
    codigo = f"IT-{t.id:03d}"
    if bd.scalar(select(Tarea.id).where(Tarea.codigo == codigo, Tarea.id != t.id).limit(1)):
        codigo = f"CAP-{t.id:03d}"
    t.codigo = codigo
    auditar(bd, _actor_de(autor), "crear_tarea", "tarea", t.id,
            {"nombre": t.nombre, "puesto_id": puesto.id, "origen": "captura"})
    return t


def _original(cap: Captura) -> Path:
    """Fichero subido de la captura. Sin él, ruta_absoluta("") sería la propia carpeta de datos (y
    los ficheros de trabajo acabarían en la carpeta de encima)."""
    if not cap.ruta_original:
        raise ErrorCaptura("No se encuentra el fichero de la captura. Vuelve a subirlo.")
    original = ruta_absoluta(cap.ruta_original)
    if not original.is_file():
        raise ErrorCaptura("No se encuentra el fichero de la captura. Vuelve a subirlo.")
    return original


def procesar_video(bd: Session, cap: Captura, aviso: Any = None) -> dict[str, Any]:
    """Cadena completa del vídeo. Guarda fase y progreso a cada paso."""
    original = _original(cap)
    carpeta = original.parent
    cap.estado, cap.mensaje = "procesando", None
    _fase(bd, cap, "extrayendo_audio", 10, aviso)
    datos = video.info(original)
    if not datos["tiene_video"]:
        raise ErrorCaptura("El fichero no contiene vídeo. Si solo es audio, súbelo como nota de voz.")
    dur = float(datos["duracion"] or video.duracion(original))
    cap.duracion = round(dur, 2)
    resultado: dict[str, Any] = {}
    try:
        resultado["miniatura"] = relativa(video.miniatura(original, carpeta / "miniatura.jpg", t=dur * 0.1))
    except video.ErrorVideo:
        pass
    cap.resultado = resultado
    wav = video.extraer_audio(original, carpeta / "audio.wav") if datos["tiene_audio"] else None

    _fase(bd, cap, "transcribiendo", 22, aviso)
    trans = asr.transcribir(wav, con_marcas=True) if wav else {"texto": "", "segmentos": [], "duracion": dur}
    cap.transcripcion = trans
    if wav:
        wav.unlink(missing_ok=True)  # ya no hace falta y ocupa mucho

    _fase(bd, cap, "detectando_pasos", 45, aviso)
    cap.escenas = video.escenas(original, umbral=UMBRAL_ESCENAS)

    _fase(bd, cap, "generando_borrador", 55, aviso)
    tarea = bd.get(Tarea, cap.tarea_id) if cap.tarea_id else None
    propuesta, origen = proponer_pasos(bd, trans, cap.escenas or [], dur, tarea.nombre if tarea else cap.titulo)
    cap.titulo = cap.titulo or propuesta.get("titulo") or Path(cap.nombre_fichero or "").stem[:300] or None
    pasos = propuesta["pasos"]
    dir_pasos = carpeta / "pasos"
    dir_pasos.mkdir(exist_ok=True)
    for i, p in enumerate(pasos, start=1):
        # Imagen del paso: el fotograma de la mitad de su tramo.
        t = ((p["t_inicio"] or 0.0) + (p["t_fin"] or 0.0)) / 2 if p.get("t_fin") else (p.get("t_inicio") or 0.0)
        try:
            imagen = video.fotograma(original, min(t, max(0.0, dur - 0.2)), dir_pasos / f"paso_{i:02d}.jpg")
            p["imagen_ruta"] = relativa(imagen)
        except video.ErrorVideo:
            log.warning("Sin imagen para el paso %s de la captura %s", i, cap.id)
    _fase(bd, cap, "generando_borrador", 65, aviso)
    vision = mejorar_con_vision(bd, pasos)

    _fase(bd, cap, "recortando_clips", 75, aviso)
    for i, p in enumerate(pasos, start=1):
        if p.get("t_inicio") is not None and p.get("t_fin") is not None:
            try:
                fin = min(p["t_fin"], p["t_inicio"] + MAX_CLIP)
                p["clip_ruta"] = relativa(video.clip(original, p["t_inicio"], fin, dir_pasos / f"paso_{i:02d}"))
            except video.ErrorVideo:
                log.warning("Sin clip para el paso %s de la captura %s", i, cap.id)
        _fase(bd, cap, "recortando_clips", 75 + int(20 * i / len(pasos)), aviso)

    autor = bd.get(Usuario, cap.autor_id) if cap.autor_id else None
    if tarea is None:
        tarea = _tarea_nueva(bd, autor, cap.titulo or "Tarea capturada")
        cap.tarea_id = tarea.id
    ins = instrucciones.crear_borrador(bd, tarea, cap.autor_id, propuesta, captura_id=cap.id,
                                       video_ruta=cap.ruta_original)
    cap.instruccion_id = ins.id
    cap.resultado = {**resultado, "origen": origen, "pasos": len(pasos), "vision": vision}
    cap.estado, cap.fase, cap.progreso = "borrador_listo", "listo", 100
    registrar(bd, _actor_de(autor), "completo", "captura", cap.id, cap.titulo,
              resultado={"tipo": "video", "pasos": len(pasos), "origen": origen, "instruccion_id": ins.id},
              contexto={"tarea_id": tarea.id})
    bd.commit()
    return {"instruccion_id": ins.id, "pasos": len(pasos), "origen": origen}


# --------------------------------------------------------------------------- fichas (nota de voz y entrevista)


def _markdown(v: Any, nivel: int = 0) -> str:
    """Contenido de la ficha en markdown aunque el modelo lo devuelva como objeto o lista
    ({"Para qué sirve": "...", "Trucos": ["...", "..."]}) en vez de como texto."""
    if v is None or isinstance(v, bool):
        return ""
    if isinstance(v, dict):
        bloques = []
        for clave, valor in v.items():
            cuerpo = _markdown(valor, nivel + 1)
            if cuerpo:
                bloques.append(f"{'#' * min(2 + nivel, 4)} {str(clave).strip()}\n\n{cuerpo}")
        return "\n\n".join(bloques)
    if isinstance(v, list):
        return "\n".join(f"- {x}" for x in (_markdown(e, nivel + 1).strip() for e in v) if x)
    return str(v).strip()


def _etiquetas(v: Any) -> list[str]:
    """Etiquetas en minúsculas y sin repetir; admite una lista o un texto separado por comas."""
    if isinstance(v, str):
        v = re.split(r"[,;\n]", v)
    if not isinstance(v, list):
        return []
    limpias = (_limpio(x, 40).lower().strip(" #") for x in v if isinstance(x, (str, int, float)))
    return list(dict.fromkeys(e for e in limpias if e))[:8]


def proponer_ficha(bd: Session, texto: str, origen: str, tarea: str | None, titulo: str | None,
                   respaldo: str | None = None) -> dict[str, Any]:
    """Ficha {titulo, contenido, etiquetas, origen}. Si el modelo falla, la transcripción ordenada."""
    try:
        datos = llm.chat_json(prompts.mensajes_ficha(origen, tarea, texto), bd=bd)
        if isinstance(datos, list) and len(datos) == 1 and isinstance(datos[0], dict):
            datos = datos[0]  # la ficha dentro de una lista: [{"titulo", "contenido", "etiquetas"}]
        # Respuesta envuelta ({"ficha": {...}}) o con claves en inglés ({"title", "content", "tags"}).
        if isinstance(datos, dict) and len(datos) == 1:
            interior = next(iter(datos.values()))
            if isinstance(interior, dict) and {"contenido", "content"} & set(interior):
                datos = interior
        if isinstance(datos, dict):
            datos = _con_alias(datos, _ALIAS_FICHA)
            contenido = _markdown(datos.get("contenido"))
            if len(contenido) >= 20 and contenido[:1] not in "{[":
                return {"titulo": _limpio(datos.get("titulo"), 300) or titulo or titulo_de(texto),
                        "contenido": contenido[:20000], "etiquetas": _etiquetas(datos.get("etiquetas")),
                        "origen": "modelo"}
    except Exception as e:  # noqa: BLE001
        log.warning("El modelo no ha generado la ficha (%s); se usa el texto tal cual", e)
    return {"titulo": titulo or titulo_de(texto) or "Ficha sin título",
            "contenido": respaldo or f"## Transcripción\n\n{texto.strip()}", "etiquetas": [], "origen": "texto"}


def _crear_ficha(bd: Session, cap: Captura, texto: str, origen: str, respaldo: str | None = None) -> Documento:
    tarea = bd.get(Tarea, cap.tarea_id) if cap.tarea_id else None
    autor = bd.get(Usuario, cap.autor_id) if cap.autor_id else None
    ficha = proponer_ficha(bd, texto, origen, tarea.nombre if tarea else cap.titulo, cap.titulo, respaldo)
    doc = Documento(
        titulo=ficha["titulo"][:300],
        descripcion=f"Ficha de {origen} de {autor.nombre}" if autor else f"Ficha de {origen}",
        tipo="ficha",
        departamento_id=instrucciones.departamento_de(tarea) if tarea else (autor.departamento_id if autor else None),
        nivel_minimo=tarea.nivel_minimo if tarea else 1,
        es_formacion=tarea is not None,
        es_publico=False,
        estado="borrador",
        contenido_texto=ficha["contenido"],
        autor_id=cap.autor_id,
        subido_por_id=cap.autor_id,
        origen="captura",
        origen_id=cap.id,
    )
    bd.add(doc)
    bd.flush()
    cap.documento_id = doc.id
    cap.resultado = {**(cap.resultado or {}), "etiquetas": ficha["etiquetas"], "origen": ficha["origen"]}
    return doc


def procesar_audio(bd: Session, cap: Captura, aviso: Any = None) -> dict[str, Any]:
    original = _original(cap)
    cap.estado, cap.mensaje = "procesando", None
    _fase(bd, cap, "transcribiendo", 20, aviso)
    trans = asr.transcribir(original, con_marcas=True)
    cap.transcripcion = trans
    dur = trans.get("duracion")
    if not dur:
        try:
            dur = video.duracion(original)
        except video.ErrorVideo:
            dur = None
    cap.duracion = round(float(dur), 2) if dur else None
    texto = (trans.get("texto") or "").strip()
    if not texto:
        raise ErrorCaptura("No se ha entendido nada en la nota de voz. Comprueba el micrófono y vuelve a grabarla.")
    _fase(bd, cap, "generando_ficha", 55, aviso)
    doc = _crear_ficha(bd, cap, texto, "nota de voz")
    cap.titulo = cap.titulo or doc.titulo
    cap.estado, cap.fase, cap.progreso = "borrador_listo", "listo", 100
    autor = bd.get(Usuario, cap.autor_id) if cap.autor_id else None
    registrar(bd, _actor_de(autor), "completo", "captura", cap.id, cap.titulo,
              resultado={"tipo": "audio", "documento_id": doc.id}, contexto={"tarea_id": cap.tarea_id})
    bd.commit()
    return {"documento_id": doc.id}


def _ficha_de(bd: Session, cap: Captura) -> Documento:
    doc = bd.get(Documento, cap.documento_id) if cap.documento_id else None
    if doc is None:
        raise HTTPException(404, "Esta captura todavía no tiene ficha.")
    return doc


def editar_ficha(bd: Session, actor: Actor, captura_id: int, datos: dict[str, Any]) -> Captura:
    cap = obtener(bd, actor, captura_id)
    doc = _ficha_de(bd, cap)
    if doc.estado != "borrador":
        raise HTTPException(409, "La ficha ya está publicada.")
    # Como al publicar: la ficha es conocimiento de su departamento (p. ej., si el autor se ha
    # cambiado de departamento, ya no la toca).
    if not instrucciones.puede_gestionar(actor, doc.departamento_id):
        raise HTTPException(403, "Solo puedes editar fichas de tu departamento.")
    if datos.get("titulo") is not None:
        titulo = _limpio(datos["titulo"], 300)
        if not titulo:
            raise HTTPException(400, "La ficha necesita un título.")
        doc.titulo = titulo
    if datos.get("contenido") is not None:
        doc.contenido_texto = str(datos["contenido"]).strip()[:20000]
    if datos.get("etiquetas") is not None:
        etiquetas = [e for e in (_limpio(x, 40).lower() for x in datos["etiquetas"]) if e]
        cap.resultado = {**(cap.resultado or {}), "etiquetas": list(dict.fromkeys(etiquetas))[:10]}
    bd.commit()
    bd.refresh(cap)
    return cap


def publicar_ficha(bd: Session, actor: Actor, captura_id: int) -> Captura:
    """El experto valida la ficha: queda con su autor y validador y se indexa en su departamento."""
    cap = obtener(bd, actor, captura_id)
    doc = _ficha_de(bd, cap)
    bd.refresh(doc, with_for_update=True)  # un doble clic no la publica (ni la indexa) dos veces
    if doc.estado != "borrador":
        raise HTTPException(409, "La ficha ya está publicada.")
    if not instrucciones.puede_gestionar(actor, doc.departamento_id):
        raise HTTPException(403, "Solo puedes publicar fichas de tu departamento.")
    contenido = (doc.contenido_texto or "").strip()
    if len(contenido) < 10:
        raise HTTPException(400, "La ficha está vacía. Escribe su contenido antes de publicarla.")
    etiquetas = (cap.resultado or {}).get("etiquetas") or []
    texto = f"{doc.titulo}\n\n{contenido}" + (f"\n\nEtiquetas: {', '.join(etiquetas)}" if etiquetas else "")
    doc.validador_id = actor.id
    doc.estado = "procesando"
    registrar(bd, actor, "publico", "ficha", doc.id, doc.titulo,
              contexto={"captura_id": cap.id, "departamento_id": doc.departamento_id, "tarea_id": cap.tarea_id})
    bd.commit()
    trabajos.encolar("indexar_documento", documentos.indexar_trabajo, doc.id,
                     [(texto, {"captura_id": cap.id, "tipo": "ficha"})],
                     entidad="documento", entidad_id=doc.id, usuario_id=actor.id)
    bd.refresh(cap)
    return cap


# --------------------------------------------------------------------------- entrevista guiada


def _mensaje(rol: str, texto: str, tema: str, **extra: Any) -> dict[str, Any]:
    return {"rol": rol, "texto": texto, "tema": tema, "momento": ahora().isoformat(), **extra}


def iniciar_entrevista(bd: Session, actor: Actor, tarea_id: int | None = None, tema: str | None = None) -> Captura:
    tema = _limpio(tema, 300)
    tarea = _tarea_para(bd, actor, tarea_id)
    if tarea is None and not tema:
        raise HTTPException(400, "Indica la tarea o el tema de la entrevista.")
    nombre = tarea.nombre if tarea else tema
    cap = Captura(
        tipo="entrevista", autor_id=actor.id, tarea_id=tarea.id if tarea else None, titulo=tema or nombre,
        estado="en_curso", fase="conversando", progreso=0,
        conversacion=[_mensaje("copiloto", prompts.primera_pregunta(nombre), prompts.GUION[0].clave)],
    )
    bd.add(cap)
    bd.flush()
    registrar(bd, actor, "capturo", "captura", cap.id, cap.titulo, resultado={"tipo": "entrevista"},
              contexto={"tarea_id": cap.tarea_id})
    bd.commit()
    bd.refresh(cap)
    return cap


def _pregunta_valida(v: Any, anteriores: set[str] | frozenset[str] = frozenset()) -> str | None:
    """Pregunta utilizable del modelo: con «?», sin JSON y que no repita una ya hecha (los modelos
    pequeños tienden a devolver la última pregunta tal cual)."""
    p = _limpio(v, 400)
    if len(p) < 8 or "?" not in p or p[:1] in "{[":
        return None
    p = p if "¿" in p else "¿" + p
    return None if _clave_pregunta(p) in anteriores else p


def _clave_pregunta(texto: str) -> str:
    return " ".join(re.sub(r"[¿?¡!.,;:«»\"']", " ", (texto or "").lower()).split())


def siguiente_pregunta(bd: Session, nombre: str, conversacion: list[dict[str, Any]], saltada: bool) -> dict[str, Any]:
    """Decide la siguiente intervención del copiloto. El orden del guion lo marca el código; el
    modelo decide si repregunta (como mucho MAX_REPREGUNTAS por tema) y redacta la pregunta
    adaptada a lo que ya se ha contado. Si el modelo falla, se usa la pregunta del guion."""
    actual_clave = _tema_actual(conversacion)
    if actual_clave not in prompts.TEMAS:
        return _mensaje("copiloto", prompts.ANOTADO, "fin")
    claves = [t.clave for t in prompts.GUION]
    i = claves.index(actual_clave)
    actual = prompts.GUION[i]
    siguiente = prompts.GUION[i + 1] if i + 1 < len(prompts.GUION) else None
    respuestas = sum(1 for m in conversacion if m.get("rol") == "experto" and m.get("tema") == actual_clave
                     and not m.get("saltada"))
    decision: Any = None
    if not saltada:
        try:
            decision = llm.chat_json(prompts.mensajes_entrevista(nombre, actual, siguiente, conversacion), bd=bd,
                                     max_tokens=300)
        except Exception as e:  # noqa: BLE001
            log.warning("El modelo no ha propuesto la siguiente pregunta: %s", e)
    repreguntar = isinstance(decision, dict) and _si(decision.get("repreguntar"))
    hechas = {_clave_pregunta(m.get("texto", "")) for m in conversacion if m.get("rol") == "copiloto"}
    pregunta = _pregunta_valida(decision.get("pregunta"), hechas) if isinstance(decision, dict) else None
    if repreguntar and pregunta and respuestas <= MAX_REPREGUNTAS:
        return _mensaje("copiloto", pregunta, actual.clave)
    if siguiente is None:
        return _mensaje("copiloto", prompts.FIN_ENTREVISTA, "fin")
    if pregunta and not repreguntar:
        return _mensaje("copiloto", pregunta, siguiente.clave)
    return _mensaje("copiloto", siguiente.pregunta, siguiente.clave)


def _entrevista_propia(bd: Session, actor: Actor, captura_id: int) -> Captura:
    cap = obtener(bd, actor, captura_id)
    if cap.tipo != "entrevista":
        raise HTTPException(400, "Esta captura no es una entrevista.")
    if cap.autor_id != actor.id:
        raise HTTPException(403, "Solo quien hace la entrevista puede responderla.")
    if cap.estado != "en_curso":
        raise HTTPException(409, "La entrevista ya ha terminado.")
    _exigir_departamento(bd, actor, cap)
    return cap


def responder_entrevista(bd: Session, actor: Actor, captura_id: int, texto: str | None = None,
                         audio: UploadFile | None = None, saltar: bool = False) -> Captura:
    cap = _entrevista_propia(bd, actor, captura_id)
    voz = False
    if audio is not None:
        datos = audio.file.read(MAX_AUDIO_RESPUESTA + 1)
        if len(datos) > MAX_AUDIO_RESPUESTA:
            raise HTTPException(413, "La grabación es demasiado larga. Divide la respuesta en partes.")
        if not datos:
            raise HTTPException(400, "La grabación está vacía.")
        try:
            texto = asr.transcribir(datos, nombre=nombre_seguro(audio.filename or "respuesta.webm"))["texto"]
        except Exception as e:  # noqa: BLE001  (servicio caído, respuesta rara...: nunca un error 500)
            log.warning("No se ha podido transcribir una respuesta de la entrevista %s: %s", captura_id, e)
            raise HTTPException(503, "No se ha podido transcribir el audio. Escribe la respuesta o inténtalo de nuevo.") from e
        voz = True
        if not (texto or "").strip():
            raise HTTPException(400, "No se ha entendido la grabación. Prueba otra vez o escribe la respuesta.")
    texto = (texto or "").strip()
    # Bloquea la fila hasta el commit (después de transcribir, que puede tardar): dos respuestas casi
    # simultáneas (doble clic, dos pestañas) se atienden una detrás de otra sin pisarse.
    bd.refresh(cap, with_for_update=True)
    if cap.estado != "en_curso":
        raise HTTPException(409, "La entrevista ya ha terminado.")
    conversacion = list(cap.conversacion or [])
    if len(conversacion) >= MAX_MENSAJES:  # después del guion se puede seguir añadiendo, pero no sin fin
        raise HTTPException(409, "La entrevista ya es muy larga. Termínala para generar el borrador.")
    tema = _tema_actual(conversacion)
    if saltar and tema != "fin":
        conversacion.append(_mensaje("experto", "", tema, saltada=True))
    else:
        if not texto:
            raise HTTPException(400, "Escribe o graba una respuesta.")
        conversacion.append(_mensaje("experto", texto[:6000], tema if tema != "fin" else "extra", voz=voz))
    tarea = bd.get(Tarea, cap.tarea_id) if cap.tarea_id else None
    nombre = (tarea.nombre if tarea else cap.titulo) or "la tarea"
    conversacion.append(siguiente_pregunta(bd, nombre, conversacion, saltar))
    cap.conversacion = conversacion
    cap.progreso = _progreso_entrevista(conversacion)
    bd.commit()
    bd.refresh(cap)
    return cap


def finalizar_entrevista(bd: Session, actor: Actor, captura_id: int, generar: str = "ficha") -> Captura:
    """Cierra la entrevista y encola la generación de la ficha (o del borrador de instrucción)."""
    if generar not in ("ficha", "instruccion"):
        raise HTTPException(400, "Elige si quieres generar una ficha o un borrador de instrucción.")
    cap = _entrevista_propia(bd, actor, captura_id)
    # Con la fila bloqueada, un doble clic no encola dos generaciones (ni dos fichas).
    bd.refresh(cap, with_for_update=True)
    if cap.estado != "en_curso":
        raise HTTPException(409, "La entrevista ya ha terminado.")
    respuestas = [m for m in cap.conversacion or [] if m.get("rol") == "experto" and (m.get("texto") or "").strip()]
    if not respuestas:
        raise HTTPException(400, "Responde al menos a una pregunta antes de terminar.")
    cap.resultado = {**(cap.resultado or {}), "generar": generar}
    cap.estado, cap.fase, cap.progreso, cap.mensaje = "procesando", "generando_ficha", 10, None
    registrar(bd, actor, "completo", "captura", cap.id, cap.titulo,
              resultado={"tipo": "entrevista", "respuestas": len(respuestas), "generar": generar},
              contexto={"tarea_id": cap.tarea_id})
    bd.commit()
    _encolar(cap)
    bd.refresh(cap)
    return cap


def _instruccion_de_entrevista(conversacion: list[dict[str, Any]], nombre: str | None) -> dict[str, Any]:
    """Plan B sin modelo: los pasos salen de las frases de la respuesta sobre los pasos."""
    por_tema: dict[str, str] = {}
    for m in conversacion:
        if m.get("rol") == "experto" and (m.get("texto") or "").strip():
            por_tema[m.get("tema", "")] = (por_tema.get(m.get("tema", ""), "") + " " + m["texto"].strip()).strip()
    frases = [f.strip() for f in re.split(r"(?<=[.;!?])\s+|\n+", por_tema.get("pasos", "")) if len(f.strip()) > 3]
    pasos = [{"titulo": titulo_de(f), "texto": f, "es_critico": False, "es_seguridad": False,
              "criterio_aceptacion": ""} for f in frases[:MAX_PASOS]]
    if pasos and por_tema.get("calidad"):
        pasos[-1]["criterio_aceptacion"] = por_tema["calidad"][:1000]
    if not pasos:
        pasos = [{"titulo": "Paso 1", "texto": "", "es_critico": False, "es_seguridad": False, "criterio_aceptacion": ""}]
    return {"titulo": nombre or "", "resumen": por_tema.get("objetivo", "")[:3000],
            "riesgos": por_tema.get("puntos_criticos", "")[:3000], "epis": "",
            "herramientas": por_tema.get("preparacion", "")[:3000], "pasos": pasos}


def _ficha_de_entrevista(conversacion: list[dict[str, Any]]) -> str | None:
    """Plan B sin modelo: la entrevista tal cual, con una sección por tema."""
    bloques: list[str] = []
    pregunta = ""
    for m in conversacion:
        if m.get("rol") == "copiloto":
            pregunta = m.get("texto", "")
        elif (m.get("texto") or "").strip():
            tema = prompts.TEMAS.get(m.get("tema", ""))
            bloques.append(f"## {tema.titulo if tema else 'Otros comentarios'}\n\n**{pregunta}**\n\n{m['texto'].strip()}")
    return "\n\n".join(bloques) or None


def procesar_entrevista(bd: Session, cap: Captura, aviso: Any = None) -> dict[str, Any]:
    generar = (cap.resultado or {}).get("generar", "ficha")
    conversacion = cap.conversacion or []
    texto = prompts.conversacion_a_texto(conversacion)
    _fase(bd, cap, "generando_ficha", 30, aviso)
    tarea = bd.get(Tarea, cap.tarea_id) if cap.tarea_id else None
    nombre = tarea.nombre if tarea else cap.titulo
    autor = bd.get(Usuario, cap.autor_id) if cap.autor_id else None
    salida: dict[str, Any]
    if generar == "instruccion":
        try:
            datos = llm.chat_json(prompts.mensajes_instruccion(nombre, texto), bd=bd)
            propuesta = normalizar_propuesta(datos, None, con_tiempos=False)
        except Exception as e:  # noqa: BLE001
            log.warning("El modelo no ha generado la instrucción de la entrevista: %s", e)
            propuesta = None
        origen = "modelo" if propuesta else "texto"
        propuesta = propuesta or _instruccion_de_entrevista(conversacion, nombre)
        propuesta["titulo"] = propuesta.get("titulo") or nombre or ""
        if tarea is None:
            tarea = _tarea_nueva(bd, autor, nombre or "Tarea de una entrevista")
            cap.tarea_id = tarea.id
        ins = instrucciones.crear_borrador(bd, tarea, cap.autor_id, propuesta, captura_id=cap.id)
        cap.instruccion_id = ins.id
        cap.resultado = {**(cap.resultado or {}), "origen": origen}
        salida = {"instruccion_id": ins.id}
    else:
        doc = _crear_ficha(bd, cap, texto, "entrevista", respaldo=_ficha_de_entrevista(conversacion))
        salida = {"documento_id": doc.id}
    cap.estado, cap.fase, cap.progreso = "borrador_listo", "listo", 100
    registrar(bd, _actor_de(autor), "completo", "captura", cap.id, cap.titulo,
              resultado={"tipo": "entrevista", **salida}, contexto={"tarea_id": cap.tarea_id})
    bd.commit()
    return salida


# --------------------------------------------------------------------------- trabajos en segundo plano


def _trabajo(procesar: Any, bd: Session, aviso: Any, captura_id: int) -> dict[str, Any]:
    """Envoltorio común: si algo falla, la captura queda en «error» con un mensaje comprensible."""
    cap = bd.get(Captura, captura_id)
    if cap is None:
        return {"error": "La captura ya no existe."}
    try:
        return procesar(bd, cap, aviso)
    except Exception as e:
        log.exception("Falló el procesado de la captura %s", captura_id)
        bd.rollback()
        cap = bd.get(Captura, captura_id)
        if cap is not None:
            cap.estado = "error"
            cap.mensaje = _mensaje_error(e)
            bd.commit()
        raise


def procesar_video_trabajo(bd: Session, aviso: Any, captura_id: int) -> dict[str, Any]:
    return _trabajo(procesar_video, bd, aviso, captura_id)


def procesar_audio_trabajo(bd: Session, aviso: Any, captura_id: int) -> dict[str, Any]:
    return _trabajo(procesar_audio, bd, aviso, captura_id)


def procesar_entrevista_trabajo(bd: Session, aviso: Any, captura_id: int) -> dict[str, Any]:
    return _trabajo(procesar_entrevista, bd, aviso, captura_id)
