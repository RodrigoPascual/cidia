# Herramientas de vídeo de CidIA

Tres piezas para hacer el vídeo de demostración de CidIA sin grabar la pantalla a mano: un **grabador** que maneja la interfaz con un cursor visible y graba cada escena, una **voz** en castellano sintetizada en local y un **montaje** que une escenas, narración, tarjetas de capítulo, rótulos y subtítulos. Todo funciona en este PC (Windows) contra el servidor de pruebas, con datos sintéticos de «Metalúrgica Arlanza, S. L.» (ver `datos-demo/README.md`).

| Fichero | Qué es |
|---|---|
| `grabador.mjs` | Node 22 + CDP sobre Edge sin cabeza a 1920x1080: ejecuta una escena (JSON) y la graba a 30 fps. |
| `voz.py` | Narración y preguntas al micrófono con Kokoro-82M (Apache-2.0), en local. Compara voces (`comparar`). |
| `voz_windows.ps1` | Síntesis con las voces de Windows, solo para la comparación. |
| `pronunciacion.json` | Cómo se dicen siglas y códigos (CidIA, IT-023, ILUO, xAPI, N·m...). Solo afecta a la voz. |
| `montaje.py` | Monta el vídeo final: MP4 H.264 + AAC, `.srt`, capítulos e informe. |
| `comun.py` | Rutas, ffmpeg, fuentes y carga de proyectos (lo usan `voz.py` y `montaje.py`). |
| `preparar.py` | Descarga y comprueba (sha256) los modelos, Piper y Fira Sans en `.herramientas/` (ignorada por git). |
| `guion_md.mjs` | Genera `docs/video/guion.md` (el guion legible) a partir del proyecto y, si se le da, del informe del montaje. |
| `ejemplos/` | Proyecto de prueba (`prueba.json`) con dos escenas reales: `inicio-javier.json` y `copiloto-voz-lucia.json`. |

El vídeo de la candidatura es `docs/video/recorrido.json` (60 piezas: tarjetas y 39 escenas en línea, una fuera del montaje) y su resumen para el jurado `docs/video/resumen.json` (13 piezas con las mismas grabaciones y voces). El resultado, cómo se grabó y qué es real o se ha acelerado: `04_VIDEO/LEEME.md`, fuera del repositorio.

## 1. Preparación (una vez)

```powershell
python herramientas/video/preparar.py          # Kokoro, Fira Sans y Piper (unos 500 MB)
```

Necesita además Node 22 (trae `fetch` y `WebSocket`), Microsoft Edge (o Chrome) y el ffmpeg LGPL de `servidor/gateway/.herramientas/` (se encuentra solo; `CIDIA_FFMPEG` para usar otro). El grabador inicia sesión por la API con un fichero de secretos con `CIDIA_DEMO_CONTRASENA` y `CIDIA_ADMIN_CONTRASENA` (por ejemplo, copiado del servidor con `ssh ... 'grep ... cidia.env' > secretos.env` en una carpeta temporal). Las contraseñas y los tokens no se imprimen nunca: el token va en el hash (`/app/#token=...`) y la app lo quita de la dirección al leerlo.

`voz.py` y `montaje.py` se pueden lanzar con cualquier Python 3.11+: si les falta algo, se relanzan solos con el entorno `.herramientas/.venv` que crea `preparar.py`.

## 2. Flujo de trabajo

```powershell
$V = "$env:TEMP\cidia-video"                  # carpeta de trabajo (fuera del repositorio)
# 1) Preguntas que «oirá» el micrófono (otra voz distinta del narrador)
python herramientas/video/voz.py frase "¿Qué llave uso para apretar los tornillos de la brida B?" --microfono --salida $V/voces/microfono/llave-brida.wav
# 2) Narración de todas las piezas (solo resintetiza lo que cambia)
python herramientas/video/voz.py narrar herramientas/video/ejemplos/prueba.json --salida $V/voces
# 3) Grabación de las escenas (todas o --solo id1,id2)
node herramientas/video/grabador.mjs herramientas/video/ejemplos/prueba.json --salida $V/grabaciones --voces $V/voces --secretos $V/secretos.env
# 4) Montaje (añade --quemar-subtitulos para dibujarlos en la imagen)
python herramientas/video/montaje.py herramientas/video/ejemplos/prueba.json --grabaciones $V/grabaciones --voces $V/voces --salida $V/prueba.mp4
```

Conviene sintetizar la voz **antes** de grabar: así el grabador espera en directo a la narración (apartado 4.4) y el montaje casi no tiene que congelar la imagen. Revisa siempre `grabaciones/<id>.json` (`fallos`, `excepciones`, `peticiones_fallidas`, `consola`): el grabador termina con código 1 si hay algo, para no montar escenas con errores en pantalla.

## 3. Formato de proyecto y de escena

**Proyecto**: lista ordenada de piezas. Una pieza es una tarjeta o una escena: en un fichero aparte (ruta relativa al proyecto) o en línea (`"escena": { ... }`, como en `docs/video/recorrido.json`). Los campos que se pongan en la pieza sustituyen a los de la escena. `"omitir": true` deja una pieza fuera de la grabación, la voz y el montaje.

```json
{ "titulo": "CidIA · recorrido completo",
  "piezas": [
    { "tipo": "tarjeta", "id": "cap-1", "capitulo": "Captura del conocimiento",
      "etiqueta": "Capítulo 1 · Experta", "titulo": "Capturar lo que sabe Carmen", "subtitulo": "Del vídeo a la instrucción",
      "narracion": [{ "texto": "..." }], "duracion_s": 3.2 },
    { "escena": "escenas/02-captura-carmen.json", "capitulo": "Captura por vídeo" } ] }
```

**Escena**:

```json
{ "id": "inicio-javier", "usuario": "javier", "ruta": "/app/",
  "titulo": "Inicio · Javier Martín, jefe de Producción",
  "bases": "Bases: acompañamiento en el puesto y gestión del conocimiento",
  "microfono": "{voces}/microfono/llave-brida.wav",
  "esperar_inicio": "Tu equipo",
  "acciones": [ { "marca": "portada" }, { "resaltar": ".ini-portada", "nota": "Lo de hoy" }, ... ],
  "duracion_minima_ms": 8000,
  "narracion": [ { "marca": "portada", "texto": "Así empieza el día de Javier..." } ] }
```

| Campo de escena | Para qué |
|---|---|
| `usuario` | Cuenta con la que entra (token por la API). Sin él, se ve la pantalla de acceso. |
| `ruta`, `esperar_inicio` | Página inicial y texto que debe estar antes de empezar a grabar (la carga no se graba). |
| `escala` | 1 por defecto (1920x1080 CSS). Con 1.25 se ve como el zoom del 125 %: misma salida 1920x1080, letra más grande. |
| `microfono` | WAV que «dice» el micrófono falso de Edge (`--use-file-for-fake-audio-capture`, sin bucle). Uno por escena: cada pulsación del micrófono lo reproduce desde el principio. |
| `cursor_inicio`, `cursor: false` | Posición inicial del cursor o escena sin cursor. |
| `titulo`, `bases`, `rotulo_s`, `rotulo_pos` | Rótulo inferior (izquierda o derecha) los primeros `rotulo_s` segundos (7). |
| `narracion` | Fragmentos `{texto, marca?, tras?}`: con `marca` empieza cuando esa acción; sin ella, detrás del anterior (`tras` = silencio previo en s). |
| `umbral_espera_s`, `espera_objetivo_s` | Esperas de más de 2,5 s se aceleran hasta 1,8 s (rotuladas). |
| `recortar`, `cola_voz_s`, `cola_accion_s`, `sincronizar_voz` | Ajustes finos del final y de la sincronía (ver apartado 5). |
| `recortes` | `[[a, b], ...]` en segundos de la grabación: tramos que el montaje quita (por ejemplo, un rato con la pantalla quieta o el inicio de una toma que repite lo que ya se vio). Sin rótulo; el informe los suma en `recortado_s`. |
| `acelerar_tramos` | `[{"acciones": [i, j], "factor": 3, "etiqueta": "Javier corrige la ficha"}]`: ratos sin espera del servidor que se hacen largos (un tecleo de 20 s) y se aceleran con su rótulo, como las esperas («… · acelerado ×3 (21 s reales)»). `i` y `j` son índices (desde 0) de `acciones` en el informe de la grabación: el tramo va del final de la acción `i - 1` al final de la `j`. También `{"desde": s, "hasta": s, ...}` en segundos. |
| `oir_microfono`, `texto_microfono`, `ganancia_microfono` | Lo que «dice» el micrófono falso también se oye en el vídeo desde que empieza a grabar (solo si ese rato no va acelerado), con su subtítulo entre comillas. |
| `conectar`, `contexto: "app"`, `emular` | `{"puerto": 9333, "objetivo": "dsh-app://app/"}`: graba la ventana ya abierta de la app de escritorio. Se emula el tamaño de la escena (1920x1080 a `escala`) y al terminar se quita la emulación, el cursor y el script; la ventana queda como estaba. |
| `cuenta_acceso` | Cuenta cuya contraseña se teclea donde la escena pone `{contrasena}` (en un campo de tipo password: se ven puntos; nunca va al informe). |
| `antes_js`, `ocultar_css` | JavaScript que se evalúa antes de empezar a grabar (por ejemplo, dejar vacía la conversación del copiloto de la app) y selector CSS que se oculta mientras se graba (las conversaciones de pruebas de la lista «Espacios»). No borran nada. |

**Acciones** (todas admiten `"pausa": ms` después; las interactivas esperan a que el elemento exista hasta `max` ms):

| Acción | Qué hace |
|---|---|
| `{"ir": "/app/ruta"}` | Navegación de la SPA sin recargar (pushState). `"recargar": true` para cargar de nuevo. |
| `{"clic": "selector"}`, `{"clicTexto": "texto", "dentro": "selector"}` | Lleva el cursor (trayectoria curva y suave) y pulsa con eventos reales; onda amarilla al pulsar. `"doble": true`. `"punto": [fx, fy]` para apuntar a otra parte del elemento. |
| `{"hover": "selector"}`, `{"hoverTexto": "texto"}` | Solo lleva el cursor (se ven los `:hover`). |
| `{"escribir": ["selector", "texto"], "limpiar": true, "ms_tecla": 52}` | Pulsa el campo y teclea carácter a carácter con ritmo humano (`\n` = Intro). |
| `{"tecla": "Enter"}` | También `Escape`, `Tab`, flechas, `Control+a`... |
| `{"seleccionar": ["selector", "valor o texto"]}` | Cambia un `<select>` nativo (su desplegable no sale en la grabación). |
| `{"subir": "{repo}/datos-demo/video/brida-b-sintetico.mp4", "clicTexto": "Subir vídeo"}` | Pulsa el botón e intercepta el selector de ficheros; sin botón, rellena el `input[type=file]`. |
| `{"esperar": ms}` | Pausa. |
| `{"esperarTexto": "texto", "max": 30000, "acelerar": "rótulo"}` | Espera a que aparezca un texto visible. También `esperarSinTexto` y `esperarSelector`. Los marcadores de posición (`placeholder`) no son texto visible: para ellos, `esperarSelector`. `"acelerar": false` para no acelerarla. |
| `{"mantenerMicro": ["selector", "auto"]}` | Mantener pulsado para hablar (pointerdown ... pointerup) lo que dura el WAV del micrófono (o los ms indicados), con un halo que late. |
| `{"scroll": 400}` / `{"scroll": "selector"}` | Rueda suave donde está el cursor (`"en": "selector"` para moverlo antes) o desplazamiento suave hasta un elemento. |
| `{"resaltar": "selector"}`, `{"resaltarTexto": "texto", "cerca": ".tarjeta"}` | Marco amarillo con halo y el resto oscurecido (`"oscurecer": false` para no oscurecer), `"nota"` opcional y `"ms"` (1800). `cerca` resalta el contenedor más próximo. |
| `{"marca": "nombre"}` | Marca de tiempo para anclar la narración. |
| `{"esperarJs": "expresión", "max": 90000, "acelerar": "rótulo"}` | Espera a que una expresión de la página sea cierta (por ejemplo, que la respuesta del modo planta lleve 1,6 s sin cambiar). |
| `{"esperar": 18100, "acelerar": "rótulo"}`, `{"mantenerMicro": [...], "acelerar": "rótulo"}` | La pausa o el rato con el micrófono pulsado quedan marcados como espera: el montaje los acelera avisándolo (notas de voz largas). |
| `{"esperarVoz": true}` | Espera a que termine la narración colocada hasta ahí (para que la pregunta por voz que se oye después no se pise con el narrador). |
| `{"microfono": true}` | Marca el momento en que el micrófono empieza a «oír» (botones de pulsar para empezar y pulsar para terminar); `mantenerMicro` lo marca solo. |
| `"marco": "iframe"` (en cualquier acción) | El selector o el texto se busca dentro del iframe visible del mismo origen (los paneles de la app de escritorio); el cursor se dibuja en el documento principal. |
| `{"cursor": false}`, `{"eval": "js"}` | Ocultar o mostrar el cursor; evaluar JavaScript (el resultado queda en el informe). |

Trampas vistas al grabar el recorrido: `dentro` busca solo en el **primer** elemento que cumple el selector (para la segunda tarjeta, `:nth-child(2)` o un texto propio de esa tarjeta); un `clicTexto` sobre un texto que está dentro de una `.tarjeta` puede pulsar la tarjeta entera (mejor `clic` con el selector de la fila); los textos con `text-transform: uppercase` salen en mayúsculas en `esperarTexto` (`resaltarTexto` no distingue mayúsculas); y un elemento centrado con desplazamiento suave se lee cuando lleva tres lecturas quieto (antes se pulsaba donde estaba).

Marcadores en rutas: `{repo}` (raíz del repositorio), `{voces}` (`--voces`), `{salida}` y `{escena}` (carpeta del fichero de la escena).

## 4. Grabador

### 4.1 Cómo graba
`Page.startScreencast` entrega un JPEG (calidad 92) cada vez que la página se repinta, con su marca de tiempo; se guardan todos y ffmpeg los une con su duración real (demuxer `concat`) y los pasa a 30 fps constantes. Así los ratos quietos repiten el último fotograma y las animaciones salen a su ritmo (en la prueba, 60 fotogramas por segundo mientras el cursor se mueve). La conversión de color es la correcta (JPEG en BT.601 de rango completo a BT.709 de rango limitado), para que el amarillo #F2C200 salga fiel. La escena se codifica en H.264 a 20 Mb/s (`--bitrate`), casi sin pérdidas para la interfaz.

### 4.2 Cursor, clics y resaltados
El cursor es un elemento inyectado en cada documento (`Page.addScriptToEvaluateOnNewDocument`) que sigue a los eventos de puntero reales que manda el grabador con `Input.dispatchMouseEvent`: por eso también se ven los estados `:hover` de la interfaz. Se mueve con una curva Bézier y aceleración suave (300 a 1050 ms según la distancia), encoge un poco al pulsar y deja una onda amarilla. El resaltado oscurece la página con una máscara SVG y deja un hueco redondeado con borde amarillo y una nota opcional.

### 4.3 Micrófono real con voz sintética
Cada escena abre su propio Edge con `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream --use-file-for-fake-audio-capture=<wav>%noloop`: la app pide el micrófono, el navegador le da el WAV y el servidor lo transcribe con Whisper como si alguien hablara. Probado: la pregunta de `ejemplos/copiloto-voz-lucia.json` llega al copiloto como «que llave uso para apretar los tornillos de la brida B.».

### 4.4 Sincronía con la narración
Si existe `<voces>/<id>.json`, en cada `marca` el grabador espera en directo a que termine el fragmento de narración anterior, con las mismas reglas que el montaje (hueco de 0,35 s, esperas largas que se acelerarán). El informe lo apunta en `esperas_voz` y la grabación se alarga hasta el final de la voz. Si una escena tiene muchas `esperas_voz`, es mejor rellenarlas con acciones (resaltar, pasar el cursor) que dejar la imagen quieta.

### 4.5 Limpieza y app de escritorio
Al terminar cierra Edge con `Browser.close`, `taskkill /T /F` sobre el árbol del proceso que lanzó y, por si algún hijo se queda colgado, los procesos cuya línea de órdenes lleva su perfil temporal (solo esos); después borra el perfil. Con `--conectar 9333 [--objetivo /app/]` o con `conectar` en la escena graba una ventana ya abierta con `--remote-debugging-port` (la app CidIA: `%LOCALAPPDATA%\Programs\CidIA\CidIA.exe --remote-debugging-port=9333`) sin lanzarla ni cerrarla. Así se grabaron 02a y 02b: el panel de cada sección es un iframe del mismo origen y las acciones llevan `"marco": "iframe"`. El micrófono no funciona dentro de los paneles de la app (límite conocido, ver `app/README.md`): las escenas de voz se graban en el navegador, que es la misma interfaz.

## 5. Montaje

Para cada **escena** rehace la línea de tiempo:

* **Esperas largas** (`esperarTexto`, `esperarSelector`... de más de 2,5 s): se aceleran hasta 1,8 s y se rotula arriba, sin engañar, por ejemplo «El copiloto prepara la respuesta en el servidor · acelerado ×9 (15 s reales)».
* **Voz anclada**: cada fragmento con `marca` empieza cuando la acción de esa marca. Si la voz anterior aún no ha terminado, se congela la imagen en esa marca (la voz nunca se adelanta ni se corta).
* **Final**: si la voz es más larga se congela el último fotograma; si sobra vídeo, se recorta, pero nunca antes del final de la última acción (o de la marca `fin`).
* **Rótulo inferior** con `titulo` y «Bases: ...» en Fira Sans sobre panel #1F2328 con filete amarillo, con fundido de entrada y salida.

Las **tarjetas** de capítulo llevan la marca (cuadrado amarillo con la C), etiqueta en amarillo, título y subtítulo que entran con un fundido y un desplazamiento corto, y el arco de la marca muy tenue moviéndose despacio. Después, todo se une con **fundidos encadenados** de 0,5 s (`xfade`). La **narración** se monta como una sola pista y se normaliza a -16 LUFS con `loudnorm` en dos pasadas (pico real de -1,5 dBTP). Se codifica en H.264 (libopenh264, perfil High, 8 Mb/s) + AAC estéreo de 192 kb/s, 1920x1080 a 30 fps.

Con `--musica` añade un colchón de acordes suaves que se **sintetiza en el propio montaje** (senos con armónicos suaves, La m9 · Fa maj7 · Do maj7 · Sol 6, 7 s por acorde, nada por encima de 1,2 kHz): no usa ninguna grabación ni muestra de terceros, así que no tiene licencia que cumplir. Va 17 dB por debajo de la voz (`--musica-db`) y se agacha otros 7 dB mientras habla el narrador. Las piezas pueden llevar `recortes`, `acelerar_tramos` y `oir_microfono` (apartado 3). Si la carpeta de voces se mueve, los WAV se buscan junto a su índice. Un capítulo se apunta solo cuando cambia (varias piezas seguidas comparten capítulo), y los subtítulos no terminan un trozo ni una línea en «de», «la», «para»...

Salidas: el MP4 (con capítulos, pista de subtítulos `mov_text` en español y metadatos), `<salida>.srt`, `<salida>.capitulos.txt` (formato de YouTube: `0:06 El inicio del jefe de equipo`) e `<salida>.informe.json` (duración de cada pieza, segundos congelados, aceleraciones, problemas de grabación). Con `--quemar-subtitulos` se dibujan con libass (Fira Sans Medium 44, caja oscura) y el rótulo inferior sube para no pisarlos. Los subtítulos salen del texto escrito, no del dicho, en trozos de 90 caracteres como mucho, partidos detrás de una coma cuando se puede y en dos líneas equilibradas. Un trozo muy corto («Esto es CidIA:», «Todo bien:») se junta con el siguiente para que no salga menos de un segundo; las líneas no se parten delante de un número («nivel 3», «prensa 3»), y los subtítulos van en orden de aparición y sin solaparse (la voz del micrófono se intercala con la narración).

Detalle técnico: OpenH264 deja a veces un rastro tenue de un rótulo que se acaba de ir en las zonas oscuras y quietas (la barra lateral) hasta el siguiente fotograma clave. El montaje fuerza un fotograma clave justo después de cada rótulo y al final de cada fundido, y el rastro desaparece.

## 6. La voz: comparación y elección

`python herramientas/video/voz.py comparar --salida <carpeta> [--asr --secretos <fichero>]` sintetiza la misma narración y la misma pregunta con cada candidata, mide la salida y, con `--asr`, la transcribe con el servidor CidIA (Whisper base) para medir lo que se entiende. Resultado en este PC (la narración contiene «CidIA», «llave dinamométrica», «25 N·m», «1/2"»):

| Voz | Licencia del modelo | Frecuencia nativa | Banda útil (99,5 % de energía) | Variación de entonación | WER de la pregunta | WER de la narración* |
|---|---|---|---|---|---|---|
| **Kokoro em_alex** (elegida, narrador) | Apache-2.0 | 24 kHz | **9,2 kHz** | **3,36 st** | **0,00** | 0,19 |
| **Kokoro ef_dora** (elegida, micrófono) | Apache-2.0 | 24 kHz | **9,6 kHz** | 2,91 st | **0,00** | 0,23 |
| Piper carlfm x_low | MIT + datos de dominio público | 16 kHz | 3,6 a 4,2 kHz | 1,9 a 2,0 st | 0,57 | 0,28 |
| Piper davefx medium | Datos CC0, pero afinada desde lessac (licencia de investigación) | 22 kHz | 5,7 a 5,9 kHz | 4,3 a 4,5 st | 0,29 | 0,64 |
| Windows Pablo (OneCore) | Licencia de Windows | 16 kHz | 6,6 kHz | 2,44 st | 0,00 | 0,17 |
| Windows Laura (OneCore) | Licencia de Windows | 16 kHz | 4,6 kHz | 2,04 st | 0,00 | 0,57 |
| Windows Helena (OneCore / SAPI) | Licencia de Windows | 16 / 22 kHz | 2,3 kHz | 2,3 st | 0,00 | 0,21 / 0,60 |

\* La transcripción de frases largas es irregular (Whisper base en CPU ARM corta a veces tras la primera frase): sirve como orientación, no como medida fina. Piper cambia un poco de una ejecución a otra (muestrea ruido al sintetizar), de ahí los intervalos.

**Por qué Kokoro.** Es la única voz neuronal moderna (StyleTTS 2) con licencia claramente comercial que habla castellano de España: fonemas con distinción (`conocimiento` → kˌonoθimjˈɛnto, `cruz` → kɾˈuθ, `llave` → ʎˈaβe, `jubile` → xuβˈile). Suena más clara (9,2 kHz de banda útil frente a 2,3 a 6,6 kHz de las voces de Windows y unos 4 kHz de Piper carlfm), menos monótona (más variación de entonación que cualquier voz de Windows) y se entiende igual de bien que la mejor (pregunta sin errores). En la CPU sintetiza unas tres veces más rápido que el tiempo real. Piper solo tiene una voz es_ES con licencia limpia (carlfm x_low, de calidad muy baja: se entiende peor y suena apagada). La mejor de Piper (davefx) y sharvard están afinadas desde lessac, cuyos datos tienen licencia de investigación, y las MLS desde ryan (CC BY-NC-SA): no sirven para un vídeo de uso comercial. Las voces de Windows (Helena, Laura, Pablo) suenan más robóticas, a 16 kHz, y su licencia no concede expresamente el uso del audio generado en vídeos comerciales.

**Ajustes.** Narrador `kokoro:em_alex` a velocidad 0,95 (unas 158 palabras por minuto, ritmo de explicación); preguntas al micrófono `kokoro:ef_dora` a 1,0, con 0,45 s de silencio delante y 1 s detrás. Pausas de 0,32 s entre frases, la mitad tras dos puntos o punto y coma, y `[pausa 600]` dentro del texto para una pausa a medida. Todo se guarda a 48 kHz mono, sin silencios en los extremos. `pronunciacion.json` adapta lo que se dice sin tocar los subtítulos («IT-023» → «i te cero 2 3», «25 N·m» → «25 newton metro», «CidIA» → «Cidía»). Para escuchar una frase: `voz.py frase "texto" --salida prueba.wav`.

## 7. Consejos para que salga fluido

* **Rellena la narración con acciones.** El informe del montaje dice cuántos segundos se ha congelado cada escena. Más de 2 o 3 s se notan: añade un `resaltar` o un `hover` en esa marca o acorta el texto.
* **Una idea por fragmento, anclada a su acción** (`marca` justo antes del clic que ilustra).
* **Datos limpios.** Las preguntas que el copiloto no sabe responder se apuntan como lagunas y aparecen después en Inicio y en Lagunas de los jefes. Antes de la grabación final, vuelve a sembrar los datos (`python -m cidia.semilla --forzar` en el servidor de demostración) y graba en el orden del guion.
* **Modelos diminutos en el servidor de pruebas.** Las respuestas cambian de una vez a otra: comprueba en el informe y en las capturas que la respuesta grabada es la que cuenta la narración y, si no, repite la escena (`--solo id`).
* **Un WAV de micrófono por escena.** Si una escena necesita dos preguntas por voz, pártela en dos.

## 8. Licencias

Ninguna de estas piezas se distribuye con CidIA: son herramientas para producir el vídeo. Todas permiten el uso comercial del resultado.

| Componente | Licencia | Uso |
|---|---|---|
| Node.js 22 | MIT | Ejecuta el grabador. |
| Microsoft Edge (o Chrome / Chromium) | Licencia de Microsoft (gratuita) / BSD | Solo dibuja la interfaz de CidIA, que es nuestra; no se redistribuye. |
| FFmpeg, compilación LGPL de BtbN (`servidor/gateway/.herramientas/`) | LGPL-3.0 | Codificación, filtros, fundidos, `loudnorm`, subtítulos (libass, ISC; FreeType, FTL; HarfBuzz, MIT; FriBidi, LGPL). |
| OpenH264 (dentro de esa compilación) | BSD-2-Clause | Codificador H.264. Para vídeo gratuito en Internet, la licencia de patentes AVC de Via LA no cobra por el contenido. |
| Kokoro-82M (hexgrad), pesos y voces em_alex y ef_dora | Apache-2.0 | La voz del vídeo. Entrenado solo con audio de licencia permisiva o sin derechos, según su ficha. |
| kokoro-onnx 0.6.1 y su conversión del modelo | MIT | Ejecuta Kokoro en ONNX. |
| ONNX Runtime | MIT | Inferencia en CPU. |
| phonemizer 3.4 y espeak-ng (en espeakng-loader 0.2.4, MIT) | GPL-3.0 | Paso de texto a fonemas. Se usan como programas; el audio generado no queda sujeto a la GPL. |
| NumPy, soundfile (libsndfile, LGPL-2.1) | BSD-3-Clause | Audio. |
| Pillow | MIT-CMU (HPND) | Tarjetas, rótulos y paneles. |
| Fondo musical (`--musica`) | Propio: se genera en `montaje.py` | Sin muestras ni grabaciones de terceros. |
| Kokoro-82M, voz em_santa | Apache-2.0 | La nota de voz de Pedro (10a), distinta del narrador. |
| Fira Sans (google/fonts) | SIL Open Font License 1.1 | Tipografía de tarjetas, rótulos y subtítulos (la misma que la interfaz). |
| Piper 2023.11.14-2 (rhasspy/piper) y voz es_ES-carlfm-x_low | MIT (incluye espeak-ng, GPL-3.0) / dominio público | Solo en la comparación de voces. |
| Voz es_ES-davefx-medium de Piper | Datos CC0, afinada desde lessac (licencia de investigación) | Solo en la comparación; **no** usar en el vídeo. |
| Voces de Windows (Helena, Laura, Pablo) | Licencia de Windows | Solo en la comparación. |

## 9. Prueba de punta a punta

`ejemplos/prueba.json` (portada, Inicio de Javier, tarjeta de capítulo y copiloto por voz de Lucía) se ha grabado, narrado y montado contra el servidor de pruebas:

* Inicio de Javier: 24 s grabados sin errores de consola ni peticiones fallidas; el grabador esperó 6,5 s en la marca `equipo` para la voz y el montaje no congeló nada.
* Copiloto por voz de Lucía: la pregunta sintética (ef_dora) por el micrófono falso se transcribió bien; la espera de 15 s de la respuesta se aceleró ×9 con su rótulo; esta toma se grabó antes de la sincronía con la voz y el montaje congeló 9,3 s (por eso conviene sintetizar la voz antes de grabar).
* Vídeo de 57 s, 1920x1080 a 30 fps, H.264 + AAC, -16,2 LUFS, 4 capítulos, 13 subtítulos (también quemados en una segunda versión). El montaje tarda unos 25 s.
