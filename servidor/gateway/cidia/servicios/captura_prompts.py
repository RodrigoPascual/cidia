"""Prompts del módulo de captura, en castellano.

Pensados también para modelos diminutos: reglas cortas, formato JSON explícito y nada de
razonamientos largos. El código que los usa valida siempre la respuesta y tiene un plan B
sin modelo (borrador por segmentos, ficha con la transcripción, pregunta del guion).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from cidia.ia import llm


class Tema(NamedTuple):
    clave: str
    titulo: str
    objetivo: str  # qué se quiere averiguar (para el modelo)
    pregunta: str  # pregunta de reserva si el modelo no propone una buena


# Guion de la entrevista guiada: una pregunta cada vez, en este orden.
GUION: list[Tema] = [
    Tema("objetivo", "Objetivo", "para qué sirve la tarea, cuándo se hace y qué resultado se busca",
         "¿Para qué sirve esta tarea, cuándo se hace y qué resultado se busca?"),
    Tema("preparacion", "Preparación", "material, herramientas, EPIs y comprobaciones antes de empezar",
         "Antes de empezar, ¿qué hay que preparar: material, herramientas, EPIs o comprobaciones?"),
    Tema("pasos", "Pasos", "los pasos principales, en orden",
         "Cuéntame los pasos principales en orden, como se lo explicarías a alguien nuevo. ¿Por dónde empiezas?"),
    Tema("puntos_criticos", "Puntos críticos", "qué pasos son críticos para la calidad o la seguridad y qué pasa si se hacen mal",
         "¿Qué pasos son críticos para la calidad o la seguridad? ¿Qué pasa si se hacen mal?"),
    Tema("errores", "Errores típicos", "errores habituales de quien empieza y cómo se evitan",
         "¿Qué errores comete más a menudo quien empieza y cómo se evitan?"),
    Tema("trucos", "Trucos", "trucos del oficio que no están escritos en ningún sitio",
         "¿Qué trucos del oficio has aprendido que no están escritos en ningún sitio?"),
    Tema("calidad", "Criterios de calidad", "cómo se comprueba al final que la tarea ha quedado bien",
         "Al terminar, ¿cómo sabes que la tarea ha quedado bien? ¿Qué compruebas?"),
]
TEMAS = {t.clave: t for t in GUION}

FIN_ENTREVISTA = (
    "Gracias, ya hemos repasado todo el guion. Si quieres añadir algo más, escríbelo; si no, pulsa "
    "«Terminar y generar ficha» y prepararé un borrador para que lo revises."
)
ANOTADO = "Anotado. Si no quieres añadir nada más, pulsa «Terminar y generar ficha»."


def primera_pregunta(nombre: str) -> str:
    return f"Vamos a documentar «{nombre}». Para empezar, ¿para qué sirve esta tarea, cuándo se hace y qué resultado se busca?"


def _recortar(texto: str, maximo: int) -> str:
    return texto if len(texto) <= maximo else texto[:maximo].rstrip() + "\n[…]"


# --------------------------------------------------------------------------- vídeo → instrucción

SISTEMA_PASOS = """Eres un técnico de métodos de una planta industrial. Conviertes la explicación de un experto, grabada en vídeo mientras trabaja, en una instrucción de trabajo para una persona nueva.
Reglas:
- Castellano, frases cortas y en imperativo («Coloca la brida…»).
- Usa solo lo que dice la transcripción: no inventes datos, medidas ni herramientas.
- Cada paso es una acción concreta, en el mismo orden que en el vídeo.
- t_inicio y t_fin son segundos del vídeo: apóyate en las marcas de la transcripción y en los cambios de plano.
- es_critico: true si un fallo en ese paso estropea el resultado. es_seguridad: true si hay riesgo para las personas.
- criterio_aceptacion: cómo se comprueba que el paso está bien hecho; "" si no se dice.
- riesgos, epis y herramientas: listas de pocas palabras por elemento; [] si no se mencionan.
Responde SOLO con un objeto JSON, sin texto antes ni después."""

FORMATO_PASOS = (
    '{"titulo": "...", "resumen": "...", "riesgos": ["..."], "epis": ["..."], "herramientas": ["..."], '
    '"pasos": [{"titulo": "...", "texto": "...", "es_critico": false, "es_seguridad": false, '
    '"criterio_aceptacion": "...", "t_inicio": 0.0, "t_fin": 12.5}]}'
)


def transcripcion_compacta(segmentos: list[dict[str, Any]], max_caracteres: int = 9000) -> str:
    """Transcripción con marcas de tiempo que cabe en `max_caracteres`.

    Si es demasiado larga no se corta por el final (el modelo solo vería el principio del vídeo y
    los pasos acabarían a mitad): se agrupan frases seguidas en bloques y se acorta cada bloque,
    así el modelo ve el vídeo entero, de principio a fin."""
    utiles = [s for s in segmentos if str(s.get("texto") or "").strip()]
    lineas = [f"[{float(s['inicio']):.1f}-{float(s['fin']):.1f}] {str(s['texto']).strip()}" for s in utiles]
    if sum(len(x) + 1 for x in lineas) <= max_caracteres:
        return "\n".join(lineas)
    bloques = max(1, min(len(utiles), max_caracteres // 220))
    por_bloque = -(-len(utiles) // bloques)  # división hacia arriba
    presupuesto = max(40, max_caracteres // bloques - 24)  # sitio para la marca de tiempo
    salida = []
    for i in range(0, len(utiles), por_bloque):
        grupo = utiles[i:i + por_bloque]
        texto = " ".join(str(s["texto"]).strip() for s in grupo)
        if len(texto) > presupuesto:
            texto = texto[:presupuesto].rsplit(" ", 1)[0] + "…"
        salida.append(f"[{float(grupo[0]['inicio']):.1f}-{float(grupo[-1]['fin']):.1f}] {texto}")
    return "\n".join(salida)


def mensajes_pasos(tarea: str | None, duracion: float, segmentos: list[dict[str, Any]], texto: str,
                   escenas: list[dict[str, Any]], max_caracteres: int = 9000) -> list[dict[str, Any]]:
    transcripcion = transcripcion_compacta(segmentos, max_caracteres) or _recortar(texto or "(sin voz)", max_caracteres)
    if len(escenas) > 80:  # muchos cambios de plano: unos repartidos por todo el vídeo, no solo los primeros
        salto = len(escenas) / 80
        escenas = [escenas[int(i * salto)] for i in range(80)]
    cortes = ", ".join(f"{e['t']:.1f}" for e in escenas) or "ninguno"
    usuario = (
        f"Tarea: {tarea or 'sin nombre'}\n"
        f"Duración del vídeo: {duracion:.1f} s\n"
        f"Cambios de plano (segundos): {cortes}\n\n"
        f"Transcripción con marcas de tiempo en segundos:\n{transcripcion}\n\n"
        f"Devuelve el JSON con esta forma:\n{FORMATO_PASOS}"
    )
    return [{"role": "system", "content": SISTEMA_PASOS}, {"role": "user", "content": usuario}]


def mensajes_vision(titulo: str, texto: str, ruta_imagen: str | Path) -> list[dict[str, Any]]:
    """Pide al modelo con visión que mejore el texto de un paso con lo que se ve en su fotograma."""
    peticion = (
        f"Esta imagen es del paso «{titulo}» de una instrucción de trabajo de una planta industrial.\n"
        f"Texto actual del paso: {texto or '(vacío)'}\n\n"
        "Reescribe el texto del paso en castellano, en 1 a 3 frases en imperativo, añadiendo solo detalles "
        "que se vean con claridad en la imagen (piezas, herramientas, posición, indicadores). No inventes nada. "
        "Si la imagen no aporta nada, devuelve el texto actual tal cual. Responde solo con el texto del paso."
    )
    return [{"role": "user", "content": [{"type": "text", "text": peticion}, llm.imagen_a_parte(ruta_imagen)]}]


# --------------------------------------------------------------------------- nota de voz o entrevista → ficha

SISTEMA_FICHA = """Eres un técnico que convierte lo que cuenta una persona experta de planta en una ficha de conocimiento clara y útil para sus compañeros.
Reglas:
- Castellano claro. No inventes nada que no se haya dicho.
- contenido: markdown con secciones breves (## Sección) y listas cuando ayuden. Secciones posibles: Para qué sirve, Preparación, Cómo se hace, Puntos críticos, Errores típicos, Trucos, Cómo comprobar que está bien. Omite las que no tengan información.
- etiquetas: de 2 a 6 palabras clave en minúsculas (máquinas, piezas, defectos, materiales).
Responde SOLO con un objeto JSON: {"titulo": "...", "contenido": "...", "etiquetas": ["...", "..."]}"""


def mensajes_ficha(origen: str, tarea: str | None, texto: str, max_caracteres: int = 12000) -> list[dict[str, Any]]:
    usuario = (
        f"Origen: {origen}\n"
        f"Tarea o tema: {tarea or 'sin indicar'}\n\n"
        f"Lo que ha contado la persona experta:\n{_recortar(texto, max_caracteres)}\n\n"
        "Devuelve el JSON de la ficha."
    )
    return [{"role": "system", "content": SISTEMA_FICHA}, {"role": "user", "content": usuario}]


# --------------------------------------------------------------------------- entrevista guiada

SISTEMA_ENTREVISTA = """Eres CidIA, un copiloto que entrevista a una persona experta de una planta industrial para guardar su conocimiento sobre una tarea.
- Haces UNA sola pregunta cada vez: breve (máximo 30 palabras), concreta, en castellano llano y tuteando.
- Te adaptas a lo que ya ha contado: no preguntes lo que ya ha explicado y aprovecha sus propias palabras.
- No opinas ni explicas nada: solo preguntas.
Responde SOLO con un objeto JSON: {"repreguntar": true o false, "pregunta": "¿...?"}"""


def turnos_texto(conversacion: list[dict[str, Any]], max_turnos: int = 8, max_caracteres: int = 600) -> str:
    salida = []
    for m in conversacion[-max_turnos:]:
        if m.get("rol") == "copiloto":
            salida.append(f"Copiloto: {m.get('texto', '')[:max_caracteres]}")
        elif m.get("saltada"):
            salida.append("Experto: (prefiere no responder a esta pregunta)")
        else:
            salida.append(f"Experto: {m.get('texto', '')[:max_caracteres]}")
    return "\n".join(salida)


def mensajes_entrevista(nombre: str, actual: Tema, siguiente: Tema | None,
                        conversacion: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sig = f"«{siguiente.titulo}»: {siguiente.objetivo}" if siguiente else "ninguno (es el último tema)"
    usuario = (
        f"Tarea: {nombre}\n"
        f"Tema actual: «{actual.titulo}»: {actual.objetivo}\n"
        f"Siguiente tema del guion: {sig}\n\n"
        f"Últimos turnos de la entrevista:\n{turnos_texto(conversacion)}\n\n"
        "Si la última respuesta es vaga o le falta algo importante del tema actual, pon repreguntar a true y "
        "haz una repregunta sobre ese tema. Si no, pon repreguntar a false y haz la pregunta del siguiente tema, "
        "adaptada a lo que ya ha contado."
    )
    return [{"role": "system", "content": SISTEMA_ENTREVISTA}, {"role": "user", "content": usuario}]


def conversacion_a_texto(conversacion: list[dict[str, Any]]) -> str:
    """Entrevista ordenada por temas, como texto para el modelo (y para el plan B)."""
    bloques: list[str] = []
    pregunta = ""
    for m in conversacion:
        if m.get("rol") == "copiloto":
            pregunta = m.get("texto", "")
            continue
        if m.get("saltada") or not (m.get("texto") or "").strip():
            continue
        tema = TEMAS.get(m.get("tema", ""))
        cabecera = tema.titulo if tema else "Comentarios"
        bloques.append(f"[{cabecera}]\nPregunta: {pregunta}\nRespuesta: {m['texto'].strip()}")
    return "\n\n".join(bloques)


# --------------------------------------------------------------------------- entrevista → instrucción

SISTEMA_INSTRUCCION = """Eres un técnico de métodos de una planta industrial. Conviertes una entrevista con una persona experta en una instrucción de trabajo para alguien nuevo.
Reglas:
- Castellano, frases cortas y en imperativo.
- Usa solo lo que se ha dicho en la entrevista: no inventes datos, medidas ni herramientas.
- Cada paso es una acción concreta, en orden.
- es_critico: true si un fallo en ese paso estropea el resultado. es_seguridad: true si hay riesgo para las personas.
- criterio_aceptacion: cómo se comprueba que el paso está bien hecho; "" si no se dice.
- riesgos, epis y herramientas: listas de pocas palabras por elemento; [] si no se mencionan.
Responde SOLO con un objeto JSON, sin texto antes ni después."""

FORMATO_INSTRUCCION = (
    '{"titulo": "...", "resumen": "...", "riesgos": ["..."], "epis": ["..."], "herramientas": ["..."], '
    '"pasos": [{"titulo": "...", "texto": "...", "es_critico": false, "es_seguridad": false, '
    '"criterio_aceptacion": "..."}]}'
)


def mensajes_instruccion(tarea: str | None, texto: str, max_caracteres: int = 12000) -> list[dict[str, Any]]:
    usuario = (
        f"Tarea: {tarea or 'sin nombre'}\n\n"
        f"Entrevista:\n{_recortar(texto, max_caracteres)}\n\n"
        f"Devuelve el JSON con esta forma:\n{FORMATO_INSTRUCCION}"
    )
    return [{"role": "system", "content": SISTEMA_INSTRUCCION}, {"role": "user", "content": usuario}]
