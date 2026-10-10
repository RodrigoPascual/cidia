# Datos de demostración de CidIA

Todo lo que hay en esta carpeta es **sintético**. «Metalúrgica Arlanza, S. L.» es una empresa
ficticia de Burgos: sus personas, proveedores, precios, códigos de piezas y máquinas son inventados.
No hay ningún dato real ni confidencial.

La semilla (`servidor/gateway/cidia/semilla.py`) carga en una base vacía la organización, las
personas, los documentos, las instrucciones y seis semanas de actividad coherente, con sus
sentencias xAPI. Esta carpeta guarda copias de los documentos y los medios para probar la
captura y las aportaciones por voz.

## Cómo se cargan

* **Al arrancar el servidor**: con `CIDIA_CREAR_SEMILLA=true` (ya puesto en `perfiles/oracle.env`).
  Si la base está vacía, la semilla se encola como trabajo en segundo plano: el servidor arranca
  enseguida y los datos aparecen en uno o dos minutos (espera a que responda el modelo de
  embeddings). Su estado se ve en Administración › Sistema. Si la base ya está sembrada no hace
  nada, y si tiene datos propios (departamentos, documentos o personas que no puso la semilla)
  tampoco: nunca mezcla cuentas de demostración con una instalación de verdad.
* **A mano**: `python -m cidia.semilla` dentro del contenedor o del entorno del gateway.
  `python -m cidia.semilla --forzar` vacía el contenido de demostración y vuelve a sembrar
  (solo para servidores de demostración: borra todos los documentos, instrucciones y actividad,
  también lo que se haya añadido después). En una base con datos propios se niega. Si ya hay
  otra siembra en marcha (por ejemplo, la del arranque mientras espera al modelo), no empieza
  otra: avisa y hay que esperar a que termine.
* **Contraseña**: todas las cuentas de demostración comparten la de la variable
  `CIDIA_DEMO_CONTRASENA` (del entorno o del fichero `.env` del gateway). Si no está definida,
  la semilla genera una aleatoria y la guarda en
  `<directorio de datos>/usuarios-demo.txt`, legible solo por su propietario. Nunca aparece en
  los registros ni en este documento. Si `CIDIA_ADMIN_CONTRASENA` creó antes la cuenta `admin`,
  esa cuenta conserva su contraseña.

## Quién es quién

| Usuario | Persona | Departamento | Nivel | Rol | Para enseñar |
|---|---|---|---|---|---|
| `ana` | Ana López | Oficina técnica | 3 · Responsable | Jefa, experta | Ve los costes de utillaje (nivel 3); valida formadores; nivel O en IT-051 |
| `luis` | Luis García | Oficina técnica | 1 · Operario (técnico junior) | Empleado | Curva de autonomía en IT-051 (7 → 1 consultas); nivel L; no ve los costes |
| `raul` | Raúl Gómez | Oficina técnica | 2 · Técnico | Empleado | Nivel U en IT-051 tras la observación de Ana |
| `javier` | Javier Martín | Producción | 3 · Responsable | Jefe, experto | Bandeja de aportaciones y lagunas; su nivel O en IT-031 caduca en menos de un mes |
| `carmen` | Carmen Díaz | Producción | 2 · Técnico | Experta | Autora de IT-023 (brida B); nivel O; ideal para la captura de vídeo |
| `marta` | Marta Sanz | Producción | 2 · Técnico | Empleada | Formación activa en Oficina técnica; curva de autonomía en IT-023 (8 → 0); nivel U |
| `pedro` | Pedro Ruiz | Producción | 1 · Operario | Empleado | Autor de la solución validada del atasco de la prensa 3; nivel L en IT-031 |
| `lucia` | Lucía Herrero | Producción | 1 · Operario | Empleada | Recién incorporada: nivel I en IT-023; nota de voz pendiente sobre las juntas |
| `elena` | Elena Moreno | Calidad | 3 · Responsable | Jefa, experta | Autora de IT-061 versión 2 |
| `david` | David Ortega | Calidad | 2 · Técnico | Empleado | Nivel U en IT-061 pendiente de reevaluación por la versión 2 |
| `irene` | Irene Castro | Calidad | 1 · Operario | Empleada | Formación activa en Producción (prensas) |
| `jorge` | Jorge Barrio | Mantenimiento | 3 · Responsable | Jefe, experto | Revisor de IT-071 |
| `nuria` | Nuria Gil | Mantenimiento | 2 · Técnico | Experta | Autora de IT-071 (sensor S4); tiene 2 preguntas propuestas por revisar |
| `oscar` | Óscar Peña | Mantenimiento | 2 · Técnico | Empleado | Nivel L en IT-071 |
| `admin` | Administración | (ninguno) | 4 · Dirección | Administración | Organización, empleados, modelos, registro xAPI y sistema |

## Qué hay

**Organización.** Cuatro departamentos con su color (Producción, Oficina técnica, Calidad y
Mantenimiento), los cuatro niveles por defecto, 9 puestos y 23 tareas con código IT-0xx,
criticidad y riesgos de prevención. Formaciones en otro departamento, asignadas por la
administración: Marta en Oficina técnica e Irene en Producción (activas) y David en Oficina
técnica (completada).

**Documentos** (copias en `documentos/`, todos indexados para la búsqueda híbrida):

| Documento | Departamento · nivel | Formación | Ana | Luis | Marta | Pedro |
|---|---|---|---|---|---|---|
| Bienvenida y PRL | Público | | ✓ | ✓ | ✓ | ✓ |
| Manual de iniciación a Oficina técnica | O. técnica · 1 | sí | ✓ | ✓ | ✓ (se forma en OT) | |
| Procedimiento de diseño de utillajes (PR-OT-02) | O. técnica · 2 | | ✓ | | | |
| Costes y proveedores de utillaje | O. técnica · 3 | | ✓ | | | |
| Instrucción de montaje de la línea 2 (PDF) | Producción · 1 | | | | ✓ | ✓ |
| Solución validada: atasco en la prensa 3 (aportación de Pedro) | Producción · 1 | | | | ✓ | ✓ |
| Guía de acogida en Producción | Producción · 1 | sí | | | ✓ | ✓ |
| Manual de manejo de la prensa 3 | Producción · 2 | | | | ✓ | |
| Plan de mantenimiento preventivo de prensas (PDF) | Mantenimiento · 1 | | | | | |
| Procedimiento de consignación de máquinas | Mantenimiento · 1 | sí | | | | |
| Plan de control de calidad del colector CL-200 | Calidad · 2 | | | | | |
| Guía de iniciación a Calidad | Calidad · 1 | sí | | | | |

Las seis primeras filas son la matriz de permisos del plan (Ana, Luis, Marta y Pedro); la prueba
`servidor/gateway/tests/test_semilla.py` comprueba que se cumple con los documentos sembrados.

**Instrucciones publicadas** (una imagen esquemática por paso, generada por la semilla):

| Código | Instrucción | Pasos | Críticos | Material |
|---|---|---|---|---|
| IT-023 | Montaje de la brida B | 7 | Paso 3: 4 tornillos en cruz a 25 N·m con llave dinamométrica de 1/2" | 3 micro-lecciones, 6 preguntas |
| IT-031 | Cambio de molde en la prensa 3 | 8 | Consignación y amarre a 180 bar | 3 micro-lecciones, 5 preguntas |
| IT-051 | Diseño de utillaje de soldadura | 6 | Referencias 3-2-1 y accesibilidad de la antorcha | 5 preguntas y 2 propuestas |
| IT-061 | Inspección dimensional con calibre (versión 2; la 1 está obsoleta) | 6 | Medición de las cotas | 4 preguntas |
| IT-071 | Calibración del sensor S4 de la prensa 3 | 6 | Consignación y ajuste de sensibilidad | 4 preguntas y 2 propuestas |

**Actividad de las últimas seis semanas.**

* Aportaciones: «Atasco en la prensa 3 al cambiar de molde: limpiar el sensor S4» (nota de voz de
  Pedro, validada por Javier, resuelve una laguna) y dos pendientes en la bandeja de Javier: el
  cambio de bobina de film sin parar la línea (Marta, por texto) y las juntas JT-80 pegadas (Lucía,
  nota de voz de hace dos horas).
* Lagunas abiertas: «¿Qué presión lleva el cilindro de la prensa 2?» (3 veces) y «¿Cómo se purga el
  circuito de refrigeración?» (2 veces) en Producción; en Oficina técnica, quién aprueba una compra
  de utillaje de más de 3.000 € (Luis no ve el documento de costes). Ningún documento responde a
  estas preguntas, a propósito.
* Modo planta: 35 ejecuciones con sus consultas por paso. Marta en IT-023 pasa de 8 consultas a 0;
  Luis en IT-051 de 7 a 1.
* Evaluación: cuestionarios aprobados y suspendidos, 5 observaciones (la de Pedro en IT-031 no
  superada por un paso crítico) y niveles ILUO I, L, U y O con fechas y caducidades. Los niveles
  ganados con CidIA coinciden con lo que calcula el servicio ILUO con las evidencias; los de los
  expertos vienen de la «matriz en papel» anterior.
* Unas 490 sentencias xAPI coherentes con todo lo anterior (subió, publicó, inició, confirmó,
  preguntó, completó, vio, aprobó, observó, aportó, validó, alcanzó el nivel...).

## Guion de demostración (unos 3 minutos)

Prepara dos ventanas: una con `carmen` (o `javier`) y otra con la persona que aprende. Ten a mano
`video/brida-b-sintetico.mp4`.

1. **El problema · 0:00.** Con `admin`, Inicio: «Metalúrgica Arlanza». Abre Organización y
   enseña los cuatro departamentos y la tarea IT-023 de la línea 2. Una frase: «Carmen es la que
   sabe montar la brida B; cuando se jubile, esto se pierde».
2. **La captura · 0:25.** Con `carmen`, Captura › subir vídeo: `video/brida-b-sintetico.mp4`
   (un minuto, siete escenas narradas). Mientras se procesa, enseña la instrucción IT-023 ya
   publicada en Instrucciones: siete pasos con imagen, el paso 3 marcado como crítico.
3. **La validación · 0:55.** Abre el borrador generado por el vídeo, corrige un texto y marca el
   paso 3 como crítico. Si lo publicas, queda como versión 2, la 1 pasa a obsoleta y CidIA marca
   a Marta y a Carmen para reevaluación (se ve en el paso 5). Si el procesado tarda, enseña la
   diferencia entre versiones con IT-061 (la versión 2 añadió «Aclimatar la pieza» y David quedó
   pendiente de reevaluación).
4. **El aprendizaje · 1:25.** Con `lucia`, Modo planta › IT-023. Avanza hasta el paso 3 y pregunta
   por voz «¿Qué llave uso?»: la respuesta cita IT-023, paso 3 (llave dinamométrica de media
   pulgada). Confirma el paso crítico. En el Copiloto, con `marta`, pregunta «La prensa 3 se ha
   atascado al cambiar el molde, ¿qué hago?»: cita la solución de Pedro validada por Javier.
5. **El progreso · 2:05.** Con `javier`, Progreso del equipo: Marta con nivel U en la brida B y su
   curva de autonomía (de 8 consultas a 0); su propio nivel O en IT-031 avisa de que caduca pronto.
   Validar aportaciones: dos pendientes (una nota de voz de Lucía de hace dos horas). Lagunas:
   «¿Qué presión lleva el cilindro de la prensa 2?» preguntada tres veces.
6. **Permisos y cierre · 2:35.** Con `luis`, pregunta «¿Quién aprueba la compra de un utillaje de
   más de 3.000 €?»: no ve el documento de costes (es de nivel 3), así que CidIA no lo cita ni
   revela que existe, y la pregunta queda como laguna.
   Con `ana`, la misma pregunta se responde con el documento de costes. Con `marta`, el Manual de
   iniciación a Oficina técnica aparece porque se está formando allí. Cierra con Registro de
   actividad (xAPI) de `admin`.

Para repetir el ensayo desde el mismo punto: `python -m cidia.semilla --forzar` en el servidor.

## Ficheros de esta carpeta

| Ruta | Qué es |
|---|---|
| `documentos/` | Copias de los 11 documentos de conocimiento (9 en Markdown y 2 en PDF con texto real). |
| `video/brida-b-sintetico.mp4` | Vídeo narrado sintético de 58 s (1280×720, H.264 con OpenH264 y AAC) del montaje de la brida B, una escena de color por paso. Para probar la captura. |
| `video/generar_medios.py` | Script que genera el vídeo y las notas de voz. |
| `audio/aportacion-prensa3.ogg`, `audio/aportacion-juntas.ogg` | Notas de voz sintéticas (Ogg Opus) de las aportaciones de Pedro y Lucía. Sirven también para probar «Aportar por voz». La semilla las adjunta desde `cidia/semilla_datos/audio/`. |

## Cómo regenerarlo

* Documentos: `servidor/gateway/.venv/Scripts/python -m cidia.semilla --exportar datos-demo/documentos`
  (desde `servidor/gateway`, ajustando la ruta). Los textos viven en `cidia/semilla_datos/documentos.py`
  y los PDF los genera `cidia/semilla_datos/pdf.py` sin dependencias externas.
* Vídeo y notas de voz (Windows): `servidor/gateway/.venv/Scripts/python datos-demo/video/generar_medios.py`.
  Necesita la síntesis de voz de Windows (System.Speech) con una voz en castellano, por ejemplo
  «Microsoft Helena Desktop» (es la que se usó: por eso la nota de «Pedro» tiene voz femenina), y
  ffmpeg: usa la compilación LGPL de BtbN de `servidor/gateway/.herramientas/` o, si no está,
  cualquiera del PATH. Las escenas son las mismas imágenes esquemáticas que la semilla genera para
  los pasos, sobre un fondo de color distinto en cada escena para que el detector de cambios de
  escena separe los pasos. La narración está en `cidia/semilla_datos/instrucciones.py` (IT-023).
* Sin Windows: cualquier síntesis de voz que produzca WAV sirve; basta con sustituir la función
  `sintetizar` del script.
