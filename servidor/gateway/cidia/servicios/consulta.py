"""Consulta al copiloto con citas (RAG), lagunas y memoria personal.

Flujo de una pregunta (docs/arquitectura.md §6):
  alcance del actor → búsqueda híbrida → ¿hay respaldo? → contexto numerado [1..n] →
  respuesta (en streaming o no) con citas → fila Consulta + xAPI «pregunto» →
  sin respaldo, laguna; con memoria activa, extracción de recuerdos en segundo plano.

`preparar()` hace todo el trabajo síncrono previo (y lanza HTTPException si algo no está
permitido), `emitir()` produce los eventos en streaming y `finalizar()` guarda el resultado.
`responder_stream()` y `responder()` son las funciones de contrato (servicios/contratos.md).
Si la persona detiene la respuesta o se corta la conexión a mitad, la consulta se guarda igual
(con lo que se llegó a escribir) en segundo plano: cuenta en el registro y, sin respaldo, en las lagunas.

Curva de autonomía: los contadores de consultas de una ejecución (Ejecucion.consultas,
consultas_criticos y EjecucionPaso.consultas) son del modo planta, que los suma antes de llamar
a `responder_stream()`. Las funciones de contrato NO los tocan; solo las rutas /api/consulta los
suman (`contar_ejecucion=True`) cuando un cliente pregunta directamente con un `ejecucion_id`, y
también ANTES de responder (preguntar ya es la evidencia, aunque luego se corte la respuesta).
"""

from __future__ import annotations

import logging
import re
import threading
import time
import unicodedata
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from cidia.config import ajustes
from cidia.conocimiento import Encontrado, motor
from cidia.db import sesion_bd
from cidia.ia import llm, prompts
from cidia.modelos import (
    Consulta, Documento, Ejecucion, EjecucionPaso, Empresa, Formacion, Instruccion, Paso, Sesion, Tarea, Usuario,
)
from cidia.permisos import Alcance, alcance_de, departamentos_visibles, puede_ver
from cidia.seguridad import Actor, limitar_invitado, url_fichero
from cidia.servicios import lagunas, memoria
from cidia.xapi import registrar

log = logging.getLogger("cidia.consulta")

MODOS = ("normal", "socratico", "planta")
MAX_PREGUNTA = 4000
MAX_HISTORIAL = 6  # últimos turnos de la conversación que se envían al modelo
MAX_TURNO = 1500  # caracteres por turno del historial
MAX_FRAGMENTO_CONTEXTO = 1800
MAX_CONTEXTO = 9000  # caracteres de contexto en total (los modelos locales tienen poca ventana)
MAX_FRAGMENTO_FUENTE = 700  # lo que se enseña del fragmento en la cita
RECUERDOS_POR_CONSULTA = 5
MARGEN_SIMILITUD = 0.2  # un fragmento más de 0,2 por debajo del mejor no se cita (salvo coincidencia de texto)

# La marca tal y como la escriben los modelos pequeños: SIN_RESPALDO, **SIN_RESPALDO**, [SIN_RESPALDO],
# `SIN_RESPALDO`, «SIN RESPALDO:» o sin_respaldo (en minúsculas solo con guion bajo, que no es texto natural).
_RE_MARCA = re.compile(r"[\[*`]*(?:SIN[_ ]RESPALDO|[Ss]in_[Rr]espaldo)[\]*`]*[ \t]*[:.\-–]?[ \t]*")
_ABRE_MARCA = "*[`"  # signos que pueden ir delante de la marca
_RE_CITA = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]")
# Restos del razonamiento de los modelos que piensan (qwen3...): el bloque entero o una etiqueta suelta.
_RE_PENSAMIENTO = re.compile(r"<think>.*?</think>\s*", re.S | re.I)
_RE_ETIQUETA_PENSAMIENTO = re.compile(r"</?think>\s*", re.I)
_ETIQUETAS_PENSAMIENTO = ("<think>", "</think>")
# Eco de la regla del modo planta («empieza con SIN_RESPALDO, di que no lo sabes…»): qwen3:0.6b escribe
# a veces «SIN_RESPALDO, no lo sabes.». Eso no es una respuesta: se quita (y, si no queda nada, se muestra
# el «no lo he encontrado» de siempre).
_RE_ECO_REGLA = re.compile(r"(?:y\s+)?(?:di\s+)?(?:que\s+)?no lo sabes\b[^.!\n]*[.!\n]?\s*", re.I)
_ECOS_REGLA = ("no lo sabes", "y di que no lo sabes", "di que no lo sabes", "que no lo sabes")
# «La respuesta está en el fragmento [2].» / «El dato aparece en el fragmento 2:» al principio de la respuesta.
_RE_ECO_FRAGMENTO = re.compile(
    r"^\s*(?:la respuesta|el dato|la informaci[oó]n)\s+(?:est[aá]|se encuentra|aparece|viene)\s+en\s+el\s+fragmento\s*"
    r"\[?(\d{1,2})\]?\s*(?:del contexto\s*)?[.:,]\s*", re.I)
# El modelo dice que la documentación no responde (con o sin la marca SIN_RESPALDO).
_RE_NIEGA = re.compile(
    r"\bno (?:lo |la |los |las |se )?(?:encuentr|he encontrado|hemos encontrado|aparece|figura|consta|indica|"
    r"especifica|menciona|recoge|detalla|tengo (?:informaci|datos?)|dispongo|hay (?:informaci|datos?|nada|ningun))",
    re.I,
)

# Palabras de cortesía (o sobre el propio copiloto): un mensaje formado solo por ellas no es una laguna.
_CORTESIA = {
    "hola", "buenas", "buenos", "dias", "tardes", "noches", "gracias", "muchas", "vale", "adios", "hasta", "luego",
    "que", "tal", "como", "estas", "esta", "perfecto", "genial", "entendido", "okey", "bien", "muy", "chao",
    "saludos", "por", "favor", "nada", "claro", "eso", "todo", "quien", "eres",
    "cidia", "copiloto", "puedes", "puede", "hacer", "haces", "ayudar", "ayudarme", "sirves", "funcionas",
}
# Frases en las que la persona habla de sí misma (solo entonces se buscan recuerdos que guardar).
_RE_HABLA_DE_SI = re.compile(
    r"\b(soy|estoy|trabajo|llevo|tengo|prefiero|me gusta|me cuesta|mi|mis|yo|nuevo|nueva|mi turno)\b", re.I
)
# «mi puesto», «mis tareas», «mi máquina»...: la pregunta se refiere al puesto de quien pregunta.
_RE_MI_PUESTO = re.compile(
    r"\bmis?\s+(puestos?|tareas?|trabajo|m[aá]quinas?|l[ií]neas?|zona|secci[oó]n|equipos?|turno|departamento)\b",
    re.I,
)

# Respaldo por coincidencia de texto. El motor marca `coincidencia_texto` en cuanto UNA palabra de la
# pregunta aparece en el fragmento («hora», «fábrica»...), y eso no respalda nada. Solo cuenta si coincide
# un código (IT-101, S4, CL-200, 9001) o al menos la mitad de las palabras con contenido de la pregunta.
_VACIAS = frozenset("""
como cual cuales cuando cuanto cuanta cuantos cuantas donde quien quienes porque para sobre entre desde hasta
este esta esto estos estas aquel aquella cada tiene tienen tengo tener hace hacer hago hacemos puedo puede
pueden podria debo debe deben debemos estan estoy estar algo alguien alguna alguno todo toda todos todas otro
otra otros otras mismo misma pero tambien solo mucho mucha muchos muchas menos bien aqui ahora despues antes
luego entonces siempre nunca segun durante tras unos unas sido quiero necesito saber dime explica explicame
ayuda favor gracias hola buenos buenas dias tardes noches vale pasa seria sera habia haber eres cosa cosas
forma manera tipo veces
""".split())
_RE_CODIGO = re.compile(r"\b[a-z]{1,4}-?\d{1,5}[a-z]?\b|\b\d{3,}\b")


# --------------------------------------------------------------------------- búsqueda


def buscar(bd: Session, actor: Actor, pregunta: str, k: int | None = None) -> list[Encontrado]:
    """Búsqueda híbrida con el alcance del actor (lo que no puede ver no existe)."""
    alcance = alcance_de(bd, actor)
    return _buscar(bd, alcance, pregunta, k)


def _buscar(bd: Session, alcance: Alcance, pregunta: str, k: int | None = None) -> list[Encontrado]:
    encontrados = motor().buscar(bd, pregunta, alcance, k or ajustes().fragmentos_por_consulta)
    if not encontrados:
        return []
    # Defensa en profundidad: se vuelve a comprobar cada documento contra la base de datos
    # (el motor externo podría devolver algo desfasado).
    ids = {e.documento_id for e in encontrados}
    docs = {d.id: d for d in bd.scalars(select(Documento).where(Documento.id.in_(ids))).all()}
    return [e for e in encontrados if (d := docs.get(e.documento_id)) is not None and puede_ver(alcance, d)]


@dataclass(frozen=True)
class Terminos:
    """Códigos y raíces de palabras con contenido de un texto (para comparar sin embeddings)."""

    codigos: frozenset[str]
    raices: frozenset[str]


def terminos(texto: str) -> Terminos:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    codigos = frozenset(c.replace("-", "") for c in _RE_CODIGO.findall(t))
    # Raíz = 5 primeras letras: «atasca», «atasco» y «atascado» cuentan como la misma palabra.
    raices = frozenset(p[:5] for p in re.findall(r"[a-z]+", t) if len(p) >= 4 and p not in _VACIAS)
    return Terminos(codigos, raices)


def coincidencia_significativa(pregunta: Terminos, e: Encontrado) -> bool:
    """¿El fragmento comparte con la pregunta un código o al menos la mitad de sus palabras con contenido?"""
    frag = terminos(f"{e.titulo} {(e.metadatos or {}).get('codigo') or ''} {e.texto}")
    if pregunta.codigos & frag.codigos:
        return True
    comunes = len(pregunta.raices & frag.raices)
    return comunes > 0 and comunes >= min(2, len(pregunta.raices)) and comunes * 2 >= len(pregunta.raices)


def con_respaldo(encontrados: list[Encontrado], pregunta: str | None = None) -> list[Encontrado]:
    """Fragmentos que respaldan una respuesta: similitud suficiente y no muy lejos de la mejor (lo que
    se parece poco solo mete ruido en las citas) o una coincidencia de texto significativa con la
    pregunta (códigos como IT-101 que los embeddings no distinguen). Sin `pregunta`, vale cualquier
    coincidencia de texto que marque el motor."""
    umbral = ajustes().umbral_respaldo
    mejor = max((e.similitud or 0.0 for e in encontrados), default=0.0)
    minimo = max(umbral, mejor - MARGEN_SIMILITUD)
    buscados = terminos(pregunta) if pregunta is not None else None

    def respalda(e: Encontrado) -> bool:
        if (e.similitud or 0.0) >= minimo:
            return True
        if not (e.metadatos or {}).get("coincidencia_texto"):
            return False
        return buscados is None or coincidencia_significativa(buscados, e)

    return [e for e in encontrados if respalda(e)]


# --------------------------------------------------------------------------- respaldo claro y respuesta extractiva
#
# Los modelos pequeños (qwen3:0.6b) contestan a menudo solo «SIN_RESPALDO» aunque el dato esté en el
# CONTEXTO (en Oracle: «¿cuántos puestos tiene Producción?», con la Guía de acogida como primera fuente).
# Cuando el respaldo es CLARO, esa respuesta se rehace: primero se reintenta con un prompt más directo y,
# si tampoco sirve, se compone una respuesta EXTRACTIVA con las frases del fragmento, citadas.
# «Claro» no es solo similitud: «¿Qué presión lleva el cilindro de la prensa 2?» (sin respuesta en la
# demo) recupera la prensa 3 con similitud 0,61 y coincidencia de texto. Hace falta además una FRASE de un
# fragmento que contenga todas las palabras con contenido de la pregunta (contando el título y el apartado
# del fragmento), sus códigos (IT-031, S4) y sus referencias numeradas («prensa 2», «nave 1» o «P2»).

MARGEN_CLARO = 0.1  # la mejor similitud supera el umbral al menos en esto (o hay coincidencia significativa)
MAX_FRASES_EXTRACTIVA = 3
MAX_EXTRACTIVA = 600  # caracteres de frases en la respuesta extractiva
MAX_TOKENS_REINTENTO = 220
MAX_FRAGMENTOS_REINTENTO = 2
# Sufijos que se quitan para comparar palabras («engrasan» y «engrase», «puesto» y «puestos»), sin llegar a
# confundir «responsable» con «responde» ni «plantilla» con «planta» (lo que hace la raíz de 5 letras).
_SUFIJOS = tuple(sorted((
    "amientos", "imientos", "amiento", "imiento", "aciones", "iciones", "ciones", "siones", "acion", "icion",
    "cion", "sion", "mente", "ables", "ibles", "able", "ible", "adoras", "adores", "adora", "ador", "ando",
    "iendo", "amos", "emos", "imos", "ados", "adas", "idos", "idas", "ajes", "ado", "ada", "ido", "ida", "aje",
    "ar", "er", "ir", "an", "en", "es", "as", "os", "a", "e", "o", "s",
), key=len, reverse=True))
# «prensa 2», «línea 2», «nave nº 1»: una referencia numerada de la pregunta tiene que estar en el fragmento.
_RE_REFERENCIA = re.compile(r"\b([a-z]{4,})\s+(?:no?\.?\s*)?(\d{1,3})\b")
_RE_SEPARADOR_TABLA = re.compile(r"^\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?$")
_RE_ABREVIATURA = re.compile(r"(?:\b[A-ZÁÉÍÓÚÑ]|\b(?:[Pp]|[Ee]j|aprox|m[aá]x|m[ií]n|n[uú]m|p[aá]g|Sr|Sra|Rev))\.$")
# Preguntas por una cantidad o por un valor: la frase que responde tiene que llevar un número («¿Cada
# cuántos ciclos se limpia?» no lo responde «reiniciar el ciclo en modo manual»).
_NUMEROS = ("dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|"
            "veinte|treinta|cuarenta|cincuenta|sesenta|cien|ciento|doscientos|quinientos|mil")
_RE_NUMERO = re.compile(rf"\d|\b(?:{_NUMEROS})\b")
_RE_CUANTOS = re.compile(r"\bcuant[oa]s\s+(?:de\s+)?([a-z]{2,})|\bcuanto\s+(tiempo)\b")
_RE_CUANTO = re.compile(r"\bcuant[oa]s?\b")
_RE_MAGNITUD = re.compile(
    r"\b(?:que|cual|cuales)\b(?:\s+\w+){0,3}?\s+(?:presion|temperatura|par|valor|distancia|tolerancias?|peso|"
    r"longitud|altura|anchura|velocidad|frecuencia|caudal|tension|potencia|capacidad|fuerza|dimension|medida|cota|"
    r"tiempo|duracion|plazo|precio|coste|cantidad)\b"
)
_RE_CIFRA = re.compile(r"\d+(?:[.,]\d+)*")
# Raíces de palabras que no aportan nada a una respuesta (versión, revisión, página, documento...).
_GENERICAS = frozenset({"version", "revi", "pagin", "document", "fragment", "tare", "segun"})
MIN_PARECIDO_REINTENTO = 0.3  # parte de lo que aporta la mejor frase que el reintento tiene que decir


def _normal(texto: str) -> str:
    """Minúsculas y sin tildes."""
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _raiz(palabra: str) -> str:
    for s in _SUFIJOS:
        if palabra.endswith(s) and len(palabra) - len(s) >= 4:
            return palabra[: -len(s)]
    return palabra


def _raices(texto: str) -> frozenset[str]:
    """Raíces (sin sufijos) de las palabras con contenido de un texto. Las siglas cortas (EPI, EPIs, CAD,
    PRL) cuentan aunque tengan menos de cuatro letras."""
    raices: set[str] = set()
    for palabra in re.findall(r"[^\W\d_]+", texto or ""):
        if re.fullmatch(r"[A-ZÁÉÍÓÚÑ]{2,4}s?", palabra):
            raices.add(_normal(palabra[:-1] if palabra.endswith("s") else palabra))
            continue
        p = _normal(palabra)
        if len(p) >= 4 and p not in _VACIAS:
            raices.add(_raiz(p))
    return frozenset(raices)


def _referencias(texto: str) -> frozenset[tuple[str, str]]:
    return frozenset((_raiz(p), n) for p, n in _RE_REFERENCIA.findall(_normal(texto)) if p not in _VACIAS)


def sin_markdown(texto: str) -> str:
    """Una línea sin marcas de Markdown (encabezado, cita, viñeta, negrita, código, enlaces)."""
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", texto or "")
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s*(?:#{1,6}\s+|>\s*|[-*+•]\s+|\d{1,2}[.)]\s+)+", "", t)
    t = t.replace("**", "").replace("__", "").replace("`", "")
    t = re.sub(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def _frases(texto: str) -> list[str]:
    frases: list[str] = []
    for p in re.split(r"(?<=[.!?])\s+", texto):
        if frases and (len(frases[-1]) < 15 or _RE_ABREVIATURA.search(frases[-1])):
            frases[-1] += " " + p  # «S. L.», «Paso 3.», «p. ej.» no terminan la frase
        else:
            frases.append(p)
    return [f.strip() for f in frases if f.strip()]


def unidades(texto: str) -> list[tuple[str, str]]:
    """(apartado, frase) de un fragmento, sin Markdown: frases de los párrafos, elementos de las listas y
    filas de las tablas («Columna: valor; …»). Las líneas partidas de un PDF se vuelven a unir."""
    lineas: list[str] = []
    for bruta in (texto or "").splitlines():
        linea = bruta.strip()
        if not linea:
            lineas.append("")
            continue
        m = re.match(r"#{1,6}\s+(.*)", linea)
        if m:
            # El troceado puede pegar un encabezado con la línea siguiente («## Codificación | Elemento |…»).
            corte = re.search(r"\s(?=\|)|\s(?=[-*•]\s)|\s(?=\d{1,2}\.\s)", m.group(1))
            if corte:
                lineas += ["#" + m.group(1)[: corte.start()], m.group(1)[corte.end():].strip()]
            else:
                lineas.append("#" + m.group(1))
            continue
        anterior = lineas[-1] if lineas else ""
        if (anterior and not anterior.startswith(("#", "|")) and not linea.startswith("|")
                and linea[0].islower() and not re.search(r"[.:;!?]$", anterior)):
            lineas[-1] = f"{anterior} {linea}"  # continuación de una línea partida
            continue
        lineas.append(linea)

    salida: list[tuple[str, str]] = []
    apartado = ""
    cabecera: list[str] | None = None
    fila: tuple[int, list[str]] | None = None  # última fila de tabla (puede resultar ser la cabecera)
    for linea in lineas:
        if not linea:
            cabecera = fila = None
        elif linea.startswith("#"):
            apartado, cabecera, fila = sin_markdown(linea.lstrip("#")), None, None
        elif linea.startswith("|"):
            if _RE_SEPARADOR_TABLA.match(linea):
                if fila is not None and fila[0] == len(salida) - 1:
                    salida.pop()
                    cabecera = fila[1]
                fila = None
                continue
            celdas = [sin_markdown(c) for c in linea.strip().strip("|").split("|")]
            if cabecera and len(cabecera) == len(celdas):
                texto_fila = "; ".join(f"{h}: {c}" if h else c for h, c in zip(cabecera, celdas) if c)
            else:
                texto_fila = " · ".join(c for c in celdas if c)
            salida.append((apartado, texto_fila))
            fila = (len(salida) - 1, celdas)
        else:
            cabecera = fila = None
            salida += [(apartado, f) for f in _frases(sin_markdown(linea))]
    return [(a, f) for a, f in salida if len(f) >= 12]


@dataclass(frozen=True)
class Frase:
    """Una frase de un fragmento que responde a la pregunta (para el reintento y la respuesta extractiva)."""

    n: int
    documento_id: int | None
    posicion: int
    texto: str
    en_frase: int  # palabras de la pregunta que están en la propia frase (las demás, en el título o el apartado)
    similitud: float
    literales: int = 0  # palabras y cifras de la pregunta que la frase repite tal cual («más de 12.000»)


def respaldo_claro(encontrados: list[Encontrado], pregunta: str) -> bool:
    """La recuperación respalda la pregunta con margen: la mejor similitud supera el umbral en
    MARGEN_CLARO o algún fragmento tiene una coincidencia de texto significativa."""
    if not encontrados:
        return False
    mejor = max((e.similitud or 0.0) for e in encontrados)
    if mejor >= ajustes().umbral_respaldo + MARGEN_CLARO:
        return True
    buscados = terminos(pregunta)
    return any(coincidencia_significativa(buscados, e) for e in encontrados)


def _pide_numero(pregunta: str) -> tuple[bool, str | None]:
    """¿La pregunta pide una cantidad o un valor? Devuelve (hace falta un número, raíz de lo que se cuenta:
    «cuántos puestos» → «puest», que tiene que ir justo detrás del número)."""
    t = _normal(pregunta)
    m = _RE_CUANTOS.search(t)
    if m:
        palabra = m.group(1) or m.group(2)
        return True, (None if palabra in _VACIAS else _raiz(palabra))
    return bool(_RE_CUANTO.search(t) or _RE_MAGNITUD.search(t)), None


def _tiene_numero(texto_normal: str, contado: str | None) -> bool:
    if contado is None:
        return bool(_RE_NUMERO.search(texto_normal))
    return bool(re.search(rf"(?:\d+(?:[.,]\d+)*|\b(?:{_NUMEROS}))\s+(?:[a-z]+\s+)?{re.escape(contado)}", texto_normal))


def _literales(texto: str) -> frozenset[str]:
    """Palabras (sin tildes, también las cortas como «de» o «más») y cifras de un texto, tal cual."""
    return frozenset(re.findall(r"\d+(?:[.,]\d+)*|[a-z]+", _normal(texto)))


def evidencia(fuentes: list[dict[str, Any]], textos: list[str], pregunta: str,
              empresa: str | None = None) -> list[Frase]:
    """Frases de los fragmentos que responden claramente a la pregunta, de la mejor a la peor.

    Una frase vale si:
    * contiene al menos la mitad de las palabras con contenido de la pregunta y el resto está en el título
      o en el apartado del fragmento (el nombre de la empresa no cuenta: sale en todas partes);
    * aporta algo más que la pregunta y el título (dos palabras nuevas, o una y una cifra);
    * el fragmento tiene todos los códigos y referencias numeradas de la pregunta («prensa 3» también
      vale escrito «P3») y la frase no habla de otra («nave 2» no responde a «nave 1»);
    * si la pregunta pide una cantidad o un valor, lleva un número («tres puestos», «cada 40 horas»);
    * no es una pregunta (la de una FAQ).
    Con menos de dos palabras con contenido (o una y un código), no hay evidencia."""
    buscadas = _raices(pregunta) - _raices(empresa or "")
    codigos = terminos(pregunta).codigos
    referencias = _referencias(pregunta)
    if len(buscadas) < 2 and not (buscadas and (codigos or referencias)):
        return []
    pide_numero, contado = _pide_numero(pregunta)
    nombres = {r[0] for r in referencias}
    literales = _literales(pregunta)
    frases: list[Frase] = []
    for f, texto in zip(fuentes, textos):
        cabeza = f"{f.get('titulo') or ''} {f.get('codigo') or ''}"
        todo = f"{cabeza}\n{texto}"
        en_doc = terminos(todo).codigos
        if codigos - en_doc:
            continue
        refs = _referencias(todo)
        if any(r not in refs and f"{r[0][0]}{r[1]}" not in en_doc for r in referencias):
            continue
        raices_titulo = _raices(cabeza)
        del_titulo = raices_titulo & buscadas
        cifras_fijas = set(_RE_CIFRA.findall(f"{cabeza} {pregunta} {f.get('version') or ''}"))
        for i, (apartado, frase) in enumerate(unidades(texto)):
            if "?" in frase or "¿" in frase:
                continue
            raices_frase = _raices(frase)
            propias = raices_frase & buscadas
            if len(propias) * 2 < len(buscadas) or propias | del_titulo | (_raices(apartado) & buscadas) != buscadas:
                continue
            normal = _normal(frase)
            nuevas = raices_frase - buscadas - raices_titulo - _GENERICAS
            cifras = set(_RE_CIFRA.findall(frase)) - cifras_fijas
            if len(nuevas) < 2 and not (nuevas and cifras):
                continue  # no aporta nada: el título del documento repetido, «Tarea: …»
            otras = {r for r in _referencias(frase) if r[0] in nombres}
            if otras and not otras & referencias:
                continue
            if pide_numero and not _tiene_numero(normal, contado):
                continue
            frases.append(Frase(f["n"], f.get("documento_id"), i, frase, len(propias),
                                float(f.get("similitud") or 0.0), len(literales & _literales(frase))))
    # A igualdad de palabras con contenido, va antes la frase que repite más palabras y cifras de la pregunta:
    # en «Hasta 3.000 € … / De 3.000 a 12.000 € … / Más de 12.000 € …», a «¿quién aprueba compras de más de
    # 12.000 €?» responde la tercera, no la primera de la lista.
    frases.sort(key=lambda x: (-x.en_frase, -x.literales, -x.similitud, x.n, x.posicion))
    return frases


def _contexto_directo(fuentes: list[dict[str, Any]], textos: list[str], frases: list[Frase]) -> str:
    """Contexto del reintento: solo los fragmentos donde está la respuesta, sin Markdown (con su número)."""
    bloques: list[str] = []
    for n in list(dict.fromkeys(f.n for f in frases))[:MAX_FRAGMENTOS_REINTENTO]:
        fu = fuentes[n - 1]
        lineas: list[str] = []
        apartado = ""
        for ap, frase in unidades(textos[n - 1]):
            if ap and ap != apartado:
                lineas.append(f"{ap}:")
                apartado = ap
            lineas.append(frase)
        bloques.append(prompts.fragmento_contexto(n, fu.get("titulo") or "", "\n".join(lineas), fu.get("version"),
                                                  fu.get("paso"), codigo=fu.get("codigo")))
    return "\n\n".join(bloques)


_RE_PROBLEMA = re.compile(r"^\s*(?:problema|pregunta|s[ií]ntoma)\s*:", re.I)
_RE_SOLUCION = re.compile(r"^\s*soluci[oó]n\s*:", re.I)


def respuesta_extractiva(prep: Preparada) -> str:
    """Respuesta compuesta con las 1-3 frases que mejor responden, del mismo documento, sin Markdown,
    precedidas de «Según «título» (vN):» y con su cita."""
    mejor = prep.evidencia[0]
    # En una ficha «Problema / Causa / Solución» (aportaciones y notas de voz), la frase que más se parece
    # a la pregunta suele ser el problema, que solo la repite: la respuesta es la solución de esa ficha.
    if _RE_PROBLEMA.match(mejor.texto) and mejor.n in prep.textos_evidencia:
        unidades_ficha = unidades(prep.textos_evidencia[mejor.n])
        solucion = next(((i, f) for i, (_, f) in enumerate(unidades_ficha) if _RE_SOLUCION.match(f)), None)
        if solucion:
            mejor = Frase(mejor.n, mejor.documento_id, solucion[0], solucion[1], mejor.en_frase, mejor.similitud)
    otras: list[Frase] = []
    vistas = {_normal(mejor.texto)}
    completa = len(_raices(prep.pregunta_terminos) - _raices(prep.empresa or ""))
    for f in prep.evidencia[1:]:
        clave = _normal(f.texto)
        # Solo se añaden frases del mismo documento que responden por sí solas (sin ayuda del título).
        if f.documento_id != mejor.documento_id or f.en_frase < max(mejor.en_frase, completa) or clave in vistas:
            continue
        vistas.add(clave)
        otras.append(f)
        if len(otras) >= MAX_FRASES_EXTRACTIVA - 1:
            break
    fuente = prep.fuentes[mejor.n - 1]
    titulo = fuente.get("titulo") or "la documentación"
    version = fuente.get("version")
    cabeza = f"Según «{titulo}»" + (f" (v{version})" if version and f"(v{version})" not in titulo else "")
    partes: list[str] = []
    total = 0
    for f in [mejor, *sorted(otras, key=lambda x: (x.n, x.posicion))]:
        t = _recortar(f.texto, 400).rstrip(" .;:,")
        if partes and total + len(t) > MAX_EXTRACTIVA:
            break
        partes.append(f"{t} [{f.n}].")
        total += len(t)
    return f"{cabeza}: " + " ".join(partes)


# --------------------------------------------------------------------------- preparación


@dataclass
class Preparada:
    """Todo lo necesario para pedir la respuesta al modelo y guardarla después."""

    pregunta: str
    modo: str
    mensajes: list[dict[str, Any]]
    fuentes: list[dict[str, Any]]
    con_contexto: bool
    modelo: str
    temperatura: float
    max_tokens: int | None
    tarea_id: int | None = None
    paso_id: int | None = None
    ejecucion_id: int | None = None
    paso_critico: bool = False
    usar_memoria: bool = False
    contar_ejecucion: bool = False  # sumar la consulta a la ejecución (solo desde /api/consulta)
    inicio: float = field(default_factory=time.monotonic)
    # Respaldo claro: frases que responden (vacía = la respuesta del modelo nunca se rehace).
    evidencia: list[Frase] = field(default_factory=list)
    contexto_directo: str = ""  # contexto del reintento
    textos_evidencia: dict[int, str] = field(default_factory=dict)  # n → texto de los fragmentos del reintento
    empresa: str | None = None
    pregunta_terminos: str = ""  # texto con el que se buscó la evidencia (la pregunta y, si acaso, tarea o puesto)
    rehecha: str | None = None  # «reintento» o «extractiva» si se rehízo la respuesta del modelo


def _recortar(texto: str, maximo: int) -> str:
    texto = (texto or "").strip()
    if len(texto) <= maximo:
        return texto
    corte = texto[:maximo].rsplit(" ", 1)[0]
    return corte + "…"


MAX_ID = 2**31 - 1  # las claves son INTEGER de PostgreSQL


def _entero(valor: Any) -> int | None:
    try:
        n = int(valor) if valor not in (None, "") else None
    except (TypeError, ValueError):
        n = -1
    if n is not None and not 0 < n <= MAX_ID:
        raise HTTPException(400, "El contexto de la consulta no es válido.")
    return n


def _puede_abrir_tarea(bd: Session, actor: Actor, alcance: Alcance, tarea: Tarea) -> bool:
    """La misma regla que el modo planta: tareas activas de su departamento hasta su nivel y las de
    sus formaciones activas (solo las de ese puesto si la formación es de un puesto). La
    administración, todas."""
    if alcance.todo:
        return True
    dep = tarea.puesto.departamento_id if tarea.puesto else None
    if not tarea.activa or dep is None or dep not in departamentos_visibles(alcance):
        return False
    if dep == actor.departamento_id and (tarea.nivel_minimo or 1) <= actor.nivel_orden:
        return True
    formaciones = bd.scalars(
        select(Formacion).where(Formacion.usuario_id == actor.id, Formacion.estado == "activa")
    ).all()
    return any((f.puesto_id == tarea.puesto_id) if f.puesto_id else (f.departamento_id == dep) for f in formaciones)


def _cargar_tarea(bd: Session, actor: Actor, alcance: Alcance,
                  contexto: dict[str, Any] | None) -> tuple[dict[str, Any] | None, int | None, int | None, int | None, bool]:
    """Valida el contexto {tarea_id, paso_id, ejecucion_id} y carga la tarea y el paso actual.

    El texto del paso va al prompt, así que se exige lo mismo que para verlo: la ejecución tiene
    que ser propia, el paso de su instrucción (o de una instrucción publicada, salvo para los
    expertos del departamento) y la tarea una de las que la persona puede abrir.
    Devuelve (datos para el prompt, tarea_id, paso_id, ejecucion_id, paso_critico).
    """
    contexto = contexto or {}
    tarea_id = _entero(contexto.get("tarea_id"))
    paso_id = _entero(contexto.get("paso_id"))
    ejecucion_id = _entero(contexto.get("ejecucion_id"))
    if not (tarea_id or paso_id or ejecucion_id):
        return None, None, None, None, False
    if actor.es_invitado:
        raise HTTPException(403, "Para preguntar sobre una tarea tienes que iniciar sesión.")
    ej: Ejecucion | None = None
    if ejecucion_id:
        ej = bd.get(Ejecucion, ejecucion_id)
        if ej is None or ej.usuario_id != actor.id:
            raise HTTPException(404, "No se encuentra esa ejecución.")
        if tarea_id and ej.tarea_id != tarea_id:
            raise HTTPException(400, "La ejecución no corresponde a esa tarea.")
        tarea_id = ej.tarea_id
    paso: Paso | None = None
    if paso_id:
        paso = bd.get(Paso, paso_id)
        if paso is None:
            raise HTTPException(404, "No se encuentra ese paso.")
        if ej is not None and paso.instruccion_id != ej.instruccion_id:
            raise HTTPException(400, "El paso no pertenece a esta ejecución.")
        tarea_paso = paso.instruccion.tarea_id
        if tarea_id and tarea_paso != tarea_id:
            raise HTTPException(400, "El paso no pertenece a esa tarea.")
        tarea_id = tarea_paso
    tarea = bd.get(Tarea, tarea_id) if tarea_id else None
    if tarea is None:
        raise HTTPException(404, "No se encuentra esa tarea.")
    if not _puede_abrir_tarea(bd, actor, alcance, tarea):
        raise HTTPException(403, "No tienes acceso a esa tarea.")
    if paso is not None and ej is None and paso.instruccion.estado not in ("publicada", "obsoleta"):
        # Un borrador solo lo ven sus expertos: para los demás no existe.
        dep = tarea.puesto.departamento_id if tarea.puesto else None
        if not (alcance.todo or (actor.es_experto and actor.departamento_id == dep)):
            raise HTTPException(404, "No se encuentra ese paso.")
    datos: dict[str, Any] = {"nombre": tarea.nombre, "codigo": tarea.codigo}
    if paso is not None:
        datos["paso"] = {"orden": paso.orden, "titulo": paso.titulo, "texto": _recortar(paso.texto or "", 1200),
                         "es_critico": paso.es_critico or paso.es_seguridad}
    return datos, tarea_id, paso_id, ejecucion_id, bool(paso and paso.es_critico)


def _historial(historial: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Normaliza el historial ({rol, texto} o {role, content}) y se queda con los últimos turnos."""
    salida: list[dict[str, str]] = []
    for h in (historial or [])[-MAX_HISTORIAL:]:
        if not isinstance(h, dict):
            continue
        rol = h.get("role") or h.get("rol")
        texto = h.get("content") if h.get("content") is not None else h.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            continue
        if rol in ("user", "usuario"):
            salida.append({"role": "user", "content": _recortar(texto, MAX_TURNO)})
        elif rol in ("assistant", "asistente"):
            # Las citas antiguas apuntan a otra numeración: se quitan para no confundir al modelo.
            salida.append({"role": "assistant", "content": _recortar(_RE_CITA.sub("", texto), MAX_TURNO)})
    return salida


MAX_TAREAS_PERSONA = 6


def _persona(bd: Session, actor: Actor) -> dict[str, Any] | None:
    """Puesto, departamento y tareas de quien pregunta (para entender «mi puesto» o «mi tarea»).
    Solo las tareas activas de su puesto que le corresponden por nivel."""
    u = actor.usuario
    if u is None or u.puesto is None:
        return None
    tareas = bd.scalars(
        select(Tarea).where(Tarea.puesto_id == u.puesto_id, Tarea.activa.is_(True),
                            Tarea.nivel_minimo <= max(1, actor.nivel_orden))
        .order_by(Tarea.codigo, Tarea.id).limit(MAX_TAREAS_PERSONA)
    ).all()
    return {
        "puesto": u.puesto.nombre,
        "departamento": u.departamento.nombre if u.departamento else None,
        "tareas": [f"{t.nombre} ({t.codigo})" if t.codigo else t.nombre for t in tareas],
    }


def _consulta_busqueda(pregunta: str, tarea: dict[str, Any] | None, historial: list[dict[str, str]],
                       persona: dict[str, Any] | None = None) -> tuple[str, str]:
    """Texto que se busca: la pregunta, con la tarea y el paso, el puesto de quien pregunta («mi tarea»)
    o la pregunta anterior si ayudan. Devuelve (texto de la búsqueda, texto con el que se comprueba la
    coincidencia de palabras: sin la lista de tareas del puesto, que diluiría la pregunta).

    Con una tarea en curso (modo planta), la coincidencia se comprueba solo con la pregunta: el nombre de la
    tarea y el título del paso ya están en el título y en el texto del fragmento, y añadidos a la pregunta
    impedían que ninguna frase reuniera la mitad de sus palabras (sin evidencia, la respuesta de un modelo
    pequeño que dice SIN_RESPALDO no se rehacía)."""
    if tarea:
        paso = tarea.get("paso") or {}
        texto = " ".join(x for x in (tarea["nombre"], paso.get("titulo") or "", pregunta) if x)
        return texto, pregunta
    if persona and _RE_MI_PUESTO.search(pregunta):
        tareas = "; ".join(persona["tareas"])
        return f"{pregunta} {persona['puesto']}. {tareas}", f"{pregunta} {persona['puesto']}"
    if historial and len(pregunta.split()) < 6:
        anteriores = [h["content"] for h in historial if h["role"] == "user"]
        if anteriores:
            texto = f"{anteriores[-1]} {pregunta}"
            return texto, texto
    return pregunta, pregunta


def _fuentes_y_contexto(bd: Session, encontrados: list[Encontrado]) -> tuple[list[dict[str, Any]], str, list[str]]:
    """(fuentes, contexto numerado, texto de cada fragmento tal y como va en el contexto)."""
    docs = {d.id: d for d in bd.scalars(
        select(Documento).where(Documento.id.in_({e.documento_id for e in encontrados}))
    ).all()} if encontrados else {}
    fuentes: list[dict[str, Any]] = []
    bloques: list[str] = []
    textos: list[str] = []
    total = 0
    for e in encontrados:
        meta = e.metadatos or {}
        d = docs.get(e.documento_id)
        texto = _recortar(e.texto, MAX_FRAGMENTO_CONTEXTO)
        if fuentes and total + len(texto) > MAX_CONTEXTO:
            break
        n = len(fuentes) + 1
        autor = meta.get("autor") or (d.autor.nombre if d and d.autor else None)
        validador = meta.get("validador") or (d.validador.nombre if d and d.validador else None)
        version = meta.get("version") or (d.version if d else None)
        fuentes.append({
            "n": n,
            "documento_id": e.documento_id,
            "titulo": e.titulo,
            "tipo": meta.get("tipo") or (d.tipo if d else None),
            "version": version,
            "paso": meta.get("paso"),
            "paso_id": meta.get("paso_id"),
            "codigo": meta.get("codigo"),
            "pagina": meta.get("pagina"),
            "hoja": meta.get("hoja"),
            "diapositiva": meta.get("diapositiva"),
            "autor": autor,
            "validador": validador,
            "origen": meta.get("origen") or (d.origen if d else None),
            "origen_id": meta.get("origen_id") or (d.origen_id if d else None),
            "fragmento": _recortar(e.texto, MAX_FRAGMENTO_FUENTE),
            "similitud": round(e.similitud, 3) if e.similitud is not None else None,
            "url": url_fichero(d.ruta_fichero) if d and d.ruta_fichero else None,
        })
        bloques.append(prompts.fragmento_contexto(n, e.titulo, texto, version, meta.get("paso"), autor, validador,
                                                  meta.get("codigo")))
        textos.append(texto)
        total += len(texto)
    _anadir_tarea(bd, fuentes)
    return fuentes, "\n\n".join(bloques), textos


def _anadir_tarea(bd: Session, fuentes: list[dict[str, Any]]) -> None:
    """Añade `tarea_id` a las fuentes que son una instrucción: la interfaz enlaza con la tarea en
    formación o en el modo planta (el editor de instrucciones solo lo abren expertos y jefes)."""
    ids = {f.get("origen_id") for f in fuentes
           if f.get("origen") == "instruccion" and f.get("origen_id") and not f.get("tarea_id")}
    if not ids:
        return
    tareas = dict(bd.execute(select(Instruccion.id, Instruccion.tarea_id).where(Instruccion.id.in_(ids))).all())
    for f in fuentes:
        if f.get("origen") == "instruccion" and not f.get("tarea_id"):
            f["tarea_id"] = tareas.get(f.get("origen_id"))


def preparar(bd: Session, actor: Actor, pregunta: str, modo: str = "normal",
             contexto: dict[str, Any] | None = None,
             historial: list[dict[str, Any]] | None = None,
             contar_ejecucion: bool = False) -> Preparada:
    """Trabajo previo a la respuesta. Lanza HTTPException si la petición no es válida o no está permitida.

    `contar_ejecucion`: sumar la consulta a la ejecución del contexto ya aquí, al preguntar (ver el
    comentario del módulo; el modo planta ya la cuenta por su cuenta). Hace commit."""
    inicio = time.monotonic()
    pregunta = (pregunta or "").strip()
    if not pregunta:
        raise HTTPException(400, "Escribe una pregunta.")
    if len(pregunta) > MAX_PREGUNTA:
        raise HTTPException(400, "La pregunta es demasiado larga. Resúmela un poco, por favor.")
    if modo not in MODOS:
        raise HTTPException(400, "Modo de consulta no válido.")
    if modo == "planta" and actor.es_invitado:
        raise HTTPException(403, "El modo planta necesita iniciar sesión.")
    limitar_invitado(bd, actor)
    alcance = alcance_de(bd, actor)
    tarea, tarea_id, paso_id, ejecucion_id, paso_critico = _cargar_tarea(bd, actor, alcance, contexto)
    try:
        modelo = llm.modelo_permitido(bd, "chat")
    except llm.ErrorModelo as e:
        raise HTTPException(503, str(e)) from e
    hist = _historial(historial)
    persona = _persona(bd, actor)
    busqueda, texto_terminos = _consulta_busqueda(pregunta, tarea, hist, persona)

    try:
        encontrados = _buscar(bd, alcance, busqueda)
    except llm.ErrorModelo as e:
        log.warning("Búsqueda sin modelo de embeddings: %s", e)
        raise HTTPException(503, "El buscador de conocimiento no está disponible ahora mismo. "
                                 "Inténtalo de nuevo en unos segundos.") from e
    respaldan = con_respaldo(encontrados, texto_terminos)
    fuentes, texto_contexto, textos = _fuentes_y_contexto(bd, respaldan)

    usar_memoria = bool(actor.usuario and actor.usuario.memoria_activa)
    recuerdos = [m.contenido for m in memoria.relevantes(bd, actor.id, pregunta, RECUERDOS_POR_CONSULTA)] \
        if usar_memoria and actor.id else []
    empresa = bd.scalar(select(Empresa.nombre).limit(1))
    # El puesto de quien pregunta solo va al prompt cuando la pregunta habla de sí misma («mi tarea»,
    # «¿qué EPI necesito?»): en las demás distrae a los modelos pequeños del CONTEXTO.
    habla_de_si = bool(_RE_MI_PUESTO.search(pregunta) or _RE_HABLA_DE_SI.search(pregunta)
                       or re.search(r"\bnecesito\b|\bme toca\b|\bdebo\b", pregunta, re.I))
    sistema = prompts.sistema_consulta(modo, bool(fuentes), empresa, tarea, recuerdos,
                                       persona if habla_de_si else None)
    mensajes = [{"role": "system", "content": sistema}, *hist,
                {"role": "user", "content": prompts.usuario_consulta(pregunta, texto_contexto or None)}]
    # En el modo tutor no se rehace la respuesta: una respuesta directa o extractiva le daría la solución.
    frases = evidencia(fuentes, textos, texto_terminos, empresa) \
        if fuentes and modo != "socratico" and respaldo_claro(respaldan, texto_terminos) else []
    prep = Preparada(
        pregunta=pregunta, modo=modo, mensajes=mensajes, fuentes=fuentes, con_contexto=bool(fuentes), modelo=modelo,
        temperatura=0.4 if modo == "socratico" else 0.2,
        max_tokens=350 if modo == "planta" else 900,
        tarea_id=tarea_id, paso_id=paso_id, ejecucion_id=ejecucion_id, paso_critico=paso_critico,
        usar_memoria=usar_memoria, contar_ejecucion=contar_ejecucion, inicio=inicio,
        evidencia=frases, contexto_directo=_contexto_directo(fuentes, textos, frases) if frases else "",
        textos_evidencia={n: textos[n - 1] for n in list(dict.fromkeys(f.n for f in frases))[:MAX_FRAGMENTOS_REINTENTO]},
        empresa=empresa, pregunta_terminos=texto_terminos,
    )
    # La consulta cuenta en la ejecución al preguntar (como en el modo planta), no al terminar la
    # respuesta: así no se libra quien corta el streaming a mitad.
    _contar_en_ejecucion(bd, prep)
    # Commit también sin cambios: libera la conexión mientras el modelo escribe (puede tardar), para
    # que unas cuantas respuestas a la vez no agoten las conexiones de la base de datos.
    bd.commit()
    return prep


# --------------------------------------------------------------------------- respuesta


class FiltroMarca:
    """Limpia el texto del modelo aunque llegue partido entre varios trozos del streaming: quita la
    marca SIN_RESPALDO (y anota que la ha visto) y los restos de razonamiento (<think>…</think> o una
    etiqueta suelta), que nunca deben llegar a la persona."""

    def __init__(self) -> None:
        self.pendiente = ""
        self.vista = False  # el modelo ha dicho que no tiene respaldo
        self.emitido = False

    def alimentar(self, delta: str) -> str:
        self.pendiente += delta
        # Al principio se espera a tener unos cuantos caracteres: ahí suele ir la marca.
        if not self.emitido and len(self.pendiente.lstrip()) < len(prompts.MARCA_SIN_RESPALDO) + 4:
            return ""
        return self._soltar(final=False)

    def terminar(self) -> str:
        return self._soltar(final=True)

    def _soltar(self, final: bool) -> str:
        t = _RE_PENSAMIENTO.sub("", self.pendiente)
        # Un razonamiento abierto y sin cerrar todavía: se guarda hasta su cierre (al final se descarta).
        en_pensamiento = ""
        abre = t.lower().rfind("<think>")
        if abre != -1:
            t, en_pensamiento = t[:abre], ("" if final else t[abre:])
        t = _RE_ETIQUETA_PENSAMIENTO.sub("", t)
        if _RE_MARCA.search(t):
            self.vista = True
            t = _RE_MARCA.sub("", t)
        if self.vista and not self.emitido:
            # Tras la marca, el eco de la regla («, no lo sabes.») no llega a la persona. Mientras pueda
            # serlo (un trozo corto como «, no lo»), se espera al siguiente.
            s = t.lstrip(" \t\n,;:.-–")
            m = _RE_ECO_REGLA.match(s)
            if m and (final or re.search(r"[.!\n]\s*$", m.group(0))):
                t = s[m.end():]
            elif not final and not en_pensamiento and (m or any(e.startswith(s.lower()) for e in _ECOS_REGLA)):
                self.pendiente = t
                return ""
        retener = 0
        if not final and not en_pensamiento:
            # Un posible comienzo de la marca («SIN_RES», «**») o de una etiqueta («</thi») al final
            # espera al siguiente trozo.
            for prefijo in (prompts.MARCA_SIN_RESPALDO, *_ETIQUETAS_PENSAMIENTO):
                for i in range(len(prefijo) - 1, retener, -1):
                    if t.endswith(prefijo[:i]):
                        retener = i
                        break
            while retener < len(t) and t[len(t) - retener - 1] in _ABRE_MARCA:
                retener += 1
        salida, self.pendiente = t[: len(t) - retener], t[len(t) - retener:] + en_pensamiento
        if not self.emitido:
            salida = salida.lstrip(" \t\n:.,;-–")
            self.emitido = bool(salida)
        return salida


def citadas(texto: str, n_fuentes: int) -> list[int]:
    """Números de fuente que aparecen citados en la respuesta ([1], [2][3] o [1, 2])."""
    vistos: set[int] = set()
    for grupo in _RE_CITA.findall(texto or ""):
        for parte in grupo.split(","):
            n = int(parte.strip())
            if 1 <= n <= n_fuentes:
                vistos.add(n)
    return sorted(vistos)


def respaldada(texto: str, marca_vista: bool, n_fuentes: int) -> bool:
    """¿La respuesta se apoya de verdad en el contexto?

    Los modelos pequeños se equivocan con la marca en los dos sentidos: escriben SIN_RESPALDO y a
    continuación responden con los fragmentos citándolos, o dicen «no lo encuentro» sin la marca.
    Manda lo que hacen: con la marca solo cuenta como respaldada si cita fragmentos que existen y
    no dice que no lo encuentra; sin la marca, una negativa sin ninguna cita tampoco es respaldo."""
    if n_fuentes <= 0:
        return False
    citas = citadas(texto, n_fuentes)
    niega = bool(_RE_NIEGA.search((texto or "")[:300]))
    if marca_vista:
        return bool(citas) and not niega
    return bool(citas) or not niega


def _redaccion_valida(prep: Preparada, texto: str, marca_vista: bool) -> bool:
    """¿Sirve lo que ha escrito el modelo? Se juzga solo cuando el respaldo es claro (prep.evidencia):
    no vale vacía, ni un «no lo encuentro» (respaldada()), ni sin relación con la pregunta (sin citas y
    sin ninguna palabra en común)."""
    t = (texto or "").strip()
    if not t or not respaldada(t, marca_vista, len(prep.fuentes)):
        return False
    return bool(citadas(t, len(prep.fuentes))) or bool(_raices(t) & _raices(prep.pregunta))


def _sin_eco(prep: Preparada, texto: str) -> str:
    """Quita la cabecera del fragmento que algunos modelos copian al principio («[1] Guía de acogida en
    Producción (versión 1)»); si la cita iba en ella, la pone al final de la respuesta."""
    for n in dict.fromkeys(f.n for f in prep.evidencia):
        titulo = prep.fuentes[n - 1].get("titulo") or ""
        eco = re.compile(rf"^\s*\[{n}\]\s*{re.escape(titulo)}\s*(?:\([^)]*\))?\s*[:.\-–]?\s*", re.I)
        if titulo and eco.match(texto):
            resto = eco.sub("", texto, count=1).strip()
            if resto and not citadas(resto, len(prep.fuentes)):
                resto = re.sub(r"\s*([.!?]?)\s*$", rf" [{n}]\1", resto, count=1)
            texto = resto
    # «La respuesta está en el fragmento [2]. La gerencia…»: el modelo repite el prompt del reintento. Se
    # quita esa frase y la cita pasa al final de lo que respalda.
    m = _RE_ECO_FRAGMENTO.match(texto)
    if m and texto[m.end():].strip():
        resto = texto[m.end():].strip()
        resto = resto[0].upper() + resto[1:]
        if not citadas(resto, len(prep.fuentes)):
            resto = re.sub(r"\s*([.!?]?)\s*$", rf" [{m.group(1)}]\1", resto, count=1)
        texto = resto
    # «[1] La P3 se engrasa…»: la cita va detrás de lo que respalda.
    m = re.match(r"\s*(\[\d{1,2}\])\s*(\S.*)$", texto, re.S)
    if m and not _RE_CITA.search(m.group(2)):
        texto = re.sub(r"\s*([.!?]?)\s*$", rf" {m.group(1)}\1", m.group(2), count=1)
    return texto


def _reintento_valido(prep: Preparada, texto: str) -> str | None:
    """La respuesta del reintento, limpia, si sirve: cita, no niega, dice algo del fragmento que no estaba
    ya en la pregunta ni en el título, no trae cifras que no estén en el contexto y, si se pregunta por
    una cantidad, la da. Si no sirve, None (y se compone la respuesta extractiva)."""
    t = _sin_eco(prep, (texto or "").strip())
    if not t or not citadas(t, len(prep.fuentes)) or _RE_NIEGA.search(t[:300]):
        return None
    cuerpo = " ".join(f for texto_n in prep.textos_evidencia.values() for _, f in unidades(texto_n))
    titulos = " ".join(prep.fuentes[n - 1].get("titulo") or "" for n in {f.n for f in prep.evidencia})
    nuevas = _raices(t) - _raices(prep.pregunta) - _raices(titulos)
    if not nuevas & _raices(cuerpo):
        return None
    sin_citas = _RE_CITA.sub("", t)
    if set(_RE_CIFRA.findall(sin_citas)) - set(_RE_CIFRA.findall(f"{cuerpo} {titulos} {prep.pregunta}")):
        return None  # una cifra inventada
    # Tiene que decir buena parte de lo que aporta la mejor frase (no basta con una palabra suelta).
    mejor = prep.evidencia[0].texto
    fijas = _raices(prep.pregunta_terminos) | _raices(titulos) | _GENERICAS
    aporta = (_raices(mejor) - fijas) | (set(_RE_CIFRA.findall(mejor)) - set(_RE_CIFRA.findall(f"{titulos} {prep.pregunta}")))
    dice = (_raices(sin_citas) | set(_RE_CIFRA.findall(sin_citas))) & aporta
    if aporta and len(dice) < MIN_PARECIDO_REINTENTO * len(aporta):
        return None
    pide_numero, _ = _pide_numero(prep.pregunta)
    if pide_numero and not _RE_NUMERO.search(_normal(sin_citas)):
        return None
    return t


def _mensajes_directos(prep: Preparada) -> list[dict[str, Any]]:
    n = prep.evidencia[0].n
    return [{"role": "system", "content": prompts.sistema_directo(prep.empresa, n)},
            {"role": "user", "content": prompts.usuario_directo(prep.pregunta, prep.contexto_directo, n)}]


def _rehacer(prep: Preparada, bruto: str) -> str:
    """Respuesta rehecha a partir de lo que escribió el reintento: la suya si sirve o, si no, la
    extractiva. Anota en prep.rehecha cuál ha sido."""
    filtro = FiltroMarca()
    valido = _reintento_valido(prep, filtro.alimentar(bruto or "") + filtro.terminar())
    prep.rehecha = "reintento" if valido else "extractiva"
    log.info("Respuesta rehecha (%s) con el modelo %s", prep.rehecha, prep.modelo)
    return valido or respuesta_extractiva(prep)


class _Intento:
    """La primera redacción del modelo en streaming. Con `retener`, no suelta nada mientras pueda acabar
    siendo un «no lo encuentro» (marca SIN_RESPALDO, una negativa o, al principio, nada citado): si lo es,
    la respuesta se rehace sin que la persona haya visto la mala. Sin `retener`, deja pasar todo al momento."""

    def __init__(self, n_fuentes: int, retener: bool) -> None:
        self.filtro = FiltroMarca()
        self.n_fuentes = n_fuentes
        self.soltado = not retener
        self.retenido = ""
        self.emitido = ""

    def alimentar(self, delta: str) -> str:
        return self._pasar(self.filtro.alimentar(delta))

    def terminar(self) -> str:
        return self._pasar(self.filtro.terminar())

    def soltar(self) -> str:
        """Deja pasar lo retenido (se ha dado por bueno)."""
        t, self.retenido, self.soltado = self.retenido, "", True
        self.emitido += t
        return t

    def sin_emitir(self) -> str:
        """Lo que el modelo escribió y la persona no llegó a ver (para guardar una respuesta cortada)."""
        return self.retenido + self.filtro.terminar()

    def _pasar(self, visible: str) -> str:
        if self.soltado:
            self.emitido += visible
            return visible
        self.retenido += visible
        return self.soltar() if self._fiable() else ""

    def _fiable(self) -> bool:
        t = self.retenido
        if self.filtro.vista or _RE_NIEGA.search(t[:300]):
            return False
        return bool(citadas(t, self.n_fuentes)) or len(t.strip()) >= 120

    @property
    def texto(self) -> str:
        return (self.emitido + self.retenido).strip()

    @property
    def vista(self) -> bool:
        return self.filtro.vista


def _merece_laguna(pregunta: str) -> bool:
    """Un saludo o un «gracias» no es una laguna de conocimiento."""
    palabras = [p for p in re.findall(r"\w+", lagunas._normalizar(pregunta)) if len(p) >= 3]
    return len(palabras) >= 2 and any(p not in _CORTESIA for p in palabras)


def _contar_en_ejecucion(bd: Session, prep: Preparada) -> None:
    """Curva de autonomía: suma la consulta a la ejecución en curso y a su paso (solo si se pidió).
    No hace commit.

    Incrementos en SQL, como el modo planta (servicios/planta.registrar_consulta): dos preguntas que
    se procesan a la vez no pueden perder una consulta de la curva."""
    if not (prep.contar_ejecucion and prep.ejecucion_id):
        return
    sumadas = bd.execute(
        update(Ejecucion).where(Ejecucion.id == prep.ejecucion_id, Ejecucion.estado == "en_curso")
        .values(consultas=func.coalesce(Ejecucion.consultas, 0) + 1,
                consultas_criticos=func.coalesce(Ejecucion.consultas_criticos, 0) + (1 if prep.paso_critico else 0))
        .execution_options(synchronize_session=False)
    ).rowcount
    if not sumadas or not prep.paso_id:
        return  # ejecución terminada o abandonada: ya no cuenta
    ej = bd.get(Ejecucion, prep.ejecucion_id)
    if ej is not None:
        bd.expire(ej, ["consultas", "consultas_criticos"])
    filtro = (EjecucionPaso.ejecucion_id == prep.ejecucion_id, EjecucionPaso.paso_id == prep.paso_id)
    mas_una = {"consultas": func.coalesce(EjecucionPaso.consultas, 0) + 1}
    if bd.execute(update(EjecucionPaso).where(*filtro).values(**mas_una)
                  .execution_options(synchronize_session=False)).rowcount:
        return
    # El modo planta crea las filas de los pasos al empezar; si falta, se crea aquí. Si otra petición
    # la crea a la vez (restricción única ejecucion_id + paso_id), se suma sobre la suya.
    try:
        with bd.begin_nested():
            bd.add(EjecucionPaso(ejecucion_id=prep.ejecucion_id, paso_id=prep.paso_id, consultas=1))
    except IntegrityError:
        bd.execute(update(EjecucionPaso).where(*filtro).values(**mas_una)
                   .execution_options(synchronize_session=False))


def finalizar(bd: Session, actor: Actor, prep: Preparada, texto: str, marca_vista: bool,
              interrumpida: bool = False) -> dict[str, Any]:
    """Guarda la consulta, registra xAPI, apunta la laguna si no hubo respaldo y hace commit.

    `interrumpida`: la respuesta se cortó a mitad (se guarda lo que llegó a escribirse, o nada)."""
    # Si había documentación y el modelo no ha escrito nada, el fallo es del modelo, no una laguna.
    fallo_del_modelo = prep.con_contexto and (texto or "").strip() == _SIN_TEXTO
    if fallo_del_modelo:
        respaldo = False
    elif interrumpida and not (texto or "").strip():
        # Una respuesta interrumpida antes de escribir nada no se juzga por su texto (no lo hay).
        respaldo = prep.con_contexto and not marca_vista
    else:
        respaldo = prep.con_contexto and respaldada(texto, marca_vista, len(prep.fuentes))
    citas = citadas(texto, len(prep.fuentes)) if respaldo else []
    duracion = int((time.monotonic() - prep.inicio) * 1000)
    laguna_id = None
    pregunta_real = _merece_laguna(prep.pregunta)
    if not respaldo and not actor.es_invitado and pregunta_real and not fallo_del_modelo:
        try:
            # Punto de guardado: si la laguna falla en la BD, la sesión sigue sirviendo para la consulta.
            with bd.begin_nested():
                laguna_id = lagunas.registrar(bd, prep.pregunta, actor.departamento_id, prep.tarea_id).id
        except Exception:  # noqa: BLE001  (apuntar la laguna nunca debe romper la respuesta)
            log.exception("No se pudo registrar la laguna")
            laguna_id = None
    # Avisar de que no hay respaldo tiene sentido para una pregunta, no para un «hola» o un «gracias».
    aviso = not respaldo and not fallo_del_modelo and (marca_vista or pregunta_real)
    c = Consulta(
        usuario_id=actor.id,
        sesion_id=actor.sesion.id if actor.sesion is not None else None,
        pregunta=prep.pregunta,
        respuesta=texto or None,
        modo=prep.modo,
        fuentes=prep.fuentes,
        con_respaldo=respaldo,
        laguna_id=laguna_id,
        tarea_id=prep.tarea_id,
        paso_id=prep.paso_id,
        ejecucion_id=prep.ejecucion_id,
        modelo=prep.modelo,
        duracion_ms=duracion,
    )
    bd.add(c)
    bd.flush()
    resultado: dict[str, Any] = {"con_respaldo": respaldo, "fuentes": len(prep.fuentes), "citadas": citas,
                                 "duracion_ms": duracion, "laguna_id": laguna_id}
    if interrumpida:
        resultado["interrumpida"] = True
    if prep.rehecha:
        resultado["rehecha"] = prep.rehecha  # el modelo no supo responder con un respaldo claro
    registrar(
        bd, actor, "pregunto", "consulta", c.id, _recortar(prep.pregunta, 200),
        resultado=resultado,
        contexto={"modo": prep.modo, "tarea_id": prep.tarea_id, "paso_id": prep.paso_id,
                  "ejecucion_id": prep.ejecucion_id, "modelo": prep.modelo},
    )
    bd.commit()
    if prep.usar_memoria and actor.id and not interrumpida and _RE_HABLA_DE_SI.search(prep.pregunta):
        memoria.encolar_extraccion(actor.id, prep.pregunta, texto)
    return {"consulta_id": c.id, "con_respaldo": respaldo, "laguna_id": laguna_id, "citadas": citas,
            "duracion_ms": duracion, "aviso_sin_respaldo": aviso}


_SIN_TEXTO = "No he podido generar una respuesta. Prueba a reformular la pregunta, por favor."
# Los modelos pequeños a veces escriben solo la marca SIN_RESPALDO: es un «no lo encuentro», no un fallo.
_NO_ENCONTRADO = ("No lo he encontrado en la documentación a la que tienes acceso. "
                  "Consúltalo con tu responsable o con una persona experta.")


def _texto_vacio(marca_vista: bool) -> str:
    """Lo que se muestra cuando, quitada la marca y el razonamiento, el modelo no ha escrito nada."""
    return _NO_ENCONTRADO if marca_vista else _SIN_TEXTO


_MODELO_CAIDO = "El modelo no responde ahora mismo. Inténtalo de nuevo en unos segundos."


def _en_hilo(funcion: Callable[[], None]) -> None:
    threading.Thread(target=funcion, name="cidia-consulta", daemon=True).start()


# Cómo se lanza el guardado de una respuesta interrumpida (las pruebas lo hacen en el mismo hilo).
lanzar_en_segundo_plano: Callable[[Callable[[], None]], None] = _en_hilo


def _guardar_interrumpida(actor: Actor, prep: Preparada, texto: str, marca_vista: bool) -> None:
    """Guarda en segundo plano una consulta cuya respuesta se cortó (la persona la detuvo o se fue).

    Se llama desde el `finally` de un generador cancelado: no puede esperar a nada ni usar la sesión
    de la petición (se está cerrando), así que abre la suya y reconstruye el actor por sus ids."""
    sesion_id = actor.sesion.id if actor.sesion is not None else None
    usuario_id = actor.id

    def guardar() -> None:
        try:
            with sesion_bd() as bd:
                sesion = bd.get(Sesion, sesion_id) if sesion_id else None
                usuario = bd.get(Usuario, usuario_id) if usuario_id else None
                if sesion is None or (usuario_id and usuario is None):
                    return
                finalizar(bd, Actor(sesion=sesion, usuario=usuario), prep, texto, marca_vista, interrumpida=True)
        except Exception:  # noqa: BLE001  (nunca debe romper nada: solo se pierde el registro)
            log.exception("No se pudo guardar la consulta interrumpida")

    lanzar_en_segundo_plano(guardar)


async def emitir(bd: Session, actor: Actor, prep: Preparada) -> AsyncIterator[dict[str, Any]]:
    """Eventos de una consulta ya preparada: fuentes, tokens y fin (o error).

    Si el generador se cierra antes de terminar (la persona detiene la respuesta o se corta la
    conexión), la consulta se guarda igual en segundo plano con el texto que llegó a escribirse.

    Con respaldo claro (prep.evidencia), lo que escribe el modelo se retiene mientras pueda ser un «no lo
    encuentro»; si lo es, se rehace (reintento directo y, si no, respuesta extractiva) y se emiten los
    tokens de la nueva respuesta. La persona solo ve la respuesta que vale."""
    rehacer = bool(prep.evidencia)
    actual = _Intento(len(prep.fuentes), retener=rehacer)
    partes: list[str] = []  # lo que ha llegado a la persona
    pendiente = True  # nadie más va a guardar esta consulta si el generador se corta aquí
    try:
        yield {"tipo": "fuentes", "fuentes": prep.fuentes}
        try:
            async for delta in llm.chat_stream(prep.mensajes, prep.modelo, temperatura=prep.temperatura,
                                               max_tokens=prep.max_tokens):
                visible = actual.alimentar(delta)
                if visible:
                    partes.append(visible)
                    yield {"tipo": "token", "texto": visible}
            resto = actual.terminar()
            if resto:
                partes.append(resto)
                yield {"tipo": "token", "texto": resto}
            if rehacer and not actual.soltado:
                if _redaccion_valida(prep, actual.texto, actual.vista):
                    resto = actual.soltar()
                else:
                    # El reintento es corto (una o dos frases): se lee entero y se juzga antes de enseñarlo.
                    bruto: list[str] = []
                    try:
                        async for delta in llm.chat_stream(_mensajes_directos(prep), prep.modelo, temperatura=0.1,
                                                           max_tokens=MAX_TOKENS_REINTENTO):
                            bruto.append(delta)
                    except llm.ErrorModelo as e:
                        log.warning("El reintento de la consulta falló: %s", e)
                    resto = _rehacer(prep, "".join(bruto))
                    actual = _Intento(len(prep.fuentes), retener=False)
                # Los tokens de la respuesta que vale, palabra a palabra.
                for trozo in re.findall(r"\s*\S+\s*", resto):
                    partes.append(trozo)
                    yield {"tipo": "token", "texto": trozo}
        except llm.ErrorModelo as e:
            log.warning("El modelo falló durante la consulta: %s", e)
            pendiente = False
            yield {"tipo": "error", "mensaje": _MODELO_CAIDO}
            return
        except Exception:  # noqa: BLE001  (un fallo inesperado no deja el flujo cortado sin explicación)
            # Lo que llegó a escribirse se guarda como respuesta interrumpida (en el finally).
            log.exception("Fallo inesperado durante la respuesta en streaming")
            yield {"tipo": "error", "mensaje": _MODELO_CAIDO}
            return
        texto = "".join(partes).strip()
        if not texto:
            texto = _texto_vacio(actual.vista)
            yield {"tipo": "token", "texto": texto}
        pendiente = False  # a partir de aquí la guarda finalizar() (aunque se cancele la espera, el hilo sigue)
        try:
            fin = await run_in_threadpool(finalizar, bd, actor, prep, texto, actual.vista)
        except Exception:  # noqa: BLE001
            log.exception("No se pudo guardar la consulta")
            bd.rollback()
            yield {"tipo": "error", "mensaje": "La respuesta se ha generado, pero no se ha podido guardar."}
            return
        yield {"tipo": "fin", **fin}
    finally:
        if pendiente:
            texto = ("".join(partes) + actual.sin_emitir()).strip()
            _guardar_interrumpida(actor, prep, texto, actual.vista)


async def responder_stream(bd: Session, actor: Actor, pregunta: str, modo: str = "normal",
                           contexto: dict[str, Any] | None = None,
                           historial: list[dict[str, str]] | None = None) -> AsyncIterator[dict[str, Any]]:
    """Contrato: eventos {tipo: fuentes|token|fin|error} de una respuesta en streaming.

    No suma la consulta a la ejecución del contexto: eso lo hace quien llama (el modo planta)."""
    try:
        prep = await run_in_threadpool(preparar, bd, actor, pregunta, modo, contexto, historial)
    except HTTPException as e:
        yield {"tipo": "error", "mensaje": str(e.detail)}
        return
    except Exception:  # noqa: BLE001
        log.exception("Error preparando la consulta")
        yield {"tipo": "error", "mensaje": "No se ha podido preparar la respuesta. Inténtalo de nuevo."}
        return
    async for evento in emitir(bd, actor, prep):
        yield evento


def responder(bd: Session, actor: Actor, pregunta: str, modo: str = "normal", contexto: dict[str, Any] | None = None,
              historial: list[dict[str, str]] | None = None, contar_ejecucion: bool = False) -> dict[str, Any]:
    """Contrato: igual que responder_stream pero sin streaming. Lanza HTTPException si no se puede."""
    prep = preparar(bd, actor, pregunta, modo, contexto, historial, contar_ejecucion)
    try:
        bruto = llm.chat(prep.mensajes, modelo=prep.modelo, temperatura=prep.temperatura, max_tokens=prep.max_tokens)
    except llm.ErrorModelo as e:
        log.warning("El modelo falló durante la consulta: %s", e)
        raise HTTPException(503, _MODELO_CAIDO) from e
    except (KeyError, IndexError, TypeError, ValueError) as e:
        # El servidor de modelos devolvió algo con otra forma (sin «choices», JSON roto...).
        log.warning("Respuesta del modelo que no se entiende: %r", e)
        raise HTTPException(503, _MODELO_CAIDO) from e
    filtro = FiltroMarca()
    texto, vista = (filtro.alimentar(bruto) + filtro.terminar()).strip(), filtro.vista
    if prep.evidencia and not _redaccion_valida(prep, texto, vista):
        try:
            bruto = llm.chat(_mensajes_directos(prep), modelo=prep.modelo, temperatura=0.1,
                             max_tokens=MAX_TOKENS_REINTENTO)
        except (llm.ErrorModelo, KeyError, IndexError, TypeError, ValueError) as e:
            log.warning("El reintento de la consulta falló: %r", e)
            bruto = ""
        texto, vista = _rehacer(prep, bruto), False
    texto = texto or _texto_vacio(vista)
    fin = finalizar(bd, actor, prep, texto, vista)
    return {"respuesta": texto, "fuentes": prep.fuentes, **fin}


# --------------------------------------------------------------------------- historial


def _version_sustituida_visible(alcance: Alcance | None, d: Documento) -> bool:
    """¿Es la versión sustituida (obsoleta) de una instrucción que la persona podría ver si siguiera vigente?

    Esas filas se conservan para la trazabilidad de las citas: una respuesta antigua sigue mostrando
    de dónde salió el dato, avisando de que hay una versión más reciente. Se aplican las mismas
    reglas de permisos (departamento, nivel, formación, público) que a un documento listo."""
    if d.estado != "obsoleto":
        return False
    if alcance is None:
        return True
    como_vigente = SimpleNamespace(estado="listo", es_publico=d.es_publico, departamento_id=d.departamento_id,
                                   nivel_minimo=d.nivel_minimo, es_formacion=d.es_formacion)
    return puede_ver(alcance, como_vigente)  # type: ignore[arg-type]


def a_dict(bd: Session, c: Consulta, alcance: Alcance | None = None) -> dict[str, Any]:
    """Consulta guardada en JSON. Las URLs de las fuentes se vuelven a firmar (caducan). Las fuentes
    de documentos que la persona ya no puede ver (o que se han borrado) se vacían: como si no
    existieran, igual que en la búsqueda. Las de una versión sustituida de una instrucción se
    muestran con `obsoleta: true` (y sin enlace al fichero)."""
    guardadas = [f for f in (c.fuentes or []) if isinstance(f, dict)]
    ids = {f.get("documento_id") for f in guardadas if f.get("documento_id")}
    docs = {d.id: d for d in bd.scalars(select(Documento).where(Documento.id.in_(ids))).all()} if ids else {}
    fuentes: list[dict[str, Any]] = []
    for f in guardadas:
        d = docs.get(f.get("documento_id"))
        if d is not None and (alcance is None or puede_ver(alcance, d)) and d.estado != "obsoleto":
            fuentes.append({**f, "url": url_fichero(d.ruta_fichero) if d.ruta_fichero else None, "disponible": True})
        elif d is not None and _version_sustituida_visible(alcance, d):
            fuentes.append({**f, "url": None, "disponible": True, "obsoleta": True})
        else:
            fuentes.append({"n": f.get("n"), "documento_id": None, "titulo": "Documento no disponible",
                            "fragmento": "", "url": None, "disponible": False})
    _anadir_tarea(bd, fuentes)  # las consultas guardadas antes de existir el campo
    return {
        "id": c.id,
        "pregunta": c.pregunta,
        "respuesta": c.respuesta,
        "modo": c.modo,
        "fuentes": fuentes,
        "con_respaldo": c.con_respaldo,
        "laguna_id": c.laguna_id,
        "aviso_sin_respaldo": not c.con_respaldo and (c.respuesta or "").strip() != _SIN_TEXTO
        and (c.laguna_id is not None or _merece_laguna(c.pregunta)),
        "citadas": citadas(c.respuesta or "", len(fuentes)) if c.con_respaldo else [],
        "valoracion": c.valoracion,
        "tarea_id": c.tarea_id,
        "paso_id": c.paso_id,
        "ejecucion_id": c.ejecucion_id,
        "duracion_ms": c.duracion_ms,
        "creada": c.creada.isoformat() if c.creada else None,
    }
