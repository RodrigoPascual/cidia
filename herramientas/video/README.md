# Herramientas de vídeo de CidIA

Tres piezas para hacer el vídeo de demostración de CidIA sin grabar la pantalla a mano: un **grabador** que maneja la interfaz con un cursor visible y graba cada escena, una **voz** en castellano sintetizada en local y un **montaje** que une escenas, narración, tarjetas de capítulo, rótulos y subtítulos. Todo funciona en este PC (Windows) contra el servidor de pruebas, con datos sintéticos de «Metalúrgica Arlanza, S. L.» (ver `datos-demo/README.md`).

| Fichero | Qué es |
|---|---|
| `grabador.mjs` | Node 22 + CDP sobre Edge sin cabeza a 1920x1080: ejecuta una escena (JSON) y la graba a 30 fps. |
| `voz.py` | Narración y preguntas al micrófono, en local. Perfil `v1`: Kokoro-82M (Apache-2.0); perfil `v2`: narrador Supertonic 3 M1 y micrófono Kokoro ef_dora (apartado 6.1). Compara voces (`comparar`). |
| `voz_voces.json` | Voces y perfiles de `voz.py` para los motores que corren en su propio entorno. |
| `voz_motores.py` | Un proceso por motor de voz, con el Python de su entorno en `.herramientas/tts/` (hoy, Supertonic). |
| `voz_banco.py`, `voz_banco_v2.json`, `voz_candidatas_v2.json` | Banco de pruebas de voces: mismos textos para todas, medidos con Whisper, UTMOS y un reconocedor de fonemas. |
| `voz_revisar.py` | Revisa con Whisper la narración sintetizada y rehace lo que se entiende mal o va rápido; prueba los WAV del micrófono como los transcribe el servidor. |
| `voz_windows.ps1` | Síntesis con las voces de Windows, solo para la comparación. |
| `pronunciacion.json` | Cómo se dicen siglas y códigos (CidIA, IT-023, ILUO, xAPI, N·m...). Solo afecta a la voz. |
| `montaje.py` | Monta el vídeo final de la v1 (MP4 H.264 + AAC, `.srt`, capítulos e informe). Con `--limpio` (v2) saca por escena el vídeo limpio con su línea de tiempo y su mapa de tiempos (apartado 10). |
| `hyperframes.py` | Montaje v2 con HyperFrames: línea de tiempo global, cámara, subtítulos, proyecto HyperFrames por bloque, render, mezcla de audio y vídeo final (apartado 10). |
| `hyperframes/` | El diseño v2: `cidia-v2.css` (estilo), `cidia-v2.js` (el «director» que pinta cada fotograma en función del tiempo) e `iconos.json` (iconos de Lucide, ISC). |
| `musica.py` | Música y efectos de la v2, sintetizados aquí (sin muestras de terceros). |
| `comun.py` | Rutas, ffmpeg, fuentes y carga de proyectos (lo usan `voz.py` y `montaje.py`). |
| `preparar.py` | Descarga y comprueba (sha256) los modelos, Piper y Fira Sans en `.herramientas/` (ignorada por git). |
| `guion_md.mjs` | Genera `docs/video/guion.md` (el guion legible) a partir del proyecto y, si se le da, del informe del montaje. |
| `ejemplos/` | Proyecto de prueba (`prueba.json`) con dos escenas reales: `inicio-javier.json` y `copiloto-voz-lucia.json`. |

El vídeo de la candidatura es `docs/video/recorrido.json` (60 piezas: tarjetas y 39 escenas en línea, una fuera del montaje) y su resumen para el jurado `docs/video/resumen.json` (13 piezas con las mismas grabaciones y voces). El resultado, cómo se grabó y qué es real o se ha acelerado: `04_VIDEO/LEEME.md`, fuera del repositorio. La **v2** (por funcionalidades, con el diseño nuevo) es `docs/video/v2/recorrido.json` y `resumen.json`, montada con `hyperframes.py` (apartado 10); resultado y LEEME en `04_VIDEO/v2/final/`.

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
| `cada_n_fotogramas` | 1 por defecto. Con 2, Edge entrega un repintado de cada dos (unos 30 por segundo, lo mismo que el vídeo). Solo para escenas con una animación continua durante minutos (la captura de 03a): con todos los repintados la captura se va retrasando (1 s a los 20 s en una prueba) y los últimos segundos de la escena se perdían; con 2 el retraso no crece (0 s a los 60 s). **No usarlo en escenas con ratos quietos**: con 2, tras un rato sin repintar, Edge entrega el fotograma siguiente con la marca de tiempo del anterior y el vídeo se adelanta al informe (en una prueba, un resaltado salía 1,4 s antes que su acción). En las demás basta con un `colchon_final_ms` de 2500 para que lleguen los últimos fotogramas. |
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

**Registro del ratón para el montaje** (zoom a la zona de cada acción). Todo en píxeles del vídeo (1920x1080: coordenadas CSS × `escala`, que el informe apunta en `coordenadas`) y en ms desde el primer fotograma, como las marcas:

* `raton`: cada evento que manda el grabador, `{t, x, y, ev}` con `ev` = `inicio`, `mover` (como mucho uno cada 30 ms), `pulsar`, `soltar` o `rueda`.
* En cada acción de `acciones`: `cursor_ini` y `cursor_fin` (`[x, y]` al empezar y al terminar; en un clic, `cursor_fin` es el punto pulsado), `elemento` (`{x, y, w, h}`, el rectángulo del elemento ya centrado en la vista: el pulsado, el campo donde se teclea o la zona resaltada) y `rueda` (píxeles CSS) en los desplazamientos con la rueda.

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

### 6.1 La voz de la v2 (11 de octubre de 2026)

Para la v2 se repitió la comparación con tres fragmentos del guion v2 y modelos más nuevos, solo con voces de catálogo y licencia comercial. Detalle, muestras y licencias: `04_VIDEO/v2/muestras-voz/indice.md` (fuera del repositorio). Resumen:

* **Narrador: Supertonic 3, voz M1** (pesos OpenRAIL-M, SDK MIT; `supertonic:M1` en `voz_voces.json`). Frente a Kokoro em_alex, en toda la narración: UTMOS 3,82 frente a 3,36, entonación 3,77 frente a 3,26 semitonos y «CidIA» entendido en 8 de 9 fragmentos frente a 3 de 9. OpenRAIL-M obliga a decir que la voz es sintética (una línea en los créditos).
* **Micrófono: Kokoro ef_dora a 0,85.** Las voces de Supertonic no las transcribe bien el servidor de pruebas (Whisper base oye «ya ve» por «llave») ni con su entonación sale la pregunta con signos.
* Uso: `voz.py narrar <proyecto> --perfil v2 --semilla 1234 --salida <voces>` y después `voz_revisar.py narracion <voces> --rehacer 4` con el Python de `.herramientas/tts/medida` (rehace con otra semilla lo que Whisper entiende mal y más despacio lo que pasa de 6,3 sílabas por segundo; cada índice guarda su `semilla` y su `velocidad`). `--incluir-omitidas` narra también las tomas nuevas aún sin grabar.

**Ajustes de la v1.** Narrador `kokoro:em_alex` a velocidad 0,95 (unas 158 palabras por minuto, ritmo de explicación); preguntas al micrófono `kokoro:ef_dora` a 1,0, con 0,45 s de silencio delante y 1 s detrás. Pausas de 0,32 s entre frases, la mitad tras dos puntos o punto y coma, y `[pausa 600]` dentro del texto para una pausa a medida. Todo se guarda a 48 kHz mono, sin silencios en los extremos. `pronunciacion.json` adapta lo que se dice sin tocar los subtítulos («IT-023» → «i te cero 2 3», «25 N·m» → «25 newton metro», «CidIA» → «Cidía»). Para escuchar una frase: `voz.py frase "texto" --salida prueba.wav`.

## 7. Consejos para que salga fluido

* **Rellena la narración con acciones.** El informe del montaje dice cuántos segundos se ha congelado cada escena. Más de 2 o 3 s se notan: añade un `resaltar` o un `hover` en esa marca o acorta el texto.
* **Una idea por fragmento, anclada a su acción** (`marca` justo antes del clic que ilustra).
* **Datos limpios.** Las preguntas que el copiloto no sabe responder se apuntan como lagunas y aparecen después en Inicio y en Lagunas de los jefes. Antes de la grabación final, vuelve a sembrar los datos (`python -m cidia.semilla --forzar` en el servidor de demostración) y graba en el orden del guion.
* **Modelos diminutos en el servidor de pruebas.** Las respuestas cambian de una vez a otra: comprueba en el informe y en las capturas que la respuesta grabada es la que cuenta la narración y, si no, repite la escena (`--solo id`).
* **Un WAV de micrófono por escena.** Si una escena necesita dos preguntas por voz, pártela en dos.
* **Lo que pidió la revisión del sector para la próxima versión:** narración con voces humanas del equipo en lugar de voz sintética, quitar el cambio de contraseña (es común a todas las aplicaciones) y un mapa del proceso en pantalla al empezar cada bloque (ya está en el README).

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
| Supertonic 3 (Supertone), pesos y voz de catálogo M1 | BigScience OpenRAIL-M (uso comercial permitido con las restricciones de uso de su anexo A: indicar que el contenido es sintético, no suplantar a nadie) | El narrador de la v2. |
| SDK `supertonic` (supertone-inc/supertonic) | MIT | Ejecuta Supertonic con ONNX Runtime en CPU. |
| faster-whisper y modelos Systran medium y base; UTMOS22 de SpeechMOS (tarepan) | MIT | Solo para medir y revisar la voz (`voz_banco.py`, `voz_revisar.py`). |
| Fira Sans (google/fonts) | SIL Open Font License 1.1 | Tipografía de tarjetas, rótulos y subtítulos (la misma que la interfaz). |
| Piper 2023.11.14-2 (rhasspy/piper) y voz es_ES-carlfm-x_low | MIT (incluye espeak-ng, GPL-3.0) / dominio público | Solo en la comparación de voces. |
| Voz es_ES-davefx-medium de Piper | Datos CC0, afinada desde lessac (licencia de investigación) | Solo en la comparación; **no** usar en el vídeo. |
| Voces de Windows (Helena, Laura, Pablo) | Licencia de Windows | Solo en la comparación. |
| HyperFrames 0.8.145 (heygen-com/hyperframes: CLI, motor de render y linter) | Apache-2.0 | Montaje v2: dibuja cada fotograma con Chrome sin cabeza. En `.herramientas/hyperframes/` (versión fija; copia de la instalación oficial de npm). Sin telemetría ni actualizaciones (variables de entorno en `hyperframes.py`); nunca `cloud`, `lambda`, `publish` ni `auth`. |
| GSAP 3.15.0 | Licencia estándar «sin coste» de GSAP (Webflow): uso comercial permitido | Solo como reloj de la composición (una línea de tiempo en pausa que mueve HyperFrames). Copia local, sin CDN. |
| Chrome for Testing, chrome-headless-shell 152 | BSD (Chromium) y licencias de sus componentes | Lo descarga HyperFrames de la fuente oficial de Google (`%USERPROFILE%\.cache\hyperframes`). Solo dibuja; no se distribuye. |
| Archivo (Omnibus-Type) y JetBrains Mono 2.304 | SIL Open Font License 1.1 | Titulares y datos del vídeo v2 (`.herramientas/fuentes/v2/`, con su `OFL-*.txt`). |
| Iconos de Lucide (lucide-react 0.468.0) | ISC | Los del mapa y las tarjetas (`hyperframes/iconos.json`, con su aviso de copyright). |
| Música y efectos de la v2 (`musica.py`) | Propios | Síntesis aditiva con NumPy; ninguna muestra ni grabación de terceros. |

## 9. Prueba de punta a punta

`ejemplos/prueba.json` (portada, Inicio de Javier, tarjeta de capítulo y copiloto por voz de Lucía) se ha grabado, narrado y montado contra el servidor de pruebas:

* Inicio de Javier: 24 s grabados sin errores de consola ni peticiones fallidas; el grabador esperó 6,5 s en la marca `equipo` para la voz y el montaje no congeló nada.
* Copiloto por voz de Lucía: la pregunta sintética (ef_dora) por el micrófono falso se transcribió bien; la espera de 15 s de la respuesta se aceleró ×9 con su rótulo; esta toma se grabó antes de la sincronía con la voz y el montaje congeló 9,3 s (por eso conviene sintetizar la voz antes de grabar).
* Vídeo de 57 s, 1920x1080 a 30 fps, H.264 + AAC, -16,2 LUFS, 4 capítulos, 13 subtítulos (también quemados en una segunda versión). El montaje tarda unos 25 s.

## 10. Montaje v2 con HyperFrames

El vídeo v2 (`docs/video/v2/`, resultado en `04_VIDEO/v2/final/`) usa el mismo grabador y la misma voz, pero el diseño lo dibuja **HyperFrames** (HTML + CSS que Chrome sin cabeza captura fotograma a fotograma) encima de la línea de tiempo de `montaje.py`. Las reglas visuales (paleta, tipografías, curvas, duraciones, cámara, transiciones, subtítulos, sonido) son las de `04_VIDEO/v2/notas/guia-estilo.md`; la elección de HyperFrames, en `04_VIDEO/v2/notas/repos.md`.

```powershell
$M = (Resolve-Path "..\04_VIDEO\material-v3").Path; $V2 = (Resolve-Path "..\04_VIDEO\v2").Path
python herramientas\video\hyperframes.py todo docs\video\v2\recorrido.json --grabaciones $M\grabaciones --voces $V2\voces-final --trabajo $V2\trabajo\recorrido --salida $V2\final\CidIA-recorrido.mp4
```

| Paso (`hyperframes.py <paso>`) | Qué hace | Deja en `--trabajo` |
|---|---|---|
| `escenas` | Llama a `montaje.py --limpio`: por escena, el vídeo con su línea de tiempo y sin rótulos, y su **mapa de tiempos**. | `escenas/<id>.mp4`, `escenas/<id>.mapa.json` |
| `linea` | Línea de tiempo global: duración de cada tarjeta (su voz, su animación y el tiempo de lectura), inicio del panel de resultado y final alargado, transición según el corte, bloques de render, cámara, subtítulos, efectos, secciones de música y capítulos. | `linea.json`, `subtitulos.srt` |
| `componer` | Un proyecto de HyperFrames por bloque (`hf/<bloque>/index.html`) con los datos del bloque, `hyperframes/cidia-v2.css` y `cidia-v2.js`, las fuentes OFL, GSAP y los medios enlazados (enlaces duros: no ocupan más disco). | `hf/`, `camaras.json` |
| `render` | `hyperframes render --gpu --quality high` de cada bloque, sin telemetría ni actualizaciones; borra la caché de fotogramas de HyperFrames en `%TEMP%` al terminar cada bloque y para si quedan menos de 4 GB libres. **No lances dos renders a la vez**: el borrado de la caché de uno estropearía el otro. | `bloques/<bloque>.mp4`, `tiempos.json`, `render.log` |
| `audio` | Narración, micrófono, música (`musica.py`) agachada bajo la voz y efectos. | `mezcla.wav` |
| `final` | Une los bloques recortando cada uno a sus fotogramas exactos (el render deja a veces uno de más y, sumados, la imagen se retrasaba respecto al sonido), loudnorm a -16 LUFS en dos pasadas y **NVENC** (H.264 High, VBR con calidad constante 19, tope de 20 Mb/s, AQ espacial y temporal; sale a unos 6 Mb/s de media porque casi todo es interfaz quieta, y los degradados quedan como en los bloques renderizados) + AAC, con capítulos y pista de subtítulos. Con OpenH264 la tasa pedida no se respetaba (salía a unos 4 Mb/s y los degradados hacían bandas). | el MP4, `.srt`, `.capitulos.txt` e `.informe.json` junto a `--salida` |

**`montaje.py --limpio`** conserva todo lo de la v1 (esperas aceleradas siempre rotuladas, voz anclada a las marcas, congelados y recortes) y añade:

* **Rampas de velocidad**: cada aceleración entra y sale en 0,3 s (la velocidad sube linealmente de 1 al factor); la misma función se usa en el filtro `setpts` de ffmpeg y para pasar los tiempos de la grabación a los del montaje.
* **Ratos quietos y mudos fuera**: busca en la toma los ratos en que no cambia nada, ni el cursor (fotogramas a 10 por segundo, 240 x 135), y quita los de más de 1,4 s que no caen en una aceleración ni con voz sonando, dejando 0,4 s a cada lado. `--sin-recortes-auto` lo desactiva.
* **Mapa de tiempos** (`<id>.mapa.json`): tramos, recortes y congelados; marcas y acciones con su caja (`elemento`) y su cursor ya en segundos del montaje; eventos del ratón visibles; esperas con factor, rampa y segundos reales; fragmentos de voz y micrófono; inicio del resultado.
* Campos de escena nuevos: `grabacion` (otra toma), `voz_de` (`{id, fragmentos}`: la voz de otra pieza) y `hasta_accion` (usar solo el principio de una toma). El resumen los usa para el modo planta.

**El director (`hyperframes/cidia-v2.js`)** pinta cada fotograma como función pura del tiempo: HyperFrames mueve una línea de tiempo de GSAP en pausa que solo hace de reloj, así que el resultado no depende de en qué orden se capturen los fotogramas (render en paralelo). Piezas: apertura, portada, problema, reparto, mapa, tarjeta de funcionalidad, escena (marco, cámara, empuje, reloj de las esperas, llamadas y panel de resultado con comparación o niveles ILUO), criterios, implantación y final. Capas globales: fondo, cabecera, subtítulos, raíl de bloques, pie «Datos sintéticos · servidor de pruebas», cortinilla y negro. Para mirar un instante sin renderizar: servir `hf/` con `python -m http.server` y abrir `<bloque>/index.html#t=12.5`.

**Cámara** (`camara()` en `hyperframes.py`): con las cajas y el cursor que el grabador apunta en cada acción; se acerca a los resaltados (su caja más un 12 %), a los clics (caja de 900 x 506 alrededor del punto, zoom 1,4 como mucho), a los campos donde se teclea y al micrófono; arranca 150 ms antes de la acción con la curva de cámara (0,6 a 0,9 s), se queda al menos 1,2 s, no se mueve si el siguiente objetivo cae en el 60 % central, y vuelve a reposo en las esperas, la navegación, los clics que llevan a otra pantalla, antes de un empuje y en el resultado. Zoom máximo 1,55.

**Datos de diseño en el guion** (campo `v2` de cada escena): `comparar` (`antes` y `despues`: acción, momento, caja del recorte y etiqueta), `iluo` (`persona`, `de`, `a`), `llamadas` (`accion`, `texto`, opcionales `desfase`, `min` y `dur`: entra `desfase` s después de la acción y dura lo que la acción, al menos 1,6 s o `min` y como mucho 2,8 s o `dur`), `tapas` (texto neutro encima de algo que no debe verse, con sus `posiciones` por acción), `congelar` (`accion`, `momento`, `desde`, `hasta`: un rato que se ve mal, como una página cargando, se sustituye por el fotograma anterior) `borrar` (`caja` y `copiar_de`: un dato que contradice el orden del guion se tapa con un trozo vacío de la misma página, que sigue el velo de los resaltados) y `parches` (`accion`, `caja`, `fuente`, `desde` y `hasta` como `[momento, desfase]` de esa acción, `velo`, `rampa` y `difuminar`: una nota que el grabador dibujó encima de lo que demuestra la escena se cubre con ese trozo de un fotograma anterior sin nota, con el mismo velo del resaltado (rgba(18,21,25,.36)) entrando en `rampa` s y los bordes difuminados; se usa en 02e para que se vea el botón «Cambiar contraseña» desactivado).

**Vídeo procesado de cada escena** (`procesar_escena`, `escenas/<id>.final.mp4`, se rehace si cambia su firma): el limpio con los congelados, los borrados, los parches, las tapas y, si hace falta, el último fotograma alargado. Las **tapas** son fijas y del mismo tamaño siempre: una etiqueta antes del desplazamiento de la página y otra después; mientras la página se mueve (medido fotograma a fotograma) no hay etiqueta y toda la franja de las columnas tapadas va pixelada en el propio vídeo, y debajo de cada etiqueta el vídeo también va pixelado. Así ninguna vista previa, miniatura o fotograma sacado de esa escena enseña lo tapado (los nombres de los modelos del servidor de pruebas en Modelos y Sistema). Todo con filtros LGPL (`gblur`, no `boxblur`, que es GPL).

**Reglas de tiempo de la revisión del 11/10**: la tarjeta de funcionalidad dura al menos 6,5 s (7,5 en el resumen) y lo bastante para que el «para qué sirve» esté en pantalla palabras / 3 + 1 s (todo el texto entra hacia 1,1 s y sale 0,75 s antes del final); el **panel de resultado** no entra antes del final de la última acción visible (clic, resaltado, tecleo, micrófono, desplazamiento) + 0,3 s y se queda al menos 2,8 s: si no cabe, la escena se alarga con su último fotograma en lugar de encoger el marco durante la acción; los subtítulos se quedan hasta 17 caracteres por segundo si el hueco hasta el siguiente lo permite; las preguntas al micrófono fijan sus cortes de línea desde la primera palabra. En el resumen, las pruebas de los criterios pueden salir de escenas del recorrido (`escena_externa`).

**Sonido**: la música (`musica.py`) es propia: 96 pulsaciones por minuto en re dórico, con colchón con armónicos (que se abren y cierran despacio), pulso de corcheas, piano con ataque y bajo; en los bloques, un charles o un shaker muy suaves (las dos variantes se distinguen por el patrón del pulso, el registro del piano y la percusión); bombo y caja en apertura, bases y cierre; una sección que crece en las bases y una resolución final en re; paso alto a 80 Hz. Cada sección empieza en tiempo fuerte en su cambio de bloque. Va unos 12 dB bajo la voz y se agacha 4 dB más mientras habla el narrador, con retención de 300 ms y suelta de 1 s para que no bombee en los huecos entre frases (4 más bajo el micrófono). Efectos: clic en los clics visibles (uno cada 0,9 s como mucho), soplo en cortinillas y empujes, confirmación en los logros, pitido del micrófono y golpe de la portada.

**Voz**: `pronunciacion.json` tiene reglas solo para Supertonic (`por_motor`): «CidIA» se escribe «Zidía» (es la grafía con la que Whisper large-v3 oye una sola palabra en casi todas las frases), «nivel L» y «en L» como «ele» y «M10» como «eme 10». Un fragmento de narración puede llevar su propia `semilla` (la toma elegida a oído; entra en la firma y solo se rehace ese fragmento).
