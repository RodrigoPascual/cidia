# Guion del vídeo de CidIA

Recorrido completo por la aplicación, pestaña a pestaña, con cada rol y con pruebas reales sobre los datos sintéticos de «Metalúrgica Arlanza, S. L.». Duración: **15:20** (1902 palabras de narración, voz kokoro:em_alex). Versión 2, 2026-10-10. Hay también un resumen para el jurado (`resumen.json`, unos 3,7 minutos).

Este documento se genera con `herramientas/video/guion_md.mjs` a partir de `docs/video/recorrido.json`, que es lo que leen las herramientas de `herramientas/video/` (grabador, voz y montaje). Cada escena dice qué cuenta y a qué punto de las bases del V DESAFÍO industrial responde; las acciones son clics y textos que existen en la interfaz desplegada, grabada con cada rol el 10 de octubre de 2026 en el servidor de pruebas (`http://127.0.0.1:18700 (servidor de pruebas Oracle por túnel SSH)`). Cómo se hizo y cómo repetirlo: `04_VIDEO/LEEME.md` y `herramientas/video/README.md`.

## Resumen por capítulos

| Capítulo | Empieza | Duración | Quién | Qué se ve | Bases |
|---|---|---|---|---|---|
| 1 · El problema | 0:00 | 1:08 | admin | Metalúrgica Arlanza, S. L. | indicadores de desempeño; gestión centralizada del conocimiento |
| 2 · La app y el acceso | 1:06 | 1:12 | invitado, lucia, javier, admin | App de escritorio CidIA; Lucía Herrero inicia sesión; Javier Martín; La administración | implantación sencilla; proteger el conocimiento experto; adaptado al perfil; integración (módulo de identidad) |
| 3 · Capturar el saber del experto | 2:16 | 1:42 | carmen | Carmen Díaz, experta; El borrador: la IA propone, la experta decide; Nota de voz: lo que no se ve en un vídeo; Entrevista guiada | captura del conocimiento de operarios expertos; generación automática de instrucciones; digitalización de procedimientos operativos; trazabilidad hasta versión y autor |
| 4 · Documentos y búsqueda | 3:55 | 1:19 | javier, ana, luis | Documentos de Producción; Probar búsqueda; Luis García; La misma pregunta, con el nivel de Ana | bases de conocimiento inteligentes; gestión centralizada del conocimiento; proteger el conocimiento experto; necesidades formativas |
| 5 · El copiloto | 5:11 | 1:22 | marta, javier | Marta Sanz; Modo socrático: un tutor, no una chuleta; Cuando no lo sabe, lo dice; Lagunas de conocimiento | copiloto inteligente; apoyo a la toma de decisiones; trazabilidad hasta versión y autor; tutorización inteligente |
| 6 · Modo planta | 6:31 | 1:26 | lucia, javier | Lucía Herrero; Foto del resultado y registro de la ejecución; Fotos por revisar | asistencia guiada paso a paso; formación contextualizada en el puesto; garantizar la correcta ejecución; validación de tareas realizadas |
| 7 · Formación | 7:55 | 0:36 | lucia, marta | El itinerario de Lucía; Micro-lecciones y tutor socrático de la tarea; Formación cruzada | itinerarios de aprendizaje personalizados; adaptado al perfil; micro-learning industrial; tutorización inteligente |
| 8 · Evaluación | 8:29 | 1:29 | lucia, nuria, javier | Cuestionario de la brida B; Revisar preguntas; Observación en el puesto | validación (cuestionario); seguimiento de hitos de aprendizaje; validación (cuestionario aprobado por el experto); documentación técnica convertida en formación |
| 9 · Progreso y certificación | 9:56 | 1:15 | marta, javier, carmen | Mi progreso; Matriz ILUO del equipo de Producción; Una versión nueva de IT-023 | pasaporte digital de habilidades; evaluación continua; seguimiento de progresos individuales; indicadores de desempeño |
| 10 · Aportaciones | 11:09 | 1:01 | pedro, javier, marta | Pedro Ruiz, operario de prensas; Validar aportaciones; Lo que aprende la planta vuelve a la planta | captura del conocimiento de operarios expertos; atraer a nuevas generaciones; mejoras añadidas (aportaciones validadas); trazabilidad hasta versión y autor |
| 11 · Espacio de trabajo | 12:08 | 0:38 | javier | Espacio de trabajo | base tecnológica e IA relevante; mejoras añadidas (agente en un espacio aislado) |
| 12 · Administración | 12:46 | 1:24 | admin | Organización; Empleados; Modelos permitidos; Registro de actividad en xAPI y auditoría; Sistema | adaptación a cada empresa (20 %); gestión de niveles; integración con los sistemas existentes; incrementar la polivalencia |
| 13 · Cómo cubre las bases | 14:07 | 1:16 | tarjetas | tarjetas con narración | criterios de valoración |

Criterios de valoración de las bases que se nombran en la voz y en los rótulos: cobertura funcional (40 %), adaptación a cada empresa (20 %), bajo coste (15 %), mejoras añadidas (15 %) y grado de innovación (10 %). Los puntos del alcance se citan con el nombre que les dan las bases (ver `docs/estado-mvp.md`).

## Antes de grabar

**P1. Datos de demostración limpios, justo antes de grabar.** ssh ... ubuntu@143.47.56.7 'docker exec cidia-gateway-1 python -m cidia.semilla --forzar' y esperar a que Administración › Sistema muestre «Cargar los datos de demostración · Completado» (1 o 2 minutos). Las sesiones anteriores dejan de valer: volver a pedir los tokens.

*Por qué:* Las exploraciones de hoy (las de este guion y las de otras pruebas) han dejado lagunas de prueba, una ejecución más de Lucía, un borrador v2 de IT-023, una ficha, una entrevista y una aportación validada de Pedro. Además los textos relativos de la semilla («hace 2 h» en la nota de Lucía) solo cuadran recién sembrado. **Aviso:** Borra todo el contenido de demostración del servidor de pruebas: confirmarlo antes con quien esté usando el servidor (hoy hay más pruebas en marcha).

**P2. Cuenta «prueba.escritorio» fuera de la lista.** Administración › Empleados › Prueba Escritorio › Desactivar (la semilla no la borra porque no la creó ella). Con el filtro «Activas» deja de verse.

*Por qué:* Si no, sale «Prueba Escritorio» en Empleados y la plantilla cuenta 16 personas en vez de 15.

**P3. Audios del micrófono.** python herramientas/video/voz.py frase "<texto>" --salida <voces>/microfono/<id>.wav --microfono, con los textos de «audios_microfono».

*Por qué:* El micrófono falso de Chromium «dice» ese WAV: la pregunta y las notas de voz se transcriben de verdad en el servidor.

**P4. Foto del resultado para el modo planta.** ffmpeg -ss 45.5 -i datos-demo/video/brida-b-sintetico.mp4 -frames:v 1 -vf crop=620:480:100:140 <grabaciones>/ficheros/foto-resultado.jpg: el dibujo del paso 6 (inspección visual final), que es la imagen de referencia de IT-023 v1.

*Por qué:* En el segundo 43 aún sale el manómetro del paso 5: con esa foto el modelo de visión ve diferencias (probado el 10/10) y, si coincide, la foto no pasa a revisión del jefe.

**P5. Ficheros del espacio de trabajo.** Crear los dos ficheros de «ficheros» en <salida>/ficheros/. Antes de grabar 11a, dejar informe_paradas.py ya en la carpeta de Javier (PUT /api/espacio/fichero con su token); paradas-prensa3.csv se sube en la escena.

*Por qué:* En pantalla se ve subir un fichero y lanzar un análisis corto y legible.

**P6. App de escritorio para el capítulo 2.** Cerrar la CidIA que esté abierta (solo los procesos de %LOCALAPPDATA%\Programs\CidIA\app\CidIA.exe; nunca DeepSeek Harness) y abrirla con "%LOCALAPPDATA%\Programs\CidIA\CidIA.exe" --remote-debugging-port=9333, ventana maximizada a 1920 x 1080, sin sesión (botón del pie › Cerrar sesión). Comprobar con app/instalador/verificar.mjs --sin-marca.

*Por qué:* Las conversaciones de pruebas anteriores de la lista «Espacios» se ocultan en la grabación con «ocultar_css» (no se borran). Los menús «Application / Edit» siguen en inglés (límite conocido de la app base).

**P7. Ensayo de las preguntas.** Lanzar cada pregunta de «comprobaciones_previas» con POST /api/consulta/simple y la cuenta indicada; si la respuesta no contiene lo esperado, repetir la toma (Nueva conversación) o cambiar la pregunta por la alternativa.

*Por qué:* El servidor de pruebas usa qwen3:0.6b: la misma pregunta puede salir bien o mal. Cada respuesta fallida crea además una laguna de prueba (otra razón para P1 justo antes).

**P8. Volver a sembrar justo antes de 03a si se repite el capítulo 3.** Cada subida de vídeo crea otro borrador de IT-023; tras la semilla solo queda el de la toma buena (03a) y 03b, 03c lo usan.

*Por qué:* Con dos borradores, «IT-023 v2» de la tabla de Instrucciones es ambiguo.

### Audios del micrófono

Chromium los «oye» con `--use-file-for-fake-audio-capture` (el grabador lo pone con la clave `microfono` de cada escena). Se generan con `voz.py frase … --microfono` (con `--voz` y `--velocidad` si la tabla lo dice). En 05a y 06a la pregunta también se oye en el vídeo (`oir_microfono`).

| Audio | Texto | Voz | Escena |
|---|---|---|---|
| `{voces}/microfono/llave.wav` | ¿Con qué llave aprieto? | kokoro:ef_dora a 0,85 | 06a-planta-pasos-lucia. Con ef_dora a 0,85 Whisper lo transcribe tal cual («¿Con qué llave aprieto?»). «¿Qué llave uso para apretar los tornillos?» no sirve: la frase de la instrucción dice «aprieta» y no «apretar», así que no hay evidencia y el modelo de pruebas dice que no lo sabe. |
| `{voces}/microfono/prensa3.wav` | La prensa 3 se ha atascado al cambiar el molde. ¿Qué hago? | kokoro:ef_dora | 05a-copiloto-voz-marta |
| `{voces}/microfono/truco-brida.wav` | Un truco de la brida B. Si la junta JT-80 no se queda centrada, pon dos tornillos a mano en diagonal antes de presentar la brida: hacen de guía y la junta ya no se mueve. Y una junta que se ha caído al suelo no se reutiliza nunca: va a la caja roja. | kokoro:ef_dora | 03d-nota-voz-carmen. Probado con la voz Helena: transcripción buena; la ficha que propone el modelo trae errores («acendiendo la guía») que Carmen corrige en la escena. |
| `{voces}/microfono/entrevista-molde.wav` | Sirve para cambiar el molde de la prensa 3 en menos de veinte minutos y sin riesgos. Se hace en cada cambio de referencia. Y lo primero, siempre, es consignar las cuatro energías antes de meter las manos. | kokoro:ef_dora | 03e-entrevista-carmen |
| `{voces}/microfono/purga.wav` | Para purgar el circuito de refrigeración del molde de la prensa 3: con la prensa parada y el molde frío, abro la válvula de purga de arriba del molde hasta que el agua sale sin burbujas, unos treinta segundos. Después la cierro y compruebo que el depósito está por encima de la marca de mínimo. | kokoro:em_santa | 10a-aportar-voz-pedro. Voz masculina distinta del narrador (Pedro). Whisper la transcribe entera y sin errores. |

### Ficheros

`{salida}/ficheros/paradas-prensa3.csv`

```csv
fecha,maquina,causa,minutos
2026-09-01,P3,Sensor S4 sucio,18
2026-09-03,P3,Cambio de molde,35
2026-09-08,P3,Sensor S4 sucio,22
2026-09-15,P3,Falta de material,12
2026-09-22,P3,Cambio de molde,31
2026-09-29,P3,Sensor S4 sucio,6
2026-10-06,P3,Cambio de molde,24
```

`{salida}/ficheros/informe_paradas.py`: Probado hoy en la consola de Javier: 3,9 s, gráfico PNG y Excel. Sin red: una conexión a example.com falla (ver 11a).

```python
# Resumen de las paradas de la prensa 3: gráfico y tabla en Excel
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

d = pd.read_csv("paradas-prensa3.csv")
r = d.groupby("causa")["minutos"].sum().sort_values()
r.plot.barh(color="#F2C200")
plt.title("Minutos de parada de la prensa 3")
plt.xlabel("minutos")
plt.tight_layout()
plt.savefig("paradas-prensa3.png", dpi=130)
r.to_excel("paradas-prensa3.xlsx")
print(r.to_string())
print("Guardados paradas-prensa3.png y paradas-prensa3.xlsx")
```

### Comprobación de las preguntas (P7)

El servidor de pruebas usa modelos diminutos (qwen3:0.6b): la misma pregunta puede salir bien o mal. Conviene lanzarlas justo antes de grabar (`POST /api/consulta/simple`, con el modo y el contexto indicados).

| Escena | Cuenta | Modo | Pregunta | Debe contener |
|---|---|---|---|---|
| 02a | invitado | normal | ¿Cuál es el teléfono de emergencias? | «200» |
| 02a | invitado | normal | ¿A cuánto se aprietan los tornillos de la brida B? | «No lo he encontrado» |
| 04c | luis | normal | ¿Quién aprueba compras de más de 12.000 €? | «No lo he encontrado» |
| 04d | ana | normal | ¿Quién aprueba compras de más de 12.000 €? | «gerencia» |
| 05a | marta | normal | La prensa 3 se ha atascado al cambiar el molde, ¿qué hago? | «S4» |
| 05b | marta | socratico | ¿Cómo se aprietan los tornillos de la brida B? | «?» |
| 05c | marta | normal | ¿Qué presión lleva el cilindro de la prensa 2? | «No lo he encontrado» |
| 06a | lucia | planta (con tarea y paso) | ¿Con qué llave aprieto? | «dinamométrica» |
| 07b | lucia | socratico (con tarea y paso) | ¿Qué puede salir mal en el paso crítico? | «Pista» |
| 10c | marta | normal | ¿Cómo se purga el circuito de refrigeración? | «válvula de purga» |

### Orden de grabación

03c (publicar la versión 2 de IT-023) se graba la última: deja obsoleta la v1, marca a Marta, Carmen y Lucía para reevaluación y regenera micro-lecciones y preguntas (que quedan pendientes de aprobar), lo que cambiaría el modo planta, la formación y el cuestionario de Lucía. 06c va después de 07 para dar tiempo a que el modelo de visión compare la foto (más de un minuto en el servidor de pruebas). 08c antes de 09b: la observación sube a Pedro a U y la matriz ya lo muestra. 10a, 10b y 10c en ese orden: la aportación pendiente, validada y citada.

1. 01d-planta-admin
2. 02a-app-invitado
3. 02b-app-sesion-lucia
4. 02c-jefe-javier
5. 02d-admin
6. 03a-captura-video-carmen
7. 03b-borrador-carmen
8. 03d-nota-voz-carmen
9. 03e-entrevista-carmen
10. 04a-documentos-javier
11. 04b-probar-busqueda-ana
12. 04c-luis-sin-acceso
13. 04d-ana-con-acceso
14. 05a-copiloto-voz-marta
15. 05b-socratico-marta
16. 05c-laguna-marta
17. 05d-lagunas-javier
18. 06a-planta-pasos-lucia
19. 06b-planta-cierre-lucia
20. 07a-itinerario-lucia
21. 07b-microleccion-tutor-lucia
22. 07c-formacion-cruzada-marta
23. 06c-foto-javier
24. 08a-cuestionario-lucia
25. 08b-revisar-preguntas-nuria
26. 08c-observacion-javier
27. 09a-pasaporte-marta
28. 09b-matriz-javier
29. 10a-aportar-voz-pedro
30. 10b-validar-javier
31. 10c-cita-marta
32. 11a-espacio-javier
33. 11b-agente-app
34. 12a-organizacion-admin
35. 12b-empleados-admin
36. 12c-modelos-admin
37. 12d-registro-admin
38. 12e-sistema-admin
39. 03c-publicar-carmen

## Escenas

Convenciones: Cada pieza de tipo «escena» lleva en «escena» un objeto con el formato de herramientas/video/grabador.mjs (id, titulo, bases, usuario, ruta, microfono, esperar_inicio, escala, acciones, narracion, duracion_minima_ms). El grabador lee hoy las escenas de ficheros sueltos: o se le añade que acepte el objeto en línea o se separan con un script (una escena por fichero, mismo id). capitulo, rol, duracion_estimada_s, preparacion, depende_de, verificado y notas son para el montaje y para quien graba; el grabador los ignora. 1.25 en todas las escenas web (ventana CSS de 1536 x 864 dentro del vídeo de 1920 x 1080): se lee bien en un móvil. Para que se vea fluido, se cambia de sección con un clic en la barra lateral ({"clic": ".lateral-nav a[href='/app/...']"}); «ir» solo para entrar en una ruta interna. Toda espera del servidor (transcribir, responder, procesar vídeo, comparar la foto) va con esperarTexto o esperarSelector y «acelerar»: el montaje la acorta y lo rotula. Nunca se corta en silencio. Las contraseñas no aparecen nunca: el grabador inicia sesión por token salvo en 02b, donde se teclea en el campo de tipo password con el marcador {contrasena} (se ven puntos).

### 1 · El problema

#### 00-portada · tarjeta «CidIA» (8,8 s)

Etiqueta: «V DESAFÍO industrial · POLO positivo». Subtítulo: «El copiloto de IA que captura, enseña, evalúa y certifica el conocimiento de la planta. Todo en local.».

> Esto es CidIA: un copiloto de inteligencia artificial para la industria que funciona entero dentro de la empresa.

#### 01a-problema · tarjeta «El conocimiento se jubila» (19,5 s)

Etiqueta: «Capítulo 1 · El problema». Subtítulo: «Entre 2026 y 2035 saldrán del mercado laboral unos 5,3 millones de personas mayores de 55 años y entrarán unos 1,8 millones de jóvenes (Fundación Adecco a partir de la EPA)».

> En cada planta hay personas que hacen bien las cosas tras años de oficio. Cuando se jubilan, ese saber se va con ellas. En España, en los próximos diez años saldrán del mercado laboral más de cinco millones de mayores de cincuenta y cinco años, y entrarán menos de dos millones de jóvenes.

#### 01b-cidia · tarjeta «Capturar, estructurar, formar, acompañar, evaluar y certificar» (19,1 s)

Etiqueta: «CidIA en una frase». Subtítulo: «Un servidor en la empresa y una app en cada puesto. Sin nube y sin pago por consulta.».

> CidIA cierra el ciclo completo que piden las bases: captura lo que sabe el experto, lo convierte en instrucciones y formación, acompaña en el puesto y certifica quién domina cada tarea. Y los modelos de IA corren en un servidor de la empresa: los datos no salen de la planta.

#### 01d-planta-admin · Metalúrgica Arlanza, S. L. · empresa ficticia con datos sintéticos

* **Quién:** Administración (admin) · cuenta `admin`
* **Dónde:** navegador, ruta `/app/`
* **Rótulo:** «Metalúrgica Arlanza, S. L. · empresa ficticia con datos sintéticos» · «Bases: indicadores de desempeño · gestión centralizada del conocimiento»
* **Duración estimada:** 20 s · **en el vídeo:** 20,8 s desde 0:46 · **preparación:** P1, P2

**Voz**

> Lo vemos en una empresa ficticia de Burgos, Metalúrgica Arlanza, con cuatro departamentos y datos sintéticos.
>
> **[cifras]** Así ve la planta la administración: personas, documentos, instrucciones publicadas y consultas con respaldo,
>
> **[equipo]** y lo que pide atención: aportaciones por validar y lagunas de conocimiento.

**Acciones**

1. pausa de 0,7 s
2. resalta «Personas en 4 departamentos» (su `.dato`) con la nota «Empresa ficticia · datos sintéticos»
3. pasa el cursor por «Documentos listos para consultar»
4. pasa el cursor por «Instrucciones publicadas»
5. **[cifras]** empieza el fragmento de voz «cifras»
6. resalta `.ini-cifras`
7. **[equipo]** empieza el fragmento de voz «equipo»
8. desplaza abajo 380 px
9. resalta «Aportaciones por validar»
10. resalta «Lagunas abiertas»
11. pausa de 0,6 s

**Comprobado:** Inicio de admin recorrido hoy sin errores de consola: cifras, aportaciones por validar, lagunas, reevaluaciones y listos para observar.

### 2 · La app y el acceso

#### 02-tarjeta · tarjeta «Una app para todos; cada uno ve lo suyo» (3,2 s)

Etiqueta: «Capítulo 2». Subtítulo: «La app de escritorio CidIA, el acceso sin sesión y con sesión».

#### 02a-app-invitado · App de escritorio CidIA · sin iniciar sesión

* **Quién:** Invitado (sin sesión) en la app de escritorio
* **Dónde:** app de escritorio (CDP en el puerto 9333)
* **Rótulo:** «App de escritorio CidIA · sin iniciar sesión» · «Bases: implantación sencilla · proteger el conocimiento experto»
* **Duración estimada:** 27 s · **en el vídeo:** 30,9 s desde 1:09, esperas aceleradas ×3 · **preparación:** P6, P1

**Voz**

> La app CidIA se instala en cada portátil sin permisos de administrador. Sin iniciar sesión, solo ofrece el acceso y el copiloto con los documentos públicos.
>
> **[respuesta]** Responde a lo general, como el teléfono de emergencias, y dice de dónde sale.
>
> **[restringida]** Lo interno del puesto, en cambio, no existe para quien no ha entrado.

**Acciones**

1. pausa de 0,9 s
2. resalta `nav[class*='panelList']` con la nota «Sin sesión: solo Acceso y Copiloto»
3. clic en «Copiloto» (dentro de `nav[class*='panelList']`)
4. espera `textarea[aria-label='Tu pregunta']` (máx. 20 s) (en el panel de la app (iframe))
5. pausa de 0,7 s
6. **[pregunta]** empieza el fragmento de voz «pregunta»
7. teclea «¿Cuál es el teléfono de emergencias?» en `textarea[aria-label='Tu pregunta']` (en el panel de la app (iframe))
8. tecla Enter
9. espera `.acciones-respuesta` (máx. 90 s; se acelera con el rótulo «El copiloto busca en los documentos públicos») (en el panel de la app (iframe))
10. **[respuesta]** empieza el fragmento de voz «respuesta»
11. resalta `.burbuja.asistente .globo`
12. clic en «Nueva conversación» (en el panel de la app (iframe))
13. pausa de 0,7 s
14. teclea «¿A cuánto se aprietan los tornillos de la brida B?» en `textarea[aria-label='Tu pregunta']` (en el panel de la app (iframe))
15. tecla Enter
16. espera `.acciones-respuesta` (máx. 90 s; se acelera con el rótulo «El copiloto busca en los documentos públicos») (en el panel de la app (iframe))
17. **[restringida]** empieza el fragmento de voz «restringida»
18. resalta `.sin-respaldo`
19. pausa de 0,5 s

**Comprobado:** Grabado el 10/10 en la app real (CDP, puerto 9333, emulando 1536 x 864 a 1,25): invitado, panel Copiloto en el iframe, teléfono 200 con cita y la brida B sin acceso (en una conversación nueva: con la anterior el modelo mezclaba preguntas).

**Notas:** «marco»: «iframe» indica que el selector se busca dentro del panel de la app (document.querySelector('iframe').contentDocument). Si el grabador no lo admite todavía, plan B: grabar el plano de la barra lateral en la app (resaltar Acceso y Copiloto) y las dos preguntas en el navegador como invitado (usuario «invitado», ruta /app/copiloto), que es la misma interfaz.

#### 02b-app-sesion-lucia · Lucía Herrero inicia sesión · operaria de Producción, nivel 1

* **Quién:** Empleada (operaria) que inicia sesión en la app · entra con `lucia`
* **Dónde:** app de escritorio (CDP en el puerto 9333)
* **Rótulo:** «Lucía Herrero inicia sesión · operaria de Producción, nivel 1» · «Bases: adaptado al perfil · integración (módulo de identidad)»
* **Duración estimada:** 18 s · **en el vídeo:** 22,1 s desde 1:39 · **preparación:** P6

**Voz**

> Lucía, recién incorporada a la línea 2, inicia sesión. La contraseña nunca se ve.
>
> **[secciones]** Aparecen sus secciones: inicio, copiloto, modo planta, formación, evaluación, progreso, aportaciones y espacio de trabajo. Lo decide el servidor según su puesto y su nivel.

**Acciones**

1. pausa de 0,5 s
2. clic en «Acceso» (dentro de `nav[class*='panelList']`)
3. espera `#usuario` (máx. 15 s) (en el panel de la app (iframe))
4. pausa de 0,6 s
5. teclea «lucia» en `#usuario` (en el panel de la app (iframe))
6. teclea «la contraseña (campo password)» en `#contrasena` (en el panel de la app (iframe))
7. **[entrar]** empieza el fragmento de voz «entrar»
8. clic en «Iniciar sesión» (en el panel de la app (iframe))
9. espera a que salga «Modo planta» (máx. 30 s)
10. pausa de 1,5 s
11. **[secciones]** empieza el fragmento de voz «secciones»
12. resalta `nav[class*='panelList']` con la nota «Ocho secciones para una operaria»
13. pausa de 0,9 s

**Comprobado:** Grabado el 10/10 en la app real: usuario y contraseña tecleados en el iframe de Acceso (campo password, se ven puntos), la barra lateral pasa a las 8 secciones de Lucía. Después se cerró la sesión de la app.

**Notas:** Plan B sin app: /app/acceso en el navegador sin token, mismos campos #usuario y #contrasena y el botón «Iniciar sesión».

#### 02c-jefe-javier · Javier Martín · jefe de Producción

* **Quién:** Jefe de equipo (javier) · cuenta `javier`
* **Dónde:** navegador, ruta `/app/`
* **Rótulo:** «Javier Martín · jefe de Producción» · «Bases: gestión centralizada del conocimiento · escalabilidad»
* **Duración estimada:** 9 s · **en el vídeo:** 7,0 s desde 2:01

**Voz**

> Javier, jefe de Producción, ve además el conocimiento de su departamento y a su equipo.

**Acciones**

1. pausa de 0,8 s
2. resalta `.lateral-grupo[aria-label='Mi equipo']`
3. resalta `.lateral-grupo[aria-label='Conocimiento']`

**Comprobado:** Barra lateral de javier (Mi trabajo, Conocimiento, Mi equipo) y de admin (más Administración) vistas hoy.

#### 02d-admin · La administración

* **Quién:** Administración (admin) · cuenta `admin`
* **Dónde:** navegador, ruta `/app/`
* **Rótulo:** «La administración» · «Bases: gestión centralizada del conocimiento · escalabilidad»
* **Duración estimada:** 11 s · **en el vídeo:** 8,6 s desde 2:07

**Voz**

> Y la administración, la organización, los empleados, los modelos y el registro. Una sola app para toda la planta.

**Acciones**

1. pausa de 0,6 s
2. resalta `.lateral-grupo[aria-label='Administración']`

**Comprobado:** Barra lateral de admin con el grupo Administración (Organización, Empleados, Modelos, Registro de actividad, Sistema) vista hoy.

### 3 · Capturar el saber del experto

#### 03-tarjeta · tarjeta «Capturar el saber del experto» (3,2 s)

Etiqueta: «Capítulo 3». Subtítulo: «Vídeo narrado, borrador y edición. Nota de voz y entrevista guiada.».

#### 03a-captura-video-carmen · Carmen Díaz, experta · captura en vídeo de la brida B

* **Quién:** Empleada experta (carmen) · cuenta `carmen`
* **Dónde:** navegador, ruta `/app/captura`
* **Rótulo:** «Carmen Díaz, experta · captura en vídeo de la brida B» · «Bases: captura del conocimiento de operarios expertos · generación automática de instrucciones»
* **Duración estimada:** 22 s · **en el vídeo:** 20,6 s desde 2:18, esperas aceleradas ×28, 9,7 s recortados · **preparación:** P1

**Voz**

> Carmen, la experta en la brida B, se graba montándola mientras lo explica y sube el vídeo a Captura.
>
> **[proceso]** El servidor extrae el audio, lo transcribe, detecta los pasos y un modelo con visión repasa cada imagen. En este servidor de pruebas tarda unos minutos; aquí va acelerado.
>
> **[listo]** Borrador listo.

**Acciones**

1. pausa de 0,8 s
2. elige «IT-023» en `select`
3. **[subir]** empieza el fragmento de voz «subir»
4. sube `{repo}/datos-demo/video/brida-b-sintetico.mp4` con `.zona-subida`
5. espera a que salga «Extrayendo audio» (máx. 30 s)
6. **[proceso]** empieza el fragmento de voz «proceso»
7. desplaza hasta `#cap-fila-1, .cap-fila`
8. espera a que salga «Revisar borrador» (máx. 1500 s; se acelera con el rótulo «El servidor transcribe el vídeo, detecta los pasos y revisa cada imagen»)
9. **[listo]** empieza el fragmento de voz «listo»
10. resalta «Los pasos siguen los que nombras»

**Montaje:** se recortan 259-268.7 s de la grabación. La grabación esperó en directo a la voz (10 s con la pantalla quieta tras el borrador): ese rato se recorta. La espera del servidor (250 s reales) se acelera a 9 s con su rótulo.

**Comprobado:** Grabado el 10/10: la captura tarda entre 4 y 12 minutos en Oracle (el modelo con visión repasa los 7 pasos); el montaje lo acelera con su rótulo. Borrador con los mismos fallos de transcripción que en la exploración («Prueba de esta enqueidad», «4 tornillos en 10»).

#### 03b-borrador-carmen · El borrador: la IA propone, la experta decide

* **Quién:** Empleada experta (carmen) · cuenta `carmen`
* **Dónde:** navegador, ruta `/app/captura`
* **Rótulo:** «El borrador: la IA propone, la experta decide» · «Bases: digitalización de procedimientos operativos · trazabilidad hasta versión y autor»
* **Duración estimada:** 31 s · **en el vídeo:** 27,5 s desde 2:38 · **depende de:** 03a-captura-video-carmen

**Voz**

> **[borrador]** Siete pasos con su imagen, su clip y lo que Carmen dice en cada uno. El paso 3 llega marcado como crítico porque ella lo dijo: cuatro tornillos en cruz a 25 N·m.
>
> **[corrige]** La IA propone; decide la experta. Corrige el título del paso 5, que la transcripción dejó mal, y lo marca como paso de seguridad.
>
> **[guarda]** Nada llega al copiloto hasta que lo publique.

**Acciones**

1. clic en «Revisar borrador» (dentro de `.cap-fila`)
2. espera a que salga «Borrador preparado por CidIA» (máx. 20 s)
3. **[borrador]** empieza el fragmento de voz «borrador»
4. resalta `.ins-pasos`
5. clic en `.ins-pasos li:nth-child(3)`
6. pausa de 0,8 s
7. resalta `.ins-medios` con la nota «Imagen y clip de este paso»
8. resalta `.ins-interruptores`
9. **[corrige]** empieza el fragmento de voz «corrige»
10. clic en `.ins-pasos li:nth-child(5)`
11. pausa de 0,6 s
12. resalta `input.ins-titulo-paso` con la nota «Prueba de esta enqueidad»
13. teclea «Prueba de estanqueidad» en `input.ins-titulo-paso` (borrando lo que había)
14. clic en `.ins-interruptores .ins-interruptor:nth-child(2) .interruptor`
15. pausa de 0,6 s
16. **[guarda]** empieza el fragmento de voz «guarda»
17. clic en «Guardar» (dentro de `.cabecera .acciones`)
18. espera a que salga «Cambios guardados» (máx. 15 s)
19. pausa de 0,8 s

**Comprobado:** Grabado el 10/10 sobre el borrador de 03a: paso 5 corregido a «Prueba de estanqueidad», marcado como seguridad y guardado.

**Notas:** El título exacto de los pasos sale de la transcripción y puede variar entre subidas: comprobar el del paso 5 antes de grabar y ajustar el resaltado.

#### 03d-nota-voz-carmen · Nota de voz: lo que no se ve en un vídeo

* **Quién:** Empleada experta (carmen) · cuenta `carmen`
* **Dónde:** navegador, ruta `/app/captura` · micrófono: `{voces}/microfono/truco-brida.wav`
* **Rótulo:** «Nota de voz: lo que no se ve en un vídeo» · «Bases: captura del conocimiento de operarios expertos (voz)»
* **Duración estimada:** 23 s · **en el vídeo:** 31,4 s desde 3:05, esperas aceleradas ×10, ×13, ×2

**Voz**

> Lo que no se ve en un vídeo, como un truco o un error típico, va en una nota de voz: Carmen pulsa y habla.
>
> **[proceso]** CidIA la transcribe y la ordena en una ficha.
>
> **[ficha]** Carmen la revisa junto a lo que dijo, corrige lo que el modelo entendió mal
>
> **[publica]** y la publica. Ya forma parte del conocimiento de Producción.

**Acciones**

1. elige «IT-023» en `select`
2. **[graba]** empieza el fragmento de voz «graba»
3. clic en `.cap-via .boton-voz`
4. el micrófono empieza a «oír» su audio
5. pausa de 18,1 s (lo que dura truco-brida.wav más medio segundo); se acelera con el rótulo «Carmen graba la nota de voz»
6. clic en `.cap-via .boton-voz`
7. espera a que salga «Enviar nota» (máx. 10 s)
8. clic en «Enviar nota»
9. espera a que salga «Nota recibida» (máx. 15 s)
10. **[proceso]** empieza el fragmento de voz «proceso»
11. espera a que salga «está listo para revisar» (máx. 400 s; se acelera con el rótulo «El servidor transcribe la nota y la ordena en una ficha»)
12. clic en «Revisar borrador» (dentro de `.cap-fila:first-child`)
13. espera a que salga «Borrador preparado por CidIA» (máx. 15 s)
14. **[ficha]** empieza el fragmento de voz «ficha»
15. resalta `.modal .cap-ficha-vista` con la nota «La ficha que propone CidIA»
16. clic en «Escuchar la nota y ver la transcripción»
17. pausa de 1,2 s
18. desplaza hasta `.cap-detalles`
19. resalta `.cap-detalles` con la nota «Lo que dijo Carmen, palabra por palabra»
20. clic en «Editar» (dentro de `.modal`)
21. espera `textarea.mono-suave` (máx. 5 s)
22. teclea «## Truco ⏎ - Si la junta JT-80 no se queda centrada, pon dos tornillos a mano en diagonal antes de presentar la brida: hacen de guía y la junta ya no se mueve. ⏎ ## Error típico ⏎ - Una junta que se ha caído al suelo no se reutiliza nunca: va a la caja roja.» en `textarea.mono-suave` (borrando lo que había)
23. clic en «Vista previa» (dentro de `.modal`)
24. pausa de 0,9 s
25. **[publica]** empieza el fragmento de voz «publica»
26. clic en «Publicar ficha»
27. espera a que salga «Confirmar» (máx. 5 s)
28. clic en «Confirmar»
29. espera a que salga «Ficha publicada» (máx. 30 s; se acelera con el rótulo «Publicando la ficha»)
30. pausa de 1,2 s

**Montaje:** la acción 22 va acelerada ×2 con el rótulo «Carmen corrige la ficha».

**Comprobado:** Grabado el 10/10 con el micrófono falso: transcripción con errores reales («pondo», «Vada la queja Roger»), ficha propuesta, edición y «Ficha publicada».

**Notas:** La corrección se teclea rápido (6 ms por carácter) sobre el contenido que propone el modelo. Si el grabador no teclea los saltos de línea del texto, partir el «escribir» en trozos con {"tecla": "Enter"} entre medias. Si el modal no tiene la clase .modal ni role=dialog, quitar «dentro» (la pestaña «Editar» del modal es el botón más corto con ese texto).

#### 03e-entrevista-carmen · Entrevista guiada · cambio de molde en la prensa 3

* **Quién:** Empleada experta (carmen) · cuenta `carmen`
* **Dónde:** navegador, ruta `/app/captura` · micrófono: `{voces}/microfono/entrevista-molde.wav`
* **Rótulo:** «Entrevista guiada · cambio de molde en la prensa 3» · «Bases: captura del conocimiento de operarios expertos (entrevista)»
* **Duración estimada:** 22 s · **en el vídeo:** 19,2 s desde 3:36, esperas aceleradas ×8, ×5

**Voz**

> Y si no sabe por dónde empezar, el copiloto la entrevista.
>
> **[pregunta]** Una pregunta cada vez, con un guion de siete temas, y Carmen responde hablando.
>
> **[siguiente]** Al terminar, CidIA genera una ficha o un borrador de instrucción, que de nuevo revisa ella.

**Acciones**

1. elige «IT-031» en `select`
2. clic en «Empezar entrevista»
3. espera a que salga «Para empezar» (máx. 120 s; se acelera con el rótulo «El copiloto prepara la primera pregunta»)
4. **[pregunta]** empieza el fragmento de voz «pregunta»
5. resalta `.cap-guion` con la nota «El guion de la entrevista: siete temas»
6. clic en `button[aria-label='Responder por voz']`
7. el micrófono empieza a «oír» su audio
8. pausa de 14,3 s (lo que dura entrevista-molde.wav más medio segundo); se acelera con el rótulo «Carmen responde por voz»
9. clic en «Parar y enviar»
10. espera a que salga «1 de 7 temas» (máx. 240 s; se acelera con el rótulo «Transcribe la respuesta y prepara la siguiente pregunta»)
11. **[siguiente]** empieza el fragmento de voz «siguiente»
12. resalta «1 de 7 temas»
13. resalta «Terminar y generar ficha»

**Comprobado:** Grabado el 10/10: respuesta por voz transcrita y segunda pregunta del modelo «¿Cuánto dura el proceso de cambio de molde en la prensa 3?».

**Notas:** El botón de voz de la entrevista es de pulsar para empezar y pulsar para terminar (GrabadorVoz compacto, aria-label «Responder por voz»); al terminar envía la respuesta sola.

### 4 · Documentos y búsqueda

#### 04-tarjeta · tarjeta «El conocimiento, ordenado y con permisos» (3,2 s)

Etiqueta: «Capítulo 4». Subtítulo: «Documentos, búsqueda híbrida y la consola «Probar búsqueda»».

#### 04a-documentos-javier · Documentos de Producción · Javier Martín

* **Quién:** Jefe de equipo (javier) · cuenta `javier`
* **Dónde:** navegador, ruta `/app/documentos`
* **Rótulo:** «Documentos de Producción · Javier Martín» · «Bases: bases de conocimiento inteligentes · gestión centralizada del conocimiento»
* **Duración estimada:** 20 s · **en el vídeo:** 18,6 s desde 3:58

**Voz**

> Los documentos que ya existen también cuentan: PDF, Office, audios o imágenes, cada uno con su departamento, su nivel mínimo, si es formación y si es público.
>
> **[subir]** Al subirlos, CidIA los indexa para buscar por significado y por palabras exactas en castellano.

**Acciones**

1. pausa de 0,7 s
2. resalta `table thead` con la nota «Departamento, nivel mínimo, formación y público»
3. resalta «Manual de manejo de la prensa 3» (su `tr`) con la nota «Nivel mínimo: Técnico»
4. resalta «Bienvenida y PRL» (su `tr`) con la nota «Público: también sin iniciar sesión»
5. **[subir]** empieza el fragmento de voz «subir»
6. clic en «Subir conocimiento»
7. espera a que salga «Nivel mínimo» (máx. 10 s)
8. pausa de 0,4 s
9. resalta `.doc-subida > div:last-child`
10. clic en «Cancelar»
11. pausa de 0,6 s

**Comprobado:** Biblioteca y panel «Subir conocimiento» (Departamento, Nivel mínimo, Material de formación, Público) presentes; recorridos hoy con ana. Javier ve los documentos de Producción.

#### 04b-probar-busqueda-ana · Probar búsqueda · Ana López, responsable de Oficina técnica (nivel 3)

* **Quién:** Jefa de equipo y experta (ana) · cuenta `ana`
* **Dónde:** navegador, ruta `/app/documentos`
* **Rótulo:** «Probar búsqueda · Ana López, responsable de Oficina técnica (nivel 3)» · «Bases: bases de conocimiento inteligentes · proteger el conocimiento experto»
* **Duración estimada:** 30 s · **en el vídeo:** 27,2 s desde 4:16

**Voz**

> Con Probar búsqueda, Ana comprueba qué encontraría el copiloto.
>
> **[resultados]** Para ella sale el documento de costes de utillaje, con su puntuación por significado y por palabras, fusionadas en un solo orden.
>
> **[comoLuis]** Ahora busca como Luis, técnico junior. Ese documento es de nivel 3 y para él no aparece: los permisos se aplican en el servidor antes de que el modelo vea nada.

**Acciones**

1. clic en «Probar búsqueda»
2. espera `input[aria-label='Pregunta']` (máx. 10 s)
3. teclea «¿Quién aprueba compras de más de 12.000 €?» en `input[aria-label='Pregunta']`
4. clic en `.doc-pregunta button[type=submit]`
5. espera a que salga «Alcance de la búsqueda» (máx. 30 s)
6. **[resultados]** empieza el fragmento de voz «resultados»
7. resalta «Costes y proveedores de utillaje»
8. resalta «Coincide por palabras»
9. resalta «Similitud»
10. **[comoLuis]** empieza el fragmento de voz «comoLuis»
11. elige «Luis» en `.doc-busqueda select`
12. clic en `.doc-pregunta button[type=submit]`
13. espera a que desaparezca «Costes y proveedores de utillaje» (máx. 30 s)
14. pausa de 0,6 s
15. resalta «Alcance de la búsqueda»

**Comprobado:** Grabado el 10/10 con «¿Quién aprueba compras de más de 12.000 €?»: como Ana, Costes y proveedores de utillaje; como Luis, Bienvenida y PRL y el manual de iniciación.

#### 04c-luis-sin-acceso · Luis García · técnico junior, nivel 1

* **Quién:** Empleado (luis) · cuenta `luis`
* **Dónde:** navegador, ruta `/app/copiloto`
* **Rótulo:** «Luis García · técnico junior, nivel 1» · «Bases: proteger el conocimiento experto · necesidades formativas»
* **Duración estimada:** 13 s · **en el vídeo:** 14,3 s desde 4:42, esperas aceleradas ×7

**Voz**

> Luis se lo pregunta al copiloto.
>
> **[respuesta]** No se cita ni se menciona el documento: no lo ha encontrado, y la pregunta queda como laguna.

**Acciones**

1. teclea «¿Quién aprueba compras de más de 12.000 €?» en `textarea[aria-label='Tu pregunta']`
2. tecla Enter
3. espera `.acciones-respuesta` (máx. 120 s; se acelera con el rótulo «El copiloto busca con los permisos de Luis»)
4. **[respuesta]** empieza el fragmento de voz «respuesta»
5. resalta `.burbuja.asistente .globo`
6. pausa de 0,6 s

**Comprobado:** Grabado el 10/10: «No se encuentra en la documentación» y laguna en Oficina técnica.

#### 04d-ana-con-acceso · La misma pregunta, con el nivel de Ana

* **Quién:** Jefa de equipo (ana) · cuenta `ana`
* **Dónde:** navegador, ruta `/app/copiloto`
* **Rótulo:** «La misma pregunta, con el nivel de Ana» · «Bases: acceso inmediato a contenidos · adaptado al perfil»
* **Duración estimada:** 12 s · **en el vídeo:** 15,6 s desde 4:56, esperas aceleradas ×2

**Voz**

> Ana sí lo ve:
>
> **[respuesta]** más de 12.000 € los aprueba la gerencia, con tres ofertas. Con la cita al documento y su versión.

**Acciones**

1. teclea «¿Quién aprueba compras de más de 12.000 €?» en `textarea[aria-label='Tu pregunta']`
2. tecla Enter
3. espera `.acciones-respuesta` (máx. 120 s; se acelera con el rótulo «El copiloto redacta la respuesta en el servidor»)
4. **[respuesta]** empieza el fragmento de voz «respuesta»
5. resalta `.burbuja.asistente .globo`
6. pasa el cursor por `.fuente.citada`
7. pausa de 1,2 s

**Comprobado:** Grabado el 10/10 tras los arreglos de consulta.py: «La persona que aprueba compras de más de 12.000 € es la gerencia, con tres ofertas y el cálculo de amortización [2]».

**Notas:** Si el modelo responde mal, Nueva conversación y repetir (P7).

### 5 · El copiloto

#### 05-tarjeta · tarjeta «Un copiloto que cita, enseña y reconoce lo que no sabe» (3,2 s)

Etiqueta: «Capítulo 5». Subtítulo: «Respuestas con fuentes, por voz, modo socrático y lagunas».

#### 05a-copiloto-voz-marta · Marta Sanz · técnica de la línea 2 · pregunta por voz

* **Quién:** Empleada (marta) · cuenta `marta`
* **Dónde:** navegador, ruta `/app/copiloto` · micrófono: `{voces}/microfono/prensa3.wav`
* **Rótulo:** «Marta Sanz · técnica de la línea 2 · pregunta por voz» · «Bases: copiloto inteligente · apoyo a la toma de decisiones · trazabilidad hasta versión y autor»
* **Duración estimada:** 25 s · **en el vídeo:** 32,8 s desde 5:14, esperas aceleradas ×4, ×47

**Voz**

> **[pregunta]** Marta, de la línea 2, pregunta por voz qué hacer con la prensa 3 atascada.
>
> **[respuesta]** La respuesta llega con sus fuentes numeradas.
>
> **[fuente]** La citada es una solución que aportó Pedro, operario de prensas, y que validó Javier: limpiar el sensor S4. Cada dato se puede comprobar en su origen.

**Acciones**

1. pausa de 0,6 s
2. **[pregunta]** empieza el fragmento de voz «pregunta»
3. pasa el cursor por `.boton-microfono`
4. espera a que termine la voz del narrador (para que no se pise con lo que se oye después)
5. mantiene pulsado `.boton-microfono` mientras el micrófono dice su audio
6. espera `.burbuja.usuario` (máx. 60 s; se acelera con el rótulo «Transcribiendo la voz en el servidor»)
7. espera `.acciones-respuesta` (máx. 150 s; se acelera con el rótulo «El copiloto prepara la respuesta en el servidor»)
8. **[respuesta]** empieza el fragmento de voz «respuesta»
9. resalta `.burbuja.asistente .globo`
10. clic en `.fuente.citada`
11. espera a que salga «Autoría» (máx. 10 s)
12. **[fuente]** empieza el fragmento de voz «fuente»
13. resalta «Validado por»
14. pausa de 0,6 s

**Comprobado:** Grabado el 10/10: la pregunta por voz se oye en el vídeo y se transcribe tal cual; respuesta con la solución de la ficha de Pedro («limpiar el sensor S4 con aire a baja presión…») y el panel con autoría y validación.

**Notas:** La redacción del modelo pequeño salió torpe en la prueba: repetir la toma hasta que la respuesta mencione el S4 sin frases raras (P7).

#### 05b-socratico-marta · Modo socrático: un tutor, no una chuleta

* **Quién:** Empleada (marta) · cuenta `marta`
* **Dónde:** navegador, ruta `/app/copiloto`
* **Rótulo:** «Modo socrático: un tutor, no una chuleta» · «Bases: tutorización inteligente · mejoras añadidas»
* **Duración estimada:** 14 s · **en el vídeo:** 18,5 s desde 5:46, esperas aceleradas ×9

**Voz**

> En modo socrático no da la respuesta hecha:
>
> **[respuesta]** pregunta y da pistas para que Marta razone por qué se aprieta en cruz. Un tutor, no una chuleta.

**Acciones**

1. clic en `.copiloto .interruptor`
2. pausa de 0,5 s
3. resalta `.copiloto .interruptor`
4. teclea «¿Cómo se aprietan los tornillos de la brida B?» en `textarea[aria-label='Tu pregunta']`
5. tecla Enter
6. espera `.acciones-respuesta` (máx. 120 s; se acelera con el rótulo «El tutor prepara su pregunta»)
7. **[respuesta]** empieza el fragmento de voz «respuesta»
8. resalta `.burbuja.asistente .globo`
9. pausa de 0,5 s

**Comprobado:** Grabado el 10/10: pregunta de vuelta, pista y cita [1].

#### 05c-laguna-marta · Cuando no lo sabe, lo dice

* **Quién:** Empleada (marta) · cuenta `marta`
* **Dónde:** navegador, ruta `/app/copiloto`
* **Rótulo:** «Cuando no lo sabe, lo dice» · «Bases: necesidades formativas · garantizar la correcta ejecución»
* **Duración estimada:** 12 s · **en el vídeo:** 14,2 s desde 6:04, esperas aceleradas ×11

**Voz**

> ¿Y si no está documentado?
>
> **[respuesta]** No se inventa la presión de la prensa 2: dice que no lo sabe y apunta la pregunta.

**Acciones**

1. teclea «¿Qué presión lleva el cilindro de la prensa 2?» en `textarea[aria-label='Tu pregunta']`
2. tecla Enter
3. espera `.acciones-respuesta` (máx. 120 s; se acelera con el rótulo «El copiloto busca en la documentación»)
4. **[respuesta]** empieza el fragmento de voz «respuesta»
5. resalta `.burbuja.asistente .globo`
6. pausa de 0,5 s

**Comprobado:** Grabado el 10/10: «No lo he encontrado…» y la laguna sube a 4 veces.

#### 05d-lagunas-javier · Lagunas de conocimiento · Javier Martín

* **Quién:** Jefe de equipo (javier) · cuenta `javier`
* **Dónde:** navegador, ruta `/app/lagunas`
* **Rótulo:** «Lagunas de conocimiento · Javier Martín» · «Bases: necesidades formativas · identificación de lagunas»
* **Duración estimada:** 15 s · **en el vídeo:** 13,3 s desde 6:18

**Voz**

> Javier ve esas lagunas agrupadas por parecido y ordenadas por frecuencia: lo que su equipo pregunta y nadie ha documentado.
>
> **[pedir]** Son necesidades formativas con datos, y la próxima captura.

**Acciones**

1. pausa de 0,8 s
2. resalta «¿Qué presión lleva el cilindro de la prensa 2?»
3. clic en «Ver las»
4. pausa de 1,5 s
5. **[pedir]** empieza el fragmento de voz «pedir»
6. resalta «Pedir a alguien que la responda»

**Comprobado:** Página de lagunas recorrida hoy: pestañas Abiertas, Resueltas y Descartadas, «Ver las 3 formas en que se ha preguntado», «Pedir a alguien que la responda» y «Descartar».

### 6 · Modo planta

#### 06-tarjeta · tarjeta «En el puesto, paso a paso» (3,2 s)

Etiqueta: «Capítulo 6». Subtítulo: «Modo planta: pasos críticos, pregunta por voz y foto del resultado».

#### 06a-planta-pasos-lucia · Lucía Herrero · modo planta en la estación E2

* **Quién:** Empleada (lucia), recién incorporada, nivel I en IT-023 · cuenta `lucia`
* **Dónde:** navegador, ruta `/app/planta` · micrófono: `{voces}/microfono/llave.wav`
* **Rótulo:** «Lucía Herrero · modo planta en la estación E2» · «Bases: asistencia guiada paso a paso · formación contextualizada en el puesto · garantizar la correcta ejecución»
* **Duración estimada:** 35 s · **en el vídeo:** 37,7 s desde 6:33, esperas aceleradas ×78

**Voz**

> Lucía abre el modo planta en el portátil del puesto y elige la brida B.
>
> **[paso1]** Un paso por pantalla, con letra grande. Antes de empezar, los EPI, las herramientas y los riesgos.
>
> **[paso3]** El paso 3 es crítico. Con las manos ocupadas, pregunta por voz con qué llave aprieta.
>
> **[respuesta]** La respuesta sale de la instrucción y cita el paso: llave dinamométrica de media pulgada, y en cruz.
>
> **[sinmarcar]** Y sin confirmar el punto crítico no puede seguir. La confirmación queda registrada.

**Acciones**

1. resalta `.pt-tarjeta:first-child`
2. clic en «Empezar» (dentro de `.pt-tarjeta:first-child`)
3. espera a que salga «Paso 1 de 7» (máx. 20 s)
4. **[paso1]** empieza el fragmento de voz «paso1»
5. resalta «Antes de empezar»
6. clic en «Hecho» (dentro de `.planta-pie`)
7. pausa de 0,9 s
8. clic en «Hecho» (dentro de `.planta-pie`)
9. espera a que salga «PASO CRÍTICO» (máx. 10 s)
10. **[paso3]** empieza el fragmento de voz «paso3»
11. espera a que termine la voz del narrador (para que no se pise con lo que se oye después)
12. mantiene pulsado `button[aria-label='Mantén pulsado para preguntar']` mientras el micrófono dice su audio
13. espera a que se cumpla una condición en la página (respuesta terminada; máx. 150 s; se acelera con el rótulo «Transcribe la voz y responde con la instrucción»)
14. **[respuesta]** empieza el fragmento de voz «respuesta»
15. resalta `.ej-columna:last-child`
16. clic en «Hecho» (dentro de `.planta-pie`)
17. espera a que salga «Sin ella no se puede seguir» (máx. 5 s)
18. **[sinmarcar]** empieza el fragmento de voz «sinmarcar»
19. clic en `.ej-casilla`
20. pausa de 0,7 s
21. clic en «Hecho» (dentro de `.planta-pie`)
22. pausa de 0,9 s

**Comprobado:** Grabado el 10/10 tras arreglar I1: «¿Con qué llave aprieto?» por voz (se oye en el vídeo), respuesta citando IT-023 v1 paso 3, aviso del paso crítico y casilla.

**Notas:** Resuelto el fallo I1 (consulta.py: en el modo planta la evidencia se comprueba con la pregunta y se quita el eco «, no lo sabes.»). La pregunta «¿Con qué llave aprieto?» da la respuesta extractiva citando IT-023 paso 3.

#### 06b-planta-cierre-lucia · Foto del resultado y registro de la ejecución

* **Quién:** Empleada (lucia) · cuenta `lucia`
* **Dónde:** navegador, ruta `/app/planta`
* **Rótulo:** «Foto del resultado y registro de la ejecución» · «Bases: validación de tareas realizadas · evaluación continua»
* **Duración estimada:** 23 s · **en el vídeo:** 22,9 s desde 7:11, 1,9 s recortados · **depende de:** 06a-planta-pasos-lucia · **preparación:** P4

**Voz**

> Termina los pasos que quedan.
>
> **[foto]** Al final, una foto: el modelo con visión la compara con la del experto. Es orientativo; decide una persona.
>
> **[fin]** Ejecución registrada, con su tiempo y sus consultas. La pregunta del paso crítico cuenta para su curva de autonomía.

**Acciones**

1. clic en «Continuar» (dentro de `.pt-tarjeta:first-child`)
2. espera a que salga «Paso 4 de 7» (máx. 20 s)
3. clic en «Hecho» (dentro de `.planta-pie`)
4. pausa de 0,7 s
5. clic en «Hecho» (dentro de `.planta-pie`)
6. pausa de 0,7 s
7. clic en «Hecho» (dentro de `.planta-pie`)
8. pausa de 0,7 s
9. clic en «Hecho» (dentro de `.planta-pie`)
10. espera a que salga «Foto del resultado» (máx. 10 s)
11. **[foto]** empieza el fragmento de voz «foto»
12. sube `{salida}/ficheros/foto-resultado.jpg` con «Hacer foto»
13. espera a que salga «Comparando con la imagen del experto» (máx. 20 s)
14. resalta «Así debe quedar»
15. **[fin]** empieza el fragmento de voz «fin»
16. clic en «Finalizar»
17. espera a que salga «Tarea completada» (máx. 20 s)
18. resalta «Consultas al copiloto»

**Montaje:** se recortan 0-1.9 s de la grabación. La toma empieza en la lista de tareas y pulsa «Continuar · paso 4 de 7»: tras el paso 4 de 06a se veía la lista y una pantalla de carga antes de volver al paso 4. Se recorta ese inicio y la escena entra directamente en el paso 4.

**Comprobado:** Grabado el 10/10 con la foto del paso 6 (P4): «Comparando con la imagen del experto…» y «Tarea completada». El modelo de visión dio después «coincide» con confianza 1.

#### 06c-foto-javier · Fotos por revisar · Javier Martín

* **Quién:** Jefe de equipo (javier) · cuenta `javier`
* **Dónde:** navegador, ruta `/app/planta?vista=fotos`
* **Rótulo:** «Fotos por revisar · Javier Martín» · «Bases: validación de tareas realizadas · garantizar la correcta ejecución»
* **Duración estimada:** 14 s · **en el vídeo:** 22,5 s desde 7:33 · **depende de:** 06b-planta-cierre-lucia (y al menos 2 minutos para que termine la comparación)

**Voz**

> Cuando el modelo no puede confirmar el resultado, la foto le llega al jefe. Esta, de un intento anterior, era la del manómetro y no la del conjunto: Javier la rechazó con un comentario.
>
> **[veredicto]** La de hoy coincide con la del experto; aun así, Javier la mira junto a la referencia y la da por buena. La IA ayuda a mirar; decide una persona.

**Acciones**

1. pausa de 0,6 s
2. clic en «Todas» (dentro de `.rv-filtros`)
3. pausa de 1,2 s
4. resalta «Rechazada» (su `.rv-tarjeta`) con la nota «El modelo vio diferencias: Javier la rechazó con un comentario»
5. **[veredicto]** empieza el fragmento de voz «veredicto»
6. resalta «Sin revisar» (su `.rv-tarjeta`)
7. clic en «El modelo cree que coincide»
8. espera a que salga «Dar por buena» (máx. 20 s)
9. pausa de 0,6 s
10. resalta `.ej-comparar`
11. clic en «Dar por buena»
12. espera a que salga «dada por buena» (máx. 15 s)
13. pausa de 1,2 s

**Comprobado:** Grabado el 10/10: como la foto coincidía no quedó pendiente; Javier abre «Todas», ve la de un intento anterior (el manómetro, rechazada con comentario) y da por buena la de hoy.

### 7 · Formación

#### 07-tarjeta · tarjeta «Formación a medida de cada puesto» (3,2 s)

Etiqueta: «Capítulo 7». Subtítulo: «Itinerario, micro-lecciones, tutor socrático y formación cruzada».

#### 07a-itinerario-lucia · El itinerario de Lucía

* **Quién:** Empleada (lucia) · cuenta `lucia`
* **Dónde:** navegador, ruta `/app/formacion`
* **Rótulo:** «El itinerario de Lucía» · «Bases: itinerarios de aprendizaje personalizados · adaptado al perfil»
* **Duración estimada:** 11 s · **en el vídeo:** 7,9 s desde 7:58

**Voz**

> En Formación, cada persona sigue su itinerario: las tareas de su puesto, con lo que le falta para dominarlas.

**Acciones**

1. pausa de 0,6 s
2. resalta «Montaje de la brida B»
3. resalta «Haz el cuestionario de evaluación»

**Comprobado:** Itinerario de Lucía visto hoy: IT-023 nivel I con micro-lecciones, cuestionario pendiente y ejecuciones; IT-024 e IT-025 sin instrucción.

#### 07b-microleccion-tutor-lucia · Micro-lecciones y tutor socrático de la tarea

* **Quién:** Empleada (lucia) · cuenta `lucia`
* **Dónde:** navegador, ruta `/app/formacion`
* **Rótulo:** «Micro-lecciones y tutor socrático de la tarea» · «Bases: micro-learning industrial · tutorización inteligente · documentación técnica convertida en formación»
* **Duración estimada:** 22 s · **en el vídeo:** 15,0 s desde 8:05, esperas aceleradas ×11

**Voz**

> Las micro-lecciones salen de los pasos de la instrucción publicada:
>
> **[control]** cortas, con su punto clave y una pregunta de control.
>
> **[tutor]** Y el tutor socrático de la tarea le hace pensar en lo que puede salir mal en el paso crítico.

**Acciones**

1. clic en «Montaje de la brida B» (dentro de `main`)
2. espera a que salga «MICRO-LECCIÓN 1 DE 3» (máx. 15 s)
3. pausa de 0,5 s
4. resalta «Por qué se aprieta en cruz»
5. **[control]** empieza el fragmento de voz «control»
6. desplaza abajo 380 px
7. clic en «En cruz: arriba, abajo, derecha, izquierda»
8. espera a que salga «Correcto» (máx. 8 s)
9. pausa de 0,9 s
10. **[tutor]** empieza el fragmento de voz «tutor»
11. desplaza hasta `textarea[aria-label='Mensaje para el tutor']`
12. clic en «¿Qué puede salir mal en el paso crítico?»
13. espera a que salga «Pista» (máx. 150 s; se acelera con el rótulo «El tutor prepara su respuesta»)
14. pausa de 2,5 s

**Comprobado:** Página de la tarea vista hoy con Lucía: micro-lección 1 «Por qué se aprieta en cruz», punto clave «En cruz y en dos pasadas: 12 N·m y después 25 N·m», pregunta de control con la opción «En cruz: arriba, abajo, derecha, izquierda», cuestionario, instrucción y «Tutor socrático» con sus tres sugerencias. Tutor probado por la API (23 s, con «Pista»).

#### 07c-formacion-cruzada-marta · Formación cruzada · Marta se forma en Oficina técnica

* **Quién:** Empleada (marta) · cuenta `marta`
* **Dónde:** navegador, ruta `/app/formacion`
* **Rótulo:** «Formación cruzada · Marta se forma en Oficina técnica» · «Bases: incrementar la polivalencia · itinerarios personalizados»
* **Duración estimada:** 10 s · **en el vídeo:** 9,7 s desde 8:20

**Voz**

> Marta se forma también en Oficina técnica: mientras dure, encuentra su material de formación. Así se gana polivalencia.

**Acciones**

1. resalta «Formación activa en otro departamento»

**Comprobado:** Visto hoy: «Formación activa en otro departamento · Oficina técnica · Diseño de utillajes, desde el 18 sept 2026 hasta el 14 nov 2026 · 3 tareas».

### 8 · Evaluación

#### 08-tarjeta · tarjeta «Evaluar con objetividad» (3,2 s)

Etiqueta: «Capítulo 8». Subtítulo: «Cuestionario aprobado por el experto y observación en el puesto».

#### 08a-cuestionario-lucia · Cuestionario de la brida B · Lucía Herrero

* **Quién:** Empleada (lucia) · cuenta `lucia`
* **Dónde:** navegador, ruta `/app/evaluacion`
* **Rótulo:** «Cuestionario de la brida B · Lucía Herrero» · «Bases: validación (cuestionario) · seguimiento de hitos de aprendizaje»
* **Duración estimada:** 21 s · **en el vídeo:** 29,5 s desde 8:32, 3,98 s congelados

**Voz**

> Lucía hace el cuestionario de la brida B.
>
> **[preguntas]** Las preguntas salen de los pasos de la instrucción, sobre todo de los críticos, y cambian de orden en cada intento.
>
> **[resultado]** Seis de seis: queda como evidencia, ligada a la versión 1, y Lucía sube al nivel L. Le falta la observación en el puesto.

**Acciones**

1. clic en «Volver a intentarlo»
2. espera a que salga «Para aprobar necesitas» (máx. 10 s)
3. clic en «Empezar»
4. **[preguntas]** empieza el fragmento de voz «preguntas»
5. marca por JS la opción correcta (ver el JSON)
6. clic en `.ev-opcion[data-correcta]`
7. pausa de 0,6 s
8. clic en «Siguiente»
9. marca por JS la opción correcta (ver el JSON)
10. clic en `.ev-opcion[data-correcta]`
11. pausa de 0,6 s
12. clic en «Siguiente»
13. marca por JS la opción correcta (ver el JSON)
14. clic en `.ev-opcion[data-correcta]`
15. pausa de 0,6 s
16. clic en «Siguiente»
17. marca por JS la opción correcta (ver el JSON)
18. clic en `.ev-opcion[data-correcta]`
19. pausa de 0,6 s
20. clic en «Siguiente»
21. marca por JS la opción correcta (ver el JSON)
22. clic en `.ev-opcion[data-correcta]`
23. pausa de 0,6 s
24. clic en «Siguiente»
25. marca por JS la opción correcta (ver el JSON)
26. clic en `.ev-opcion[data-correcta]`
27. pausa de 0,6 s
28. clic en «Entregar»
29. espera a que salga «Cuestionario aprobado» (máx. 15 s)
30. **[resultado]** empieza el fragmento de voz «resultado»
31. resalta «Cuestionario aprobado»

**Comprobado:** Grabado el 10/10: 6 de 6, «Has subido al nivel L», falta la observación del supervisor.

**Notas:** Las respuestas correctas van en la propia escena: un eval marca con data-correcta la opción cuyo texto coincide (el orden de preguntas y opciones cambia en cada intento) y el clic lo da el cursor. Comprobado que en cada pregunta solo una opción coincide.

#### 08b-revisar-preguntas-nuria · Revisar preguntas · Nuria Gil, experta de Mantenimiento

* **Quién:** Empleada experta (nuria) · cuenta `nuria`
* **Dónde:** navegador, ruta `/app/evaluacion`
* **Rótulo:** «Revisar preguntas · Nuria Gil, experta de Mantenimiento» · «Bases: validación (cuestionario aprobado por el experto) · documentación técnica convertida en formación»
* **Duración estimada:** 16 s · **en el vídeo:** 24,1 s desde 9:00

**Voz**

> Pero ninguna pregunta entra sin el visto bueno de un experto.
>
> **[propuestas]** Nuria, de Mantenimiento, revisa las que propone la IA para la calibración del sensor S4: enunciado, opciones, paso y explicación.
>
> **[corrige]** Aquí la IA marcó mal la respuesta: la tuerca se aprieta con llave dinamométrica a 50 N·m. Nuria lo corrige
>
> **[aprueba]** y la aprueba.

**Acciones**

1. clic en «Revisar preguntas»
2. espera a que salga «Calibración del sensor S4 de la prensa 3» (máx. 10 s)
3. **[propuestas]** empieza el fragmento de voz «propuestas»
4. resalta «Por revisar»
5. resalta `.ev-editable.propuesta` con la nota «Propuesta de la IA: enunciado, opciones, paso y explicación»
6. **[corrige]** empieza el fragmento de voz «corrige»
7. resalta `.ev-editable.propuesta .ev-opcion-editable.correcta` con la nota «La IA la marcó como correcta»
8. clic en `.ev-editable.propuesta .ev-opcion-editable:first-child .ev-marca-correcta`
9. pausa de 1,0 s
10. **[aprueba]** empieza el fragmento de voz «aprueba»
11. clic en `.ev-editable.propuesta .boton.verde`
12. pausa de 2,0 s

**Comprobado:** Grabado el 10/10: la propuesta de la tuerca M18 llegaba con la respuesta correcta mal marcada; Nuria marca «Con llave dinamométrica a 50 N·m» y «Guardar y aprobar».

#### 08c-observacion-javier · Observación en el puesto · Javier observa a Pedro

* **Quién:** Jefe de equipo (javier) · cuenta `javier`
* **Dónde:** navegador, ruta `/app/evaluacion?pestana=observar`
* **Rótulo:** «Observación en el puesto · Javier observa a Pedro» · «Bases: validación (observación) · evidencias de competencia · certificación por puesto o tarea»
* **Duración estimada:** 28 s · **en el vídeo:** 32,5 s desde 9:24, esperas aceleradas ×2

**Voz**

> La otra mitad se evalúa en el puesto: Javier observa a Pedro mientras cambia el molde de la prensa 3.
>
> **[lista]** Marca cada paso en una lista de comprobación. Si un crítico, en rojo, sale mal, no se puede aprobar.
>
> **[aprueba]** Todo bien: comentario y aprobada.
>
> **[nivel]** Con eso Pedro alcanza el nivel U: ya trabaja solo en esta tarea.

**Acciones**

1. clic en «Cambio de molde en la prensa 3 · en L desde el 22 sept 2026»
2. espera a que salga «Pasos marcados» (máx. 15 s)
3. **[lista]** empieza el fragmento de voz «lista»
4. resalta `.ev-paso.critico` con la nota «Los críticos, en rojo»
5. clic en `.ev-boton-marca.bien:not(.activo)`
6. clic en `.ev-boton-marca.bien:not(.activo)`
7. clic en `.ev-boton-marca.bien:not(.activo)`
8. clic en `.ev-boton-marca.bien:not(.activo)`
9. clic en `.ev-boton-marca.bien:not(.activo)`
10. clic en `.ev-boton-marca.bien:not(.activo)`
11. clic en `.ev-boton-marca.bien:not(.activo)`
12. clic en `.ev-boton-marca.bien:not(.activo)`
13. teclea «Consigna las cuatro energías y comprueba la energía cero antes de entrar. Cambio limpio y seguro.» en `.ev-observacion > .tarjeta:last-child textarea`
14. **[aprueba]** empieza el fragmento de voz «aprueba»
15. clic en «Aprobar»
16. espera a que salga «Observación aprobada» (máx. 20 s)
17. **[nivel]** empieza el fragmento de voz «nivel»
18. pausa de 1,5 s

**Montaje:** la acción 13 va acelerada ×2 con el rótulo «Javier escribe el comentario».

**Comprobado:** Grabado el 10/10: 8 pasos bien, comentario y «Pedro Ruiz sube al nivel U».

**Notas:** IT-031 tiene 8 pasos: ocho clics en el siguiente «Bien» sin marcar.

### 9 · Progreso y certificación

#### 09-tarjeta · tarjeta «El pasaporte de habilidades» (3,2 s)

Etiqueta: «Capítulo 9». Subtítulo: «Niveles ILUO con evidencias, curva de autonomía, matriz del equipo y versiones nuevas».

#### 09a-pasaporte-marta · Mi progreso · Marta Sanz

* **Quién:** Empleada (marta) · cuenta `marta`
* **Dónde:** navegador, ruta `/app/progreso`
* **Rótulo:** «Mi progreso · Marta Sanz» · «Bases: pasaporte digital de habilidades · evaluación continua · seguimiento de progresos individuales»
* **Duración estimada:** 25 s · **en el vídeo:** 24,8 s desde 9:59

**Voz**

> El pasaporte de habilidades muestra qué tareas domina cada persona, con qué nivel ILUO y hasta cuándo,
>
> **[camino]** y qué le falta para el siguiente.
>
> **[curva]** Esta es la curva de autonomía de Marta en la brida B: de ocho consultas en su primera ejecución a cero en la última. Una medida objetiva.
>
> **[evidencias]** Debajo, las evidencias con su fecha.

**Acciones**

1. pausa de 0,8 s
2. resalta `.pp-fila.activa`
3. **[camino]** empieza el fragmento de voz «camino»
4. resalta «Camino al siguiente nivel» (su `.tarjeta`)
5. **[curva]** empieza el fragmento de voz «curva»
6. resalta «Curva de autonomía» (su `.tarjeta`)
7. **[evidencias]** empieza el fragmento de voz «evidencias»
8. resalta «Alcanzó el nivel U» (su `.tarjeta`)

**Comprobado:** Visto hoy: U en Montaje de la brida B, «Válido hasta septiembre de 2027», camino I, L, U, O con lo cumplido, curva «De 8 consultas en la primera ejecución a 0 en la última» (ejecuciones 8, 6, 5, 3, 2, 1, 1, 0) y 12 evidencias.

#### 09b-matriz-javier · Matriz ILUO del equipo de Producción · Javier Martín

* **Quién:** Jefe de equipo (javier) · cuenta `javier`
* **Dónde:** navegador, ruta `/app/equipo`
* **Rótulo:** «Matriz ILUO del equipo de Producción · Javier Martín» · «Bases: indicadores de desempeño · gestión de niveles · renovación y actualización»
* **Duración estimada:** 30 s · **en el vídeo:** 23,8 s desde 10:23 · **depende de:** 08c-observacion-javier

**Voz**

> Javier ve los indicadores de su equipo
>
> **[matriz]** y la matriz ILUO, ya sin papeles: cada celda con sus evidencias. Pedro acaba de pasar a U.
>
> **[caducidades]** Abajo, caducidades y reevaluaciones: su propio nivel en la prensa 3 caduca en menos de un mes.
>
> **[formador]** Marta ya es autónoma en la brida B: Javier la valida como formadora y pasa al nivel O.

**Acciones**

1. pausa de 0,8 s
2. resalta «niveles L o más»
3. **[matriz]** empieza el fragmento de voz «matriz»
4. resalta `.mz-tabla`
5. pasa el cursor por `button.mz-celda[aria-label^='Pedro Ruiz · Cambio de molde en la prensa 3']`
6. pausa de 0,9 s
7. **[caducidades]** empieza el fragmento de voz «caducidades»
8. desplaza abajo 520 px
9. resalta «Caducidades próximas»
10. **[formador]** empieza el fragmento de voz «formador»
11. desplaza arriba 520 px
12. clic en `button.mz-celda[aria-label^='Marta Sanz · Montaje de la brida B']`
13. espera a que salga «Validar como formador» (máx. 10 s)
14. clic en «Validar como formador»
15. espera a que salga «Confirmar» (máx. 5 s)
16. clic en «Confirmar»
17. pausa de 2,0 s

**Comprobado:** Grabado el 10/10: Lucía en L, Pedro en U, caducidad de Javier a 24 días y Marta validada como formadora (O).

**Notas:** Tras P1 los días hasta la caducidad cambian: comprobar que sigue siendo menos de un mes.

#### 03c-publicar-carmen · Una versión nueva de IT-023 · Carmen Díaz publica la versión 2

* **Quién:** Empleada experta (carmen) · cuenta `carmen`
* **Dónde:** navegador, ruta `/app/instrucciones`
* **Rótulo:** «Una versión nueva de IT-023 · Carmen Díaz publica la versión 2» · «Bases: documentación técnica convertida en formación · renovación y actualización»
* **Duración estimada:** 22 s · **en el vídeo:** 22,9 s desde 10:46, 9,6 s recortados, 1,38 s congelados · **depende de:** 03b-borrador-carmen · **preparación:** Grabar la última (ver orden_grabacion)

**Voz**

> Y cuando cambia el procedimiento, Carmen publica una versión nueva.
>
> **[dialogo]** CidIA avisa: la versión 1 queda obsoleta, la nueva se indexa, se preparan micro-lecciones y preguntas, y quien tenía nivel en esta tarea tendrá que reevaluarse.
>
> **[publicada]** La documentación técnica se convierte en formación, con su historial de versiones.

**Acciones**

1. clic en «Borradores»
2. pausa de 0,6 s
3. clic en `table tbody tr`
4. espera a que salga «Publicar versión 2» (máx. 15 s)
5. clic en «Publicar versión 2»
6. espera a que salga «Al publicarla» (máx. 10 s)
7. **[dialogo]** empieza el fragmento de voz «dialogo»
8. resalta `.ins-lista-confirmar`
9. clic en «Confirmar»
10. espera a que salga «Versión 2 publicada» (máx. 60 s; se acelera con el rótulo «Publicando e indexando la instrucción»)
11. resalta «deberán reevaluarse»
12. **[publicada]** empieza el fragmento de voz «publicada»
13. clic en «Historial»
14. pausa de 1,8 s

**Montaje:** se recortan 17.3-26.9 s de la grabación. Toma única (publicar no se puede repetir): se recortan 9,6 s quietos tras el aviso de publicación.

**Comprobado:** Grabado el 10/10 al final (una sola toma: publicar no se repite sin otro borrador). Aviso «Versión 2 publicada. 3 personas deberán reevaluarse» e historial v2 publicada y v1 obsoleta. En el montaje va en el capítulo 9, después de la matriz.

**Notas:** El texto del enlace del borrador en la tabla puede ser «IT-023 v2» o el título: ajustar el clicTexto. Si se prefiere, abrir directamente desde Captura con «Revisar borrador».

### 10 · Aportaciones

#### 10-tarjeta · tarjeta «El conocimiento que nace en la planta» (3,2 s)

Etiqueta: «Capítulo 10». Subtítulo: «Una nota de voz, la validación del jefe y la cita en el copiloto».

#### 10a-aportar-voz-pedro · Pedro Ruiz, operario de prensas · aporta por voz

* **Quién:** Empleado (pedro) · cuenta `pedro`
* **Dónde:** navegador, ruta `/app/aportaciones` · micrófono: `{voces}/microfono/purga.wav`
* **Rótulo:** «Pedro Ruiz, operario de prensas · aporta por voz» · «Bases: captura del conocimiento de operarios expertos · atraer a nuevas generaciones»
* **Duración estimada:** 24 s · **en el vídeo:** 21,4 s desde 11:12, esperas aceleradas ×11, ×8

**Voz**

> Pedro ve las preguntas que el copiloto todavía no sabe responder.
>
> **[responde]** Sabe cómo se purga el circuito de refrigeración:
>
> **[graba]** lo cuenta en una nota de voz, sin teclear.
>
> **[ordenada]** CidIA la transcribe, la ordena en problema, causa y solución, y se la manda a su jefe.

**Acciones**

1. resalta «Preguntas pendientes en tu departamento»
2. **[responde]** empieza el fragmento de voz «responde»
3. clic en «Yo sé la respuesta» (dentro de `.apo-pregunta:nth-child(2)`)
4. espera a que salga «Respondes a una pregunta pendiente» (máx. 5 s)
5. clic en «Nota de voz» (dentro de `.apo-conmutador`)
6. pausa de 0,6 s
7. **[graba]** empieza el fragmento de voz «graba»
8. mantiene pulsado `button[aria-label='Mantén pulsado para grabar una nota de voz']` mientras el micrófono dice su audio; se acelera con el rótulo «Pedro graba la nota de voz»
9. espera a que salga «Volver a grabar» (máx. 5 s)
10. elige «IT-031» en `.apo-formulario select`
11. clic en «Enviar aportación»
12. espera a que salga «Ordenándose» (máx. 10 s)
13. espera a que desaparezca «Ordenándose» (máx. 400 s; se acelera con el rótulo «El servidor transcribe la nota y la ordena»)
14. **[ordenada]** empieza el fragmento de voz «ordenada»
15. resalta «SOLUCIÓN»

**Comprobado:** Grabado el 10/10 con la voz em_santa (Pedro): nota de 18 s transcrita y ordenada en problema, causa y solución.

**Notas:** En la prueba hice clic en otra laguna por error (había lagunas de prueba): tras P1 en Producción solo quedan la de la prensa 2 (primera) y la de la purga (segunda).

#### 10b-validar-javier · Validar aportaciones · Javier Martín

* **Quién:** Jefe de equipo (javier) · cuenta `javier`
* **Dónde:** navegador, ruta `/app/validar`
* **Rótulo:** «Validar aportaciones · Javier Martín» · «Bases: mejoras añadidas (aportaciones validadas) · trazabilidad hasta versión y autor»
* **Duración estimada:** 21 s · **en el vídeo:** 21,4 s desde 11:32, esperas aceleradas ×3 · **depende de:** 10a-aportar-voz-pedro

**Voz**

> Javier la revisa con la transcripción delante.
>
> **[edita]** El modelo ha mezclado la causa y la solución; lo corrige en un momento
>
> **[valida]** y la valida. Queda publicada con Pedro como autor y Javier como validador, y la laguna se cierra.

**Acciones**

1. resalta `.apo-revision` con la nota «La de Pedro, la más reciente»
2. clic en «Ver la transcripción» (dentro de `.apo-revision`)
3. pausa de 1,5 s
4. **[edita]** empieza el fragmento de voz «edita»
5. clic en «Editar» (dentro de `.apo-revision`)
6. teclea «Purga del circuito de refrigeración del molde (prensa 3)» en `.apo-revision input.apo-titulo-edicion` (borrando lo que había)
7. teclea «Tras cambiar el molde queda aire en las mangueras y la pieza sale mal enfriada.» en `.apo-revision .apo-ficha .apo-bloque:nth-child(1) textarea` (borrando lo que había)
8. teclea «Aire acumulado al desconectar y volver a conectar las mangueras del molde.» en `.apo-revision .apo-ficha .apo-bloque:nth-child(2) textarea` (borrando lo que había)
9. teclea «Para purgar el circuito de refrigeración: con la prensa parada y el molde frío, abre la válvula de purga de la parte alta del molde hasta que el agua salga sin burbujas, unos 30 segundos. Después ciérrala y comprueba que el depósito está por encima de la marca de mínimo.» en `.apo-revision .apo-ficha .apo-bloque:nth-child(3) textarea` (borrando lo que había)
10. **[valida]** empieza el fragmento de voz «valida»
11. clic en «Guardar y validar» (dentro de `.apo-revision`)
12. pausa de 2,5 s

**Montaje:** las acciones 6 a 9 van aceleradas ×3 con el rótulo «Javier corrige el título, el problema, la causa y la solución». Son unos 21 s de tecleo sin narración.

**Comprobado:** Grabado el 10/10: edición de título y bloques y «Publicada. El copiloto ya puede responderlo citando a Pedro Ruiz».

**Notas:** Los selectores de edición salen de Validar.tsx (input.apo-titulo-edicion y un textarea por bloque en .apo-ficha); comprobarlos en un ensayo.

#### 10c-cita-marta · Lo que aprende la planta vuelve a la planta

* **Quién:** Empleada (marta) · cuenta `marta`
* **Dónde:** navegador, ruta `/app/copiloto`
* **Rótulo:** «Lo que aprende la planta vuelve a la planta» · «Bases: acceso inmediato a contenidos · trazabilidad hasta versión y autor»
* **Duración estimada:** 13 s · **en el vídeo:** 15,3 s desde 11:53, esperas aceleradas ×4 · **depende de:** 10b-validar-javier

**Voz**

> Al momento, Marta pregunta lo mismo
>
> **[respuesta]** y el copiloto ya responde, citando a Pedro y a Javier. Lo que aprende la planta vuelve a la planta.

**Acciones**

1. teclea «¿Cómo se purga el circuito de refrigeración?» en `textarea[aria-label='Tu pregunta']`
2. tecla Enter
3. espera `.acciones-respuesta` (máx. 150 s; se acelera con el rótulo «El copiloto busca en la documentación»)
4. **[respuesta]** empieza el fragmento de voz «respuesta»
5. resalta `.burbuja.asistente .globo`
6. clic en `.fuente.citada`
7. espera a que salga «Autoría» (máx. 10 s)
8. resalta «Validado por»
9. pausa de 0,5 s

**Comprobado:** Grabado el 10/10: respuesta con la solución de la purga y fuente «Purga del circuito de refrigeración del molde (prensa 3)» con autoría y validación.

### 11 · Espacio de trabajo

#### 11-tarjeta · tarjeta «El espacio de trabajo del agente» (3,2 s)

Etiqueta: «Capítulo 11». Subtítulo: «Una carpeta privada en el servidor y una consola aislada, sin red».

#### 11a-espacio-javier · Espacio de trabajo · Javier Martín

* **Quién:** Jefe de equipo (javier) · cuenta `javier`
* **Dónde:** navegador, ruta `/app/espacio`
* **Rótulo:** «Espacio de trabajo · Javier Martín» · «Bases: base tecnológica e IA relevante · mejoras añadidas (agente en un espacio aislado)»
* **Duración estimada:** 33 s · **en el vídeo:** 35,3 s desde 12:11, esperas aceleradas ×2 · **preparación:** P5

**Voz**

> Cada persona tiene además un espacio de trabajo privado en el servidor.
>
> **[consola]** La consola ejecuta las órdenes en un contenedor aislado y sin red. Javier sube el registro de paradas de la prensa 3 y lanza un análisis:
>
> **[resultado]** gráfico y tabla en Excel en unos segundos.
>
> **[agente]** La app de escritorio ofrece este mismo espacio a su agente, por MCP y con los permisos de cada persona. Y desde aquí no se sale a Internet: la conexión falla.

**Acciones**

1. resalta «Privada»
2. sube `{salida}/ficheros/paradas-prensa3.csv` con «Subir»
3. espera a que salga «paradas-prensa3.csv» (máx. 15 s)
4. **[consola]** empieza el fragmento de voz «consola»
5. resalta «Aislada · sin red»
6. teclea «python3 informe_paradas.py» en `.consola-entrada input`
7. clic en «Ejecutar»
8. espera a que salga «Guardados paradas-prensa3.png» (máx. 60 s; se acelera con el rótulo «Ejecutando en un contenedor aislado del servidor»)
9. **[resultado]** empieza el fragmento de voz «resultado»
10. clic en «paradas-prensa3.png»
11. pausa de 2,2 s
12. **[agente]** empieza el fragmento de voz «agente»
13. desplaza hasta `.consola-entrada input`
14. clic en `.consola-entrada input`
15. pausa de 0,3 s
16. teclea «python3 -c "import socket; socket.create_connection(('example.com', 80), 3)"» en `.consola-entrada input`
17. clic en «Ejecutar»
18. espera a que salga «Traceback» (máx. 30 s)
19. resalta `.consola-salida, .consola pre, pre` con la nota «Sin red: la conexión falla»
20. pausa de 1,2 s

**Comprobado:** Grabado el 10/10: análisis en 3,6 s (gráfico y Excel) y la conexión a example.com falla con Traceback (sin red).

**Notas:** Limpiar después la carpeta de Javier (los tres ficheros) si se repite la toma. El texto exacto del error de red puede variar: esperar «Error» o el código de salida distinto de 0 que muestra la consola.

#### 11b-agente-app · El agente de la app usa el espacio por MCP (fuera del vídeo)

* **Quién:** Jefe de equipo (javier) en la app de escritorio
* **Dónde:** app de escritorio (CDP en el puerto 9333)
* **Rótulo:** «El agente de la app usa el espacio por MCP» · «Bases: integración (MCP y API compatible con OpenAI)»
* **Duración estimada:** 10 s

**Voz**

> Desde la app, el agente usa esas mismas herramientas del servidor, siempre con los permisos de la persona.

**Acciones**

1. clic en «Nueva conversación»
2. teclea «Usa la herramienta mcp__cidia__espacio_listar y dime qué ficheros hay en mi carpeta de trabajo.» en `textarea, [contenteditable=true]`
3. tecla Enter
4. espera a que salga «paradas-prensa3» (máx. 180 s; se acelera con el rótulo «El agente llama a la herramienta del servidor»)

**Comprobado:** Probado el 10/10 en la app con Lucía: con qwen3:0.6b el agente no llama a las herramientas MCP ni siquiera nombrándolas y responde sin fuentes (inventa). Se deja fuera del vídeo; la frase de 11a dice solo lo que hay (el espacio se ofrece al agente por MCP).

**Notas:** Solo si sale bien en un ensayo. Si no, se queda fuera y basta la frase final de 11a.

### 12 · Administración

#### 12-tarjeta · tarjeta «La administración, dentro de la misma app» (3,2 s)

Etiqueta: «Capítulo 12». Subtítulo: «Organización, empleados, modelos permitidos, registro xAPI y sistema».

#### 12a-organizacion-admin · Organización · departamentos, puestos, tareas, niveles y reglas ILUO

* **Quién:** Administración (admin) · cuenta `admin`
* **Dónde:** navegador, ruta `/app/admin/organizacion`
* **Rótulo:** «Organización · departamentos, puestos, tareas, niveles y reglas ILUO» · «Bases: adaptación a cada empresa (20 %) · gestión de niveles»
* **Duración estimada:** 27 s · **en el vídeo:** 24,4 s desde 12:48

**Voz**

> La administración define la organización: departamentos, puestos y tareas, cada una con su nivel, su criticidad y sus riesgos de prevención.
>
> **[niveles]** Los niveles deciden qué documentos encuentra cada persona.
>
> **[reglas]** Y aquí se ajustan las reglas de cada nivel ILUO: ejecuciones, nota del cuestionario y caducidad. Cada empresa lo adapta a su forma de trabajar.

**Acciones**

1. pausa de 0,6 s
2. clic en «IT-023»
3. espera a que salga «Criticidad» (máx. 8 s)
4. resalta «Criticidad»
5. resalta «Riesgos PRL»
6. **[niveles]** empieza el fragmento de voz «niveles»
7. clic en «Niveles»
8. espera a que salga «Niveles de responsabilidad» (máx. 8 s)
9. resalta «Cómo funcionan los niveles»
10. **[reglas]** empieza el fragmento de voz «reglas»
11. clic en «Empresa y reglas ILUO»
12. espera a que salga «Reglas ILUO» (máx. 8 s)
13. desplaza abajo 420 px
14. resalta «Así quedan los niveles»

**Comprobado:** Visto hoy: árbol con 4 departamentos, 9 puestos y 23 tareas; ficha de IT-023 (nombre, código, puesto, nivel mínimo, criticidad, descripción, riesgos PRL, tarea activa); pestaña Niveles (Operario, Técnico, Responsable, Dirección y «Cómo funcionan los niveles»); pestaña «Empresa y reglas ILUO» (ejecuciones para L, umbral 80 %, validez en meses y «Así quedan los niveles»).

#### 12b-empleados-admin · Empleados · cuentas, roles, formaciones e identidad

* **Quién:** Administración (admin) · cuenta `admin`
* **Dónde:** navegador, ruta `/app/admin/empleados`
* **Rótulo:** «Empleados · cuentas, roles, formaciones e identidad» · «Bases: integración con los sistemas existentes · incrementar la polivalencia»
* **Duración estimada:** 19 s · **en el vídeo:** 18,2 s desde 13:12 · **preparación:** P2

**Voz**

> En Empleados, cuentas, roles, niveles y formaciones en otros departamentos, como la de Marta.
>
> **[identidad]** Las cuentas pueden ser de CidIA o venir del directorio de la empresa: el módulo de identidad está preparado.

**Acciones**

1. pausa de 0,6 s
2. resalta `table`
3. clic en «Marta Sanz»
4. espera a que salga «Datos y acceso» (máx. 8 s)
5. clic en «Formaciones»
6. pausa de 1,2 s
7. resalta «Diseño de utillajes» (su `li, .tarjeta, div[class*=formacion], div[class*=fila]`) con la nota «Formación en otro departamento»
8. tecla Escape
9. **[identidad]** empieza el fragmento de voz «identidad»
10. clic en «Nueva persona»
11. espera a que salga «Origen de la identidad» (máx. 8 s)
12. resalta «Origen de la identidad» con la nota «Cuenta de CidIA, directorio LDAP o inicio de sesión único»
13. tecla Escape

**Comprobado:** Visto hoy: tabla con filtros, ficha de Marta (pestañas «Datos y acceso» y «Formaciones 1», rol, departamento, puesto, nivel, experto, «Restablecer contraseña»), «Nueva persona» con «Origen de la identidad: Cuenta de CidIA, Directorio de la empresa (LDAP), Inicio de sesión único (OIDC)» y «CidIA genera una contraseña inicial que verás una sola vez».

**Notas:** No crear la cuenta en la escena: se cierra el panel.

#### 12c-modelos-admin · Modelos permitidos · solo locales

* **Quién:** Administración (admin) · cuenta `admin`
* **Dónde:** navegador, ruta `/app/admin/modelos`
* **Rótulo:** «Modelos permitidos · solo locales» · «Bases: bajo coste (15 %) · proteger el conocimiento experto»
* **Duración estimada:** 20 s · **en el vídeo:** 15,9 s desde 13:30

**Voz**

> En Modelos se decide qué IA se usa para el chat, la visión y la búsqueda. Todos se ejecutan en el servidor de la empresa.
>
> **[nube]** Los servicios en la nube están bloqueados y nadie puede poner sus claves: sin nube, sin pago por consulta.

**Acciones**

1. pausa de 0,6 s
2. resalta «CHAT Y COPILOTO»
3. resalta «VISIÓN»
4. **[nube]** empieza el fragmento de voz «nube»
5. desplaza abajo 380 px
6. resalta «EN LA NUBE»

**Comprobado:** Grabado el 10/10. La fila «DeepSeek» de los proveedores en la nube (bloqueado) se oculta en la grabación por la regla de no mostrar esa marca; quedan Gemini, OpenAI y OpenRouter.

**Notas:** La interfaz lista «DeepSeek» entre los proveedores en la nube bloqueados: conviene quitarlo o renombrarlo en el producto (regla del equipo: ningún rastro de esa marca).

#### 12d-registro-admin · Registro de actividad en xAPI y auditoría

* **Quién:** Administración (admin) · cuenta `admin`
* **Dónde:** navegador, ruta `/app/admin/registro`
* **Rótulo:** «Registro de actividad en xAPI y auditoría» · «Bases: registro de actividades · auditoría y trazabilidad · integración»
* **Duración estimada:** 20 s · **en el vídeo:** 18,1 s desde 13:45

**Voz**

> Toda la actividad queda en xAPI, el estándar de la formación: quién preguntó, quién completó una tarea, quién alcanzó un nivel. Se filtra y se exporta.
>
> **[auditoria]** Y cada cambio de administración queda en la auditoría.

**Acciones**

1. pausa de 0,6 s
2. resalta `main`
3. elige «alcanzó el nivel» en `select`
4. pausa de 1,5 s
5. clic en «Ver sentencia»
6. espera `pre.adm-json` (máx. 5 s)
7. resalta `pre.adm-json` con la nota «La sentencia xAPI completa»
8. clic en «Ocultar»
9. resalta «Exportar JSON»
10. **[auditoria]** empieza el fragmento de voz «auditoria»
11. clic en «Auditoría»
12. pausa de 1,8 s

**Comprobado:** Visto hoy: pestañas «Actividad (xAPI)» y «Auditoría», filtros de persona, acción (incluye «alcanzó el nivel»), objeto y fechas, «Exportar JSON», «Ver sentencia» y paginación (569 sentencias, 15 páginas). «Ver sentencia» despliega la sentencia en línea (pre.adm-json) y el botón pasa a «Ocultar» (comprobado: no abre un diálogo).

#### 12e-sistema-admin · Sistema · estado real del servidor

* **Quién:** Administración (admin) · cuenta `admin`
* **Dónde:** navegador, ruta `/app/admin/sistema`
* **Rótulo:** «Sistema · estado real del servidor» · «Bases: aplicable en entornos industriales reales · escalabilidad»
* **Duración estimada:** 7 s · **en el vídeo:** 4,5 s desde 14:03

**Voz**

> Y el estado del servidor, comprobado al momento.

**Acciones**

1. resalta «Todo funciona»
2. desplaza abajo 380 px
3. pausa de 1,5 s

**Comprobado:** Visto hoy: «Todo funciona», CidIA 0.1.0, motor propio PostgreSQL + pgvector, servicios con su latencia, documentos por estado y trabajos recientes.

### 13 · Cómo cubre las bases

#### 13a-cobertura · tarjeta «Cobertura funcional» (14,2 s)

Etiqueta: «Criterio de las bases · 40 %». Subtítulo: «El ciclo completo funciona: capturar, estructurar, formar, acompañar, evaluar y certificar. 27 de los 30 puntos del alcance se demuestran y 3 aparecen simplificados.».

> Así cubre CidIA las bases. Cobertura funcional, el cuarenta por ciento: el ciclo completo funciona de verdad, con veintisiete de los treinta puntos del alcance demostrados y tres simplificados.

#### 13b-adaptacion · tarjeta «Adaptación a cada empresa» (11,7 s)

Etiqueta: «Criterio de las bases · 20 %». Subtítulo: «Departamentos, puestos, niveles y reglas ILUO configurables. Tres configuraciones de servidor: del PC de una pyme a un servidor con GPU para varias plantas.».

> Adaptación a cada empresa: organización, niveles y reglas configurables, y tres configuraciones de servidor, del PC de una pyme a un servidor con GPU.

#### 13c-coste · tarjeta «Bajo coste» (6,7 s)

Etiqueta: «Criterio de las bases · 15 %». Subtítulo: «Todo en local y sobre software libre. Sin pago por consulta ni por usuario: el único desembolso relevante es el hardware.».

> Bajo coste: todo en local y libre, sin pago por consulta ni por usuario.

#### 13d-mejoras · tarjeta «Mejoras añadidas» (9,1 s)

Etiqueta: «Criterio de las bases · 15 %». Subtítulo: «Tutor socrático, aportaciones desde la planta validadas por el jefe, lagunas de conocimiento y espacio de trabajo aislado para el agente.».

> Mejoras añadidas: el tutor socrático, las aportaciones validadas, las lagunas y el espacio de trabajo del agente.

#### 13e-innovacion · tarjeta «Grado de innovación» (9,3 s)

Etiqueta: «Criterio de las bases · 10 %». Subtítulo: «La combinación: el ciclo completo con IA en local, progreso basado en evidencias y un conocimiento que crece desde la propia planta.».

> Y la innovación está en la combinación: el ciclo completo, en local, con evidencias y con un saber que crece desde la planta.

#### 13f-implantacion · tarjeta «Un instalador para el servidor y otro para los puestos» (16,9 s)

Etiqueta: «Implantación sencilla y licencias libres». Subtítulo: «instalar-servidor.sh deja cualquier Ubuntu listo · CidIA-Setup.exe en cada portátil · Ejemplo: 1 servidor y 5 puestos, unos 6.200 € con IVA en hardware · Software libre con licencias que permiten el uso comercial».

> Se implanta con un instalador para el servidor y otro para los portátiles. Para una pyme, un servidor y cinco puestos cuestan unos seis mil doscientos euros en hardware, sin cuotas. Y todo el software es libre, con licencias que permiten el uso comercial.

#### 13g-final · tarjeta «CidIA» (7,7 s)

Etiqueta: «Rodrigo Pascual · Lydia Blanco · Gadea Lucas · Universidad de Burgos». Subtítulo: «El conocimiento se queda».

> CidIA: el conocimiento de la planta, capturado, enseñado y medido, sin salir de la empresa.

## Incidencias encontradas al preparar y grabar el vídeo

* **I1 (resuelta).** Modo planta: el copiloto respondía «, no lo sabes.» a cualquier pregunta del paso. servicios/consulta.py: con tarea en curso la evidencia se comprueba con la pregunta (no con el nombre de la tarea y el título del paso) y el eco de la regla («, no lo sabes.») ya no llega a la persona. Pruebas nuevas en tests/test_consulta.py; desplegado en Oracle.
* **I2 (mejorada).** Preguntas razonables que el modelo pequeño no responde. Se eligen preguntas que funcionan («¿Con qué llave aprieto?», «¿Quién aprueba compras de más de 12.000 €?») y consulta.py prefiere ahora la frase que repite las palabras y cifras de la pregunta, da la «Solución» de una ficha en vez de su «Problema» y quita el «La respuesta está en el fragmento [n].» del reintento. Sigue sin casar «aprieta» con «apretar».
* **I3 (sin cambios).** qwen3:1.7b descargado y sin registrar.
* **I4 (resuelta en el guion).** Si la foto coincide con la referencia no pasa a «Fotos por revisar». 06c enseña «Todas» y da por buena la de hoy.
* **I5 (resuelta en la grabación).** Conversaciones de pruebas en «Espacios» de la app. Se ocultan con «ocultar_css» mientras se graba (no se borran).
* **I6 (sin cambios).** «Faltan -2 ejecuciones completadas» en un requisito cumplido (no se ve en pantalla).
* **I7 (resuelta).** Datos de prueba acumulados. Semilla de nuevo antes de grabar (dos veces: antes y después de la primera captura).
* **I8 (abierta).** Administración › Modelos muestra «DeepSeek» como proveedor en la nube bloqueado. Oculto en la grabación; conviene quitarlo del producto.
* **I9 (abierta).** El agente de la app no usa las herramientas MCP con qwen3:0.6b. 11b fuera del vídeo; probar con un modelo mayor (perfil del MSI).
* **I10 (resuelta).** Revisión del montaje (fotogramas cada 3 s, transcripción con Whisper y lectura de los subtítulos): entre 06a y 06b se volvía a la lista de tareas y salía una pantalla de carga; tres tecleos largos sin narración (10b, 21 s; 03d, 5 s; 08c, 7 s); subtítulos de menos de un segundo, desordenados alrededor de la voz del micrófono y uno solapado al final. Recorte del inicio de 06b, «acelerar_tramos» con rótulo en los tecleos y subtítulos ordenados, sin solapes y con los trozos cortos unidos (montaje.py). El vídeo pasa de 15:42 a 15:20.

## Cómo se usa con las herramientas

1. Voz: `python herramientas/video/voz.py narrar docs/video/recorrido.json --salida <voces>` y los audios del micrófono con `voz.py frase … --microfono`.
2. Grabación, escena a escena y en el orden de grabación: `node herramientas/video/grabador.mjs docs/video/recorrido.json --solo <id> --salida <grabaciones> --voces <voces> --secretos <cidia.env>`. Las de la app de escritorio llevan `conectar` en la escena (la app abierta con `--remote-debugging-port=9333`).
3. Montaje: `python herramientas/video/montaje.py docs/video/recorrido.json --grabaciones <grabaciones> --voces <voces> --salida 04_VIDEO/CidIA-recorrido-completo.mp4 --musica` (y lo mismo con `resumen.json` para el resumen).
4. Revisar el informe del grabador de cada escena (fallos, consola, peticiones fallidas) y unos fotogramas; si una respuesta del modelo sale mal, repetir solo esa escena.
