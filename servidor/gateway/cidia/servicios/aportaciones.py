"""Aportaciones desde la planta: el conocimiento que nace al resolver un problema.

Flujo: alguien cuenta lo que ha resuelto (texto o nota de voz) → se guarda en estado
«procesando» → un trabajo en segundo plano transcribe el audio y el LLM lo ordena en
título, problema, causa, solución, etiquetas y nivel mínimo sugerido → «pendiente» → el jefe
de su departamento lo valida (se publica como pregunta frecuente con autor y validador), lo
corrige o lo rechaza con un motivo que el autor verá.

Los modelos pequeños fallan a menudo con el JSON: `ordenar()` nunca lanza; si no puede
interpretar la respuesta usa un respaldo (título = primera frase, solución = texto completo)
y el jefe lo corrige al revisar.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session

from cidia import trabajos
from cidia.ficheros import guardar_subida, ruta_absoluta
from cidia.ia import asr, llm
from cidia.modelos import Aportacion, Departamento, Documento, Laguna, Nivel, Puesto, Tarea, Usuario, ahora
from cidia.seguridad import Actor, url_fichero
from cidia.servicios import documentos, iluo, lagunas
from cidia.xapi import auditar, registrar

log = logging.getLogger("cidia.aportaciones")

ESTADOS = ("procesando", "pendiente", "validada", "rechazada")
ABIERTAS = ("procesando", "pendiente")  # aún no revisadas: el autor puede retirarlas

MIN_TEXTO = 15
MAX_TEXTO = 8000
MAX_AUDIO = 25 * 1024 * 1024  # una nota de 2 min en opus ocupa ~1 MB; margen para wav
EXT_AUDIO = {".webm", ".ogg", ".oga", ".opus", ".mp3", ".wav", ".m4a", ".mp4", ".aac", ".flac"}
# Extensión con la que se guarda según el tipo que declara el navegador (si el nombre no trae una válida).
EXT_POR_TIPO = {
    "audio/webm": ".webm", "video/webm": ".webm", "audio/ogg": ".ogg", "audio/opus": ".opus", "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/wave": ".wav", "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a", "audio/aac": ".aac", "audio/flac": ".flac", "audio/x-flac": ".flac",
}
ATASCADA = timedelta(minutes=15)  # si sigue «procesando» pasado este tiempo, se rescata

# Respuestas de relleno que algunos modelos copian literalmente del esquema.
_RELLENO = {"", "...", "…", "string", "texto", "n/a", "na", "ninguno", "ninguna", "null", "none", "-", "desconocido"}

PROMPT_SISTEMA = (
    "Eres CidIA, el asistente de conocimiento de una planta industrial. Un trabajador cuenta con sus "
    "palabras un problema que ha resuelto. Ordénalo como una ficha breve para que sus compañeros "
    "puedan resolverlo la próxima vez.\n"
    "Responde SOLO con un objeto JSON con estas claves:\n"
    '- "titulo": frase corta (máximo 12 palabras) que describa el problema.\n'
    '- "problema": qué pasaba, en una o dos frases.\n'
    '- "causa": por qué pasaba. Cadena vacía si el relato no lo dice.\n'
    '- "solucion": qué hay que hacer para resolverlo. Si hay varios pasos, uno por línea empezando por "- ".\n'
    '- "etiquetas": lista de 1 a 5 palabras clave copiadas del relato: el nombre de la máquina, '
    "de la pieza, del código o de la herramienta que se mencione.\n"
    '- "nivel_minimo": número del 1 al 4 con el nivel mínimo que debe conocerlo '
    "(1 operario, 2 técnico, 3 responsable, 4 dirección). Casi siempre 1.\n"
    "Reglas: escribe en castellano, con frases cortas y claras. Usa solo lo que dice el relato: "
    "no inventes datos, medidas ni códigos. Respeta los nombres de máquinas y códigos tal y como aparecen."
)


# --------------------------------------------------------------------------- utilidades de texto


def sin_nulos(s: str | None) -> str:
    """Quita el carácter NUL, que PostgreSQL no admite en un texto (daría un error 500)."""
    return (s or "").replace("\x00", "")


def _sin_acentos(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _clave(k: Any) -> str:
    """'Solución ' → 'solucion'; 'Nivel mínimo' → 'nivel_minimo'."""
    return re.sub(r"[^a-z0-9]+", "_", _sin_acentos(str(k)).lower()).strip("_")


_RELLENO_CLAVES = {_clave(r) for r in _RELLENO}
_ETIQUETA_CAMPO = re.compile(r"^\s*(t[ií]tulo|problema|causa|soluci[oó]n)\s*:\s*", re.I)


def _es_relleno(s: str) -> bool:
    return _clave(s) in _RELLENO_CLAVES


def _texto(v: Any) -> str:
    """Convierte lo que devuelva el modelo (cadena, lista, objeto) en texto limpio."""
    if v is None or isinstance(v, bool):
        return ""
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        s = _ETIQUETA_CAMPO.sub("", v.strip()).strip()  # «Solución: ...» dentro del valor
        return "" if _es_relleno(s) else s
    if isinstance(v, list):
        partes = [_texto(x) for x in v]
        partes = [p for p in partes if p]
        if len(partes) <= 1:
            return partes[0] if partes else ""
        return "\n".join(p if p.startswith("- ") else f"- {p}" for p in partes)
    if isinstance(v, dict):
        return "\n".join(t for t in (_texto(x) for x in v.values()) if t)
    return str(v).strip()


def primera_frase(texto: str, maximo: int = 100) -> str:
    """Primera frase de un texto, recortada, para usarla como título."""
    t = re.sub(r"\s+", " ", texto or "").strip()
    if not t:
        return "Aportación sin título"
    frase = re.split(r"(?<=[.!?…])\s+|[\n\r]", t, maxsplit=1)[0].strip(" .")
    if len(frase) > maximo:
        corte = frase[:maximo].rsplit(" ", 1)[0]
        frase = corte + "…"
    return frase[:1].upper() + frase[1:]


def limpiar_etiquetas(v: Any, maximo: int = 6) -> list[str]:
    if isinstance(v, str):
        partes = re.split(r"[,;\n#]+", v)
    elif isinstance(v, list):
        partes = [_texto(x) for x in v]
    else:
        partes = []
    salida: list[str] = []
    vistas: set[str] = set()
    for p in partes:
        p = re.sub(r"\s+", " ", p).strip(" .-·\"'#«»").strip()
        if not p or len(p) > 40 or _es_relleno(p) or p.lower() in vistas:
            continue
        vistas.add(p.lower())
        salida.append(p)
    return salida[:maximo]


_NIVELES_TEXTO = (("operari", 1), ("tecnic", 2), ("responsabl", 3), ("jefe", 3), ("direcc", 4), ("director", 4))


def _nivel(v: Any, maximo: int) -> int:
    n = 1
    if isinstance(v, bool) or v is None:
        n = 1
    elif isinstance(v, (int, float)):
        n = int(v)
    else:
        s = _clave(v)
        m = re.search(r"\d", s)
        if m:
            n = int(m.group())
        else:
            n = next((valor for raiz, valor in _NIVELES_TEXTO if raiz in s), 1)
    return max(1, min(maximo, n))


def nivel_maximo(bd: Session) -> int:
    return bd.scalar(select(func.max(Nivel.orden))) or 4


# --------------------------------------------------------------------------- ordenar con el LLM

_SINONIMOS: dict[str, tuple[str, ...]] = {
    "titulo": ("titulo", "title", "asunto", "nombre", "encabezado"),
    "problema": ("problema", "problem", "sintoma", "sintomas", "descripcion", "que_pasaba", "incidencia"),
    "causa": ("causa", "cause", "causa_raiz", "causas", "motivo", "por_que"),
    "solucion": ("solucion", "solution", "resolucion", "como_se_resolvio", "pasos", "respuesta", "soluciones"),
    "etiquetas": ("etiquetas", "tags", "palabras_clave", "keywords", "etiqueta", "claves"),
    "nivel_minimo": ("nivel_minimo", "nivel", "level", "nivel_sugerido", "min_level", "nivel_recomendado"),
}


def _campos(datos: Any) -> dict[str, Any]:
    """Busca las claves esperadas aunque vengan con acentos, en inglés o envueltas en otro objeto."""
    if isinstance(datos, list):
        datos = next((d for d in datos if isinstance(d, dict)), None)
    if not isinstance(datos, dict):
        return {}
    por_clave = {_clave(k): v for k, v in datos.items()}
    encontrados = {campo: next((por_clave[s] for s in sinonimos if s in por_clave), None)
                   for campo, sinonimos in _SINONIMOS.items()}
    if not any(v is not None for v in encontrados.values()):
        # {"ficha": {...}}: algunos modelos envuelven la respuesta.
        internos = [v for v in datos.values() if isinstance(v, dict)]
        if len(internos) == 1:
            return _campos(internos[0])
    return encontrados


def respaldo(texto: str) -> dict[str, Any]:
    """Ficha mínima cuando el modelo no ayuda: el jefe la completará al revisar."""
    t = (texto or "").strip()
    return {"titulo": primera_frase(t), "problema": "", "causa": "", "solucion": t, "etiquetas": [],
            "nivel_minimo": 1, "ordenada_por_ia": False}


# Palabras frecuentes que no sirven para comprobar si un campo sale del relato.
_VACIAS = {
    "para", "pero", "como", "cuando", "esta", "este", "esto", "estos", "estas", "porque", "donde", "desde",
    "sobre", "entre", "hasta", "tambien", "cada", "todo", "toda", "todos", "todas", "otro", "otra", "hace",
    "hacer", "debe", "deben", "tras", "luego", "despues", "antes", "bien", "solo", "algo", "nada", "mas",
    "menos", "tiene", "tienen", "puede", "pueden", "eso", "ese", "esa", "aqui", "alli", "entonces", "pues",
    "listo", "vez", "veces", "hay", "que", "del", "los", "las", "una", "uno", "unos", "unas", "por", "con", "sin",
}
# Respuestas genéricas que los modelos pequeños copian del propio enunciado.
_GENERICAS = {"maquina", "maquinas", "pieza", "piezas", "codigo", "codigos", "herramienta", "herramientas",
              "problema", "problemas", "solucion", "causa", "titulo", "etiqueta", "etiquetas", "aportacion",
              "ficha", "incidencia", "palabras_clave", "palabra_clave"}


def _raices(texto: str) -> set[str]:
    """Raíces (5 letras, sin acentos) de las palabras con contenido; los códigos con cifras cuentan siempre."""
    palabras = re.findall(r"\w+", _sin_acentos(texto or "").lower())
    return {p[:5] for p in palabras
            if p not in _VACIAS and (len(p) >= 4 or any(ch.isdigit() for ch in p))}


def _apoyo(campo: str, base: set[str]) -> float:
    """Parte de las palabras de `campo` que aparecen en el relato (0..1). Detecta invenciones."""
    propias = _raices(campo)
    return len(propias & base) / len(propias) if propias else 1.0


def normalizar(datos: Any, texto: str, maximo_nivel: int = 4, referencia: str | None = None) -> dict[str, Any]:
    """Convierte la respuesta del modelo en una ficha válida (o en el respaldo).

    Los modelos pequeños a veces inventan: cada campo se contrasta con el relato (más la tarea y
    la pregunta, en `referencia`). Una causa sin apoyo se descarta; una solución sin apoyo se
    sustituye por el relato completo, que es lo que de verdad dijo la persona."""
    texto = (texto or "").strip()
    base = _raices(f"{texto} {referencia or ''}")
    c = _campos(datos)
    problema = _texto(c.get("problema"))
    if problema and _apoyo(problema, base) < 0.5:
        problema = ""
    causa = _texto(c.get("causa"))
    if causa and _apoyo(causa, base) < 0.6:
        causa = ""
    solucion = _texto(c.get("solucion"))
    if solucion and _apoyo(solucion, base) < 0.5:
        solucion = ""
    if not problema and not solucion:
        return respaldo(texto)
    titulo = _texto(c.get("titulo")).replace("\n", " ").strip(" .\"'«»")
    if not titulo or _clave(titulo) in _GENERICAS or len(titulo.split()) < 2:
        titulo = primera_frase(problema or texto)
    if len(titulo) > 120:
        titulo = titulo[:119].rsplit(" ", 1)[0] + "…"
    etiquetas = [e for e in limpiar_etiquetas(c.get("etiquetas"))
                 if _clave(e) not in _GENERICAS and _apoyo(e, base) >= 0.5]
    return {
        "titulo": titulo[:1].upper() + titulo[1:],
        "problema": problema,
        "causa": causa,
        "solucion": solucion or texto,
        "etiquetas": etiquetas,
        "nivel_minimo": _nivel(c.get("nivel_minimo"), maximo_nivel),
        "ordenada_por_ia": True,
    }


def ordenar(bd: Session | None, texto: str, tarea: Tarea | None = None, pregunta: str | None = None,
            maximo_nivel: int = 4, modelo: str | None = None) -> dict[str, Any]:
    """Pide al LLM la ficha estructurada. Nunca lanza: si algo falla, devuelve el respaldo.

    Si se pasa `modelo` (ya comprobado como permitido) no se toca la BD durante la llamada."""
    texto = (texto or "").strip()
    if not texto:
        return respaldo("")
    contexto = []
    if tarea is not None:
        contexto.append(f"Tarea relacionada: {tarea.codigo + ' · ' if tarea.codigo else ''}{tarea.nombre}.")
    if pregunta:
        contexto.append(f"Responde a esta pregunta pendiente de sus compañeros: «{pregunta}».")
    usuario = ("\n".join(contexto) + "\n\n" if contexto else "") + f"Relato del trabajador:\n<<<\n{texto[:MAX_TEXTO]}\n>>>"
    mensajes = [{"role": "system", "content": PROMPT_SISTEMA}, {"role": "user", "content": usuario}]
    try:
        datos = llm.chat_json(mensajes, modelo=modelo, bd=None if modelo else bd, max_tokens=900)
    except Exception as e:  # noqa: BLE001  (modelo caído, JSON roto, modelo no permitido...)
        log.warning("No se pudo ordenar la aportación con el modelo: %s", e)
        return respaldo(texto)
    try:
        return normalizar(datos, texto, maximo_nivel, referencia=" ".join(contexto))
    except Exception:  # noqa: BLE001
        log.exception("Respuesta del modelo inesperada al ordenar una aportación")
        return respaldo(texto)


# --------------------------------------------------------------------------- permisos


def puede_gestionar(actor: Actor, ap: Aportacion) -> bool:
    """Jefe de su departamento o administración."""
    if actor.es_admin:
        return True
    return actor.rol == "jefe" and ap.departamento_id is not None and ap.departamento_id == actor.departamento_id


def puede_ver(actor: Actor, ap: Aportacion) -> bool:
    return ap.autor_id == actor.id or puede_gestionar(actor, ap)


def obtener(bd: Session, actor: Actor, aportacion_id: int, gestionar: bool = False,
            bloquear: bool = False) -> Aportacion:
    """Carga una aportación visible para el actor. Si no puede verla, como si no existiera (404).

    Con `bloquear` la fila queda reservada (SELECT ... FOR UPDATE) hasta el commit: dos jefes que
    validan a la vez no publican dos preguntas frecuentes; el segundo recibe «ya no está pendiente»."""
    ap = bd.get(Aportacion, aportacion_id, with_for_update=True) if bloquear else bd.get(Aportacion, aportacion_id)
    if ap is None or not (puede_gestionar(actor, ap) if gestionar else puede_ver(actor, ap)):
        raise HTTPException(404, "Aportación no encontrada.")
    return ap


def departamento_de_tarea(bd: Session, tarea_id: int) -> int | None:
    return bd.scalar(select(Puesto.departamento_id).join(Tarea, Tarea.puesto_id == Puesto.id).where(Tarea.id == tarea_id))


def tareas_de(bd: Session, departamento_id: int | None, todas: bool = False) -> list[dict[str, Any]]:
    """Tareas activas de un departamento (o de toda la planta) para los selectores."""
    q = (select(Tarea, Puesto).join(Puesto, Tarea.puesto_id == Puesto.id).where(Tarea.activa.is_(True))
         .order_by(Tarea.codigo, Tarea.nombre))
    if not todas:
        if departamento_id is None:
            return []
        q = q.where(Puesto.departamento_id == departamento_id)
    return [{"id": t.id, "codigo": t.codigo, "nombre": t.nombre, "puesto": p.nombre, "departamento_id": p.departamento_id}
            for t, p in bd.execute(q).all()]


def _comprobar_tarea(bd: Session, actor: Actor, tarea_id: int, departamento_id: int | None) -> None:
    dep = departamento_de_tarea(bd, tarea_id)
    if dep is None and bd.get(Tarea, tarea_id) is None:
        raise HTTPException(404, "La tarea indicada no existe.")
    if not actor.es_admin and dep != departamento_id:
        raise HTTPException(400, "Esa tarea no es de tu departamento.")


# --------------------------------------------------------------------------- alta y procesado


def extension_audio(audio: UploadFile) -> str:
    """Extensión de audio válida para la nota (o 400 si no parece audio).

    El fichero se guarda SIEMPRE con esta extensión y no con el nombre que manda el navegador:
    /api/ficheros deduce el tipo por la extensión y una «nota.html» se serviría como página web."""
    nombre = (audio.filename or "").lower()
    ext = nombre[nombre.rfind("."):] if "." in nombre else ""
    tipo = (audio.content_type or "").lower().split(";")[0].strip()
    if not (tipo.startswith("audio/") or tipo == "video/webm" or ext in EXT_AUDIO):
        raise HTTPException(400, "La nota de voz no tiene un formato de audio reconocible.")
    return ext if ext in EXT_AUDIO else EXT_POR_TIPO.get(tipo, ".webm")


def crear(
    bd: Session,
    actor: Actor,
    texto: str | None,
    tarea_id: int | None = None,
    laguna_id: int | None = None,
    audio: UploadFile | None = None,
    duracion: float | None = None,
) -> Aportacion:
    """Guarda la aportación en estado «procesando» y encola su procesado. Hace commit."""
    texto = sin_nulos(texto).strip()
    if len(texto) > MAX_TEXTO:
        raise HTTPException(400, f"El texto es demasiado largo (máximo {MAX_TEXTO} caracteres).")
    if audio is None and len(texto) < MIN_TEXTO:
        raise HTTPException(400, "Cuéntalo con un poco más de detalle: qué pasaba y cómo lo resolviste.")
    ext_audio = extension_audio(audio) if audio is not None else ""
    if audio is not None and (getattr(audio, "size", None) or 0) > MAX_AUDIO:
        raise HTTPException(413, "La nota de voz es demasiado grande (máximo 25 MB).")

    # La aportación es del departamento de quien la envía. Solo la administración (que no suele
    # tener departamento) la asigna al de la pregunta o la tarea que responde.
    departamento_id = actor.departamento_id
    laguna: Laguna | None = None
    if laguna_id is not None:
        laguna = bd.get(Laguna, laguna_id)
        visible = laguna is not None and (
            actor.es_admin or (laguna.departamento_id is not None and laguna.departamento_id == actor.departamento_id))
        if laguna is None or not visible:
            raise HTTPException(404, "Esa pregunta pendiente no existe en tu departamento.")
        if laguna.estado != "abierta":
            raise HTTPException(409, "Esa pregunta ya no está pendiente: alguien la respondió o se descartó.")
        if actor.es_admin and departamento_id is None:
            departamento_id = laguna.departamento_id
        if tarea_id is None and laguna.tarea_id and bd.get(Tarea, laguna.tarea_id) is not None:
            tarea_id = laguna.tarea_id  # hereda la tarea de la pregunta
    if tarea_id is not None:
        if actor.es_admin and departamento_id is None:
            departamento_id = departamento_de_tarea(bd, tarea_id)
        # Un empleado sin departamento no puede colar su aportación en la bandeja de otro.
        _comprobar_tarea(bd, actor, tarea_id, departamento_id)

    ruta = None
    if audio is not None:
        audio.filename = f"nota-de-voz{ext_audio}"
        ruta, _, tam = guardar_subida(audio, "aportaciones")
        if tam == 0 or tam > MAX_AUDIO:
            ruta_absoluta(ruta).unlink(missing_ok=True)
            if tam == 0:
                raise HTTPException(400, "La nota de voz está vacía. Vuelve a grabarla.")
            raise HTTPException(413, "La nota de voz es demasiado grande (máximo 25 MB).")

    ap = Aportacion(
        autor_id=actor.id,
        departamento_id=departamento_id,
        tarea_id=tarea_id,
        laguna_id=laguna.id if laguna else None,
        texto_original=texto or None,
        audio_ruta=ruta,
        duracion_audio=duracion if duracion and duracion > 0 else None,
        estado="procesando",
        etiquetas=[],
        nivel_minimo=1,
    )
    bd.add(ap)
    bd.flush()
    registrar(bd, actor, "aporto", "aportacion", ap.id, primera_frase(texto) if texto else "Nota de voz",
              contexto={"via": "voz" if ruta else "texto", "tarea_id": tarea_id, "laguna_id": ap.laguna_id,
                        "estado": "enviada"})
    bd.commit()
    trabajos.encolar("procesar_aportacion", procesar_trabajo, ap.id, entidad="aportacion", entidad_id=ap.id,
                     usuario_id=actor.id)
    return ap


def _aplicar(ap: Aportacion, ficha: dict[str, Any]) -> None:
    ap.titulo = sin_nulos(ficha.get("titulo"))[:300] or None
    ap.problema = sin_nulos(ficha.get("problema")) or None
    ap.causa = sin_nulos(ficha.get("causa")) or None
    ap.solucion = sin_nulos(ficha.get("solucion")) or None
    ap.etiquetas = [sin_nulos(str(e)) for e in ficha.get("etiquetas") or []]
    ap.nivel_minimo = int(ficha.get("nivel_minimo") or 1)


def procesar_trabajo(bd: Session, progreso: Any, aportacion_id: int) -> dict[str, Any]:
    """Trabajo en segundo plano: transcribe (si hay audio) y ordena con el LLM. Deja «pendiente»."""
    ap = bd.get(Aportacion, aportacion_id)
    if ap is None or ap.estado != "procesando":
        return {"omitida": True}
    tarea = bd.get(Tarea, ap.tarea_id) if ap.tarea_id else None
    laguna = bd.get(Laguna, ap.laguna_id) if ap.laguna_id else None
    pregunta = laguna.pregunta if laguna else None
    maximo = nivel_maximo(bd)
    try:
        modelo: str | None = llm.modelo_permitido(bd, "chat")
    except Exception:  # noqa: BLE001  (sin modelo permitido: ordenar() usará el respaldo)
        modelo = None
    bd.commit()  # no se deja una transacción abierta mientras trabajan los modelos
    transcripcion: str | None = None
    duracion: float | None = None
    if ap.audio_ruta:
        progreso(15, "Transcribiendo la nota de voz")
        try:
            r = asr.transcribir(ruta_absoluta(ap.audio_ruta))
            transcripcion = (r.get("texto") or "").strip() or None
            duracion = r.get("duracion")
        except Exception as e:  # noqa: BLE001  (el jefe podrá escuchar el audio igualmente)
            log.warning("No se pudo transcribir la aportación %s: %s", ap.id, e)
    relato = "\n\n".join(t for t in (ap.texto_original, transcripcion) if t)
    progreso(55, "Ordenando en problema, causa y solución")
    if relato:
        ficha = ordenar(None if modelo else bd, relato, tarea, pregunta, maximo, modelo=modelo)
    else:
        ficha = respaldo("")
        ficha["titulo"] = "Nota de voz sin transcribir"
        ficha["solucion"] = ""
    # Mientras tanto pudo retirarse, rechazarse o rescatarse: solo se escribe si sigue en proceso.
    # La fila se bloquea al releerla para que un rechazo simultáneo no quede pisado.
    try:
        bd.refresh(ap, with_for_update=True)
    except InvalidRequestError:  # la retiró su autor (ya no existe)
        return {"omitida": True}
    if ap.estado != "procesando":
        return {"omitida": True}
    ap.transcripcion = transcripcion
    if duracion:
        ap.duracion_audio = float(duracion)
    _aplicar(ap, ficha)
    ap.estado = "pendiente"
    bd.flush()
    return {"estado": ap.estado, "ordenada_por_ia": ficha.get("ordenada_por_ia", False)}


def rescatar_atascadas(bd: Session) -> int:
    """Las que llevan demasiado tiempo «procesando» (p. ej. por un reinicio) pasan a pendientes
    con la ficha de respaldo, para que no queden bloqueadas. Hace commit si cambia algo."""
    atascadas = bd.scalars(
        select(Aportacion).where(Aportacion.estado == "procesando", Aportacion.creada < ahora() - ATASCADA)
    ).all()
    for ap in atascadas:
        _aplicar(ap, respaldo(ap.texto_original or ap.transcripcion or ""))
        if not ap.texto_original and not ap.transcripcion:
            ap.titulo, ap.solucion = "Nota de voz sin transcribir", None
        ap.estado = "pendiente"
    if atascadas:
        bd.commit()
    return len(atascadas)


# --------------------------------------------------------------------------- revisión del jefe

CAMPOS_EDITABLES = ("titulo", "problema", "causa", "solucion", "etiquetas", "nivel_minimo", "tarea_id")


def editar(bd: Session, actor: Actor, ap: Aportacion, cambios: dict[str, Any]) -> None:
    """Aplica los cambios del jefe (solo los campos presentes en `cambios`). No hace commit."""
    if ap.estado != "pendiente":
        raise HTTPException(409, "Solo se pueden editar aportaciones pendientes de validar.")
    for campo in ("titulo", "problema", "causa", "solucion"):
        if campo in cambios:
            valor = sin_nulos(cambios[campo]).strip()
            limite = 300 if campo == "titulo" else MAX_TEXTO
            if len(valor) > limite:
                nombre = {"titulo": "título", "solucion": "solución"}.get(campo, campo)
                raise HTTPException(400, f"El campo «{nombre}» es demasiado largo (máximo {limite} caracteres).")
            if campo == "titulo" and not valor:
                raise HTTPException(400, "El título no puede quedar vacío.")
            setattr(ap, campo, valor or None)
    if "etiquetas" in cambios:
        ap.etiquetas = limpiar_etiquetas([sin_nulos(str(e)) for e in cambios["etiquetas"] or []], maximo=10)
    if "nivel_minimo" in cambios and cambios["nivel_minimo"] is not None:
        n = int(cambios["nivel_minimo"])
        if n < 1 or n > nivel_maximo(bd):
            raise HTTPException(400, "Ese nivel no existe.")
        ap.nivel_minimo = n
    if "tarea_id" in cambios:
        tid = cambios["tarea_id"]
        if tid is not None:
            _comprobar_tarea(bd, actor, tid, ap.departamento_id)
        ap.tarea_id = tid
    campos = sorted(k for k in cambios if k in CAMPOS_EDITABLES)
    if campos:  # un envío vacío no deja rastro en la auditoría
        auditar(bd, actor, "editar_aportacion", "aportacion", ap.id, {"campos": campos})


def texto_faq(bd: Session, ap: Aportacion) -> str:
    """Texto que se indexa: Problema / Causa / Solución, más lo que ayuda a encontrarlo."""
    lineas: list[str] = []
    laguna = bd.get(Laguna, ap.laguna_id) if ap.laguna_id else None
    if laguna is not None:
        lineas.append(f"Pregunta: {laguna.pregunta}")
    if ap.problema:
        lineas.append(f"Problema: {ap.problema}")
    if ap.causa:
        lineas.append(f"Causa: {ap.causa}")
    lineas.append(f"Solución: {ap.solucion}")
    tarea = bd.get(Tarea, ap.tarea_id) if ap.tarea_id else None
    if tarea is not None:
        lineas.append(f"Tarea: {tarea.codigo + ' · ' if tarea.codigo else ''}{tarea.nombre}")
    if ap.etiquetas:
        lineas.append("Etiquetas: " + ", ".join(str(e) for e in ap.etiquetas))
    return "\n\n".join(lineas)


def validar(bd: Session, actor: Actor, ap: Aportacion) -> Documento:
    """Publica la aportación como pregunta frecuente de su departamento. Hace commit."""
    if ap.estado != "pendiente":
        raise HTTPException(409, "Esta aportación ya no está pendiente de validar.")
    if ap.autor_id == actor.id and not actor.es_admin:
        raise HTTPException(403, "No puedes validar tu propia aportación: pídeselo a otro responsable.")
    if not (ap.solucion or "").strip():
        raise HTTPException(400, "Añade la solución antes de validar.")
    if not (ap.titulo or "").strip():
        ap.titulo = primera_frase(ap.problema or ap.solucion or "")
    autor = bd.get(Usuario, ap.autor_id)
    ap.estado = "validada"
    ap.validador_id = actor.id
    ap.validada_en = ahora()
    ap.motivo_rechazo = None
    # Hace commit (incluye los cambios de la aportación) y encola el indexado.
    doc = documentos.crear_desde_texto(
        bd,
        titulo=ap.titulo or "Pregunta frecuente",
        texto=texto_faq(bd, ap),
        tipo="faq",
        departamento_id=ap.departamento_id,
        nivel_minimo=ap.nivel_minimo or 1,
        autor_id=ap.autor_id,
        validador_id=actor.id,
        subido_por_id=actor.id,
        origen="aportacion",
        origen_id=ap.id,
        en_segundo_plano=True,
        descripcion=f"Aportación de {autor.nombre if autor else 'un compañero'} validada por {actor.nombre}.",
    )
    ap.documento_id = doc.id
    # Si dos personas respondieron a la misma pregunta, la laguna queda enlazada a la primera
    # respuesta validada; la segunda se publica igualmente como pregunta frecuente.
    laguna = bd.get(Laguna, ap.laguna_id) if ap.laguna_id else None
    if laguna is not None and laguna.estado != "resuelta":
        lagunas.resolver(bd, laguna.id, ap.id)
    registrar(bd, actor, "valido", "aportacion", ap.id, ap.titulo,
              resultado={"success": True, "response": "validada", "documento_id": doc.id},
              contexto={"autor_id": ap.autor_id, "departamento_id": ap.departamento_id, "tarea_id": ap.tarea_id})
    registrar(bd, None, "aporto", "aportacion", ap.id, ap.titulo,
              resultado={"success": True, "completion": True, "response": "validada", "documento_id": doc.id},
              contexto={"validador_id": actor.id, "tarea_id": ap.tarea_id, "laguna_id": ap.laguna_id},
              actor_id=ap.autor_id, actor_nombre=autor.nombre if autor else None)
    auditar(bd, actor, "validar_aportacion", "aportacion", ap.id, {"documento_id": doc.id, "autor_id": ap.autor_id})
    bd.commit()
    # Sus aportaciones validadas cuentan como evidencia ILUO de la tarea (nivel O).
    if ap.tarea_id and ap.autor_id:
        try:
            iluo.recalcular(bd, ap.autor_id, ap.tarea_id)
            bd.commit()
        except Exception:  # noqa: BLE001  (no debe deshacer la validación)
            bd.rollback()
            log.exception("No se pudo recalcular el ILUO tras validar la aportación %s", ap.id)
    return doc


def rechazar(bd: Session, actor: Actor, ap: Aportacion, motivo: str | None) -> None:
    """Rechaza con un motivo que verá el autor. Hace commit."""
    motivo = sin_nulos(motivo).strip()
    if len(motivo) < 5:
        raise HTTPException(400, "Indica el motivo del rechazo: la persona que lo aportó lo verá.")
    if len(motivo) > 2000:
        raise HTTPException(400, "El motivo es demasiado largo (máximo 2000 caracteres).")
    if ap.estado not in ABIERTAS:
        raise HTTPException(409, "Esta aportación ya está revisada.")
    ap.estado = "rechazada"
    ap.motivo_rechazo = motivo
    ap.validador_id = actor.id
    ap.validada_en = ahora()
    registrar(bd, actor, "rechazo", "aportacion", ap.id, ap.titulo,
              resultado={"success": False, "response": motivo}, contexto={"autor_id": ap.autor_id})
    auditar(bd, actor, "rechazar_aportacion", "aportacion", ap.id, {"motivo": motivo, "autor_id": ap.autor_id})
    bd.commit()


def borrar(bd: Session, actor: Actor, ap: Aportacion) -> None:
    """El autor retira una aportación que aún no se ha revisado. Hace commit."""
    if ap.autor_id != actor.id:
        raise HTTPException(404, "Aportación no encontrada.")
    if ap.estado not in ABIERTAS:
        raise HTTPException(409, "Ya está revisada: no se puede retirar.")
    if ap.audio_ruta:
        try:
            fichero = ruta_absoluta(ap.audio_ruta)
            fichero.unlink(missing_ok=True)
            if fichero.parent.name != "aportaciones" and not any(fichero.parent.iterdir()):
                fichero.parent.rmdir()  # la carpeta <uuid>/ que creó guardar_subida
        except (OSError, HTTPException):
            log.warning("No se pudo borrar el audio de la aportación %s", ap.id)
    registrar(bd, actor, "retiro", "aportacion", ap.id, ap.titulo or "Aportación",
              contexto={"estado": ap.estado, "laguna_id": ap.laguna_id})
    bd.delete(ap)
    bd.commit()


# --------------------------------------------------------------------------- contadores (evidencia ILUO)


def contar_validadas(bd: Session, usuario_id: int, tarea_id: int | None = None) -> int:
    """Aportaciones validadas de una persona (de una tarea, si se indica). Evidencia para el nivel O."""
    q = select(func.count()).select_from(Aportacion).where(Aportacion.autor_id == usuario_id,
                                                           Aportacion.estado == "validada")
    if tarea_id is not None:
        q = q.where(Aportacion.tarea_id == tarea_id)
    return bd.scalar(q) or 0


def validadas_por_persona(bd: Session, departamento_id: int | None = None) -> dict[int, int]:
    """{usuario_id: nº de aportaciones validadas}, de un departamento o de toda la planta."""
    q = (select(Aportacion.autor_id, func.count()).where(Aportacion.estado == "validada")
         .group_by(Aportacion.autor_id))
    if departamento_id is not None:
        q = q.where(Aportacion.departamento_id == departamento_id)
    return {uid: n for uid, n in bd.execute(q).all()}


# --------------------------------------------------------------------------- respuestas JSON


def a_dicts(bd: Session, aps: list[Aportacion], actor: Actor) -> list[dict[str, Any]]:
    """Serializa varias aportaciones con una sola consulta por tabla relacionada.

    El autor ve su ficha completa (con su audio); quien gestiona ve además el autor, el
    departamento y el nivel mínimo (las etiquetas de acceso no se muestran a los empleados).
    """
    tareas = {t.id: t for t in bd.scalars(select(Tarea).where(Tarea.id.in_({a.tarea_id for a in aps if a.tarea_id})))}
    lags = {g.id: g for g in bd.scalars(select(Laguna).where(Laguna.id.in_({a.laguna_id for a in aps if a.laguna_id})))}
    docs = {d.id: d for d in bd.scalars(select(Documento).where(Documento.id.in_({a.documento_id for a in aps if a.documento_id})))}
    deps = {d.id: d.nombre for d in bd.scalars(select(Departamento).where(
        Departamento.id.in_({a.departamento_id for a in aps if a.departamento_id})))}
    niveles = {n.orden: n.nombre for n in bd.scalars(select(Nivel))}
    salida = []
    for ap in aps:
        tarea = tareas.get(ap.tarea_id) if ap.tarea_id else None
        laguna = lags.get(ap.laguna_id) if ap.laguna_id else None
        doc = docs.get(ap.documento_id) if ap.documento_id else None
        d: dict[str, Any] = {
            "id": ap.id,
            "estado": ap.estado,
            "creada": ap.creada.isoformat() if ap.creada else None,
            "validada_en": ap.validada_en.isoformat() if ap.validada_en else None,
            "titulo": ap.titulo,
            "problema": ap.problema,
            "causa": ap.causa,
            "solucion": ap.solucion,
            "etiquetas": list(ap.etiquetas or []),
            "via": "voz" if ap.audio_ruta else "texto",
            "texto_original": ap.texto_original,
            "transcripcion": ap.transcripcion,
            "audio_url": url_fichero(ap.audio_ruta),
            "duracion_audio": ap.duracion_audio,
            "tarea": {"id": tarea.id, "codigo": tarea.codigo, "nombre": tarea.nombre} if tarea else None,
            "laguna": {"id": laguna.id, "pregunta": laguna.pregunta, "frecuencia": laguna.frecuencia,
                       "estado": laguna.estado} if laguna else None,
            "motivo_rechazo": ap.motivo_rechazo,
            "revisada_por": ap.validador.nombre if ap.validador else None,
            "documento": {"id": doc.id, "titulo": doc.titulo, "estado": doc.estado, "tipo": doc.tipo,
                          "contenido": doc.contenido_texto} if doc else None,
            "es_mia": ap.autor_id == actor.id,
        }
        if puede_gestionar(actor, ap):
            autor = ap.autor
            d["autor"] = {"id": autor.id, "nombre": autor.nombre,
                          "puesto": autor.puesto.nombre if autor.puesto else None,
                          "nivel": autor.nivel.nombre if autor.nivel else None} if autor else None
            d["departamento"] = {"id": ap.departamento_id, "nombre": deps.get(ap.departamento_id)} \
                if ap.departamento_id else None
            d["nivel_minimo"] = ap.nivel_minimo
            d["nivel_nombre"] = niveles.get(ap.nivel_minimo)
        salida.append(d)
    return salida


def a_dict(bd: Session, ap: Aportacion, actor: Actor) -> dict[str, Any]:
    return a_dicts(bd, [ap], actor)[0]
