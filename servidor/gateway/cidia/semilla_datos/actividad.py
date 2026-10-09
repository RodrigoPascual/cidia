"""Actividad sintética de las últimas seis semanas: aportaciones, lagunas, consultas, ejecuciones en
el modo planta, cuestionarios, observaciones, micro-lecciones vistas y niveles ILUO.

Las fechas se expresan en días hacia atrás desde el momento de sembrar (negativo = futuro).
Todo es coherente con las reglas ILUO de docs/arquitectura.md §7: quien tiene L ha aprobado el
cuestionario y tiene al menos 3 ejecuciones; quien tiene U además tiene una observación aprobada
y su última ejecución no tuvo consultas en pasos críticos; quien tiene O está validado como formador.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------- aportaciones

APORTACIONES: list[dict[str, Any]] = [
    {
        "clave": "prensa3", "autor": "pedro", "departamento": "prod", "tarea": "IT-031", "dias": 22,
        "estado": "validada", "validador": "javier", "dias_validada": 20, "nivel_minimo": 1,
        "titulo": "Atasco en la prensa 3 al cambiar de molde: limpiar el sensor S4",
        "transcripcion": "Esto me ha pasado ya tres veces. Después de cambiar el molde en la prensa 3, la prensa se "
                         "queda parada con la alarma de falta de pieza aunque la pieza está bien puesta, y si fuerzas "
                         "el ciclo se atasca. Es el sensor S4, el de presencia de pieza: con el cambio se le queda "
                         "pegada viruta y aceite del desmoldeo. Lo que hago es soplarlo con la pistola de aire, "
                         "flojito, sin disolvente, y luego reinicio el ciclo en modo manual, un golpe, y ya va. Lo "
                         "suyo sería limpiarlo siempre al terminar el cambio.",
        "problema": "La prensa 3 se atasca o se queda parada con la alarma A12 (falta pieza S4) justo después de "
                    "cambiar de molde, aunque la pieza está bien colocada.",
        "causa": "El sensor S4 de presencia de pieza queda sucio tras el cambio (virutas y aceite de desmoldeo) y no "
                 "detecta la pieza.",
        "solucion": "Con la prensa en modo manual, limpiar el sensor S4 con aire a baja presión (máximo 2 bar, sin "
                    "disolventes) y reiniciar el ciclo en modo manual con un golpe antes de volver a automático. "
                    "Recomendación: soplar el S4 al terminar cada cambio de molde.",
        "etiquetas": ["prensa 3", "sensor S4", "cambio de molde", "alarma A12"],
    },
    {
        "clave": "bobina", "autor": "marta", "departamento": "prod", "tarea": "IT-025", "dias": 1,
        "estado": "pendiente", "nivel_minimo": 1,
        "titulo": "Cambio de bobina de film sin parar la línea",
        "texto_original": "En la enfardadora de la E6 se puede cambiar la bobina de film sin parar la línea. Si "
                          "dejas la bobina nueva preparada en el carro de reserva y empalmas el film con el conjunto "
                          "en la mesa giratoria, no hace falta parar: el empalme aguanta una vuelta y no se nota. "
                          "Así no se acumulan colectores en la E5.",
        "problema": "Cada cambio de bobina de film en la enfardadora de la E6 para la línea unos 4 minutos y se "
                    "acumulan colectores en la E5.",
        "causa": "La bobina se cambia con la mesa parada y sin bobina de reserva preparada.",
        "solucion": "Dejar la bobina nueva preparada en el carro de reserva y empalmar el film con el conjunto girando "
                    "en la mesa, sin parar la línea.",
        "etiquetas": ["línea 2", "E6", "enfardadora", "bobina de film"],
    },
    {
        "clave": "juntas", "autor": "lucia", "departamento": "prod", "tarea": "IT-023", "horas": 2,
        "estado": "pendiente", "nivel_minimo": 1,
        "titulo": "Las juntas JT-80 del lote nuevo vienen pegadas de dos en dos",
        "transcripcion": "Una cosa de la brida B. Las juntas de las cajas nuevas vienen pegadas de dos en dos y casi "
                         "monto dos juntas a la vez. Yo ahora antes de ponerla la doblo un poco con los dedos para ver "
                         "que es una sola. Habría que decírselo a Calidad por si es del lote.",
        "problema": "En las cajas del último lote, las juntas JT-80 vienen pegadas de dos en dos y es fácil montar dos "
                    "juntas a la vez en la brida B.",
        "causa": "Posible lote sin separador entre juntas (pendiente de confirmar con Calidad).",
        "solucion": "Antes de colocar la junta, flexionarla con los dedos para comprobar que es una sola y avisar a "
                    "Calidad del número de lote.",
        "etiquetas": ["brida B", "junta JT-80", "línea 2", "lote"],
    },
]

# --------------------------------------------------------------------------- lagunas

RESPUESTA_SIN_RESPALDO = ("No he encontrado esta información en la documentación a la que tienes acceso, así que "
                          "prefiero no inventarla. He registrado tu pregunta para que la responsable o el responsable "
                          "de tu departamento la resuelva.")

LAGUNAS: list[dict[str, Any]] = [
    {"pregunta": "¿Qué presión lleva el cilindro de la prensa 2?", "departamento": "prod", "tarea": None,
     "estado": "abierta",
     "consultas": [("pedro", 6, "¿Qué presión lleva el cilindro de la prensa 2?"),
                   ("marta", 3, "¿A cuántos bar trabaja el cilindro de la prensa 2?"),
                   ("lucia", 1, "Presión del cilindro de la prensa 2")]},
    {"pregunta": "¿Cómo se purga el circuito de refrigeración?", "departamento": "prod", "tarea": None,
     "estado": "abierta",
     "consultas": [("carmen", 5, "¿Cómo se purga el circuito de refrigeración?"),
                   ("pedro", 2, "¿Cómo se purga el circuito de refrigeración del molde?")]},
    {"pregunta": "¿Quién aprueba la compra de un utillaje de más de 3.000 €?", "departamento": "ot", "tarea": None,
     "estado": "abierta",
     "consultas": [("luis", 12, "¿Quién aprueba la compra de un utillaje de más de 3.000 €?")]},
    {"pregunta": "¿Por qué se atasca la prensa 3 después de cambiar el molde?", "departamento": "prod",
     "tarea": "IT-031", "estado": "resuelta", "aportacion": "prensa3",
     "consultas": [("pedro", 24, "¿Por qué se atasca la prensa 3 después de cambiar el molde?"),
                   ("carmen", 23, "La prensa 3 se para con la alarma A12 después del cambio de molde, ¿qué hago?")]},
]

# --------------------------------------------------------------------------- consultas con respaldo (fuera de planta)
# (usuario, días, pregunta, respuesta, claves de documentos citados, valoración)
# Las claves «it:IT-0xx» son los documentos de las instrucciones; «faq:prensa3», el de la aportación.

CONSULTAS: list[tuple[str, int, str, str, list[str], int | None]] = [
    ("luis", 29, "¿Qué es el sistema de referencias 3-2-1?",
     "Es la forma de fijar la pieza en el utillaje con seis apoyos: tres en el plano principal, dos en un lateral y "
     "uno en el tercer plano. Los amarres empujan la pieza contra esos apoyos [1].", ["manual_ot"], 1),
    ("luis", 25, "¿Qué plantilla de CAD uso para un utillaje?",
     "La plantilla UT-PLANTILLA-03, que trae el cajetín, las capas y la lista de materiales [1].", ["manual_ot"], 1),
    ("marta", 19, "¿Cómo se codifican los utillajes?",
     "Con el formato UT-AAAA-NNN, por ejemplo UT-2025-014 para el utillaje de soldadura de los soportes SL-12 [1].",
     ["manual_ot"], 1),
    ("marta", 16, "¿Qué tolerancias se aplican si el plano no dice nada?",
     "Las tolerancias generales ISO 2768-mK [1].", ["manual_ot"], None),
    ("marta", 8, "La prensa 3 se ha atascado después del cambio de molde, ¿qué hago?",
     "Con la prensa en modo manual, limpia el sensor S4 con aire a baja presión (máximo 2 bar, sin disolventes) y "
     "reinicia el ciclo en modo manual con un golpe antes de volver a automático [1]. Es una solución aportada por "
     "Pedro Ruiz y validada por Javier Martín.", ["faq:prensa3"], 1),
    ("ana", 16, "¿Qué plazo de entrega tiene Utillajes Páramo?",
     "Entre 5 y 6 semanas. En 2025 tuvo un retraso en el UT-2025-009, por eso su valoración es B [1].", ["costes"], 1),
    ("david", 26, "¿Cada cuánto se verifican las llaves dinamométricas?",
     "Cada 6 meses en el banco de par, con una tolerancia de ± 4 % [1].", ["control"], 1),
    ("elena", 20, "¿Qué reacción hay si la estanqueidad no cumple?",
     "Etiqueta roja y contenedor de no conforme; el control de estanqueidad es al 100 % [1].", ["control"], None),
    ("nuria", 14, "¿Cada cuántas horas se engrasan las guías de la prensa 3?",
     "Cada 40 horas de trabajo, con grasa EP-2 en los 8 engrasadores [1].", ["preventivo"], 1),
    ("oscar", 11, "¿Qué hay que revisar cada mes en la prensa 3?",
     "La calibración del sensor S4 con la pieza patrón PT-S4 y la plataforma de acceso, además de los filtros de "
     "aire de los cuadros [1].", ["preventivo"], None),
    ("pedro", 4, "¿Qué presión tienen los amarres de la prensa 3?",
     "180 bar. Si algún amarre no llega a presión salta la alarma A17 y no se debe golpear [1].", ["it:IT-031"], 1),
    ("irene", 7, "¿Cuántos golpes en vacío se dan tras un cambio de molde?",
     "Tres golpes en vacío en modo manual y después una pieza en modo lento [1].", ["it:IT-031"], 1),
    ("lucia", 9, "¿Dónde está el punto de reunión en una emergencia?",
     "En el aparcamiento norte (P-1), junto a la portería [1].", ["prl"], 1),
]

# --------------------------------------------------------------------------- preguntas en el modo planta
# código de instrucción -> orden del paso (en la versión vigente) -> [(pregunta, respuesta)]

PREGUNTAS_PASO: dict[str, dict[int, list[tuple[str, str]]]] = {
    "IT-023": {
        1: [("¿Dónde veo la referencia de la brida?", "En la etiqueta del carro: BR-B-080, igual que la orden [1]."),
            ("¿Cuántos tornillos lleva la brida B?", "Cuatro tornillos M10 × 40 de calidad 8.8 con arandela [1].")],
        2: [("¿Puedo reutilizar la junta si está bien?", "No. La junta JT-80 no se reutiliza nunca [1]."),
            ("¿Con qué limpio el asiento?", "Con un paño sin pelusa humedecido en desengrasante [1].")],
        3: [("¿Qué llave uso?", "La llave dinamométrica de media pulgada (1/2\") con vaso de 17 mm [1]."),
            ("¿A cuántos N·m aprieto?", "Primera pasada a 12 N·m y segunda a 25 N·m [1]."),
            ("¿En qué orden aprieto los tornillos?", "En cruz: 1 arriba, 2 abajo, 3 derecha y 4 izquierda [1]."),
            ("¿Puedo usar el atornillador de impacto?", "No. En esta unión nunca se usa [1].")],
        4: [("¿De qué color es la marca de testigo?", "Amarilla, con el rotulador de pintura [1].")],
        5: [("¿A qué presión se hace la prueba?", "A 3 bar durante 60 s; caída máxima de 0,05 bar [1]."),
            ("¿Cuándo abro la tapa del banco?", "Cuando el banco haya despresurizado [1].")],
        6: [("¿Cuánto puede asomar la junta?", "Como máximo 1 mm por cualquier lado [1].")],
        7: [("¿Qué hago si el banco da NOK?", "Etiqueta roja y al contenedor rojo de la estación E5 [1].")],
    },
    "IT-031": {
        1: [("¿Dónde veo la receta del molde?", "Grabada en la placa del molde, por ejemplo M-318 [1].")],
        2: [("¿Cuántos amarres tiene la prensa 3?", "Ocho: cuatro en el carro y cuatro en la mesa [1].")],
        3: [("¿Qué llave descarga el acumulador?", "La llave de bola KB-3 [1]."),
            ("¿Cómo compruebo la energía cero?", "Pulsa marcha y mira que la central marca 0 bar [1].")],
        4: [("¿Desde dónde empujo el molde?", "Siempre desde el lateral, nunca por delante [1].")],
        5: [("¿Con qué limpio las ranuras de la mesa?", "Con aire, retirando recortes, virutas y aceite [1].")],
        6: [("¿Hasta dónde meto el molde?", "Hasta que toque los dos tacos de centrado de la mesa [1].")],
        7: [("¿Qué presión deben tener los amarres?", "180 bar, con los 8 indicadores en verde [1]."),
            ("¿Qué significa la alarma A17?", "Que un amarre no llega a presión: no golpees y avisa [1].")],
        8: [("¿Cuántos golpes en vacío hago?", "Tres golpes en vacío en modo manual [1].")],
    },
    "IT-051": {
        1: [("¿Dónde encuentro el plano liberado?", "En el PDM, junto con el modelo 3D de la pieza [1].")],
        2: [("¿Cuántos apoyos pongo en el plano principal?", "Tres; dos en un lateral y uno en el extremo [1]."),
            ("¿Qué holgura dejo en los topes?", "Entre 0,2 y 0,5 mm [1].")],
        3: [("¿Cuándo uso amarres neumáticos?", "Cuando la cadencia supera 30 piezas por hora [1].")],
        4: [("¿Qué altura de trabajo tiene que tener el utillaje?", "Entre 900 y 1.100 mm [1].")],
        5: [("¿Qué ángulo debe tener la antorcha?", "45° ± 15°, con 15 mm libres alrededor de la boquilla [1]."),
            ("¿Qué hago si un cordón colisiona?", "Mueve el amarre o el apoyo y repite la comprobación [1].")],
        6: [("¿Cuándo es la revisión de diseño?", "Los jueves, con la lista del PR-OT-02 [1].")],
    },
    "IT-061": {
        1: [("¿Cada cuánto se calibra el calibre?", "Cada 12 meses, con verificación interna mensual [1].")],
        2: [("¿Con qué bloque patrón compruebo el calibre?", "Con el de 25 mm: 25,00 ± 0,02 [1].")],
        3: [("¿A qué temperatura mido?", "A 20 ± 2 °C [1].")],
        4: [("¿Cuántas veces mido cada cota?", "Tres veces, y se anota la media [1]."),
            ("¿Cómo mido el diámetro interior?", "Con las palas de interiores, perpendicular y sin forzar [1].")],
        5: [("¿Dónde registro las medidas?", "En la pantalla de control estadístico o en la hoja de control [1].")],
        6: [("¿Dónde dejo las piezas no conformes?", "En la jaula roja, con etiqueta roja [1].")],
    },
    "IT-071": {
        1: [("¿Dónde está el seccionador de la prensa 3?", "Es el Q0 del armario A1 [1].")],
        2: [("¿Puedo limpiar el sensor con disolvente?", "No, solo aire a baja presión y paño seco [1].")],
        3: [("¿Qué distancia debe tener el S4?", "8 mm ± 0,5 mm con la pieza patrón PT-S4 [1].")],
        4: [("¿Cómo alimento el sensor para ajustarlo?", "Con la llave de prueba del armario A1, solo 24 V [1].")],
        5: [("¿Cuánto aprieto la tuerca del sensor?", "A mano más un cuarto de vuelta [1].")],
        6: [("¿Qué alarma debe salir sin pieza?", "La A12, falta pieza S4 [1].")],
    },
}

# --------------------------------------------------------------------------- ejecuciones en el modo planta
# filas: (días, consultas, consultas en pasos críticos, minutos[, estado])
# Las de Marta y Luis bajan de consultas con el tiempo: es la curva de autonomía.

EJECUCIONES: list[dict[str, Any]] = [
    {"usuario": "marta", "codigo": "IT-023",
     "filas": [(35, 8, 3, 38), (32, 6, 2, 33), (29, 5, 2, 30), (25, 3, 1, 26), (21, 2, 1, 24), (17, 1, 0, 21),
               (12, 1, 0, 19), (6, 0, 0, 17)]},
    {"usuario": "luis", "codigo": "IT-051",
     "filas": [(30, 7, 2, 95), (26, 5, 2, 86), (22, 4, 1, 80), (18, 3, 1, 72), (13, 2, 0, 66), (8, 1, 0, 61),
               (3, 1, 0, 58)]},
    {"usuario": "pedro", "codigo": "IT-031",
     "filas": [(33, 4, 2, 42), (27, 3, 1, 37), (20, 1, 0, 33), (14, 1, 0, 31), (7, 1, 0, 30)]},
    {"usuario": "lucia", "codigo": "IT-023", "filas": [(5, 2, 0, 12, "abandonada"), (4, 6, 2, 41)]},
    {"usuario": "carmen", "codigo": "IT-023", "filas": [(37, 0, 0, 15), (15, 0, 0, 14), (5, 0, 0, 13)]},
    {"usuario": "raul", "codigo": "IT-051", "filas": [(28, 1, 0, 55), (20, 0, 0, 50), (12, 0, 0, 48)]},
    {"usuario": "david", "codigo": "IT-061", "version": 1, "filas": [(38, 2, 0, 20), (34, 1, 0, 18), (31, 0, 0, 16)]},
    {"usuario": "irene", "codigo": "IT-061", "filas": [(4, 3, 1, 25)]},
    {"usuario": "oscar", "codigo": "IT-071", "filas": [(24, 3, 1, 50), (16, 2, 0, 44), (9, 1, 0, 40)]},
]

# --------------------------------------------------------------------------- micro-lecciones vistas
# (usuario, código, índices de micro-lección, día de la primera)

VISTAS: list[tuple[str, str, list[int], int]] = [
    ("marta", "IT-023", [0, 1, 2], 36),
    ("lucia", "IT-023", [0, 1, 2], 7),
    ("pedro", "IT-023", [0], 5),
    ("pedro", "IT-031", [0, 1, 2], 34),
    ("irene", "IT-031", [0, 1], 8),
]

# --------------------------------------------------------------------------- cuestionarios
# (usuario, código, versión o None para la vigente, días, aciertos, total)

INTENTOS: list[tuple[str, str, int | None, int, int, int]] = [
    ("carmen", "IT-023", None, 37, 6, 6),
    ("marta", "IT-023", None, 30, 4, 6),
    ("marta", "IT-023", None, 26, 6, 6),
    ("lucia", "IT-023", None, 3, 3, 6),
    ("pedro", "IT-031", None, 18, 4, 5),
    ("luis", "IT-051", None, 20, 3, 5),
    ("luis", "IT-051", None, 15, 4, 5),
    ("raul", "IT-051", None, 24, 5, 5),
    ("david", "IT-061", 1, 33, 3, 3),
    ("oscar", "IT-071", None, 17, 4, 4),
]

# --------------------------------------------------------------------------- observaciones en el puesto

OBSERVACIONES: list[dict[str, Any]] = [
    {"evaluador": "javier", "usuario": "carmen", "codigo": "IT-023", "dias": 30, "aprobada": True, "notas": {},
     "comentario": "Referente de la estación E2. Su nivel O de la matriz anterior queda respaldado en CidIA."},
    {"evaluador": "javier", "usuario": "marta", "codigo": "IT-023", "dias": 10, "aprobada": True,
     "notas": {3: "Secuencia en cruz correcta y dos pasadas.", 5: "Cierra la tapa antes de presurizar."},
     "comentario": "Trabaja con seguridad y sin consultar. Lista para trabajar sola en la estación E2."},
    {"evaluador": "javier", "usuario": "pedro", "codigo": "IT-031", "dias": 7, "aprobada": False, "fallos": [7],
     "notas": {7: "No comprobó el manómetro de amarre antes del primer golpe."},
     "comentario": "Repetir la observación después de repasar la micro-lección de los amarres hidráulicos."},
    {"evaluador": "ana", "usuario": "raul", "codigo": "IT-051", "dias": 11, "aprobada": True,
     "notas": {2: "Buen criterio en las referencias."},
     "comentario": "Revisar con más detalle la accesibilidad en los cordones interiores."},
    {"evaluador": "elena", "usuario": "david", "codigo": "IT-061", "version": 1, "dias": 30, "aprobada": True,
     "notas": {}, "comentario": "Medición correcta y registro completo."},
]

# --------------------------------------------------------------------------- niveles ILUO
# (usuario, código, nivel 1..4, desde (días), formador validado por, requiere reevaluación)
# Los niveles anteriores a la implantación de CidIA vienen de la matriz en papel.

ILUO: list[tuple[str, str, int, int, str | None, bool]] = [
    ("carmen", "IT-023", 4, 160, "javier", False),
    ("marta", "IT-023", 3, 10, None, False),
    ("lucia", "IT-023", 1, 7, None, False),
    ("pedro", "IT-023", 1, 5, None, False),
    ("javier", "IT-031", 4, 340, "carmen", False),  # caduca en menos de un mes
    ("carmen", "IT-031", 2, 120, None, False),
    ("pedro", "IT-031", 2, 18, None, False),
    ("irene", "IT-031", 1, 8, None, False),
    ("ana", "IT-051", 4, 300, "admin", False),
    ("raul", "IT-051", 3, 11, None, False),
    ("luis", "IT-051", 2, 15, None, False),
    ("marta", "IT-051", 1, 21, None, False),
    ("elena", "IT-061", 4, 250, "admin", False),
    ("david", "IT-061", 3, 30, None, True),  # la versión 2 de la IT-061 obliga a reevaluar
    ("irene", "IT-061", 1, 4, None, False),
    ("nuria", "IT-071", 4, 200, "jorge", False),
    ("jorge", "IT-071", 3, 280, None, False),
    ("oscar", "IT-071", 2, 9, None, False),  # cuestionario aprobado y tercera ejecución hace 9 días
]

DIAS_IMPLANTACION = 42  # CidIA empezó a usarse hace seis semanas
