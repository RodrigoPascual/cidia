"""Comparación léxica de palabras en castellano: raíces y formas con y sin diptongo.

La usan el copiloto (servicios/consulta.py: evidencia, respaldo y respuesta extractiva) y la búsqueda de
texto del motor propio (conocimiento/pgvector.py), siempre igual para la pregunta y para el texto.

Raíz de una palabra (`raiz()`): sin tildes, sin su terminación («engrasan» y «engrase», «puesto» y
«puestos») y sin diptongo (abajo). Al quitar la terminación quedan al menos 4 letras (salvo en los
infinitivos de abajo), para no confundir «responsable» con «responde» ni «plantilla» con «planta».

Diptongos. Muchos verbos y nombres diptongan la vocal tónica: apretar → aprieta, cerrar → cierra,
colgar → cuelga, soltar → suelta, probar → prueba, mover → mueve. Ni la raíz de arriba ni el
lematizador 'spanish' de PostgreSQL (Snowball) los unen: «aprieta» da «apriet» y «apretar», «apret».
En la grabación del vídeo, «¿Qué llave uso para apretar los tornillos?» no encontraba la frase de IT-023
que dice «aprieta». La normalización es ligera:

* `sin_diptongo()` reduce «ie» → «e» y «ue» → «o» dentro de la palabra (nunca en la primera letra, y
  «ue» tampoco detrás de «q» o «g», donde la «u» no suena: «que», «guerra», «sigue»).
* Un infinitivo de 5 letras en -ar o -er cuya raíz acaba en «e» u «o» entre consonantes (mover,
  poder, sonar, regar) puede quedarse en 3 letras: «mover» → «mov», como «mueve» → «muev» → «mov».
  Los demás infinitivos cortos conservan la palabra entera, como hasta ahora: «lugar» sigue unido a
  «lugares» y «medir» (e → i, que no se trata) no se queda en «med».
* `variante()` da, para la búsqueda de texto, la otra forma de una palabra: la reducida si tiene
  diptongo («aprieta» → «apreta») o la diptongada si no lo tiene («apretar» → «aprietar»), para que el
  lematizador de PostgreSQL encuentre las dos sin reindexar (ver pgvector.py).

Falsos positivos. Unos pocos nombres frecuentes en planta no se reducen (`_SIN_REDUCIR`): no tienen
familia sin diptongo y la forma reducida chocaría con otras palabras («puerta» y «porte», «puesto» y
«poste», «vuelta» y «voltaje», «viento» y «venta», «pies» y «pesar»; al comparar la semilla, «¿Cuándo se
cierra la puerta de la prensa?» encontraba «altura de cierre» por un «…porte» del manual de la prensa).
Se asumen (palabras distintas que quedan con la misma raíz): «suelo» y «soler»; «sueño» y «sonar»;
«piel» y «pelar»; «tienda» y «tender»; «cuello» y «collar»; «nuevo» y «nueve» (ya lo eran). Son raros
en la documentación de planta y una sola palabra no basta: la evidencia del copiloto pide la mitad de las
palabras de la pregunta en la misma frase y el resto en el título o en el apartado. Las «ie» que no son
diptongo («cliente», «serie», «ingeniero») se reducen igual en la pregunta y en el texto, así que siguen
casando entre sí. En la búsqueda de texto, la forma añadida solo trae candidatos (el «OR» de pgvector.py).
No se cubren los cambios e → i (pedir y pide, medir y mide, seguir y sigue) ni u → ue (jugar y juega):
la «i» y la «u» son demasiado frecuentes para cambiarlas sin un diccionario.
"""

from __future__ import annotations

import re
import unicodedata

# Terminaciones que se quitan para comparar palabras, de la más larga a la más corta.
SUFIJOS = tuple(sorted((
    "amientos", "imientos", "amiento", "imiento", "aciones", "iciones", "ciones", "siones", "acion", "icion",
    "cion", "sion", "mente", "ables", "ibles", "able", "ible", "adoras", "adores", "adora", "ador", "ando",
    "iendo", "amos", "emos", "imos", "ados", "adas", "idos", "idas", "ajes", "ado", "ada", "ido", "ida", "aje",
    "ar", "er", "ir", "an", "en", "es", "as", "os", "a", "e", "o", "s",
), key=len, reverse=True))
_INFINITIVOS = ("ar", "er")  # los -ir cortos cambian e → i (medir, pedir), que no se trata
MIN_RAIZ = 4
# «ie» dentro de la palabra; «ue» dentro de la palabra y no detrás de «q» ni de «g».
_RE_DIPTONGO = re.compile(r"(?<=[a-z])ie|(?<=[a-fh-pr-z])ue")
# Raíces con diptongo que no se reducen (ni se generan al diptongar): ver «Falsos positivos» arriba.
_SIN_REDUCIR = frozenset({"puert", "puest", "vuelt", "vient", "pies"})
_CONSONANTE = "bcdfghjklmnpqrstvwxyz"
# Última vocal de una raíz, «e» u «o» entre consonantes («apret», «colg», «mov»): la que diptonga.
_RE_VOCAL_TONICA = re.compile(rf"(?<=[{_CONSONANTE}])([eo])(?=[{_CONSONANTE}]+$)")


def normal(texto: str) -> str:
    """Minúsculas y sin tildes («Aprieta» → «aprieta», «ñ» → «n»)."""
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def sin_diptongo(palabra: str) -> str:
    """«aprieta» → «apreta», «cuelga» → «colga», «prueba» → «proba»; «que» y «sigue» no cambian.
    La palabra tiene que venir en minúsculas y sin tildes (`normal()`)."""
    return _RE_DIPTONGO.sub(lambda m: "e" if m.group(0) == "ie" else "o", palabra)


def _partir(palabra: str) -> tuple[str, str]:
    """(raíz, terminación) de una palabra en minúsculas y sin tildes; terminación vacía si no tiene."""
    for s in SUFIJOS:
        if not palabra.endswith(s):
            continue
        base = palabra[: -len(s)]
        if len(base) >= MIN_RAIZ:
            return base, s
        # «mover» → «mov» (como «mueve» → «mov»), pero «lugar» no se queda en «lug».
        if s in _INFINITIVOS and len(base) == MIN_RAIZ - 1 and _RE_VOCAL_TONICA.search(base):
            return base, s
    return palabra, ""


def raiz(palabra: str) -> str:
    """Raíz para comparar: sin terminación y sin diptongo. «aprieta», «aprieto» y «apretar» → «apret»;
    «pruebas» → «prob»; «mueve» y «mover» → «mov»; «puertas» → «puert» (no se reduce). La palabra viene
    en minúsculas y sin tildes."""
    base = _partir(palabra)[0]
    return base if base in _SIN_REDUCIR else sin_diptongo(base)


def variante(palabra: str) -> str | None:
    """La otra forma de una palabra para la búsqueda de texto de PostgreSQL, o None si no tiene.

    Con diptongo, la reducida: «aprieta» → «apreta» (Snowball: «apret», como «apretar»). Sin él y con
    una terminación que quitar, la diptongada en la última vocal de la raíz: «apretar» → «aprietar»
    («apriet», como «aprieta»), «cerrar» → «cierrar», «mover» → «muever». La forma diptongada no suele
    ser una palabra real: solo sirve para que el lematizador dé la raíz de la otra forma."""
    p = normal(palabra)
    if len(p) < MIN_RAIZ or not p.isascii() or not p.isalpha():
        return None
    base, sufijo = _partir(p)
    if base in _SIN_REDUCIR:
        return None
    reducida = sin_diptongo(p)
    if reducida != p:
        return reducida
    m = _RE_VOCAL_TONICA.search(base) if sufijo else None
    if m is None:
        return None
    diptongada = base[: m.start()] + ("ie" if m.group(1) == "e" else "ue") + base[m.end():]
    return None if diptongada in _SIN_REDUCIR else diptongada + sufijo
