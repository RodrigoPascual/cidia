"""Memoria personal del copiloto (opcional, desactivada por defecto).

Cada persona decide en su perfil si la activa. Los recuerdos se guardan en el servidor, la
propia persona puede verlos y borrarlos, y solo se usan en sus conversaciones. Ninguna
función hace commit (el del trabajo en segundo plano `extraer_trabajo` lo hace trabajos.py).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cidia import trabajos
from cidia.ia import llm, prompts
from cidia.modelos import Memoria, Usuario

log = logging.getLogger("cidia.memoria")

MAX_RECUERDOS = 200  # por persona; al pasarse se olvidan los más antiguos
MAX_LONGITUD = 500
UMBRAL_DUPLICADO = 0.92  # dos recuerdos casi iguales se guardan una sola vez


# --------------------------------------------------------------------------- estado


def activa(bd: Session, usuario_id: int | None) -> bool:
    if not usuario_id:
        return False
    return bool(bd.scalar(select(Usuario.memoria_activa).where(Usuario.id == usuario_id)))


def activar(bd: Session, usuario: Usuario, valor: bool) -> None:
    """Activa o desactiva la memoria. Desactivarla no borra los recuerdos: deja de usarlos."""
    usuario.memoria_activa = bool(valor)
    bd.flush()


# --------------------------------------------------------------------------- consulta y edición


def listar(bd: Session, usuario_id: int) -> list[Memoria]:
    return list(bd.scalars(
        select(Memoria).where(Memoria.usuario_id == usuario_id).order_by(Memoria.creada.desc(), Memoria.id.desc())
    ).all())


def contar(bd: Session, usuario_id: int) -> int:
    return int(bd.scalar(select(func.count(Memoria.id)).where(Memoria.usuario_id == usuario_id)) or 0)


def _vector(texto: str) -> list[float] | None:
    try:
        return llm.embeddings([texto])[0]
    except Exception as e:  # noqa: BLE001  (sin embeddings el recuerdo se guarda igual)
        log.warning("Sin embedding para el recuerdo: %s", e)
        return None


def _duplicado(bd: Session, usuario_id: int, contenido: str, vector: list[float] | None) -> Memoria | None:
    igual = bd.scalar(select(Memoria).where(Memoria.usuario_id == usuario_id,
                                            func.lower(Memoria.contenido) == contenido.lower()))
    if igual is not None or vector is None:
        return igual
    dist = Memoria.embedding.cosine_distance(vector)
    fila = bd.execute(
        select(Memoria, (1 - dist).label("sim"))
        .where(Memoria.usuario_id == usuario_id, Memoria.embedding.is_not(None),
               func.vector_dims(Memoria.embedding) == len(vector))
        .order_by(dist)
        .limit(1)
    ).first()
    if fila and float(fila.sim) >= UMBRAL_DUPLICADO:
        return fila[0]
    return None


def anadir(bd: Session, usuario_id: int, contenido: str, origen: str = "manual") -> Memoria:
    """Guarda un recuerdo (o devuelve el que ya había si es prácticamente el mismo)."""
    contenido = " ".join((contenido or "").split())[:MAX_LONGITUD]
    if not contenido:
        raise ValueError("El recuerdo está vacío.")
    vector = _vector(contenido)
    existente = _duplicado(bd, usuario_id, contenido, vector)
    if existente is not None:
        return existente
    m = Memoria(usuario_id=usuario_id, contenido=contenido, embedding=vector, origen=origen)
    bd.add(m)
    bd.flush()
    # Límite por persona: se olvidan los recuerdos más antiguos.
    sobrantes = bd.scalars(
        select(Memoria.id).where(Memoria.usuario_id == usuario_id)
        .order_by(Memoria.creada.desc(), Memoria.id.desc()).offset(MAX_RECUERDOS)
    ).all()
    if sobrantes:
        bd.execute(delete(Memoria).where(Memoria.id.in_(sobrantes)))
    return m


def borrar(bd: Session, usuario_id: int, memoria_id: int) -> bool:
    """Borra un recuerdo de esa persona. Devuelve False si no existe o es de otra persona."""
    m = bd.get(Memoria, memoria_id)
    if m is None or m.usuario_id != usuario_id:
        return False
    bd.delete(m)
    bd.flush()
    return True


def borrar_todo(bd: Session, usuario_id: int) -> int:
    n = contar(bd, usuario_id)
    bd.execute(delete(Memoria).where(Memoria.usuario_id == usuario_id))
    return n


def relevantes(bd: Session, usuario_id: int, pregunta: str, k: int = 5) -> list[Memoria]:
    """Los k recuerdos más relacionados con la pregunta (por significado).

    Sin umbral: una persona tiene pocos recuerdos y algunos (p. ej. «prefiere respuestas cortas»)
    sirven para cualquier pregunta aunque no se parezcan a ella. El prompt pide usarlos solo si vienen al caso.
    """
    if not pregunta.strip() or not contar(bd, usuario_id):
        return []  # sin recuerdos no se gasta una llamada al modelo de embeddings
    try:
        # Comparación simétrica (frase con frase): sin la instrucción de búsqueda de documentos.
        q = llm.embeddings([pregunta])[0]
    except Exception as e:  # noqa: BLE001
        log.warning("Sin embedding para buscar recuerdos: %s", e)
        return listar(bd, usuario_id)[:k]
    dist = Memoria.embedding.cosine_distance(q)
    filas = bd.execute(
        select(Memoria, (1 - dist).label("sim"))
        .where(Memoria.usuario_id == usuario_id, Memoria.embedding.is_not(None),
               func.vector_dims(Memoria.embedding) == len(q))
        .order_by(dist)
        .limit(k)
    ).all()
    return [m for m, _sim in filas]


def a_dict(m: Memoria) -> dict[str, Any]:
    return {"id": m.id, "contenido": m.contenido, "origen": m.origen,
            "creada": m.creada.isoformat() if m.creada else None}


# --------------------------------------------------------------------------- extracción automática


# Lo que nunca se guarda aunque el modelo lo proponga (los modelos pequeños no siempre hacen caso
# al prompt): datos de contacto, identificadores, credenciales y categorías especiales (RGPD art. 9).
# Términos acotados para no descartar lenguaje de planta («punto clave», «tratamiento térmico»,
# «medición», «seguridad y salud»).
_SENSIBLE = re.compile(
    r"@|\b\d{3}[ .-]?\d{3}[ .-]?\d{3}\b|\b\d{8}[A-Za-z]\b|\b[XYZxyz]\d{7}[A-Za-z]\b|\bES\d{2}[ \d]{10,}"
    r"|contrase[ñn]a|password|clave de acceso|\bpin\b"
    r"|enferm|\bm[eé]dic[oa]s?\b|diagn[oó]stic|embaraz|discapacid|baja m[eé]dica|medicaci[oó]n|depresi[oó]n|ansiedad"
    r"|religi|ideolog|partido pol[ií]tico|sindica|afiliad|orientaci[oó]n sexual|domicilio|vive en",
    re.I,
)


def _recuerdos_propuestos(datos: Any) -> list[str]:
    """Saca la lista de recuerdos de lo que devuelva el modelo, aunque no respete el formato:
    {"recuerdos": [...]}, {"recuerdos": "una frase"}, una lista suelta o elementos como {"hecho": "..."}.
    Un texto suelto fuera del JSON esperado se descarta (suele ser un mensaje de error del modelo)."""
    if isinstance(datos, dict):
        datos = datos.get("recuerdos", datos.get("hechos", datos.get("memoria", [])))
        if isinstance(datos, str):
            datos = [datos]
    if not isinstance(datos, list):
        return []
    salida: list[str] = []
    for r in datos:
        if isinstance(r, dict):
            r = next((v for v in r.values() if isinstance(v, str)), None)
        if not isinstance(r, str):
            continue
        r = " ".join(r.split()).strip(" -•*")
        if len(r) >= 8 and not _SENSIBLE.search(r):
            salida.append(r)
    return salida[:5]


def extraer(bd: Session, usuario_id: int, pregunta: str, respuesta: str) -> list[Memoria]:
    """Pide al modelo hechos estables sobre la persona y los guarda (si sigue con la memoria activa)."""
    if not activa(bd, usuario_id):
        return []
    conocidos = [m.contenido for m in listar(bd, usuario_id)[:30]]
    try:
        datos = llm.chat_json(prompts.mensajes_extraer_memoria(pregunta, respuesta, conocidos), bd=bd)
    except llm.ErrorModelo as e:
        # Los modelos pequeños a veces no devuelven un JSON válido ni al segundo intento: esta vez
        # no se recuerda nada (no es un fallo del trabajo).
        log.info("Sin recuerdos que extraer: %s", e)
        return []
    return [anadir(bd, usuario_id, r, origen="copiloto") for r in _recuerdos_propuestos(datos)]


def extraer_trabajo(bd: Session, progreso: Any, usuario_id: int, pregunta: str, respuesta: str) -> dict[str, Any]:
    nuevos = extraer(bd, usuario_id, pregunta, respuesta)
    return {"recuerdos": len(nuevos)}


def encolar_extraccion(usuario_id: int, pregunta: str, respuesta: str) -> int | None:
    """Extrae recuerdos en segundo plano al terminar una consulta."""
    try:
        return trabajos.encolar("memoria_extraer", extraer_trabajo, usuario_id, pregunta, respuesta,
                                entidad="usuario", entidad_id=usuario_id, usuario_id=usuario_id)
    except Exception as e:  # noqa: BLE001  (la memoria nunca debe romper una consulta)
        log.warning("No se pudo encolar la extracción de memoria: %s", e)
        return None
