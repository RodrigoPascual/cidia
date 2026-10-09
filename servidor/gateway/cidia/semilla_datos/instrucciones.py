"""Instrucciones de trabajo sintéticas con sus pasos, micro-lecciones y preguntas de cuestionario.

Cada paso lleva `dibujo` (pictograma de semilla_datos/imagenes.py) y `dato` (rótulo corto del
dibujo). Las preguntas indican el `paso` (orden) al que se refieren y su estado (aprobada o
propuesta, para que la persona experta tenga algo que revisar). `anteriores` describe
versiones previas ya obsoletas (se crean quitando pasos de la vigente).
"""

from __future__ import annotations

from typing import Any


def _p(enunciado: str, opciones: list[str], correcta: int, explicacion: str, paso: int | None = None,
       estado: str = "aprobada") -> dict[str, Any]:
    return {"enunciado": enunciado, "opciones": opciones, "correcta": correcta, "explicacion": explicacion,
            "paso": paso, "estado": estado}


INSTRUCCIONES: list[dict[str, Any]] = [
    # ================================================================== IT-023
    {
        "codigo": "IT-023", "tarea": "IT-023", "version": 1, "titulo": "Montaje de la brida B",
        "autor": "carmen", "revisor": "javier", "dias": 38,
        "resumen": "Montaje de la brida B (BR-B-080) con junta JT-80 sobre el colector CL-200 en la estación E2 de "
                   "la línea 2: apriete en cruz a 25 N·m, marca de testigo y prueba de estanqueidad.",
        "riesgos": "Atrapamiento de dedos al presentar la brida; sobreesfuerzo en el apriete; proyección de aire en "
                   "la prueba de estanqueidad.",
        "epis": "Guantes de protección mecánica (EN 388), gafas de seguridad y calzado de seguridad S3.",
        "herramientas": "Llave dinamométrica de 1/2\" (10 a 60 N·m) con vaso de 17 mm, rotulador de pintura "
                        "amarillo, banco de estanqueidad BE-2, paño sin pelusa y desengrasante.",
        "pasos": [
            {"titulo": "Preparar el puesto y el material",
             "texto": "Comprueba que en la estación E2 tienes la brida B (referencia BR-B-080), una junta de EPDM "
                      "JT-80 nueva, 4 tornillos M10 × 40 de calidad 8.8 y 4 arandelas planas. Verifica que la "
                      "referencia de la etiqueta del carro coincide con la orden de fabricación de la pantalla y que "
                      "la etiqueta de verificación de la llave dinamométrica está vigente.",
             "criterio": "Todo el material presente, sin golpes ni rebabas, y la llave con verificación vigente.",
             "dibujo": "material"},
            {"titulo": "Limpiar el asiento y colocar la junta",
             "texto": "Limpia la cara de asiento del colector con un paño sin pelusa humedecido en desengrasante y "
                      "deja que se seque. Coloca la junta JT-80 centrada en el resalte, sin pellizcos ni "
                      "retorcimientos. La junta no se reutiliza nunca: si se cae al suelo o ya se ha montado antes, "
                      "cámbiala por una nueva.",
             "criterio": "Junta nueva, centrada, limpia y sin pliegues.",
             "dibujo": "junta", "dato": "junta JT-80 centrada"},
            {"titulo": "Apretar los 4 tornillos en cruz a 25 N·m", "critico": True,
             "texto": "Presenta la brida sobre la junta y enrosca a mano los 4 tornillos con sus arandelas hasta que "
                      "asienten. Con la llave dinamométrica de media pulgada (1/2\"), aprieta en cruz: 1 arriba, "
                      "2 abajo, 3 derecha y 4 izquierda. Haz dos pasadas: la primera a 12 N·m y la segunda a 25 N·m, "
                      "hasta oír el clic de la llave en cada tornillo. No uses nunca el atornillador de impacto en "
                      "esta unión.",
             "criterio": "Los 4 tornillos a 25 N·m, apretados en cruz y en dos pasadas (12 y 25 N·m).",
             "dibujo": "par_cruz", "dato": "25 N·m"},
            {"titulo": "Marcar los tornillos con la marca de testigo",
             "texto": "Marca cada tornillo con el rotulador de pintura amarillo: una raya que cruce la cabeza del "
                      "tornillo y continúe sobre la brida. Si un tornillo se afloja, la raya se desalinea y se ve a "
                      "simple vista.",
             "criterio": "Los 4 tornillos con marca de testigo continua.",
             "dibujo": "marcado"},
            {"titulo": "Hacer la prueba de estanqueidad", "seguridad": True,
             "texto": "Lleva el conjunto al banco BE-2 de la estación E4, conecta los dos tapones rápidos y cierra la "
                      "tapa de protección antes de presurizar. El banco sube a 3 bar y mide durante 60 segundos. La "
                      "caída de presión máxima admitida es de 0,05 bar. No abras la tapa hasta que el banco haya "
                      "despresurizado.",
             "criterio": "Resultado OK del banco: caída igual o inferior a 0,05 bar en 60 s.",
             "dibujo": "manometro", "dato": "3 bar · 60 s"},
            {"titulo": "Inspección visual final",
             "texto": "Comprueba que las 4 marcas de testigo siguen alineadas, que la junta no asoma más de 1 mm por "
                      "ningún lado, que no hay rebabas ni golpes en la brida y que la etiqueta del colector es "
                      "legible.",
             "criterio": "Marcas alineadas, junta sin asomar más de 1 mm y brida sin defectos.",
             "dibujo": "lupa"},
            {"titulo": "Registrar y etiquetar el conjunto",
             "texto": "Registra el número de serie del conjunto en la pantalla de la estación con su resultado de "
                      "estanqueidad, pega la etiqueta verde «OK estanqueidad» en el lateral del colector y deja el "
                      "conjunto en el carro de salida. Si el banco dio NOK: etiqueta roja y contenedor rojo de la "
                      "estación E5.",
             "criterio": "Conjunto registrado, etiquetado y en el carro de salida.",
             "dibujo": "etiqueta"},
        ],
        "microlecciones": [
            {"titulo": "Por qué se aprieta en cruz",
             "contenido": "Si aprietas los tornillos uno detrás de otro alrededor de la brida, la junta se aplasta más "
                          "por un lado que por otro y la brida queda inclinada: es el origen de muchas fugas. "
                          "Apretando en cruz (arriba, abajo, derecha, izquierda) la fuerza se reparte y la junta se "
                          "comprime por igual. Por eso además se hacen dos pasadas: la primera, a 12 N·m, asienta la "
                          "brida; la segunda, a 25 N·m, da el par final.",
             "punto_clave": "En cruz y en dos pasadas: 12 N·m y después 25 N·m.",
             "pregunta": {"enunciado": "¿En qué orden se aprietan los tornillos de la brida B?",
                          "opciones": ["En el sentido de las agujas del reloj",
                                       "En cruz: arriba, abajo, derecha, izquierda",
                                       "Primero los dos de arriba y después los de abajo",
                                       "Da igual el orden si se llega a 25 N·m"],
                          "correcta": 1, "explicacion": "En cruz, para que la junta se comprima por igual."}},
            {"titulo": "La llave dinamométrica",
             "contenido": "La llave dinamométrica de media pulgada limita el par: al llegar al valor ajustado hace "
                          "clic y cede un poco. En ese momento deja de apretar. Antes de empezar, comprueba que la "
                          "etiqueta de verificación del laboratorio está vigente (se verifica cada 6 meses). Al "
                          "terminar el turno, guárdala con el valor más bajo de la escala para que el muelle no "
                          "pierda tensión.",
             "punto_clave": "Al oír el clic, para. Solo llaves con verificación vigente.",
             "pregunta": {"enunciado": "¿Qué haces si la etiqueta de verificación de la llave está caducada?",
                          "opciones": ["La uso con cuidado", "No la uso y aviso a mi responsable",
                                       "Aprieto un poco más para compensar", "Uso el atornillador de impacto"],
                          "correcta": 1,
                          "explicacion": "Una llave sin verificación vigente no garantiza el par: se retira."}},
            {"titulo": "La junta y la prueba de estanqueidad",
             "contenido": "La junta JT-80 de EPDM es la que garantiza que el colector no pierde. Una junta pellizcada, "
                          "retorcida o reutilizada es la causa más frecuente de NOK en el banco BE-2. El banco sube a "
                          "3 bar y admite una caída máxima de 0,05 bar en 60 segundos. Nunca abras la tapa con el "
                          "conjunto presurizado.",
             "punto_clave": "Junta nueva y centrada. Tapa cerrada hasta que el banco despresuriza.",
             "pregunta": {"enunciado": "¿Cuál es la caída de presión máxima admitida en la prueba de estanqueidad?",
                          "opciones": ["0,5 bar en 60 s", "0,05 bar en 60 s", "No se admite ninguna caída",
                                       "0,05 bar en 10 s"],
                          "correcta": 1, "explicacion": "0,05 bar durante 60 segundos a 3 bar."}},
        ],
        "preguntas": [
            _p("¿A qué par se aprietan los tornillos de la brida B?", ["12 N·m", "25 N·m", "40 N·m",
               "Hasta que no giren más"], 1, "25 N·m en la segunda pasada; la primera es a 12 N·m.", 3),
            _p("¿Qué herramienta se usa para el apriete final de la brida B?", ["Atornillador de impacto",
               "Llave fija de 17 mm", "Llave dinamométrica de 1/2\"", "Llave allen"], 2,
               "Solo la llave dinamométrica garantiza los 25 N·m.", 3),
            _p("¿En qué orden se aprietan los 4 tornillos?", ["1 arriba, 2 abajo, 3 derecha, 4 izquierda",
               "En el sentido de las agujas del reloj", "Los de arriba primero", "En cualquier orden"], 0,
               "En cruz, para comprimir la junta por igual.", 3),
            _p("¿Qué haces con una junta JT-80 que se ha caído al suelo?", ["La limpio y la monto",
               "La cambio por una nueva", "La monto si no tiene cortes", "La guardo para la prueba"], 1,
               "La junta no se reutiliza nunca.", 2),
            _p("¿Para qué sirve la marca de testigo amarilla?", ["Para indicar que la pieza es de la línea 2",
               "Para ver a simple vista si un tornillo se ha aflojado", "Para contar los tornillos",
               "Para indicar el par aplicado"], 1, "Si el tornillo gira, la raya se desalinea.", 4),
            _p("¿Cuándo se puede abrir la tapa del banco BE-2?", ["A los 60 segundos exactos",
               "Cuando el banco ha despresurizado", "En cualquier momento si no hay fuga", "Cuando suena la alarma"],
               1, "Abrir con presión puede proyectar los tapones.", 5),
        ],
        # Narración del vídeo sintético de datos-demo (frases cortas para la voz de Windows).
        "narracion": {
            "inicio": "Montaje de la brida B, en la estación dos de la línea dos.",
            "pasos": [
                "Paso uno. Preparo la brida B, una junta nueva y cuatro tornillos M diez con su arandela.",
                "Paso dos. Limpio el asiento y centro la junta. La junta nunca se reutiliza.",
                "Paso tres, y es crítico. Aprieto los cuatro tornillos en cruz a veinticinco newton metro, con la "
                "llave dinamométrica de media pulgada. Primero a doce y luego a veinticinco.",
                "Paso cuatro. Marco cada tornillo con el rotulador amarillo.",
                "Paso cinco. Prueba de estanqueidad: tapa cerrada, tres bar durante un minuto.",
                "Paso seis. Reviso las marcas, la junta y que no haya rebabas.",
                "Paso siete. Registro el número de serie, pego la etiqueta verde y al carro de salida.",
            ],
            "cierre": "Brida B montada.",
        },
    },
    # ================================================================== IT-031
    {
        "codigo": "IT-031", "tarea": "IT-031", "version": 1, "titulo": "Cambio de molde en la prensa 3",
        "autor": "javier", "revisor": "carmen", "dias": 36,
        "resumen": "Cambio rápido de molde en la prensa P3 (630 t): preparación, suelta de amarres, consignación, "
                   "extracción, limpieza, colocación, amarre hidráulico, prueba en vacío y primera pieza.",
        "riesgos": "Atrapamiento grave entre molde y mesa; caída de cargas (moldes de hasta 1.800 kg); energía "
                   "hidráulica residual; quemaduras con el molde caliente.",
        "epis": "Calzado S3, guantes anticorte, gafas de seguridad, protección auditiva y guantes térmicos si el "
                "molde está caliente.",
        "herramientas": "Carro de cambio rápido, pistola de aire con regulador, llave de bola KB-3, calzos amarillos, "
                        "candado personal y tarjeta.",
        "pasos": [
            {"titulo": "Preparar el cambio",
             "texto": "Comprueba en el panel que la orden siguiente corresponde al molde que vas a montar y anota su "
                      "receta (va grabada en la placa del molde, por ejemplo M-318). Deja el molde nuevo en el lado "
                      "libre del carro de cambio rápido, con los tacos de centrado limpios. Ten a mano la pistola de "
                      "aire, la llave de bola KB-3 y tu candado.",
             "criterio": "Molde correcto en el carro y receta identificada.",
             "dibujo": "panel", "dato": "Siguiente: M-318 · Orden 4471 · Altura 412,5 mm"},
            {"titulo": "Bajar el carro y soltar los amarres",
             "texto": "En modo de reglaje, baja el carro hasta que apoye sobre el molde. Suelta los 8 amarres "
                      "hidráulicos (4 del carro y 4 de la mesa) desde el panel y comprueba que todos los indicadores "
                      "pasan a rojo. Sube el carro despacio hasta su punto superior.",
             "criterio": "8 indicadores en rojo y carro arriba.",
             "dibujo": "amarre", "dato": "amarres sueltos"},
            {"titulo": "Parar y consignar la prensa", "critico": True, "seguridad": True,
             "texto": "Para la prensa y consígnala según IT-073: seccionador Q0 en OFF con tu candado y tu tarjeta, "
                      "válvula neumática V-N1 cerrada y bloqueada, acumulador descargado con la llave KB-3 y calzos "
                      "amarillos bajo el carro. Comprueba la energía cero: pulsa marcha y mira que el manómetro de la "
                      "central marca 0 bar. Nadie entra en la zona del molde sin este paso.",
             "criterio": "Prensa consignada con tu candado y energía cero comprobada.",
             "dibujo": "candado"},
            {"titulo": "Sacar el molde anterior", "seguridad": True,
             "texto": "Empuja el molde sobre los rodillos de la mesa hasta el carro de cambio, siempre desde el lateral "
                      "y nunca por delante del molde. Si está caliente, usa guantes térmicos. Bloquea el molde en el "
                      "carro con su pasador.",
             "criterio": "Molde en el carro y bloqueado con el pasador.",
             "dibujo": "prensa_sacar"},
            {"titulo": "Limpiar la mesa y las caras de apoyo",
             "texto": "Sopla con aire las ranuras en T, los rodillos y las caras de apoyo de la mesa y del carro. "
                      "Retira recortes, virutas y restos de aceite de desmoldeo: una viruta bajo el molde lo deja "
                      "inclinado y marca la pieza.",
             "criterio": "Mesa, ranuras y caras de apoyo limpias.",
             "dibujo": "aire", "dato": "mesa y ranuras limpias"},
            {"titulo": "Colocar y centrar el molde nuevo",
             "texto": "Introduce el molde nuevo desde el carro hasta que toque los dos tacos de centrado de la mesa. "
                      "Comprueba que apoya en toda su superficie y que el código del molde coincide con la orden.",
             "criterio": "Molde apoyado contra los dos tacos y código correcto.",
             "dibujo": "prensa_meter"},
            {"titulo": "Retirar la consignación y amarrar el molde", "critico": True,
             "texto": "Comprueba que no queda nadie ni ninguna herramienta en la zona del molde, quita los calzos y "
                      "retira tu candado. En modo de reglaje, baja el carro lento hasta apoyar en el molde y cierra "
                      "los 8 amarres. Todos los indicadores deben pasar a verde y el manómetro de amarre debe marcar "
                      "180 bar. Si algún amarre no llega a presión (alarma A17), no golpees y avisa a Mantenimiento.",
             "criterio": "8 amarres en verde y 180 bar en el manómetro de amarre.",
             "dibujo": "amarre", "dato": "180 bar · 8 amarres en verde"},
            {"titulo": "Cargar la receta, probar y pedir la primera pieza",
             "texto": "Carga la receta del molde en el panel y comprueba la altura de cierre. Haz 3 golpes en vacío en "
                      "modo manual con el mando a dos manos y después una pieza en modo lento. Lleva la primera pieza "
                      "a Calidad para el control de primera pieza (IT-065) y no pases a automático hasta tener el OK.",
             "criterio": "Prueba en vacío sin alarmas y primera pieza con OK de Calidad.",
             "dibujo": "pieza_ok"},
        ],
        "microlecciones": [
            {"titulo": "Por qué se consigna aunque sea un momento",
             "contenido": "La mayoría de los accidentes graves en prensas ocurren durante cambios y ajustes, no en "
                          "producción. Una prensa hidráulica parada puede tener energía guardada en el acumulador y el "
                          "carro puede bajar por su propio peso. Por eso se aíslan las cuatro energías (eléctrica, "
                          "hidráulica, neumática y gravedad) y se comprueba la energía cero antes de entrar.",
             "punto_clave": "Cuatro energías aisladas y energía cero comprobada antes de meter las manos.",
             "pregunta": {"enunciado": "¿Qué energías se aíslan en la prensa 3 antes de entrar en la zona del molde?",
                          "opciones": ["Solo la eléctrica", "Eléctrica e hidráulica",
                                       "Eléctrica, hidráulica, neumática y gravedad",
                                       "Ninguna si la prensa está en modo manual"],
                          "correcta": 2, "explicacion": "Las cuatro: cualquiera de ellas puede mover el carro."}},
            {"titulo": "Los amarres hidráulicos",
             "contenido": "Los 8 amarres (4 en el carro y 4 en la mesa) sujetan el molde a 180 bar. Si uno no llega a "
                          "presión, el molde puede moverse al golpear, romperse o salir despedido. El panel lo avisa "
                          "con la alarma A17 y el indicador en rojo. Nunca golpees con un amarre en rojo.",
             "punto_clave": "8 indicadores en verde y 180 bar antes del primer golpe.",
             "pregunta": {"enunciado": "¿Qué haces si aparece la alarma A17 tras amarrar el molde?",
                          "opciones": ["Golpeo en modo lento para comprobar", "No golpeo y aviso a Mantenimiento",
                                       "Reinicio el panel", "Aprieto los amarres a mano"],
                          "correcta": 1, "explicacion": "A17 es amarre sin presión: no se golpea."}},
            {"titulo": "La primera pieza",
             "contenido": "Tras un cambio de molde, la primera pieza se mide completa en Calidad. Así se comprueba que "
                          "el molde está bien montado y que la receta es la correcta antes de fabricar cientos de "
                          "piezas. Mientras esperas el OK, la prensa no pasa a automático.",
             "punto_clave": "Sin OK de Calidad, no hay automático.",
             "pregunta": {"enunciado": "¿Cuándo puedes pasar la prensa a automático tras un cambio de molde?",
                          "opciones": ["Después de 3 golpes en vacío", "Cuando Calidad da el OK de la primera pieza",
                                       "Cuando el molde está caliente", "Inmediatamente"],
                          "correcta": 1, "explicacion": "La primera pieza libera la producción."}},
        ],
        "preguntas": [
            _p("¿Quién puede retirar tu candado de consignación?", ["Cualquier persona de Mantenimiento", "Solo tú",
               "El responsable de turno", "Quien termine el trabajo"], 1,
               "Un candado, una persona, una llave.", 3),
            _p("¿Qué presión debe marcar el manómetro de amarre?", ["80 bar", "120 bar", "180 bar", "250 bar"], 2,
               "Los amarres de la prensa 3 trabajan a 180 bar.", 7),
            _p("¿Desde dónde se empuja el molde para sacarlo?", ["Desde delante", "Desde el lateral",
               "Desde detrás de la prensa", "Da igual"], 1, "Nunca por delante del molde.", 4),
            _p("¿Por qué se limpian las ranuras y las caras de apoyo de la mesa?", ["Por estética",
               "Una viruta deja el molde inclinado y marca la pieza", "Para no gastar aceite", "Para que suene menos"],
               1, "El molde debe apoyar en toda su superficie.", 5),
            _p("¿Cuántos golpes en vacío se hacen antes de la primera pieza?", ["Ninguno", "1", "3", "10"], 2,
               "Tres golpes en vacío en modo manual.", 8),
        ],
    },
    # ================================================================== IT-051
    {
        "codigo": "IT-051", "tarea": "IT-051", "version": 1, "titulo": "Diseño de utillaje de soldadura",
        "autor": "ana", "revisor": "ana", "dias": 34,
        "resumen": "Diseño de un utillaje manual de soldadura con la plantilla UT-PLANTILLA-03: análisis de la pieza, "
                   "referencias 3-2-1, amarres, modelo 3D, comprobación de la antorcha y documentación para la "
                   "revisión de diseño.",
        "riesgos": "Trabajo con pantallas de visualización (pausas cada 2 horas). En visitas a soldadura, radiación "
                   "del arco y proyecciones.",
        "epis": "En oficina, ninguno. En visitas a soldadura: gafas, calzado S3 y pantalla si hay arco cerca.",
        "herramientas": "CAD 3D con la biblioteca de normalizados, plantilla UT-PLANTILLA-03, PDM y lista de "
                        "comprobación de revisión del PR-OT-02.",
        "pasos": [
            {"titulo": "Analizar el plano y la secuencia de soldadura",
             "texto": "Abre en el PDM el plano liberado de la pieza y su modelo 3D. Identifica las cotas críticas, las "
                      "superficies de referencia y la secuencia de cordones. Pregunta a Producción si la soldadura "
                      "será manual o en la célula R2 y qué cadencia se espera.",
             "criterio": "Cotas críticas, referencias y secuencia anotadas en la hoja de inicio.",
             "dibujo": "plano"},
            {"titulo": "Definir las referencias 3-2-1", "critico": True,
             "texto": "Elige tres apoyos en la superficie principal, dos en un lateral y uno en el extremo, sobre las "
                      "mismas superficies que el plano usa para acotar. Deja entre 0,2 y 0,5 mm de holgura en los "
                      "topes laterales para la dilatación al soldar.",
             "criterio": "Seis apoyos sobre superficies de referencia del plano y holguras de 0,2 a 0,5 mm.",
             "dibujo": "referencias"},
            {"titulo": "Elegir los amarres",
             "texto": "Coloca los amarres de modo que empujen la pieza contra los apoyos. Usa gatos de palanca de la "
                      "biblioteca de normalizados; si la cadencia supera 30 piezas por hora, amarres neumáticos. "
                      "Ningún amarre puede quedar en la trayectoria de la antorcha.",
             "criterio": "Amarres contra los apoyos y fuera de la trayectoria de la antorcha.",
             "dibujo": "amarre", "dato": "contra los apoyos"},
            {"titulo": "Modelar el utillaje con la plantilla",
             "texto": "Modela base, apoyos, amarres y placas de cobre en la plantilla UT-PLANTILLA-03, con una altura "
                      "de trabajo de 900 a 1.100 mm y piezas desmontables de 15 kg como máximo. Añade el poka-yoke "
                      "que impida colocar la pieza girada.",
             "criterio": "Modelo completo, ergonomía dentro de límites y poka-yoke incluido.",
             "dibujo": "cad"},
            {"titulo": "Comprobar la accesibilidad de la antorcha", "critico": True,
             "texto": "Simula cada cordón con el modelo de antorcha: ángulo de trabajo de 45° ± 15° y al menos 15 mm "
                      "libres alrededor de la boquilla. Si algún cordón colisiona, mueve el amarre o el apoyo y repite "
                      "la comprobación.",
             "criterio": "Todos los cordones accesibles y sin colisiones.",
             "dibujo": "antorcha", "dato": "45° ± 15°"},
            {"titulo": "Generar los planos y pedir la revisión",
             "texto": "Genera los planos de conjunto y despiece, la lista de materiales y la hoja de mantenimiento. "
                      "Sube el paquete al PDM en estado «en revisión» y apúntalo para la revisión de diseño de los "
                      "jueves con la lista de comprobación del PR-OT-02.",
             "criterio": "Paquete completo en el PDM y revisión solicitada.",
             "dibujo": "etiqueta", "dato": "paquete en revisión"},
        ],
        "microlecciones": [],
        "preguntas": [
            _p("¿Cuántos puntos de apoyo tiene un sistema de referencias 3-2-1?", ["3", "5", "6", "9"], 2,
               "Tres más dos más uno: seis apoyos.", 2),
            _p("¿Qué holgura se deja en los topes laterales?", ["Ninguna", "De 0,2 a 0,5 mm", "De 1 a 2 mm", "5 mm"],
               1, "Absorbe la dilatación al soldar.", 2),
            _p("¿Hacia dónde deben empujar los amarres la pieza?", ["Contra los apoyos", "Hacia el operario",
               "En contra de los apoyos", "Hacia arriba"], 0, "El amarre lleva la pieza contra su referencia.", 3),
            _p("¿Qué ángulo de trabajo de la antorcha se considera accesible?", ["90° exactos", "45° ± 15°",
               "Menos de 10°", "Cualquiera"], 1, "Además, 15 mm libres alrededor de la boquilla.", 5),
            _p("¿Qué peso máximo puede tener una parte desmontable sin puntos de elevación?", ["5 kg", "15 kg",
               "25 kg", "40 kg"], 1, "Por encima de 15 kg se añaden puntos de elevación.", 4),
            _p("¿En qué estado se sube el paquete de planos al PDM antes de la revisión?", ["Liberado",
               "En revisión", "Obsoleto", "Borrador personal"], 1, "Se libera después de la revisión.", 6,
               estado="propuesta"),
            _p("¿Qué tolerancias generales se aplican si el plano no indica otra cosa?", ["ISO 2768-mK",
               "ISO 2768-fH", "± 1 mm", "Ninguna"], 0, "Es la tolerancia general de nuestros planos.", 1,
               estado="propuesta"),
        ],
    },
    # ================================================================== IT-061 (versión 2; la 1 está obsoleta)
    {
        "codigo": "IT-061", "tarea": "IT-061", "version": 2, "titulo": "Inspección dimensional con calibre",
        "autor": "elena", "revisor": "elena", "dias": 9,
        "anteriores": [{"version": 1, "dias": 40, "sin_pasos": [3]}],
        "resumen": "Medición de las cotas del plan de control PC-CAL-01 con calibre digital de 150 mm: verificación "
                   "del equipo, puesta a cero, aclimatación de la pieza, medición, registro e identificación.",
        "riesgos": "Cortes con aristas de piezas sin desbarbar; posturas forzadas en la mesa de medición.",
        "epis": "Calzado de seguridad en planta y guantes anticorte para manipular piezas sin desbarbar.",
        "herramientas": "Calibre digital de 150 mm (resolución 0,01 mm), bloque patrón de 25 mm, termómetro de "
                        "contacto, pantalla de control estadístico y etiquetas verde y roja.",
        "pasos": [
            {"titulo": "Comprobar la calibración del calibre",
             "texto": "Mira la etiqueta del calibre: debe tener la calibración anual vigente y la verificación interna "
                      "del mes. Si está caducada, no lo uses: déjalo en el armario de equipos retirados y coge otro.",
             "criterio": "Etiqueta de calibración y verificación vigentes.",
             "dibujo": "etiqueta", "dato": "calibración vigente"},
            {"titulo": "Limpiar y poner a cero",
             "texto": "Limpia las palas con un paño seco, ciérralas suavemente y pulsa cero: la pantalla debe marcar "
                      "0,00. Comprueba con el bloque patrón de 25 mm que el calibre marca 25,00 ± 0,02.",
             "criterio": "Cero correcto y bloque patrón dentro de ± 0,02 mm.",
             "dibujo": "cero"},
            {"titulo": "Aclimatar la pieza",
             "texto": "Si la pieza viene de soldadura o de la prensa, déjala en la mesa de medición hasta que esté a "
                      "20 ± 2 °C (compruébalo con el termómetro de contacto). Una pieza de acero de 80 mm a 50 °C mide "
                      "unas 3 centésimas más: suficiente para dar por mala una pieza buena.",
             "criterio": "Pieza a 20 ± 2 °C.",
             "dibujo": "termometro", "dato": "20 ± 2 °C"},
            {"titulo": "Medir las cotas del plan de control", "critico": True,
             "texto": "Mide cada cota de la hoja de control con el calibre perpendicular a la superficie, sin forzar "
                      "las palas y lejos de rebabas. Repite cada medida tres veces y anota la media. Para el diámetro "
                      "interior de la brida B usa las palas de interiores.",
             "criterio": "Tres medidas por cota, calibre perpendicular y sin forzar.",
             "dibujo": "calibre", "dato": "80,04"},
            {"titulo": "Registrar los resultados",
             "texto": "Registra las medias en la pantalla de control estadístico del laboratorio o en la hoja de "
                      "control. Si un valor sale fuera de tolerancia, repite la medida antes de registrarlo y avisa a "
                      "tu responsable.",
             "criterio": "Todas las cotas registradas.",
             "dibujo": "spc"},
            {"titulo": "Identificar y segregar",
             "texto": "Pon etiqueta verde a las piezas conformes y roja a las no conformes, y lleva estas a la jaula "
                      "roja. Si una cota crítica está fuera, avisa a Producción para parar y segregar desde el último "
                      "control bueno.",
             "criterio": "Piezas identificadas y no conformes segregadas.",
             "dibujo": "semaforo"},
        ],
        "microlecciones": [],
        "preguntas": [
            _p("¿Qué debe marcar el calibre con las palas cerradas?", ["0,00", "0,01",
               "Lo que marque, se resta después", "25,00"], 0, "Si no marca 0,00, se pulsa cero.", 2),
            _p("¿A qué temperatura debe estar la pieza para medirla?", ["A la que salga de la prensa", "20 ± 2 °C",
               "Por debajo de 10 °C", "Da igual"], 1, "La dilatación falsea la medida.", 3),
            _p("¿Cuántas veces se repite cada medida?", ["1", "2", "3", "5"], 2, "Tres veces y se anota la media.", 4),
            _p("¿Qué haces con un calibre con la calibración caducada?", ["Lo uso y lo apunto", "Lo retiro y cojo otro",
               "Lo calibro yo", "Lo uso solo para cotas no críticas"], 1, "Un equipo caducado no se usa.", 1),
        ],
    },
    # ================================================================== IT-071
    {
        "codigo": "IT-071", "tarea": "IT-071", "version": 1, "titulo": "Calibración del sensor S4 de la prensa 3",
        "autor": "nuria", "revisor": "jorge", "dias": 28,
        "resumen": "Ajuste mensual de la distancia de detección del sensor inductivo S4 (presencia de pieza) de la "
                   "prensa P3 con la pieza patrón PT-S4.",
        "riesgos": "Atrapamiento si la prensa no está consignada; caída a distinto nivel desde la plataforma.",
        "epis": "Calzado S3, gafas de seguridad y guantes de protección mecánica.",
        "herramientas": "Pieza patrón PT-S4, galga de 8 mm, destornillador de ajuste de 2,5 mm, llave fija de 24 mm, "
                        "pistola de aire con regulador y candado personal.",
        "pasos": [
            {"titulo": "Consignar la prensa 3", "critico": True, "seguridad": True,
             "texto": "Consigna la prensa según IT-073 (seccionador Q0, válvula V-N1, acumulador descargado y calzos). "
                      "El sensor S4 está dentro de la zona del molde: no se ajusta nunca con la prensa en tensión.",
             "criterio": "Prensa consignada con tu candado y energía cero comprobada.",
             "dibujo": "candado"},
            {"titulo": "Limpiar el sensor",
             "texto": "Sopla la cara del sensor con aire a baja presión (máximo 2 bar) y límpiala con un paño seco. No "
                      "uses disolventes: dañan la cara activa. Revisa que el cable y el conector no están pellizcados.",
             "criterio": "Cara activa limpia y cable sin daños.",
             "dibujo": "aire", "dato": "máx. 2 bar, sin disolventes"},
            {"titulo": "Comprobar la distancia con la pieza patrón",
             "texto": "Coloca la pieza patrón PT-S4 en su alojamiento del molde y mide con la galga la distancia hasta "
                      "la cara del sensor: debe ser de 8 mm ± 0,5 mm. Si no, afloja la tuerca de fijación y desplaza "
                      "el sensor hasta conseguirla.",
             "criterio": "Distancia de 8 mm ± 0,5 mm.",
             "dibujo": "sensor", "dato": "8 ± 0,5 mm"},
            {"titulo": "Ajustar la sensibilidad", "critico": True,
             "texto": "Activa solo la alimentación de mando de 24 V del sensor con la llave de prueba del armario A1 "
                      "(la potencia de la prensa sigue consignada). Gira el potenciómetro hasta que el LED amarillo se "
                      "encienda con la pieza patrón a 8 mm y se apague al retirarla.",
             "criterio": "LED encendido con la pieza patrón y apagado sin ella.",
             "dibujo": "potenciometro"},
            {"titulo": "Fijar el sensor",
             "texto": "Aprieta la tuerca de fijación M18 con la llave de 24 mm a mano más un cuarto de vuelta, sin "
                      "pasarte: un apriete excesivo deforma la rosca del sensor. Vuelve a comprobar los 8 mm.",
             "criterio": "Sensor fijo y distancia de 8 mm confirmada.",
             "dibujo": "sensor", "dato": "8 mm"},
            {"titulo": "Prueba funcional y registro",
             "texto": "Retira la pieza patrón y la consignación. Haz un ciclo en modo manual con pieza y otro sin "
                      "pieza: sin pieza debe saltar la alarma A12. Cierra la orden de trabajo en el GMAO con la "
                      "distancia medida.",
             "criterio": "Alarma A12 sin pieza y orden de trabajo cerrada.",
             "dibujo": "panel", "dato": "A12 · Falta pieza S4 · Prueba correcta"},
        ],
        "microlecciones": [],
        "preguntas": [
            _p("¿Cuál es la distancia de detección del sensor S4?", ["2 mm", "8 mm ± 0,5 mm", "18 mm", "24 mm"], 1,
               "Se ajusta con la pieza patrón PT-S4.", 3),
            _p("¿Con qué se limpia la cara del sensor?", ["Disolvente", "Aire a baja presión y paño seco",
               "Agua a presión", "Lija fina"], 1, "Los disolventes dañan la cara activa.", 2),
            _p("¿Qué alarma debe saltar en el ciclo de prueba sin pieza?", ["A12", "A17", "A21", "A30"], 0,
               "A12 es «falta pieza S4».", 6),
            _p("¿Se puede ajustar el S4 con la prensa en tensión?", ["Sí, en modo manual",
               "No, siempre con la prensa consignada", "Sí, si el carro está arriba", "Solo en el turno de noche"],
               1, "Está dentro de la zona del molde.", 1),
            _p("¿Cómo se aprieta la tuerca de fijación M18?", ["Con llave dinamométrica a 50 N·m",
               "A mano más un cuarto de vuelta", "Con el atornillador", "Hasta el tope"], 1,
               "Un apriete excesivo deforma la rosca.", 5, estado="propuesta"),
            _p("¿Qué indica el LED amarillo del sensor?", ["Que hay tensión", "Que detecta la pieza",
               "Que hay una avería", "Que está calibrado"], 1, "Se usa para ajustar la sensibilidad.", 4,
               estado="propuesta"),
        ],
    },
]
