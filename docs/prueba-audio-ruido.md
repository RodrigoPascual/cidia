# Prueba de audio con ruido industrial (propuesta C7)

Mide cómo transcribe el servicio de voz de CidIA (`servidor/asr`, faster-whisper) preguntas típicas de planta con ruido industrial, para decidir el modelo de Whisper del MSI y si hace falta reducción de ruido. Prueba hecha el 10 de octubre de 2026 contra el servidor de pruebas de Oracle.

**Resumen.** Con el modelo `base` la voz solo es fiable sin ruido o con ruido leve (20 dB): a 10 dB ya falla la mitad de los códigos, cifras y términos técnicos. El modelo `small` con un prompt inicial de vocabulario aguanta bien hasta 5 dB (WER 8,5 %, frente al 21 % de `base` con prompt y el 32 % de `base` sin prompt, sin contar un bucle de repetición). El prompt de vocabulario es la mejora más barata: reduce el WER entre un 35 y un 65 % en los dos modelos y sube el acierto de términos clave entre 18 y 39 puntos. Recomendación para el MSI: `small` (ya está en el perfil `msi`) con más hilos, prompt con el vocabulario de la tarea, VAD activado, pulsar para hablar y micrófono de diadema. No hace falta, por ahora, un reductor de ruido en el servidor.

## 1. Método

Script: [`servidor/asr/prueba_ruido.py`](../servidor/asr/prueba_ruido.py) (Python con numpy y la biblioteca estándar; ffmpeg LGPL como programa externo). Resultados completos, con cada transcripción: [`servidor/asr/resultados/`](../servidor/asr/resultados/).

* **Frases.** 20 preguntas y avisos de planta con el vocabulario de la semilla (Metalúrgica Arlanza): «¿Qué par de apriete lleva la brida B?», «La prensa 3 se ha atascado al cambiar el molde», «Abre la instrucción IT-023, paso 4», «Mide la cota de 12,5 milímetros con el calibre», «El lote 4521 tiene tres piezas rechazadas por rebaba»... Cada una lleva de 1 a 3 términos clave (códigos, cifras con unidad y términos técnicos), 38 en total.
* **Voz.** Síntesis de Windows (System.Speech, «Microsoft Helena Desktop», velocidad +1) a 16 kHz, como en `datos-demo/video/generar_medios.py`. Los códigos se dicen como los diría una persona («i te, cero veintitrés», «ese cuatro», «e dos»).
* **Ruido industrial sintético** (mismo ruido para una frase en todos los niveles, semilla fija):
  * ruido rosa (45 % de la potencia);
  * zumbido de motor de 50 Hz con armónicos hasta 1,2 kHz, dominado por el de 100 Hz, con variación lenta de carga (25 %);
  * golpes de prensa cada 0,9-1,4 s: chasquido metálico, resonancias de 380, 1150 y 2700 Hz y golpe sordo de 60 Hz (30 %).
* **Relación señal/ruido (SNR)**: limpio, 20, 10, 5 y 0 dB, sobre el nivel activo de la voz (tramas de 20 ms a menos de 35 dB de la más fuerte). Se añaden 0,6 s de ruido antes y después de la voz, como al pulsar el botón un poco antes de hablar. Referencia orientativa: un móvil o una tableta a 30-50 cm de la boca en una nave de 85-90 dB(A) queda entre 0 y 5 dB; un micrófono de diadema a 2-3 cm, por encima de 15-20 dB.
* **Envío.** Opus a 32 kbit/s en Ogg (como el navegador) a `POST /v1/audio/transcriptions` con `language=es` y `temperature=0`; con prompt, el campo `prompt` (que el servicio pasa como `initial_prompt`).
* **Servicio.** faster-whisper 1.2.1, int8, CPU ARM Neoverse-N1 de Oracle, 2 hilos y 1,5 CPU (los límites del compose), `beam_size=5` y VAD de Silero activado. `base`: el servicio `asr` del compose. `small`: un contenedor temporal con la misma imagen y los mismos límites en otro puerto, borrado al terminar.
* **Métricas.** WER y CER con distancia de Levenshtein propia, tras normalizar mayúsculas, tildes y signos, cifras escritas en letra («25 N·m» = «veinticinco newton metro», «4.521» = «cuatro mil quinientos veintiuno», «IT-023» = «I. T. 0-23») y siglas deletreadas. Acierto de términos clave, separado en los que están en el vocabulario del prompt y los que no. Tiempo de cada petición medido en el cliente (incluye el túnel SSH) y RTF = tiempo / duración del audio (4,75 s de media con los rellenos).
* **Prompt de vocabulario** (el que enviaría el gateway con la tarea y la planta): «Metalúrgica Arlanza. Instrucciones IT-023, IT-031, IT-051, IT-061 e IT-071. Montaje de la brida B, prensa 3, línea 2, estación E2, sensor S4. Par de apriete en newton metro, llave dinamométrica, apriete en cruz, marca de testigo, junta tórica, prueba de estanqueidad. Cambio de molde, consignar la prensa, amarres hidráulicos, punto muerto inferior, primera pieza. Utillaje de soldadura, referencias 3-2-1, EPI, calibre, cota, rebaba.» Deja fuera a propósito parte del vocabulario de las frases (horno, husillo, fresa, lote, grupo hidráulico, fuga de aceite...).

Volumen: `base` con los 5 niveles, sin y con prompt (200 transcripciones); `small` solo a 10 y 5 dB, sin y con prompt (80), para no cargar el servidor compartido.

## 2. Resultados

| Modelo | Prompt | SNR | WER | CER | Términos clave | En el vocabulario | Fuera | Frases exactas | Tiempo medio (s) | RTF |
|---|---|---|---|---|---|---|---|---|---|---|
| base | no | limpio | 10,1% | 2,2% | 71% | 67% | 79% | 8/20 | 2,05 | 0,44 |
| base | no | 20 dB | 9,0% | 2,0% | 74% | 67% | 86% | 9/20 | 2,02 | 0,43 |
| base | no | 10 dB | 20,6% | 6,4% | 47% | 42% | 57% | 4/20 | 1,98 | 0,42 |
| base | no | 5 dB | 142,2% (32,5% *) | 77,1% | 34% | 29% | 43% | 0/20 | 2,30 | 0,49 |
| base | no | 0 dB | 52,3% | 23,6% | 11% | 12% | 7% | 0/20 | 2,01 | 0,43 |
| base | sí | limpio | 4,5% | 1,2% | 92% | 100% | 79% | 15/20 | 2,19 | 0,47 |
| base | sí | 20 dB | 3,0% | 0,8% | 92% | 96% | 86% | 15/20 | 2,18 | 0,46 |
| base | sí | 10 dB | 12,1% | 3,8% | 76% | 83% | 64% | 8/20 | 2,19 | 0,47 |
| base | sí | 5 dB | 21,1% | 7,6% | 58% | 71% | 36% | 6/20 | 2,25 | 0,48 |
| base | sí | 0 dB | 32,2% | 17,0% | 50% | 67% | 21% | 2/20 | 2,28 | 0,48 |
| small | no | 10 dB | 11,6% | 2,7% | 63% | 50% | 86% | 6/20 | 5,71 | 1,21 |
| small | no | 5 dB | 15,6% | 4,7% | 53% | 42% | 71% | 3/20 | 5,97 | 1,27 |
| small | sí | 10 dB | 6,5% | 1,3% | 82% | 83% | 79% | 11/20 | 6,51 | 1,38 |
| small | sí | 5 dB | 8,5% | 1,6% | 76% | 79% | 71% | 9/20 | 6,50 | 1,38 |

(*) A 5 dB sin prompt, una frase («¿Qué EPI necesito para soldar en el utillaje?») entró en un bucle de repetición («que es el que es el que es...», 221 palabras); sin ella, el WER es 32,5 %.

Comparación directa en los niveles decisivos:

| SNR | base sin prompt | base con prompt | small sin prompt | small con prompt |
|---|---|---|---|---|
| 10 dB: WER / términos | 20,6 % / 47 % | 12,1 % / 76 % | 11,6 % / 63 % | **6,5 % / 82 %** |
| 5 dB: WER / términos | 32,5 %* / 34 % | 21,1 % / 58 % | 15,6 % / 53 % | **8,5 % / 76 %** |

## 3. Qué falla

* **Códigos y siglas.** Sin prompt, `base` escribe «Abre la instrucción, y T, 0, 23», «estación 2» (pierde la E) o «¿Qué he pinecesito?» (EPI); `small` escribe «IP 023». Con el prompt, los dos escriben «IT-023», «E2» y «S4» en limpio y con ruido de 10 y 5 dB; «EPI» solo lo acierta `base` sin ruido (con ruido sale «¿Qué te necesito?», por la unión «qué epi» de la voz sintética).
* **Términos técnicos.** Sin prompt, «amarres» sale «amares» en todos los niveles; «husillo», «usillo» o «huesillo»; «utillaje», «utiliaje», «utilizaje» o «lutillaje»; «estanqueidad», «estanqueída»; «punto muerto inferior», «interior». El prompt corrige casi todos los que contiene («utillaje» sigue fallando con ruido) y apenas ayuda a los que no (términos fuera del vocabulario: 79 % → 79 % en limpio con `base`, 86 % → 79 % a 10 dB con `small`).
* **Cifras con ruido.** A 5 dB y menos, `base` cambia cifras y unidades («25 newton metro» → «15,8 metros», «12,5» → «2,5», «150 bar» → «150 bathes»). Es el error más peligroso en planta: una cifra plausible pero falsa. `small` con prompt acierta todas las cifras a 10 y 5 dB (25, 150, 12,5, 4521, 3-2-1 y 10).
* **Bucles de repetición.** El servicio pasa `temperature=0` como valor único, así que faster-whisper no puede reintentar con más temperatura cuando la salida se repite (umbral de compresión 2,4). Un solo bucle dispara el WER y produce una «pregunta» absurda.
* **Efectos secundarios del prompt.** Con mucho ruido, `base` copia formatos del prompt: «La prensa 3-2-2, Cambio de molde» o «El 9-4-521» (por «referencias 3-2-1»). El prompt debe ser corto, con frases naturales y solo el vocabulario de la tarea.
* **Errores de la voz sintética.** Algunos fallos aparecen ya sin ruido y en los dos modelos («lote» → «Note», «del horno» → «de los no», «del apriete» → «de la priete», «en cruz a 25» → «en cruza 25»): son de pronunciación y unión de palabras de la voz de Windows, y por eso el WER en limpio no es 0.
* **Tiempo.** El prompt añade unos 0,2 s por pregunta con `base` y 0,8 s con `small`. En Oracle (1,5 CPU ARM), `small` tarda unos 6 s por pregunta (RTF 1,2-1,4), demasiado para una conversación; `base`, unos 2 s.

## 4. Conclusiones y recomendación para el MSI

1. **Modelo: `small`** (es el que fija ya `perfiles/msi.env`). `base` solo sirve en ambientes tranquilos. En el MSI, subir los recursos del servicio de voz, que en el compose se quedan en 2 hilos y 1,5 CPU: `ASR_HILOS=4` y `CIDIA_CPU_ASR=4` (y `CIDIA_MEM_ASR=2g` por margen). Con un procesador x86 de portátil moderno y 4 hilos, `small` debería quedar en 1-2 s por pregunta (hay que medirlo allí). `medium` o `large-v3-turbo` solo tienen sentido si la voz pasa a la GPU, lo que exige una imagen con las bibliotecas de CUDA y compartir la memoria de la gráfica con Ollama: queda para después de medir `small` en el MSI.
2. **Prompt inicial con el vocabulario de la tarea: sí.** Es la mejora más barata y la que más ayuda con códigos, siglas y cifras (+21 puntos de acierto de términos clave en limpio con `base`, +19 a 10 dB y +23 a 5 dB con `small`). Ojo: la ganancia medida es optimista porque el prompt contiene la mayoría de los términos de las frases; en uso real dependerá de lo bien que el gateway elija el vocabulario. Cambio propuesto en el apartado 5.
3. **VAD: mantenerlo** (`vad_filter=True`). Recorta el ruido sin voz de antes y después, que es lo que hace que Whisper «oiga» frases que nadie ha dicho. Además, en el servicio de voz conviene activar la reserva de temperaturas cuando el cliente pide `temperature=0` (usar `[0.0, 0.2, 0.4, 0.6, 0.8, 1.0]`), para que faster-whisper rehaga los bucles de repetición, y pasar `condition_on_previous_text=False`, que en preguntas cortas no aporta y reduce las repeticiones.
4. **Micrófono: de diadema** con cápsula de cancelación de ruido cerca de la boca. Los resultados marcan el umbral: con 10 dB o más, `small` con prompt acierta más del 80 % de los términos; por debajo de 5 dB nada es fiable. El micrófono de una tableta o de un portátil en la nave queda en esa zona mala. Un micrófono de mano vale si se habla muy cerca, pero ocupa una mano (guantes, piezas). Si es inalámbrico, que sea Bluetooth de banda ancha (16 kHz, HFP 1.6 o superior), no el de 8 kHz.
5. **Pulsar para hablar: mantenerlo** como único modo de voz en planta (ya está: «mantén pulsado para hablar»). Evita enviar ruido sin voz y limita la grabación a la pregunta. Conviene seguir grabando unos 300 ms tras soltar el botón y mostrar el texto transcrito antes de enviarlo, con las cifras y los códigos destacados, sobre todo en pasos críticos.
6. **Reducción de ruido: no hace falta en el servidor por ahora.** El paso de 10 a 5 dB con `small` y prompt solo cuesta 2 puntos de WER, y los reductores genéricos suelen empeorar Whisper por los artefactos que introducen. El navegador ya pide la supresión de ruido de WebRTC (`noiseSuppression: true` en `ui/index.tsx`), que esta prueba no incluye. Si la prueba en planta con voces reales da menos de 5 dB, probar RNNoise (BSD) antes de Whisper y medirlo con este mismo script.

## 5. Cambio propuesto en el gateway (no aplicado)

Hoy el gateway no envía `prompt` al servicio de voz (`cidia/ia/asr.py`). Propuesta:

1. `cidia/ia/asr.py`: nuevo parámetro `vocabulario: str | None` en `transcribir()`, que se envía como campo `prompt` recortado a unos 600 caracteres (Whisper solo usa los últimos 224 tokens del prompt; lo más específico, al final).
2. Nueva función `vocabulario_voz(bd, actor, tarea_id=None, ejecucion_id=None) -> str`: frases naturales con el nombre de la empresa, el código y el título de la instrucción, los títulos de sus pasos, la máquina o el puesto y un glosario fijo opcional de la planta (ajuste nuevo, por ejemplo `CIDIA_ASR_VOCABULARIO`). Sin enumeraciones largas de cifras ni formatos raros, para que Whisper no los copie.
3. `rutas/voz.py`: aceptar los campos opcionales `tarea_id` o `ejecucion_id` y construir el vocabulario solo si el usuario puede ver esa tarea (los mismos permisos que la consulta). El modo planta (`web/src/paginas/planta/copiloto.ts`, función `transcribir`) los enviaría con la ejecución en curso; el copiloto general, con la tarea abierta si la hay.
4. Captura y aportaciones (`servicios/captura.py`, `servicios/aportaciones.py`): pasar el vocabulario de la instrucción a la que se asocia la grabación.
5. Salvaguardas en `limpiar_transcripcion`: descartar el texto si repite un mismo grupo de palabras más de 3 veces, si tiene muchas más palabras de las que caben en la duración del audio (más de 4 por segundo, pidiendo `verbose_json`) o si es un trozo del propio prompt (Whisper lo repite a veces con audio casi en silencio).

## 6. Límites de la prueba

* Voz sintética: una sola voz, dicción clara y constante, sin acento ni el efecto Lombard (en la nave la gente alza la voz, lo que ayuda). Los resultados sirven para comparar modelos y opciones, no como cifra absoluta.
* Ruido sintético sin reverberación, voces de fondo, alarmas ni carretillas; micrófono ideal; sin la supresión de ruido del navegador.
* 20 frases: diferencias de 2 o 3 puntos de WER no son significativas.
* `small` solo se probó a 10 y 5 dB. Quedan pendientes `small` en limpio, 20 y 0 dB, los tiempos en el MSI y una prueba con grabaciones reales en planta.

## 7. Cómo repetirla

Desde la raíz del repositorio, en Windows (voz en castellano instalada y túnel al servicio de voz abierto):

```
python servidor/asr/prueba_ruido.py --prompt ambos
python servidor/asr/prueba_ruido.py --url http://127.0.0.1:18731/v1 --niveles 10,5 --prompt ambos
python servidor/asr/prueba_ruido.py --tabla servidor/asr/resultados/ruido-base-*.json servidor/asr/resultados/ruido-small-*.json
```

Otras opciones: `--frases N`, `--formato wav`, `--texto-prompt "..."`, `--guardar-audios` (deja las mezclas en la caché para escucharlas) y `--semilla`.

## Aplicado tras la prueba (10 de octubre de 2026)

* El servicio de voz reintenta con temperaturas de reserva (0,0 a 1,0) y no arrastra el texto anterior entre segmentos (`condition_on_previous_text=False`), contra los bucles de repetición.
* El gateway envía como prompt inicial el vocabulario de las tareas que la persona puede ver (códigos y nombres) y, si se indica `tarea_id`, los pasos de esa tarea (`rutas/voz.py`, función `vocabulario`).
* Pendiente: que el modo planta envíe `tarea_id` al transcribir y medir de nuevo en el MSI con el modelo `small` y voces reales.
