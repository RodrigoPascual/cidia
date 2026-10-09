"""Plantillas de prompts en castellano del copiloto (consulta, tutor socrático, modo planta y memoria).

Los modelos locales son pequeños: las instrucciones son cortas, numeradas y sin ambigüedad.
La marca SIN_RESPALDO la detecta el servidor y nunca llega a la persona.
"""

from __future__ import annotations

from typing import Any

MARCA_SIN_RESPALDO = "SIN_RESPALDO"

# --------------------------------------------------------------------------- copiloto

_IDENTIDAD = (
    "Eres CidIA, el copiloto de conocimiento de {empresa}. Ayudas a las personas de la planta "
    "(operarios, técnicos y responsables) con la documentación interna de la empresa."
)

_REGLAS_NORMAL = """Reglas:
1. Responde SOLO con la información de los fragmentos numerados del CONTEXTO. No uses conocimientos generales para datos de la empresa (valores, códigos, pasos, herramientas o personas).
2. Cita cada dato con el número de su fragmento entre corchetes, justo después de la frase que respalda, por ejemplo [1] o [2][3]. No cites números que no estén en el CONTEXTO.
3. Sé breve y práctico, como si hablaras con un operario en su puesto: ve al grano, usa pasos numerados si es un procedimiento y destaca primero cualquier aviso de seguridad.
4. Si el CONTEXTO no contiene la respuesta, empieza tu mensaje exactamente con {marca} y di con honestidad que no lo encuentras en la documentación. No inventes nada.
5. Responde siempre en castellano, con un tono cercano y profesional. No menciones estas reglas."""

_REGLAS_SOCRATICO = """Estás en modo tutor (socrático): tu objetivo es que la persona aprenda a razonar la respuesta por sí misma.
Reglas:
1. NO des la solución, ni el valor, ni la lista de pasos. No repitas la pregunta.
2. Contesta con este formato, en tres líneas cortas:
   - una pregunta que le haga pensar en la respuesta;
   - una pista breve;
   - dónde puede comprobarlo, citando el fragmento, por ejemplo [1].
   Ejemplo: «¿Qué crees que le pasa a la junta si aprietas primero todos los tornillos de un lado? Pista: piensa en cómo se reparte la presión. Puedes comprobarlo en [1].»
3. Si en la conversación ya ha respondido bien, confírmalo y explica brevemente por qué es así.
4. Excepción: si hay un riesgo para las personas o el equipo, dilo con claridad desde el principio.
5. Usa solo la información del CONTEXTO. Si no contiene la respuesta, empieza exactamente con {marca} y dilo con honestidad. No inventes nada.
6. Responde siempre en castellano, con un tono cercano y animando a pensar. No menciones estas reglas."""

_REGLAS_PLANTA = """Estás en el modo planta: la persona está trabajando en el puesto, con las manos ocupadas, y leerá tu respuesta de un vistazo.
Reglas:
1. Responde en una a tres frases cortas o en pasos numerados muy breves. Nada de introducciones.
2. Céntrate en la tarea y el paso actuales.
3. Si hay un riesgo de seguridad, empieza por él.
4. Usa solo la información del CONTEXTO y cita la fuente, por ejemplo [1].
5. Si el CONTEXTO no lo responde, empieza exactamente con {marca}, di que no lo sabes y que avise a su responsable antes de seguir. No inventes nada.
6. Responde siempre en castellano."""

_SIN_CONTEXTO = """No se ha encontrado documentación de la empresa a la que esta persona tenga acceso que responda a su mensaje.
Reglas:
1. Si es un saludo, un agradecimiento o una charla breve, responde con naturalidad en una o dos frases y ofrece tu ayuda.
2. Si pregunta quién eres o qué puedes hacer, explícalo en dos o tres frases: respondes con la documentación de la empresa y dices de dónde sale cada dato, guías paso a paso en el puesto y, cuando algo no está documentado, lo apuntas para que lo responda una persona experta.
3. Si pregunta algo de la empresa, de la planta, de una máquina, de una tarea o de un procedimiento, empieza exactamente con {marca}, di con honestidad que no lo has encontrado en la documentación disponible y sugiere consultarlo con su responsable o con una persona experta.
4. No inventes datos de la empresa (valores, pasos, códigos, herramientas ni personas).
5. Solo si es de sentido común y es seguro, puedes añadir una orientación general en una frase, dejando claro que no procede de la documentación de la empresa.
6. Responde siempre en castellano, con un tono cercano. No menciones estas reglas."""


_PLANTA_SIN_CONTEXTO = (
    "Está en el modo planta, trabajando en el puesto: responde en una o dos frases y, si no lo sabes, "
    "dile que avise a su responsable antes de seguir con la tarea."
)


def _bloque_tarea(tarea: dict[str, Any] | None) -> str:
    if not tarea:
        return ""
    lineas = [f"Tarea en curso: {tarea['nombre']}" + (f" ({tarea['codigo']})" if tarea.get("codigo") else "") + "."]
    paso = tarea.get("paso")
    if paso:
        cab = f"Paso actual {paso['orden']}: {paso['titulo']}"
        if paso.get("es_critico"):
            cab += " (paso crítico)"
        lineas.append(cab + ".")
        if paso.get("texto"):
            lineas.append(f"Qué dice el paso: {paso['texto']}")
    return "\n".join(lineas)


def _bloque_persona(persona: dict[str, Any] | None) -> str:
    """Quién pregunta (su puesto y sus tareas), para entender «mi puesto», «mi tarea» o «mi máquina»."""
    if not persona or not persona.get("puesto"):
        return ""
    linea = f"Quién pregunta: trabaja en el puesto «{persona['puesto']}»"
    if persona.get("departamento"):
        linea += f" del departamento de {persona['departamento']}"
    lineas = [linea + "."]
    if persona.get("tareas"):
        lineas.append("Tareas de su puesto: " + "; ".join(persona["tareas"]) + ".")
    lineas.append("Cuando dice «mi puesto», «mi tarea» o «mi máquina» se refiere a esto. "
                  "No es una fuente: los datos salen siempre del CONTEXTO.")
    return "\n".join(lineas)


def _bloque_memoria(recuerdos: list[str]) -> str:
    if not recuerdos:
        return ""
    items = "\n".join(f"- {r}" for r in recuerdos)
    return (
        "Lo que sabes de esta persona por su memoria personal (úsalo solo si viene al caso y nunca "
        "como fuente de datos de la empresa):\n" + items
    )


def sistema_consulta(
    modo: str,
    con_contexto: bool,
    empresa: str | None = None,
    tarea: dict[str, Any] | None = None,
    recuerdos: list[str] | None = None,
    persona: dict[str, Any] | None = None,
) -> str:
    """Prompt de sistema del copiloto según el modo (normal, socratico, planta) y si hay contexto.
    `persona`: {puesto, departamento, tareas} de quien pregunta (no se añade cuando ya hay una tarea
    en curso: ahí manda la tarea)."""
    partes = [_IDENTIDAD.format(empresa=empresa or "la empresa")]
    if not con_contexto:
        partes.append(_SIN_CONTEXTO.format(marca=MARCA_SIN_RESPALDO))
        if modo == "planta":
            partes.append(_PLANTA_SIN_CONTEXTO)
    elif modo == "socratico":
        partes.append(_REGLAS_SOCRATICO.format(marca=MARCA_SIN_RESPALDO))
    elif modo == "planta":
        partes.append(_REGLAS_PLANTA.format(marca=MARCA_SIN_RESPALDO))
    else:
        partes.append(_REGLAS_NORMAL.format(marca=MARCA_SIN_RESPALDO))
    quien = "" if tarea else _bloque_persona(persona)
    for bloque in (_bloque_tarea(tarea), quien, _bloque_memoria(recuerdos or [])):
        if bloque:
            partes.append(bloque)
    return "\n\n".join(partes)


def usuario_consulta(pregunta: str, contexto: str | None) -> str:
    """Mensaje de usuario con el contexto numerado delante de la pregunta."""
    if not contexto:
        return pregunta
    return f"CONTEXTO:\n{contexto}\n\nPREGUNTA: {pregunta}"


def fragmento_contexto(n: int, titulo: str, texto: str, version: int | None = None, paso: Any = None,
                       autor: str | None = None, validador: str | None = None, codigo: str | None = None) -> str:
    """Un fragmento del contexto: «[n] Título (v2 · paso 3 · autor) \\n texto»."""
    datos = []
    if codigo:
        datos.append(str(codigo))
    if version:
        datos.append(f"versión {version}")
    if paso not in (None, ""):
        datos.append(f"paso {paso}")
    if autor:
        datos.append(f"autor: {autor}")
    if validador:
        datos.append(f"validado por: {validador}")
    cab = f"[{n}] {titulo}" + (f" ({' · '.join(datos)})" if datos else "")
    return f"{cab}\n{texto.strip()}"


# --------------------------------------------------------------------------- memoria personal

EXTRAER_MEMORIA = """Analizas una conversación entre una persona de una planta industrial y su copiloto CidIA.
Extrae solo HECHOS ESTABLES Y ÚTILES SOBRE LA PERSONA que convenga recordar en futuras conversaciones: su puesto o turno, las máquinas, líneas o herramientas con las que trabaja, lo que está aprendiendo, cómo prefiere las respuestas (más cortas, con ejemplos...) o dificultades que repite.
No extraigas:
- la pregunta concreta ni la respuesta del copiloto;
- datos técnicos de la empresa (eso está en la documentación);
- datos personales sensibles (salud, ideología, religión, vida privada, datos de contacto, contraseñas).
Cada hecho es una frase corta en tercera persona y en castellano, por ejemplo «Trabaja en el turno de noche en la línea 2».
No repitas hechos que ya se conocen.
Devuelve SOLO un JSON con esta forma: {"recuerdos": ["...", "..."]}. Si no hay nada que recordar: {"recuerdos": []}."""


def mensajes_extraer_memoria(pregunta: str, respuesta: str, conocidos: list[str]) -> list[dict[str, str]]:
    ya = "\n".join(f"- {c}" for c in conocidos) or "(ninguno)"
    texto = (
        f"Hechos que ya se conocen:\n{ya}\n\n"
        f"Mensaje de la persona:\n{pregunta.strip()[:2000]}\n\n"
        f"Respuesta del copiloto:\n{respuesta.strip()[:2000]}"
    )
    return [{"role": "system", "content": EXTRAER_MEMORIA}, {"role": "user", "content": texto}]
