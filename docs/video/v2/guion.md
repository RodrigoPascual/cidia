# Guion v2 de CidIA · recorrido sistemático por funcionalidades

Generado con `herramientas/video/guion_v2.py` a partir de `docs/video/v2/recorrido.json` y de los informes de las tomas de `--grabaciones`. Duraciones medidas con la narración ya sintetizada (supertonic:M1; si cambia la voz, se vuelve a sintetizar y a ejecutar este guion). Fecha del guion: 2026-10-11.

**Vídeo completo: 14:47** (887 s) con 25 funcionalidades grabadas · **resumen: 4:21** (261 s). Falta 1 por grabar (sección 6).

Son los tiempos del guion (escenas y voz). El vídeo montado dura más, porque las tarjetas de funcionalidad se alargan para que se puedan leer y el panel de resultado no tapa la última acción: las duraciones reales están en `04_VIDEO/v2/final/*.informe.json` y en los capítulos (nota del apartado 8).

## 1. La idea

El vídeo enseña todas las funcionalidades de CidIA con el mismo patrón, para que el jurado sepa siempre dónde está y para qué sirve lo que ve:

1. **Tarjeta «Funcionalidad N · nombre»** con quién la usa (rol y persona del ejemplo).
2. **Para qué sirve en la planta**, en una frase, dicha sobre la tarjeta.
3. **Demostración real** con Metalúrgica Arlanza: solo acciones que están en las tomas grabadas el 10/10, con sus tiempos.
4. **Resultado** en una frase y, en un panel, los **puntos de las bases** que cubre.

Empieza con el problema, el ejemplo (la empresa ficticia y su gente) y un **mapa de funcionalidades** organizado por el ciclo que piden las bases: capturar, estructurar, formar, acompañar, evaluar y certificar, con el acceso delante y la administración debajo. Antes de cada bloque se vuelve al mapa con ese bloque encendido. El cierre repasa los cinco criterios (40, 20, 15, 15 y 10 %), la implantación y las licencias.

Por qué así (decidido sin preguntar, como se pidió):

* **Por el ciclo de las bases y no por pantallas.** El 40 % de la nota es cobertura funcional y las bases describen un ciclo; ordenar por ese ciclo deja ver que no falta ningún paso. Las pantallas de la app ya se ven dentro de cada funcionalidad.
* **Una funcionalidad, una idea.** Cada tarjeta responde a una pregunta del jurado («¿quién lo usa?, ¿para qué?») y cada resultado, a «¿y qué gano?». El rótulo de bases sale al final, cuando ya se ha visto la prueba.
* **Mismo ejemplo de principio a fin.** La brida B (IT-023) y la prensa 3 (IT-031) atraviesan todo el ciclo: Carmen captura, Lucía aprende y la ejecuta, Javier evalúa y certifica. Los errores reales de los modelos se enseñan y se corrigen en pantalla.
* **Más corto que la v1 sin perder nada.** La narración es más breve y concreta; los ratos en que el grabador esperó a la voz larga de la v1 se recortan (pantalla quieta), las esperas del servidor se aceleran con su rótulo como en la v1, los clics repetidos (las seis respuestas del cuestionario y los ocho pasos de la observación) van a ×3 y el tecleo de las preguntas a ×2, siempre con su rótulo. Nada se acelera ni se corta sin avisar, salvo ratos con la pantalla quieta.
* **Compatible.** El proyecto se monta ya con `montaje.py` (tarjetas sencillas). El montaje v2 usa los campos nuevos para el diseño nuevo: mapa, tarjeta de funcionalidad, panel de resultado con bases, criterios.

## 2. Mapa de funcionalidades

| Bloque | N | Funcionalidad | Quién la usa | Tomas | Estado |
|---|---|---|---|---|---|
| 1 · Entrar | 1 | App de escritorio y acceso público | Cualquier persona, sin iniciar sesión | 02a2-app-invitado | grabada |
| 1 · Entrar | 2 | Cada rol ve lo suyo | Todos los roles | 02b2-app-sesion-lucia, 02c-jefe-javier, 02d-admin | grabada |
| 1 · Entrar | 3 | Mi perfil: contraseña y memoria personal | Cualquier empleado | 02e-perfil-lucia | grabada |
| 2 · Capturar | 4 | Del vídeo a la instrucción | Experta | 03a-captura-video-carmen, 03b-borrador-carmen | grabada |
| 2 · Capturar | 5 | Nota de voz convertida en ficha | Experta | 03d-nota-voz-carmen | grabada |
| 2 · Capturar | 6 | Entrevista guiada | Experta | 03e-entrevista-carmen | grabada |
| 3 · Estructurar | 7 | Biblioteca de documentos | Jefe de equipo | 04a-documentos-javier | grabada |
| 3 · Estructurar | 8 | Búsqueda con permisos | Responsable y recién llegado | 04b-probar-busqueda-ana, 04c-luis-sin-acceso | grabada |
| 4 · Formar | 9 | Itinerario y micro-lecciones | Operaria recién llegada | 07a-itinerario-lucia, 07b-microleccion-tutor-lucia | grabada |
| 4 · Formar | 10 | Tutor socrático | Técnica en formación | 05b-socratico-marta | grabada |
| 4 · Formar | 11 | Formación cruzada | Técnica | 07c-formacion-cruzada-marta | grabada |
| 5 · Acompañar | 12 | Copiloto con fuentes, por voz | Técnica de la línea 2 | 05a-copiloto-voz-marta | grabada |
| 5 · Acompañar | 13 | Modo planta paso a paso | Operaria recién llegada | 06-planta-lucia | grabada |
| 5 · Acompañar | 14 | Foto del resultado, revisada | Jefe de equipo | 06c-foto-javier | grabada |
| 5 · Acompañar | 15 | Lagunas de conocimiento | Técnica y jefe de equipo | 05c-laguna-marta, 05d-lagunas-javier | grabada |
| 5 · Acompañar | 16 | Aportaciones desde la planta | Operario y jefe de equipo | 10a-aportar-voz-pedro, 10b-validar-javier, 10c-cita-marta | grabada |
| 6 · Evaluar | 17 | Cuestionario aprobado por un experto | Experta y operaria | 08b-revisar-preguntas-nuria, 08a-cuestionario-lucia | grabada |
| 6 · Evaluar | 18 | Observación en el puesto | Jefe de equipo | 08c-observacion-javier | grabada |
| 7 · Certificar | 19 | Pasaporte de habilidades | Cada persona | 09a-pasaporte-marta | grabada |
| 7 · Certificar | 20 | Matriz ILUO del equipo | Jefe de equipo | 09b-matriz-javier | grabada |
| 7 · Certificar | 21 | Versiones nuevas y reevaluación | Experta | 03c-publicar-carmen | grabada |
| 8 · Administrar | 22 | Espacio de trabajo aislado | Jefe de equipo | 11a-espacio-javier | grabada |
| 8 · Administrar | 23 | Organización, personas e identidad | Administración | 12a-organizacion-admin, 12b-empleados-admin | grabada |
| 8 · Administrar | 24 | Modelos solo locales | Administración | 12c2-modelos-admin | grabada |
| 8 · Administrar | 25 | Registro xAPI, auditoría y estado | Administración | 12d-registro-admin, 12e-sistema-admin | grabada |
| 8 · Administrar | - | Agente de escritorio con herramientas | Jefe de equipo, en la app de escritorio | 11b-agente-app | **requiere grabación** |

## 3. Escaleta y tiempos

| Empieza | Pieza | Qué es | Dura | Ajustes |
|---|---|---|---|---|
| 0:00 | `v2-portada` | portada | 9.3 s |  |
| 0:09 | `v2-problema` | problema | 9.2 s |  |
| 0:17 | `01d-planta-admin` | Metalúrgica Arlanza, S. L. · empresa ficticia con datos sintéticos | 15.7 s | congela 4.2 s |
| 0:33 | `v2-reparto` | reparto | 5.4 s |  |
| 0:38 | `mapa-inicio` | mapa | 13.0 s |  |
| 0:50 | `mapa-A` | mapa (A) | 2.3 s |  |
| 0:52 | `func-app-acceso` | tarjeta: App de escritorio y acceso público | 4.8 s |  |
| 0:56 | `02a2-app-invitado` | App de escritorio CidIA · sin iniciar sesión | 31.8 s | acelera ×7 |
| 1:27 | `func-roles` | tarjeta: Cada rol ve lo suyo | 4.1 s |  |
| 1:31 | `02b2-app-sesion-lucia` | Lucía Herrero inicia sesión · operaria de Producción, nivel 1 | 14.6 s |  |
| 1:45 | `02c-jefe-javier` | Javier Martín · jefe de Producción | 6.8 s |  |
| 1:51 | `02d-admin` | La administración | 5.2 s |  |
| 1:56 | `func-perfil` | tarjeta: Mi perfil: contraseña y memoria personal | 5.2 s |  |
| 2:01 | `02e-perfil-lucia` | Mi perfil · Lucía Herrero | 39.3 s | congela 0.3 s |
| 2:40 | `mapa-B` | mapa (B) | 2.2 s |  |
| 2:41 | `func-captura-video` | tarjeta: Del vídeo a la instrucción | 4.7 s |  |
| 2:45 | `03a-captura-video-carmen` | Carmen Díaz, experta · captura en vídeo de la brida B | 14.0 s | congela 0.6 s; acelera ×203 |
| 2:59 | `03b-borrador-carmen` | El borrador: la IA propone, la experta decide | 38.9 s | acelera ×5 |
| 3:37 | `func-nota-voz` | tarjeta: Nota de voz convertida en ficha | 4.0 s |  |
| 3:41 | `03d-nota-voz-carmen` | Nota de voz: lo que no se ve en un vídeo | 29.5 s | acelera ×10, ×5, ×4 |
| 4:10 | `func-entrevista` | tarjeta: Entrevista guiada | 4.8 s |  |
| 4:14 | `03e-entrevista-carmen` | Entrevista guiada · cambio de molde en la prensa 3 | 19.5 s | acelera ×8, ×4 |
| 4:33 | `mapa-C` | mapa (C) | 2.2 s |  |
| 4:35 | `func-documentos` | tarjeta: Biblioteca de documentos | 4.4 s |  |
| 4:39 | `04a-documentos-javier` | Documentos de Producción · Javier Martín | 19.0 s | congela 1.0 s |
| 4:57 | `func-busqueda-permisos` | tarjeta: Búsqueda con permisos | 4.0 s |  |
| 5:01 | `04b-probar-busqueda-ana` | Probar búsqueda · Ana López, responsable de Oficina técnica (nivel 3) | 24.3 s | congela 0.8 s |
| 5:25 | `04c-luis-sin-acceso` | Luis García · recién llegado, nivel 1 | 9.6 s | acelera ×2 |
| 5:34 | `mapa-D` | mapa (D) | 2.2 s |  |
| 5:35 | `func-itinerario` | tarjeta: Itinerario y micro-lecciones | 4.5 s |  |
| 5:39 | `07a-itinerario-lucia` | El itinerario de Lucía | 8.4 s |  |
| 5:47 | `07b-microleccion-tutor-lucia` | Micro-lecciones y tutor socrático de la tarea | 15.7 s | acelera ×4 |
| 6:02 | `func-tutor-socratico` | tarjeta: Tutor socrático | 3.9 s |  |
| 6:06 | `05b-socratico-marta` | Modo socrático: un tutor, no una chuleta | 14.7 s | acelera ×2, ×2 |
| 6:20 | `func-formacion-cruzada` | tarjeta: Formación cruzada | 4.8 s |  |
| 6:24 | `07c-formacion-cruzada-marta` | Formación cruzada · Marta se forma en Oficina técnica | 6.1 s |  |
| 6:30 | `mapa-E` | mapa (E) | 2.2 s |  |
| 6:32 | `func-copiloto` | tarjeta: Copiloto con fuentes, por voz | 4.1 s |  |
| 6:35 | `05a-copiloto-voz-marta` | Marta Sanz · técnica de la línea 2 · pregunta por voz | 27.5 s | congela 2.6 s; acelera ×2 |
| 7:02 | `func-modo-planta` | tarjeta: Modo planta paso a paso | 4.2 s |  |
| 7:06 | `06-planta-lucia` | Lucía Herrero · modo planta en la estación E2, de principio a fin | 49.2 s | acelera ×12, ×2 |
| 7:55 | `func-foto-revisada` | tarjeta: Foto del resultado, revisada | 4.5 s |  |
| 7:59 | `06c-foto-javier` | Fotos por revisar · Javier Martín | 17.3 s |  |
| 8:15 | `func-lagunas` | tarjeta: Lagunas de conocimiento | 4.8 s |  |
| 8:20 | `05c-laguna-marta` | Cuando no lo sabe, lo dice | 10.8 s | congela 0.5 s; acelera ×2, ×10 |
| 8:30 | `05d-lagunas-javier` | Lagunas de conocimiento · Javier Martín | 11.8 s |  |
| 8:41 | `func-aportaciones` | tarjeta: Aportaciones desde la planta | 4.3 s |  |
| 8:45 | `10a-aportar-voz-pedro` | Pedro Ruiz, operario de prensas · aporta por voz | 20.1 s | acelera ×10, ×8 |
| 9:05 | `10b-validar-javier` | Validar aportaciones · Javier Martín | 16.9 s | acelera ×3 |
| 9:21 | `10c-cita-marta` | Lo que aprende la planta vuelve a la planta | 13.4 s | acelera ×2, ×4 |
| 9:34 | `mapa-F` | mapa (F) | 2.2 s |  |
| 9:36 | `func-cuestionario` | tarjeta: Cuestionario aprobado por un experto | 4.7 s |  |
| 9:40 | `08b-revisar-preguntas-nuria` | Revisar preguntas · Nuria Gil, experta de Mantenimiento | 22.3 s |  |
| 10:02 | `08a-cuestionario-lucia` | Cuestionario de la brida B · Lucía Herrero | 15.9 s | acelera ×3 |
| 10:17 | `func-observacion` | tarjeta: Observación en el puesto | 3.2 s |  |
| 10:20 | `08c-observacion-javier` | Observación en el puesto · Javier observa a Pedro | 17.8 s | acelera ×3 |
| 10:37 | `mapa-G` | mapa (G) | 2.2 s |  |
| 10:39 | `func-pasaporte` | tarjeta: Pasaporte de habilidades | 4.5 s |  |
| 10:43 | `09a-pasaporte-marta` | Mi progreso · Marta Sanz | 23.6 s | congela 0.6 s |
| 11:06 | `func-matriz-iluo` | tarjeta: Matriz ILUO del equipo | 4.5 s |  |
| 11:10 | `09b-matriz-javier` | Matriz ILUO del equipo de Producción · Javier Martín | 21.5 s | congela 0.6 s |
| 11:31 | `func-versiones` | tarjeta: Versiones nuevas y reevaluación | 5.0 s |  |
| 11:36 | `03c-publicar-carmen` | Una versión nueva de IT-023 · Carmen Díaz publica la versión 2 | 23.0 s |  |
| 11:58 | `mapa-H` | mapa (H) | 2.4 s |  |
| 12:00 | `func-espacio-trabajo` | tarjeta: Espacio de trabajo aislado | 4.0 s |  |
| 12:04 | `11a-espacio-javier` | Espacio de trabajo · Javier Martín | 31.5 s | acelera ×2, ×2, ×2 |
| 12:35 | `func-organizacion` | tarjeta: Organización, personas e identidad | 4.8 s |  |
| 12:39 | `12a-organizacion-admin` | Organización · departamentos, puestos, tareas, niveles y reglas ILUO | 17.4 s |  |
| 12:56 | `12b-empleados-admin` | Empleados · cuentas, roles, formaciones e identidad | 19.7 s |  |
| 13:15 | `func-modelos-locales` | tarjeta: Modelos solo locales | 4.4 s |  |
| 13:19 | `12c2-modelos-admin` | Modelos permitidos · solo locales | 10.8 s |  |
| 13:29 | `func-registro` | tarjeta: Registro xAPI, auditoría y estado | 4.3 s |  |
| 13:33 | `12d-registro-admin` | Registro de actividad en xAPI y auditoría | 17.7 s |  |
| 13:50 | `12e-sistema-admin` | Sistema · estado real del servidor | 4.4 s |  |
| 13:54 | `cierre-criterios` | criterios | 30.7 s |  |
| 14:24 | `cierre-implantacion` | implantacion | 15.7 s |  |
| 14:40 | `cierre-final` | final | 7.8 s |  |

## 4. Guion pieza a pieza

### V DESAFÍO industrial · POLO positivo · 0:00

*CidIA*: El copiloto de IA que captura, enseña, evalúa y certifica el conocimiento de la planta. Todo en local.

* `0:01` Esto es CidIA: un copiloto de inteligencia artificial para la industria que funciona entero dentro de la empresa.

### El problema · 0:09

*El conocimiento se jubila*: Entre 2026 y 2035 saldrán del mercado laboral unos 5,3 millones de personas mayores de 55 años y entrarán unos 1,8 millones de jóvenes (Fundación Adecco a partir de la EPA)

* `0:09` En diez años saldrán más de cinco millones de mayores de cincuenta y cinco, y entrarán menos de dos millones de jóvenes.

**Escena `01d-planta-admin`** · Metalúrgica Arlanza, S. L. · empresa ficticia con datos sintéticos · 15.7 s en el vídeo (toma de 12 s)

* Quién y dónde: Administración (admin) · `/app/`
* Qué se ve: resalta «Personas en 4 departamentos» con la nota «Empresa ficticia · datos sintéticos»; pasa por «Documentos listos para consultar»; pasa por «Instrucciones publicadas»; resalta las cifras de la planta; desplaza la página; resalta «Aportaciones por validar»; resalta «Lagunas abiertas».
* Comprobado: Inicio de admin recorrido hoy sin errores de consola: cifras, aportaciones por validar, lagunas, reevaluaciones y listos para observar.
* Narración:
  * `0:18` Todo lo que vas a ver funciona de verdad, en un servidor de pruebas con modelos pequeños y una empresa ficticia: Metalúrgica Arlanza.
  * `0:27` [cifras] En cifras: personas, documentos, instrucciones y consultas con respaldo.

### Quién es quién en Metalúrgica Arlanza · 0:33

*Las personas del ejemplo*: Carmen, experta · Lucía, recién llegada · Marta, técnica · Pedro, operario de prensas · Javier, jefe de Producción · Ana y Luis, Oficina técnica · Nuria, Mantenimiento

* `0:33` Carmen, la experta; Lucía, la recién llegada; Javier, su jefe.

### Mapa · Mapa de funcionalidades · 0:38

*Capturar · Estructurar · Formar · Acompañar · Evaluar · Certificar*: El ciclo que piden las bases, con el acceso delante y la administración debajo. Cada funcionalidad: quién la usa, para qué sirve, la prueba real y el resultado.

* `0:38` El ciclo de las bases: capturar, estructurar, formar, acompañar, evaluar y certificar. Cada funcionalidad: quién, para qué, la prueba y el resultado.

### Mapa · Bloque 1 de 8 · Entrar · 0:50

*Acceso y perfil*: 1 App de escritorio y acceso público · 2 Cada rol ve lo suyo · 3 Mi perfil: contraseña y memoria personal

* `0:50` Primero, entrar.

### Funcionalidad 1 · Entrar · Cualquier persona, sin iniciar sesión · 0:52

**App de escritorio y acceso público** · Un visitante o alguien de la planta sin cuenta

* Para qué sirve: Instalar CidIA en cada portátil y consultar lo público sin cuenta.
* Tarjeta (4.8 s):
  * `0:52` Una app en cada portátil; sin sesión, solo lo público.

**Escena `02a2-app-invitado`** · App de escritorio CidIA · sin iniciar sesión · 31.8 s en el vídeo (toma de 43 s)

* Quién y dónde: Invitado (sin sesión) en la app de escritorio · `app de escritorio`
* Qué se ve: resalta la lista de secciones de la app con la nota «Sin sesión: solo Acceso y Copiloto»; pulsa «Copiloto»; escribe «¿Cuál es el teléfono de emergencias?»; tecla Enter; espera al servidor (El copiloto busca en los documentos públicos, acelerado); resalta la respuesta; pulsa «Nueva conversación»; escribe «¿A cuánto se aprietan los tornillos de la brida B?»; tecla Enter; espera al servidor (El copiloto busca en los documentos públicos, acelerado); resalta el aviso «No lo he encontrado».
* Montaje: «Tecleo de la pregunta» ×2; «Tecleo de la pregunta» ×2.
* Comprobado: Grabada el 11/10/2026 (04_VIDEO/material-v3, revisada fotograma a fotograma). Antes: Mismas acciones que 02a-app-invitado (probadas el 10/10 en la app instalada por CDP), con la app ya traducida.
* Narración:
  * `0:57` Así se ve sin iniciar sesión: solo el acceso y el copiloto.
  * `1:04` [pregunta] Cualquiera puede preguntar, por ejemplo, el teléfono de emergencias.
  * `1:11` [respuesta] Responde con la extensión 200 y cita de dónde sale: la guía de bienvenida. Ahora, algo del puesto: el apriete de la brida B.
  * `1:24` [restringida] **(resultado)** No lo encuentra: lo interno no existe para quien no ha entrado.
* **Resultado** (panel desde el fragmento 4): Lo público, a mano para todos; lo interno, protegido.
* **Bases**: Implantación sencilla y económica · Proteger el conocimiento experto · Acceso inmediato a contenidos

*Toma antigua `02a-app-invitado`, sustituida por `02a2-app-invitado` (fuera del montaje).*

### Funcionalidad 2 · Entrar · Operaria, jefe de equipo y administración · 1:27

**Cada rol ve lo suyo** · Lucía Herrero, Javier Martín y la administración

* Para qué sirve: Que cada persona vea solo las secciones de su trabajo.
* Tarjeta (4.1 s):
  * `1:28` Cada rol ve lo suyo, y lo decide el servidor.

**Escena `02b2-app-sesion-lucia`** · Lucía Herrero inicia sesión · operaria de Producción, nivel 1 · 14.6 s en el vídeo (toma de 15 s)

* Quién y dónde: Empleada (operaria) que inicia sesión en la app · `app de escritorio`
* Qué se ve: pulsa «Acceso»; escribe «lucia»; teclea la contraseña (se ven puntos); pulsa «Iniciar sesión»; resalta la lista de secciones de la app con la nota «Ocho secciones para una operaria».
* Comprobado: Grabada el 11/10/2026 (04_VIDEO/material-v3, revisada fotograma a fotograma). Antes: Mismas acciones que 02b-app-sesion-lucia (probadas el 10/10 en la app instalada por CDP), con la app ya traducida.
* Narración:
  * `1:32` Lucía, operaria recién llegada a la línea 2, entra con su usuario. La contraseña nunca se ve.
  * `1:41` [secciones] Ve ocho secciones: las de su trabajo, ni una más.

**Escena `02c-jefe-javier`** · Javier Martín · jefe de Producción · 6.8 s en el vídeo (toma de 9 s)

* Quién y dónde: Jefe de equipo (javier) · `/app/`
* Qué se ve: resalta «Mi equipo»; resalta «Conocimiento».
* Comprobado: Barra lateral de javier (Mi trabajo, Conocimiento, Mi equipo) y de admin (más Administración) vistas hoy.
* Narración:
  * `1:46` Javier, jefe de Producción, ve además el conocimiento de su departamento y a su equipo.

**Escena `02d-admin`** · La administración · 5.2 s en el vídeo (toma de 8 s)

* Quién y dónde: Administración (admin) · `/app/`
* Qué se ve: resalta «Administración».
* Comprobado: Barra lateral de admin con el grupo Administración (Organización, Empleados, Modelos, Registro de actividad, Sistema) vista hoy.
* Narración:
  * `1:52` **(resultado)** Y la administración, toda la planta. Una sola app para todos.
* **Resultado** (panel desde el fragmento 1): Una sola app para toda la planta, adaptada a cada perfil.
* **Bases**: Adaptado al perfil · Gestión centralizada del conocimiento · Integración (módulo de identidad)

*Toma antigua `02b-app-sesion-lucia`, sustituida por `02b2-app-sesion-lucia` (fuera del montaje).*

### Funcionalidad 3 · Entrar · Cualquier empleado · 1:56

**Mi perfil: contraseña y memoria personal** · Lucía Herrero, operaria

* Para qué sirve: Cambiar la contraseña y decidir si el copiloto te recuerda.
* Tarjeta (5.2 s):
  * `1:56` En su perfil, cada persona decide si el copiloto la recuerda.

**Escena `02e-perfil-lucia`** · Mi perfil · Lucía Herrero · 39.3 s en el vídeo (toma de 41 s)

* Quién y dónde: Empleada (lucia) · `/app/copiloto`
* Qué se ve: pulsa Su nombre, al pie de la barra lateral; resalta sus datos con la nota «Usuario, puesto, formaciones y preguntas al copiloto»; escribe «Dos pasadas en cruz»; pulsa input[id$='-nueva'] ~ button.accion-entrada; escribe «Dos pasadas en cruz»; resalta las reglas de la contraseña con la nota «Se comprueban al escribir. Sin la contraseña actual no se envía»; pasa el cursor por .perfil-pie-form button[type=submit]; desplaza la página; resalta la explicación de la memoria con la nota «Desactivada por defecto; solo la ve ella»; pulsa «Activar la memoria»; escribe «Trabajo en el turno de mañana en la línea 2»; pulsa «Añadir»; espera al servidor (Guardando el recuerdo en el servidor, acelerado); resalta los recuerdos con la nota «Se ve, se borra uno a uno o todo»; pasa el cursor por .recuerdo button[aria-label^='Borrar el recuerdo'].
* Comprobado: Grabada el 11/10/2026 (04_VIDEO/material-v3, revisada fotograma a fotograma). Antes: Selectores y textos sacados de servidor/web/src/paginas/Perfil.tsx, Acceso.tsx (CampoContrasena) y Marco.tsx (.usuario-enlace) el 10/10: «Cambiar la contraseña», «Contraseña cambiada», «Activar la memoria», input aria-label «Nuevo recuerdo», «Añadir», «Lo añadiste tú», .recuerdos, .memoria-explicacion y .reglas-contrasena.
* Narración:
  * `2:01` Lucía entra en su perfil desde su nombre.
  * `2:05` [perfil] Ve sus datos: su puesto, sus formaciones y cuántas preguntas ha hecho al copiloto.
  * `2:11` [contrasena] Puede cambiar la contraseña: las reglas se comprueban al escribir y el ojo le deja ver lo que teclea. Sin la contraseña actual, no se envía.
  * `2:24` [memoria] Y decide si el copiloto la recuerda: la memoria está apagada por defecto, y lo que guarda solo lo ve ella.
  * `2:35` [recuerdo] **(resultado)** Lo que recuerda se ve, se borra y se queda en el servidor de la empresa.
* **Resultado** (panel desde el fragmento 5): Privacidad por defecto: la memoria está apagada hasta que la persona la enciende.
* **Bases**: Adaptado al perfil · Proteger el conocimiento experto

### Mapa · Bloque 2 de 8 · Capturar · 2:40

*Capturar el saber del experto*: 4 Del vídeo a la instrucción · 5 Nota de voz convertida en ficha · 6 Entrevista guiada

* `2:40` Capturar.

### Funcionalidad 4 · Capturar · Experta · 2:41

**Del vídeo a la instrucción** · Carmen Díaz, experta en la brida B

* Para qué sirve: Convertir lo que la experta hace y explica en una instrucción.
* Tarjeta (4.7 s):
  * `2:42` Del vídeo de la experta a una instrucción de trabajo.

**Escena `03a-captura-video-carmen`** · Carmen Díaz, experta · captura en vídeo de la brida B · 14.0 s en el vídeo (toma de 721 s)

* Quién y dónde: Empleada experta (carmen) · `/app/captura`
* Qué se ve: elige «IT-023»; sube brida-b-sintetico.mp4; desplaza la página; espera al servidor (El servidor transcribe el vídeo, detecta los pasos y revisa cada imagen, acelerado); resalta «Los pasos siguen los que nombras».
* Montaje: esperas a 3.5 s.
* Comprobado: Grabado el 10/10: la captura tarda entre 4 y 12 minutos en Oracle (el modelo con visión repasa los 7 pasos); el montaje lo acelera con su rótulo. Borrador con los mismos fallos de transcripción que en la exploración («Prueba de esta enqueidad», «4 tornillos en 10»).
* Narración:
  * `2:46` Elige la instrucción y sube el vídeo.
  * `2:49` [proceso] El servidor extrae el audio, lo transcribe, detecta los pasos y un modelo con visión revisa cada imagen.
  * `2:57` [listo] Borrador listo.

**Escena `03b-borrador-carmen`** · El borrador: la IA propone, la experta decide · 38.9 s en el vídeo (toma de 77 s)

* Quién y dónde: Empleada experta (carmen) · `/app/captura`
* Qué se ve: pulsa «Revisar borrador»; resalta la lista de pasos; pulsa el paso 3; resalta la imagen y el clip del paso con la nota «Imagen y clip de este paso»; resalta los interruptores de paso crítico y de seguridad; pulsa el paso 5; resalta el título del paso con la nota «Prueba de esta enqueidad»; escribe «Prueba de estanqueidad»; pulsa el interruptor «seguridad»; escribe «Prueba de estanqueidad: tapa cerrada, tres bar durante un minuto.»; pulsa el paso 1; escribe «Prepara la brida B, una junta nueva y 4 tornillos M10 con su arandela.»; pulsa el paso 2; escribe «Limpia el asiento y centra la junta JT-80. La junta nunca se reutil...»; pulsa el paso 3; escribe «Aprieta los 4 tornillos en cruz a 25 N·m con la llave dinamométrica...»; escribe «Par de 25 N·m comprobado con la llave dinamométrica.»; pulsa el paso 4; escribe «Marca cada tornillo con el rotulador amarillo.»; pulsa el paso 6; escribe «Revisa las marcas, la junta y que no haya rebabas.»; pulsa el paso 7; escribe «Registra el número de serie, pega la etiqueta verde y lleva el conj...»; escribe «Montaje de la brida B en la estación 2 de la línea 2.»; pulsa el paso 5; pulsa «Guardar».
* Montaje: «Carmen repasa los siete pasos» ×5.
* Comprobado: Toma v4 (11/10/2026): borrador generado de nuevo con el mismo vídeo; Carmen corrige el título del paso 5 y lo marca de seguridad, y en un tramo acelerado repasa los siete pasos (M10, verbos, lo que el modelo añadió en los pasos 4 y 7, rebabas, criterio del paso 3 y resumen). Comprobado por la API tras guardar.
* Narración:
  * `3:02` [borrador] Siete pasos, cada uno con su imagen, su clip y lo que dijo Carmen. El paso 3 sale crítico porque ella lo dijo: cuatro tornillos en cruz a 25 N·m.
  * `3:14` [corrige] La transcripción partió en dos la palabra «estanqueidad»: Carmen la corrige y marca el paso como de seguridad.
  * `3:23` [repasa] Después repasa los siete pasos: los tornillos son M10, quita lo que el modelo añadió y pone el criterio del apriete.
  * `3:34` [guarda] **(resultado)** La inteligencia artificial propone; decide la experta.
* **Resultado** (panel desde el fragmento 4): Un borrador de siete pasos con imagen y clip, que revisa y decide la experta.
* **Bases**: Captura del conocimiento de operarios expertos · Generación automática de instrucciones · Digitalización de procedimientos operativos

### Funcionalidad 5 · Capturar · Experta · 3:37

**Nota de voz convertida en ficha** · Carmen Díaz

* Para qué sirve: Guardar lo que no se ve en un vídeo: trucos, criterios y errores.
* Tarjeta (4.0 s):
  * `3:38` Lo que no se ve en un vídeo, en una nota de voz.

**Escena `03d-nota-voz-carmen`** · Nota de voz: lo que no se ve en un vídeo · 29.5 s en el vídeo (toma de 60 s)

* Quién y dónde: Empleada experta (carmen) · `/app/captura`
* Qué se ve: elige «IT-023»; pulsa el micrófono de la nota de voz; espera (Carmen graba la nota de voz, acelerado); pulsa el micrófono de la nota de voz; pulsa «Enviar nota»; espera al servidor (El servidor transcribe la nota y la ordena en una ficha, acelerado); pulsa «Revisar borrador»; resalta la ficha propuesta con la nota «La ficha que propone CidIA»; pulsa «Escuchar la nota y ver la transcripción»; desplaza la página; resalta la transcripción con la nota «Lo que dijo Carmen, palabra por palabra»; escribe «Truco de la brida B»; pulsa «Editar»; escribe «## Truco - Si la junta JT-80 no se queda centrada, pon dos tornillo...»; pulsa «Vista previa»; pulsa «Publicar ficha»; pulsa «Confirmar»; espera al servidor (Publicando la ficha, acelerado).
* Montaje: «Carmen corrige la ficha» ×4.
* Comprobado: Grabado el 10/10 con el micrófono falso: transcripción con errores reales («pondo», «Vada la queja Roger»), ficha propuesta, edición y «Ficha publicada».
* Narración:
  * `3:41` Carmen pulsa el micrófono y lo cuenta.
  * `3:47` [proceso] CidIA lo transcribe y lo ordena en una ficha.
  * `3:51` [ficha] Carmen la revisa junto a lo que dijo. Donde dijo «va a la caja roja», el modelo entendió «Vada la queja Roger»: lo corrige.
  * `4:06` [publica] **(resultado)** Y la publica: el truco ya es conocimiento de Producción.
* **Resultado** (panel desde el fragmento 4): El truco de la junta ya es conocimiento de Producción, con su autora.
* **Bases**: Captura del conocimiento de operarios expertos · Gestión centralizada del conocimiento

### Funcionalidad 6 · Capturar · Experta · 4:10

**Entrevista guiada** · Carmen Díaz

* Para qué sirve: Sacar el saber de quien no sabe por dónde empezar.
* Tarjeta (4.8 s):
  * `4:10` Si no sabe por dónde empezar, el copiloto la entrevista.

**Escena `03e-entrevista-carmen`** · Entrevista guiada · cambio de molde en la prensa 3 · 19.5 s en el vídeo (toma de 40 s)

* Quién y dónde: Empleada experta (carmen) · `/app/captura`
* Qué se ve: elige «IT-031»; pulsa «Empezar entrevista»; espera al servidor (El copiloto prepara la primera pregunta, acelerado); resalta el guion de la entrevista con la nota «El guion de la entrevista: siete temas»; pulsa el micrófono de la respuesta; espera (Carmen responde por voz, acelerado); pulsa «Parar y enviar»; espera al servidor (Transcribe la respuesta y prepara la siguiente pregunta, acelerado); resalta «1 de 7 temas»; resalta «Terminar y generar ficha».
* Comprobado: Grabado el 10/10: respuesta por voz transcrita y segunda pregunta del modelo «¿Cuánto dura el proceso de cambio de molde en la prensa 3?».
* Narración:
  * `4:15` El tema: el cambio de molde de la prensa 3.
  * `4:18` [pregunta] Un guion de siete temas, una pregunta cada vez, y Carmen responde hablando.
  * `4:27` [siguiente] **(resultado)** Transcribe su respuesta y pasa al siguiente tema. Al final, sale una ficha para revisar.
* **Resultado** (panel desde el fragmento 3): Siete temas por voz y, al final, una ficha que revisa la experta.
* **Bases**: Captura del conocimiento de operarios expertos

### Mapa · Bloque 3 de 8 · Estructurar · 4:33

*El conocimiento, ordenado y con permisos*: 7 Biblioteca de documentos · 8 Búsqueda con permisos

* `4:34` Estructurar.

### Funcionalidad 7 · Estructurar · Jefe de equipo · 4:35

**Biblioteca de documentos** · Javier Martín, jefe de Producción

* Para qué sirve: Reunir los documentos que ya existen, con quién puede verlos.
* Tarjeta (4.4 s):
  * `4:35` Los documentos que ya existen, ordenados y con dueño.

**Escena `04a-documentos-javier`** · Documentos de Producción · Javier Martín · 19.0 s en el vídeo (toma de 20 s)

* Quién y dónde: Jefe de equipo (javier) · `/app/documentos`
* Qué se ve: resalta las columnas de la tabla con la nota «Departamento, nivel mínimo, formación y público»; resalta «Manual de manejo de la prensa 3» con la nota «Nivel mínimo: Técnico»; resalta «Bienvenida y PRL» con la nota «Público: también sin iniciar sesión»; pulsa «Subir conocimiento»; resalta el panel de subida; pulsa «Cancelar».
* Comprobado: Biblioteca y panel «Subir conocimiento» (Departamento, Nivel mínimo, Material de formación, Público) presentes; recorridos hoy con ana. Javier ve los documentos de Producción.
* Narración:
  * `4:39` Cada uno con su departamento, su nivel mínimo, si es formación y si es público: el manual de la prensa 3, para técnicos; la bienvenida, para todos.
  * `4:50` [subir] **(resultado)** Al subirlos, CidIA los indexa para buscar por significado y por palabras exactas en castellano.
* **Resultado** (panel desde el fragmento 2): Todo el conocimiento en un sitio, con permisos y buscable.
* **Bases**: Gestión centralizada del conocimiento · Bases de conocimiento inteligentes

### Funcionalidad 8 · Estructurar · Responsable y recién llegado · 4:57

**Búsqueda con permisos** · Ana López, responsable de Oficina técnica, y Luis García, recién llegado

* Para qué sirve: Encontrar por significado y que cada uno vea solo lo suyo.
* Tarjeta (4.0 s):
  * `4:58` Una búsqueda que respeta quién puede ver qué.

**Escena `04b-probar-busqueda-ana`** · Probar búsqueda · Ana López, responsable de Oficina técnica (nivel 3) · 24.3 s en el vídeo (toma de 25 s)

* Quién y dónde: Jefa de equipo y experta (ana) · `/app/documentos`
* Qué se ve: pulsa «Probar búsqueda»; escribe «¿Quién aprueba compras de más de 12.000 €?»; pulsa «Buscar»; resalta «Costes y proveedores de utillaje»; resalta «Coincide por palabras»; resalta «Similitud»; elige «Luis»; pulsa «Buscar»; resalta «Alcance de la búsqueda».
* Comprobado: Grabado el 10/10 con «¿Quién aprueba compras de más de 12.000 €?»: como Ana, Costes y proveedores de utillaje; como Luis, Bienvenida y PRL y el manual de iniciación.
* Narración:
  * `5:01` Ana, de Oficina técnica, prueba qué encontraría el copiloto: quién aprueba compras de más de 12.000 €.
  * `5:09` [resultados] Sale el documento de costes de utillaje, puntuado por significado y por palabras, en un solo orden.
  * `5:16` [comoLuis] Buscando como Luis, recién llegado con nivel 1, ese documento de nivel 3 no aparece: el filtro se aplica antes del modelo.

**Escena `04c-luis-sin-acceso`** · Luis García · recién llegado, nivel 1 · 9.6 s en el vídeo (toma de 15 s)

* Quién y dónde: Empleado (luis) · `/app/copiloto`
* Qué se ve: escribe «¿Quién aprueba compras de más de 12.000 €?»; tecla Enter; espera al servidor (El copiloto busca con los permisos de Luis, acelerado); resalta la respuesta.
* Montaje: «Tecleo de la pregunta» ×2.
* Comprobado: Grabado el 10/10: «No se encuentra en la documentación» y laguna en Oficina técnica.
* Narración:
  * `5:25` Luis se lo pregunta al copiloto.
  * `5:29` [respuesta] **(resultado)** No lo encuentra ni lo menciona: cada persona ve lo que le toca, y nada más.
* **Resultado** (panel desde el fragmento 2): Cada persona encuentra lo que le toca, y nada más.
* **Bases**: Bases de conocimiento inteligentes · Proteger el conocimiento experto · Adaptado al perfil

*Escena opcional `04d-ana-con-acceso` (La misma pregunta, con el nivel de Ana), grabada pero fuera del montaje: Repite lo que ya enseñan las escenas anteriores; fuera del completo por tiempo. Para usarla, quitar «omitir» y mover el «resultado» a esta escena. Narración: «Ana, con su nivel, sí obtiene la respuesta: la gerencia, con tres ofertas, citando el documento y su versión.»*

### Mapa · Bloque 4 de 8 · Formar · 5:34

*Aprender antes de hacer*: 9 Itinerario y micro-lecciones · 10 Tutor socrático · 11 Formación cruzada

* `5:34` Formar.

### Funcionalidad 9 · Formar · Operaria recién llegada · 5:35

**Itinerario y micro-lecciones** · Lucía Herrero

* Para qué sirve: Saber qué falta por dominar y aprenderlo en lecciones cortas.
* Tarjeta (4.5 s):
  * `5:36` Lo que le falta a cada uno, en lecciones cortas.

**Escena `07a-itinerario-lucia`** · El itinerario de Lucía · 8.4 s en el vídeo (toma de 10 s)

* Quién y dónde: Empleada (lucia) · `/app/formacion`
* Qué se ve: resalta «Montaje de la brida B»; resalta «Haz el cuestionario de evaluación».
* Comprobado: Itinerario de Lucía visto hoy: IT-023 nivel I con micro-lecciones, cuestionario pendiente y ejecuciones; IT-024 e IT-025 sin instrucción.
* Narración:
  * `5:40` Lucía tiene la brida B en nivel I, con las micro-lecciones hechas, y su siguiente paso: el cuestionario.

**Escena `07b-microleccion-tutor-lucia`** · Micro-lecciones y tutor socrático de la tarea · 15.7 s en el vídeo (toma de 24 s)

* Quién y dónde: Empleada (lucia) · `/app/formacion`
* Qué se ve: pulsa «Montaje de la brida B»; resalta «Por qué se aprieta en cruz»; desplaza la página; pulsa «En cruz: arriba, abajo, derecha, izquierda»; desplaza la página; pulsa «¿Qué puede salir mal en el paso crítico?»; espera al servidor (El tutor prepara su respuesta, acelerado).
* Comprobado: Página de la tarea vista hoy con Lucía: micro-lección 1 «Por qué se aprieta en cruz», punto clave «En cruz y en dos pasadas: 12 N·m y después 25 N·m», pregunta de control con la opción «En cruz: arriba, abajo, derecha, izquierda», cuestionario, instrucción y «Tutor socrático» con sus tres sugerencias. Tutor probado por la API (23 s, con «Pista»).
* Narración:
  * `5:48` Las micro-lecciones salen de los pasos de la instrucción:
  * `5:52` [control] cortas, con su punto clave y una pregunta de control.
  * `5:56` [tutor] Y el tutor de la tarea le hace pensar qué puede fallar en el paso crítico.
  * `6:00` **(resultado)** Llega al puesto sabiendo el porqué.
* **Resultado** (panel desde el fragmento 4): Llega al puesto sabiendo por qué se hace cada paso.
* **Bases**: Itinerarios de aprendizaje personalizados · Micro-learning industrial · Documentación técnica convertida en formación · Recomendaciones según el contexto

### Funcionalidad 10 · Formar · Técnica en formación · 6:02

**Tutor socrático** · Marta Sanz, técnica de la línea 2

* Para qué sirve: Que la persona razone la respuesta en lugar de copiarla.
* Tarjeta (3.9 s):
  * `6:03` Un tutor que enseña a razonar, no a copiar.

**Escena `05b-socratico-marta`** · Modo socrático: un tutor, no una chuleta · 14.7 s en el vídeo (toma de 21 s)

* Quién y dónde: Empleada (marta) · `/app/copiloto`
* Qué se ve: pulsa el interruptor «Modo socrático»; resalta el interruptor «Modo socrático»; escribe «¿Cómo se aprietan los tornillos de la brida B?»; tecla Enter; espera al servidor (El tutor prepara su pregunta, acelerado); resalta la respuesta.
* Montaje: «Tecleo de la pregunta» ×2.
* Comprobado: Grabado el 10/10: pregunta de vuelta, pista y cita [1].
* Narración:
  * `6:06` Marta, que ya domina la brida B, prueba el modo socrático con una pregunta que sabe responder.
  * `6:15` [respuesta] **(resultado)** Le devuelve una pregunta y una pista para que piense por qué se aprieta en cruz.
* **Resultado** (panel desde el fragmento 2): Un tutor, no una chuleta.
* **Bases**: Tutorización inteligente · Mejoras añadidas

### Funcionalidad 11 · Formar · Técnica · 6:20

**Formación cruzada** · Marta Sanz

* Para qué sirve: Formarse un tiempo en otro departamento, con acceso a su material.
* Tarjeta (4.8 s):
  * `6:20` Formarse en otro departamento, para ganar polivalencia.

**Escena `07c-formacion-cruzada-marta`** · Formación cruzada · Marta se forma en Oficina técnica · 6.1 s en el vídeo (toma de 8 s)

* Quién y dónde: Empleada (marta) · `/app/formacion`
* Qué se ve: resalta .fm-formacion-cabecera con la nota «Oficina técnica, hasta el 15 de noviembre».
* Comprobado: Visto hoy: «Formación activa en otro departamento · Oficina técnica · Diseño de utillajes, desde el 18 sept 2026 hasta el 14 nov 2026 · 3 tareas».
* Narración:
  * `6:25` **(resultado)** Marta se forma en Oficina técnica hasta noviembre, con acceso a su material.
* **Resultado** (panel desde el fragmento 1): Más polivalencia, con fecha de inicio y de fin.
* **Bases**: Incrementar la polivalencia · Itinerarios de aprendizaje personalizados

### Mapa · Bloque 5 de 8 · Acompañar · 6:30

*Ayuda en el puesto, en el momento*: 12 Copiloto con fuentes, por voz · 13 Modo planta paso a paso · 14 Foto del resultado, revisada · 15 Lagunas de conocimiento · 16 Aportaciones desde la planta

* `6:30` Acompañar.

### Funcionalidad 12 · Acompañar · Técnica de la línea 2 · 6:32

**Copiloto con fuentes, por voz** · Marta Sanz

* Para qué sirve: Resolver dudas al momento, diciendo de dónde sale cada dato.
* Tarjeta (4.1 s):
  * `6:32` Respuestas al momento, con la fuente de cada dato.

**Escena `05a-copiloto-voz-marta`** · Marta Sanz · técnica de la línea 2 · pregunta por voz · 27.5 s en el vídeo (toma de 29 s)

* Quién y dónde: Empleada (marta) · `/app/copiloto`
* Qué se ve: pasa el cursor por el micrófono; mantiene pulsado el micrófono (habla el audio de la escena); espera al servidor (Transcribiendo la voz en el servidor, acelerado); espera al servidor (El copiloto prepara la respuesta en el servidor, acelerado); resalta la respuesta; pulsa la fuente citada; resalta «Validado por».
* Comprobado: Toma v4: la ficha de Pedro dice ya «Con la prensa parada y consignada (IT-073)…» (corregida en la base del servidor de pruebas antes de grabar; falta corregir la semilla, actividad.py) y el copiloto lo cita.
* Narración:
  * `6:37` [pregunta] Marta pregunta por voz:
  * `6:39` (se oye el micrófono) «La prensa 3 se ha atascado al cambiar el molde. ¿Qué hago?»
  * `6:50` [respuesta] Solución: con la prensa parada y consignada, limpiar el sensor S4 con aire a baja presión.
  * `6:57` [fuente] **(resultado)** La fuente: una ficha de Pedro, validada por Javier. Todo se puede comprobar.
* **Resultado** (panel desde el fragmento 3): Respuestas comprobables: documento, versión, autor y validador.
* **Bases**: Copiloto inteligente · Apoyo a la toma de decisiones · Trazabilidad hasta versión y autor · Acceso inmediato a contenidos

### Funcionalidad 13 · Acompañar · Operaria recién llegada · 7:02

**Modo planta paso a paso** · Lucía Herrero

* Para qué sirve: Hacer la tarea guiada, con los críticos confirmados y preguntas por voz.
* Tarjeta (4.2 s):
  * `7:03` En el puesto, paso a paso y con las manos libres.

**Escena `06-planta-lucia`** · Lucía Herrero · modo planta en la estación E2, de principio a fin · 49.2 s en el vídeo (toma de 74 s)

* Quién y dónde: Empleada (lucia), recién incorporada, nivel I en IT-023 · `/app/planta`
* Qué se ve: resalta la tarea de la brida B; pulsa «Empezar»; resalta «Antes de empezar»; pulsa «Hecho» (×2); mantiene pulsado el micrófono (habla el audio de la escena); espera al servidor (Transcribe la voz y responde con la instrucción, acelerado); resalta la respuesta del copiloto en el paso; pulsa «Hecho»; pulsa la casilla del punto crítico; pulsa «Hecho» (×5); pulsa «Hacer foto» (sube foto-resultado.jpg); resalta «Así debe quedar»; pulsa «Finalizar»; resalta «Consulta al copiloto».
* Montaje: «Lucía confirma los pasos 4 a 7» ×2.5.
* Comprobado: Grabada el 11/10/2026 (04_VIDEO/material-v3, revisada fotograma a fotograma). Antes: Une las acciones de 06a (hasta el paso 4) y de 06b (pasos 4 a 7, foto y cierre), ya probadas por separado el 10/10. En la v1 el reloj saltaba de 2:52 a 5:34 entre las dos tomas.
* Narración:
  * `7:07` Lucía empieza la brida B en el portátil del puesto.
  * `7:10` [paso1] Un paso por pantalla, con letra grande. Primero, EPI, herramientas y riesgos.
  * `7:17` [paso3] El paso 3 es crítico. Con las manos ocupadas, Lucía pregunta por voz:
  * `7:24` (se oye el micrófono) «¿Qué llave uso para apretar los tornillos?»
  * `7:30` [respuesta] La respuesta sale de la instrucción y cita el paso: llave dinamométrica de media pulgada.
  * `7:37` [sinmarcar] Sin confirmar el punto crítico, no puede seguir.
  * `7:44` [foto] Al final, una foto: un modelo con visión la compara con la del experto.
  * `7:49` [fin] **(resultado)** Ejecución registrada, con su tiempo y sus consultas: así se mide su autonomía.
* **Resultado** (panel desde el fragmento 7): Guiada paso a paso, con los críticos confirmados y la ejecución registrada.
* **Bases**: Asistencia guiada paso a paso · Formación contextualizada en el puesto · Garantizar la correcta ejecución

*Toma antigua `06a-planta-pasos-lucia`, sustituida por `06-planta-lucia` (fuera del montaje).*

*Toma antigua `06b-planta-cierre-lucia`, sustituida por `06-planta-lucia` (fuera del montaje).*

### Funcionalidad 14 · Acompañar · Jefe de equipo · 7:55

**Foto del resultado, revisada** · Javier Martín

* Para qué sirve: Comprobar el resultado: la IA compara la foto y decide una persona.
* Tarjeta (4.5 s):
  * `7:55` La foto del resultado, revisada por una persona.

**Escena `06c-foto-javier`** · Fotos por revisar · Javier Martín · 17.3 s en el vídeo (toma de 20 s)

* Quién y dónde: Jefe de equipo (javier) · `/app/planta?vista=fotos`
* Qué se ve: pulsa «Todas»; resalta «Rechazada» con la nota «El modelo vio diferencias: Javier la rechazó con un comentario»; resalta «Sin revisar»; pulsa «El modelo cree que coincide»; resalta la foto junto a la de referencia; pulsa «Dar por buena».
* Comprobado: Grabado el 10/10: como la foto coincidía no quedó pendiente; Javier abre «Todas», ve la de un intento anterior (el manómetro, rechazada con comentario) y da por buena la de hoy.
* Narración:
  * `7:59` Esta, de un intento anterior, era la del manómetro: Javier la rechazó con un comentario.
  * `8:06` [veredicto] La de hoy coincide con la referencia; aun así, Javier la mira y la da por buena.
  * `8:12` **(resultado)** La inteligencia artificial ayuda a mirar; decide una persona.
* **Resultado** (panel desde el fragmento 3): La IA ayuda a mirar; decide una persona.
* **Bases**: Validación de tareas realizadas · Garantizar la correcta ejecución

### Funcionalidad 15 · Acompañar · Técnica y jefe de equipo · 8:15

**Lagunas de conocimiento** · Marta Sanz y Javier Martín

* Para qué sirve: Detectar lo que nadie ha documentado: no se lo inventa, lo apunta.
* Tarjeta (4.8 s):
  * `8:16` Lo que el copiloto no sabe, no se lo inventa: lo apunta.

**Escena `05c-laguna-marta`** · Cuando no lo sabe, lo dice · 10.8 s en el vídeo (toma de 33 s)

* Quién y dónde: Empleada (marta) · `/app/copiloto`
* Qué se ve: escribe «¿Qué presión lleva el cilindro de la prensa 2?»; tecla Enter; espera al servidor (El copiloto busca en la documentación, acelerado); resalta la respuesta.
* Montaje: «Tecleo de la pregunta» ×2.
* Comprobado: Grabado el 10/10: «No lo he encontrado…» y la laguna sube a 4 veces.
* Narración:
  * `8:20` Marta pregunta algo sin documentar: la presión del cilindro de la prensa 2.
  * `8:26` [respuesta] No se la inventa: dice que no lo ha encontrado y apunta la pregunta.

**Escena `05d-lagunas-javier`** · Lagunas de conocimiento · Javier Martín · 11.8 s en el vídeo (toma de 14 s)

* Quién y dónde: Jefe de equipo (javier) · `/app/lagunas`
* Qué se ve: resalta «¿Qué presión lleva el cilindro de la prensa 2?»; pulsa «Ver las»; resalta «Pedir a alguien que la responda».
* Comprobado: Página de lagunas recorrida hoy: pestañas Abiertas, Resueltas y Descartadas, «Ver las 3 formas en que se ha preguntado», «Pedir a alguien que la responda» y «Descartar».
* Narración:
  * `8:31` Javier ve las lagunas de su equipo, agrupadas por parecido y ordenadas por frecuencia.
  * `8:37` [pedir] **(resultado)** Puede pedir que alguien la responda: necesidades formativas, con datos.
* **Resultado** (panel desde el fragmento 2): Necesidades formativas con datos, y la próxima captura.
* **Bases**: Necesidades formativas · Mejoras añadidas (lagunas)

### Funcionalidad 16 · Acompañar · Operario y jefe de equipo · 8:41

**Aportaciones desde la planta** · Pedro Ruiz, operario de prensas, y Javier Martín

* Para qué sirve: Que quien sabe la respuesta la cuente por voz y el copiloto la use.
* Tarjeta (4.3 s):
  * `8:42` Quien sabe la respuesta, la aporta desde la planta.

**Escena `10a-aportar-voz-pedro`** · Pedro Ruiz, operario de prensas · aporta por voz · 20.1 s en el vídeo (toma de 52 s)

* Quién y dónde: Empleado (pedro) · `/app/aportaciones`
* Qué se ve: resalta «Preguntas pendientes en tu departamento»; pulsa «Yo sé la respuesta»; pulsa «Nota de voz»; mantiene pulsado el micrófono (habla el audio de la escena); elige «IT-031»; pulsa «Enviar aportación»; espera al servidor (El servidor transcribe la nota y la ordena, acelerado); resalta «SOLUCIÓN».
* Comprobado: Grabado el 10/10 con la voz em_santa (Pedro): nota de 18 s transcrita y ordenada en problema, causa y solución.
* Narración:
  * `8:46` Pedro ve las preguntas que el copiloto no supo responder.
  * `8:50` [responde] Sabe cómo se purga el circuito de refrigeración y lo cuenta en una nota de voz.
  * `9:00` [ordenada] CidIA la ordena en problema, causa y solución, y se la manda a su jefe.

**Escena `10b-validar-javier`** · Validar aportaciones · Javier Martín · 16.9 s en el vídeo (toma de 36 s)

* Quién y dónde: Jefe de equipo (javier) · `/app/validar`
* Qué se ve: resalta la aportación con la nota «La de Pedro, la más reciente»; pulsa «Ver la transcripción»; pulsa «Editar»; escribe «Purga del circuito de refrigeración del molde (prensa 3)»; escribe «Tras cambiar el molde queda aire en las mangueras y la pieza sale m...»; escribe «Aire acumulado al desconectar y volver a conectar las mangueras del...»; escribe «Para purgar el circuito de refrigeración: con la prensa parada y el...»; pulsa «Guardar y validar».
* Montaje: «Javier corrige el título, el problema, la causa y la solución» ×3.
* Comprobado: Grabado el 10/10: edición de título y bloques y «Publicada. El copiloto ya puede responderlo citando a Pedro Ruiz».
* Narración:
  * `9:05` Javier la revisa con la transcripción delante.
  * `9:10` [edita] El modelo mezcló la causa y la solución: lo corrige en un momento.
  * `9:19` [valida] Y la valida, con Pedro como autor.

**Escena `10c-cita-marta`** · Lo que aprende la planta vuelve a la planta · 13.4 s en el vídeo (toma de 23 s)

* Quién y dónde: Empleada (marta) · `/app/copiloto`
* Qué se ve: escribe «¿Cómo se purga el circuito de refrigeración?»; tecla Enter; espera al servidor (El copiloto busca en la documentación, acelerado); resalta la respuesta; pulsa la fuente citada; resalta «Validado por».
* Montaje: «Tecleo de la pregunta» ×2.
* Comprobado: Grabado el 10/10: respuesta con la solución de la purga y fuente «Purga del circuito de refrigeración del molde (prensa 3)» con autoría y validación.
* Narración:
  * `9:22` Al momento, Marta pregunta cómo se purga el circuito
  * `9:26` [respuesta] y el copiloto ya responde, citando a Pedro y a Javier.
  * `9:30` **(resultado)** Lo que aprende la planta vuelve a la planta, y la laguna se cierra.
* **Resultado** (panel desde el fragmento 3): Lo que aprende la planta vuelve a la planta: la laguna se cierra.
* **Bases**: Captura del conocimiento de operarios expertos · Mejoras añadidas (aportaciones validadas) · Trazabilidad hasta versión y autor

### Mapa · Bloque 6 de 8 · Evaluar · 9:34

*Evaluar con objetividad*: 17 Cuestionario aprobado por un experto · 18 Observación en el puesto

* `9:35` Evaluar.

### Funcionalidad 17 · Evaluar · Experta y operaria · 9:36

**Cuestionario aprobado por un experto** · Nuria Gil, experta de Mantenimiento, y Lucía Herrero

* Para qué sirve: Comprobar lo que se sabe con preguntas revisadas por un experto.
* Tarjeta (4.7 s):
  * `9:36` Preguntas de la instrucción, aprobadas por un experto.

**Escena `08b-revisar-preguntas-nuria`** · Revisar preguntas · Nuria Gil, experta de Mantenimiento · 22.3 s en el vídeo (toma de 26 s)

* Quién y dónde: Empleada experta (nuria) · `/app/evaluacion`
* Qué se ve: pulsa «Revisar preguntas»; resalta «Por revisar»; resalta la pregunta propuesta con la nota «Propuesta de la IA: enunciado, opciones, paso y explicación»; resalta la opción que la IA marcó como correcta con la nota «La IA la marcó como correcta»; pulsa la opción buena como correcta; resalta la opción que la IA marcó como correcta con la nota «Como dice IT-071, paso 5»; pulsa «Guardar y aprobar».
* Comprobado: Toma v4: la propuesta de la IA llega con «Con llave dinamométrica a 50 N·m» marcada (mal) y Nuria marca «A mano más un cuarto de vuelta», como dice IT-071, paso 5. La semilla tiene la propuesta al revés: corregirla.
* Narración:
  * `9:41` Nuria, de Mantenimiento, revisa las preguntas que la inteligencia artificial propone para calibrar el sensor:
  * `9:48` enunciado, opciones, paso de la instrucción y explicación.
  * `9:52` [corrige] Aquí marcó mal la respuesta: según la instrucción, la tuerca va a mano más un cuarto de vuelta. Nuria lo corrige.
  * `10:01` [aprueba] Y la da por buena.

**Escena `08a-cuestionario-lucia`** · Cuestionario de la brida B · Lucía Herrero · 15.9 s en el vídeo (toma de 27 s)

* Quién y dónde: Empleada (lucia) · `/app/evaluacion`
* Qué se ve: pulsa «Volver a intentarlo»; pulsa «Empezar»; pulsa la opción correcta; pulsa «Siguiente» (×5); pulsa la opción correcta; pulsa «Entregar»; resalta «Cuestionario aprobado».
* Montaje: «Lucía responde las seis preguntas» ×3.
* Comprobado: Grabado el 10/10: 6 de 6, «Has subido al nivel L», falta la observación del supervisor.
* Narración:
  * `10:03` Lucía hace el cuestionario de la brida B.
  * `10:06` [preguntas] Seis preguntas sacadas de los pasos, sobre todo de los críticos, que cambian de orden en cada intento.
  * `10:14` [resultado] **(resultado)** Seis de seis: sube al nivel L, con su evidencia.
* **Resultado** (panel desde el fragmento 3): Evidencia objetiva, ligada a la versión de la instrucción.
* **Bases**: Validación (cuestionario) · Seguimiento de hitos de aprendizaje · Documentación técnica convertida en formación

### Funcionalidad 18 · Evaluar · Jefe de equipo · 10:17

**Observación en el puesto** · Javier Martín observa a Pedro Ruiz

* Para qué sirve: Ver hacer la tarea con una lista: lo que no mide un cuestionario.
* Tarjeta (3.2 s):
  * `10:18` Evaluar viendo hacer la tarea.

**Escena `08c-observacion-javier`** · Observación en el puesto · Javier observa a Pedro · 17.8 s en el vídeo (toma de 32 s)

* Quién y dónde: Jefe de equipo (javier) · `/app/evaluacion?pestana=observar`
* Qué se ve: pulsa «Pedro Ruiz»; resalta los pasos críticos con la nota «Los críticos, en rojo»; pulsa «Bien» en el siguiente paso (×8); escribe «Consigna las cuatro energías y comprueba la energía cero antes de e...»; pulsa «Aprobar».
* Montaje: «Javier marca los ocho pasos y escribe el comentario» ×3.
* Comprobado: Grabado el 10/10: 8 pasos bien, comentario y «Pedro Ruiz sube al nivel U».
* Narración:
  * `10:21` Javier observa a Pedro mientras cambia el molde de la prensa 3.
  * `10:25` [lista] Marca cada paso. Si un crítico, en rojo, sale mal, no se puede aprobar.
  * `10:34` [aprueba] **(resultado)** Aprobada: Pedro sube al nivel U, ya trabaja solo.
* **Resultado** (panel desde el fragmento 3): Nivel U con evidencia: Pedro ya trabaja solo en esta tarea.
* **Bases**: Validación (observación) · Evidencias de competencia · Certificación por puesto o tarea

### Mapa · Bloque 7 de 8 · Certificar · 10:37

*Quién domina cada tarea*: 19 Pasaporte de habilidades · 20 Matriz ILUO del equipo · 21 Versiones nuevas y reevaluación

* `10:38` Certificar.

### Funcionalidad 19 · Certificar · Cada persona · 10:39

**Pasaporte de habilidades** · Marta Sanz

* Para qué sirve: Ver qué tareas se dominan, hasta cuándo y qué falta para subir.
* Tarjeta (4.5 s):
  * `10:39` El pasaporte de habilidades de cada persona.

**Escena `09a-pasaporte-marta`** · Mi progreso · Marta Sanz · 23.6 s en el vídeo (toma de 25 s)

* Quién y dónde: Empleada (marta) · `/app/progreso`
* Qué se ve: resalta la fila de la brida B; resalta «Camino al siguiente nivel»; resalta «Curva de autonomía»; resalta «Alcanzó el nivel U».
* Comprobado: Visto hoy: U en Montaje de la brida B, «Válido hasta septiembre de 2027», camino I, L, U, O con lo cumplido, curva «De 8 consultas en la primera ejecución a 0 en la última» (ejecuciones 8, 6, 5, 3, 2, 1, 1, 0) y 12 evidencias.
* Narración:
  * `10:44` Marta es autónoma, nivel U, en la brida B, hasta octubre de 2027.
  * `10:49` [camino] Y ve qué le falta para el siguiente nivel.
  * `10:54` [curva] Su curva de autonomía: de ocho consultas al copiloto en la primera ejecución a cero en la última. Una medida objetiva.
  * `11:02` [evidencias] **(resultado)** Cada nivel, con sus evidencias y su fecha.
* **Resultado** (panel desde el fragmento 4): Cada nivel, con sus evidencias y su fecha.
* **Bases**: Pasaporte digital de habilidades · Evaluación continua · Seguimiento de progresos individuales · Evidencias de competencia

### Funcionalidad 20 · Certificar · Jefe de equipo · 11:06

**Matriz ILUO del equipo** · Javier Martín

* Para qué sirve: Ver quién domina cada tarea, qué caduca y quién puede formar.
* Tarjeta (4.5 s):
  * `11:07` El equipo de un vistazo: quién domina qué y qué caduca.

**Escena `09b-matriz-javier`** · Matriz ILUO del equipo de Producción · Javier Martín · 21.5 s en el vídeo (toma de 23 s)

* Quién y dónde: Jefe de equipo (javier) · `/app/equipo`
* Qué se ve: resalta «niveles L o más»; resalta la matriz ILUO; pasa el cursor por la celda de Pedro Ruiz en «Cambio de molde en la prensa 3»; desplaza la página; resalta «Caducidades próximas»; desplaza la página; pulsa la celda de Marta Sanz en «Montaje de la brida B»; pulsa «Validar como formador»; pulsa «Confirmar».
* Comprobado: Grabado el 10/10: Lucía en L, Pedro en U, caducidad de Javier a 24 días y Marta validada como formadora (O).
* Narración:
  * `11:11` Javier ve los indicadores de su equipo
  * `11:14` [matriz] y la matriz ILUO, sin papeles: Lucía ya está en L, y Pedro, en U.
  * `11:19` [caducidades] Abajo, lo que caduca: su propio nivel en la prensa 3, en 25 días.
  * `11:25` [formador] **(resultado)** Marta ya es autónoma en la brida B: Javier la valida como formadora y pasa al nivel O.
* **Resultado** (panel desde el fragmento 4): Quién sabe qué, con evidencias y caducidad, sin papeles.
* **Bases**: Indicadores de desempeño · Certificación por puesto o tarea · Gestión de niveles · Renovación y actualización

### Funcionalidad 21 · Certificar · Experta · 11:31

**Versiones nuevas y reevaluación** · Carmen Díaz

* Para qué sirve: Que al cambiar un procedimiento se ponga al día la formación.
* Tarjeta (5.0 s):
  * `11:32` Si cambia el procedimiento, la formación se pone al día.

**Escena `03c-publicar-carmen`** · Una versión nueva de IT-023 · Carmen Díaz publica la versión 2 · 23.0 s en el vídeo (toma de 26 s)

* Quién y dónde: Empleada experta (carmen) · `/app/instrucciones`
* Qué se ve: pulsa «Borradores»; pulsa el borrador de la tabla; pulsa «Publicar versión 2»; resalta la lista de lo que pasará al publicar; pulsa «Confirmar»; espera al servidor (Publicando e indexando la instrucción, acelerado); resalta «deberán reevaluarse»; pulsa «Historial».
* Comprobado: Toma v4: publica el borrador ya revisado (paso 1 con M10); «3 personas deberán reevaluarse» (Carmen, Marta y Lucía).
* Narración:
  * `11:36` Carmen publica la versión 2 de la brida B.
  * `11:41` [dialogo] CidIA avisa de lo que va a pasar: la versión 1 queda obsoleta, se preparan micro-lecciones y preguntas nuevas, y quien tenía nivel tendrá que volver a evaluarse.
  * `11:54` [publicada] **(resultado)** Tres personas, a evaluar de nuevo, y cada versión, en el historial.
* **Resultado** (panel desde el fragmento 3): Tres personas, a evaluar de nuevo, y cada versión, en el historial.
* **Bases**: Renovación y actualización · Documentación técnica convertida en formación · Trazabilidad hasta versión y autor

### Mapa · Bloque 8 de 8 · Administrar · 11:58

*La plataforma*: 22 Espacio de trabajo aislado · 23 Organización, personas e identidad · 24 Modelos solo locales · 25 Registro xAPI, auditoría y estado

* `11:59` Y administrar.

### Funcionalidad 22 · Administrar · Jefe de equipo · 12:00

**Espacio de trabajo aislado** · Javier Martín

* Para qué sirve: Analizar datos en una carpeta privada y una consola sin red.
* Tarjeta (4.0 s):
  * `12:00` Una carpeta y una consola privadas, sin red.

**Escena `11a-espacio-javier`** · Espacio de trabajo · Javier Martín · 31.5 s en el vídeo (toma de 41 s)

* Quién y dónde: Jefe de equipo (javier) · `/app/espacio`
* Qué se ve: resalta «Privada»; pulsa «Subir» (sube paradas-prensa3.csv); resalta «Aislada · sin red»; escribe «python3 informe_paradas.py»; pulsa «Ejecutar»; espera al servidor (Ejecutando en un contenedor aislado del servidor, acelerado); pulsa «paradas-prensa3.png»; desplaza la página; pulsa la línea de órdenes; escribe «python3 -c "import socket; socket.create_connection(('example.com',...»; pulsa «Ejecutar»; resalta la salida de la consola con la nota «Sin red: la conexión falla».
* Montaje: «Tecleo de la orden» ×2; «Tecleo de la orden» ×2.
* Comprobado: Grabado el 10/10: análisis en 3,6 s (gráfico y Excel) y la conexión a example.com falla con Traceback (sin red).
* Narración:
  * `12:04` Javier sube el registro de paradas de la prensa 3
  * `12:13` [consola] y lanza un análisis en la consola, aislada y sin red:
  * `12:21` [resultado] gráfico y tabla en Excel en unos segundos.
  * `12:24` [agente] ¿Y si intenta salir a Internet?
  * `12:31` **(resultado)** La conexión falla: los datos no salen de la empresa.
* **Resultado** (panel desde el fragmento 5): Los datos se analizan sin salir de la empresa.
* **Bases**: Base tecnológica e IA relevante · Mejoras añadidas (espacio de trabajo aislado) · Proteger el conocimiento experto

### Funcionalidad 23 · Administrar · Administración · 12:35

**Organización, personas e identidad** · La administración

* Para qué sirve: Adaptar CidIA a cada empresa: departamentos, puestos, niveles y reglas.
* Tarjeta (4.8 s):
  * `12:35` Cada empresa configura su organización, sin programar.

**Escena `12a-organizacion-admin`** · Organización · departamentos, puestos, tareas, niveles y reglas ILUO · 17.4 s en el vídeo (toma de 20 s)

* Quién y dónde: Administración (admin) · `/app/admin/organizacion`
* Qué se ve: pulsa «IT-023»; resalta «Criticidad»; resalta «Riesgos PRL»; pulsa «Niveles»; resalta «Cómo funcionan los niveles»; pulsa «Empresa y reglas ILUO»; desplaza la página; resalta «Así quedan los niveles».
* Comprobado: Visto hoy: árbol con 4 departamentos, 9 puestos y 23 tareas; ficha de IT-023 (nombre, código, puesto, nivel mínimo, criticidad, descripción, riesgos PRL, tarea activa); pestaña Niveles (Operario, Técnico, Responsable, Dirección y «Cómo funcionan los niveles»); pestaña «Empresa y reglas ILUO» (ejecuciones para L, umbral 80 %, validez en meses y «Así quedan los niveles»).
* Narración:
  * `12:39` Departamentos, puestos y tareas, cada una con su nivel, su criticidad y sus riesgos de prevención.
  * `12:47` [niveles] Los niveles deciden qué documentos encuentra cada persona.
  * `12:51` [reglas] Y las reglas ILUO: ejecuciones, nota del cuestionario y caducidad.

**Escena `12b-empleados-admin`** · Empleados · cuentas, roles, formaciones e identidad · 19.7 s en el vídeo (toma de 20 s)

* Quién y dónde: Administración (admin) · `/app/admin/empleados`
* Qué se ve: resalta la tabla; pulsa «Marta Sanz»; pulsa «Formaciones»; resalta «Diseño de utillajes» con la nota «Formación en otro departamento»; tecla Escape; pulsa «Nueva persona»; resalta «Origen de la identidad» con la nota «Cuenta de CidIA, directorio LDAP o inicio de sesión único»; tecla Escape.
* Comprobado: Visto hoy: tabla con filtros, ficha de Marta (pestañas «Datos y acceso» y «Formaciones 1», rol, departamento, puesto, nivel, experto, «Restablecer contraseña»), «Nueva persona» con «Origen de la identidad: Cuenta de CidIA, Directorio de la empresa (LDAP), Inicio de sesión único (OIDC)» y «CidIA genera una contraseña inicial que verás una sola vez».
* Narración:
  * `12:56` En Empleados, las cuentas, los roles y las formaciones, como la de Marta en Oficina técnica.
  * `13:07` [identidad] Las cuentas pueden ser de CidIA o venir del directorio de la empresa, con el conector ya preparado.
  * `13:13` **(resultado)** Cada empresa, a su manera.
* **Resultado** (panel desde el fragmento 3): Cada empresa lo ajusta a su forma de trabajar.
* **Bases**: Adaptación a cada empresa (20 %) · Gestión de niveles · Integración (identidad) · Incrementar la polivalencia

### Funcionalidad 24 · Administrar · Administración · 13:15

**Modelos solo locales** · La administración

* Para qué sirve: Elegir el modelo de cada función, siempre en el servidor propio.
* Tarjeta (4.4 s):
  * `13:15` Qué modelos usa CidIA, siempre en el servidor propio.

**Escena `12c2-modelos-admin`** · Modelos permitidos · solo locales · 10.8 s en el vídeo (toma de 14 s)

* Quién y dónde: Administración (admin) · `/app/admin/modelos`
* Qué se ve: comprueba que no aparece «DeepSeek»; resalta «CHAT Y COPILOTO»; resalta «VISIÓN»; desplaza la página; resalta «EN LA NUBE»; comprueba que no aparece «DeepSeek».
* Comprobado: Grabada el 11/10/2026 (04_VIDEO/material-v3, revisada fotograma a fotograma). Antes: Mismas acciones que 12c, sin «antes_js»: solo cuando Administración › Modelos ya no liste ese proveedor (incidencia I8). Las dos guardas «esperarSinTexto» hacen fallar la toma si aparece.
* Narración:
  * `13:20` Uno para el chat, otro para la visión, otro para la búsqueda.
  * `13:24` [nube] **(resultado)** Los servicios en la nube están bloqueados: sin nube y sin pago por consulta.
* **Resultado** (panel desde el fragmento 2): Sin nube y sin pago por consulta.
* **Bases**: Bajo coste (15 %) · Proteger el conocimiento experto · Base tecnológica e IA relevante

*Toma antigua `12c-modelos-admin`, sustituida por `12c2-modelos-admin` (fuera del montaje).*

### Funcionalidad 25 · Administrar · Administración · 13:29

**Registro xAPI, auditoría y estado** · La administración

* Para qué sirve: Dejar constancia de todo, exportable, y ver el estado del servidor.
* Tarjeta (4.3 s):
  * `13:30` Todo queda registrado, con un estándar exportable.

**Escena `12d-registro-admin`** · Registro de actividad en xAPI y auditoría · 17.7 s en el vídeo (toma de 20 s)

* Quién y dónde: Administración (admin) · `/app/admin/registro`
* Qué se ve: resalta la página; elige «alcanzó el nivel»; pulsa «Ver sentencia»; resalta la sentencia xAPI con la nota «La sentencia xAPI completa»; pulsa «Ocultar»; resalta «Exportar JSON»; pulsa «Auditoría».
* Comprobado: Visto hoy: pestañas «Actividad (xAPI)» y «Auditoría», filtros de persona, acción (incluye «alcanzó el nivel»), objeto y fechas, «Exportar JSON», «Ver sentencia» y paginación (569 sentencias, 15 páginas). «Ver sentencia» despliega la sentencia en línea (pre.adm-json) y el botón pasa a «Ocultar» (comprobado: no abre un diálogo).
* Narración:
  * `13:34` Cada actividad queda en xAPI, el estándar del aprendizaje: aquí, quién alcanzó un nivel. Se filtra y se exporta para integrarla con otros sistemas.
  * `13:47` [auditoria] Y cada cambio de administración, en la auditoría.

**Escena `12e-sistema-admin`** · Sistema · estado real del servidor · 4.4 s en el vídeo (toma de 8 s)

* Quién y dónde: Administración (admin) · `/app/admin/sistema`
* Qué se ve: resalta «Todo funciona»; desplaza la página.
* Comprobado: Visto hoy: «Todo funciona», CidIA 0.1.0, motor propio PostgreSQL + pgvector, servicios con su latencia, documentos por estado y trabajos recientes.
* Narración:
  * `13:51` **(resultado)** Y el estado del servidor, comprobado al momento.
* **Resultado** (panel desde el fragmento 1): Evidencias objetivas, listas para auditar e integrar.
* **Bases**: Registro de actividades · Auditoría y trazabilidad · Integración (xAPI exportable)

### Cómo cubre las bases · 13:54

*40 · 20 · 15 · 15 · 10 %*: Cobertura funcional · Adaptación · Bajo coste · Mejoras añadidas · Innovación

* `13:55` Así cubre las bases. Cobertura funcional, el cuarenta por ciento: 27 de los 30 puntos del alcance, demostrados.
* `14:04` Adaptación, el veinte: organización, niveles y reglas configurables.
* `14:09` Bajo coste, el quince: todo local y libre, sin pago por consulta.
* `14:14` Mejoras, otro quince: tutor socrático, lagunas, aportaciones y espacio de trabajo.
* `14:20` E innovación, el diez: todo el ciclo, en local y con evidencias.

### Implantación sencilla y licencias libres · 14:24

*Un instalador para los puestos y otro para el servidor*: CidIA-Setup.exe en cada portátil, sin permisos de administrador · instalar-servidor.sh preparado (probado en modo comprobación) · Ejemplo: 1 servidor y 5 puestos, unos 6.200 € con IVA en hardware

* `14:25` Un instalador para cada portátil y otro para el servidor, ya preparado. Un servidor y cinco puestos: unos seis mil doscientos euros, sin cuotas.
* `14:36` Todo con software libre que permite el uso comercial.

### Rodrigo Pascual · Lydia Blanco · Gadea Lucas · Universidad de Burgos · 14:40

*CidIA*: El conocimiento se queda

* `14:40` CidIA: el conocimiento de la planta, capturado, enseñado y medido, sin salir de la empresa.

## 5. Cobertura de las bases

Punto por punto del alcance (`docs/estado-mvp.md`: ✓ funciona de punta a punta, ◐ simplificado, ○ preparado sin probar en el equipo real) y dónde se ve en el vídeo.

| Bloque de las bases | Punto | Estado | Funcionalidades (N) | Escenas |
|---|---|---|---|---|
| Captura y estructuración | Digitalización de procedimientos operativos | ✓ | Del vídeo a la instrucción (4), Versiones nuevas y reevaluación (21) | 03a-captura-video-carmen, 03b-borrador-carmen, 03c-publicar-carmen |
| Captura y estructuración | Captura del conocimiento de operarios expertos | ✓ | Del vídeo a la instrucción (4), Nota de voz convertida en ficha (5), Entrevista guiada (6), Aportaciones desde la planta (16) | 03a-captura-video-carmen, 03b-borrador-carmen, 03d-nota-voz-carmen, 03e-entrevista-carmen, 10a-aportar-voz-pedro, 10b-validar-javier, 10c-cita-marta |
| Captura y estructuración | Generación automática de instrucciones | ✓ | Del vídeo a la instrucción (4) | 03a-captura-video-carmen, 03b-borrador-carmen |
| Captura y estructuración | Documentación técnica convertida en formación | ✓ | Itinerario y micro-lecciones (9), Cuestionario aprobado por un experto (17), Versiones nuevas y reevaluación (21) | 03c-publicar-carmen, 07a-itinerario-lucia, 07b-microleccion-tutor-lucia, 08a-cuestionario-lucia, 08b-revisar-preguntas-nuria |
| Captura y estructuración | Bases de conocimiento inteligentes | ✓ | Biblioteca de documentos (7), Búsqueda con permisos (8) | 04a-documentos-javier, 04b-probar-busqueda-ana, 04c-luis-sin-acceso |
| Captura y estructuración | Gestión centralizada del conocimiento | ✓ | Biblioteca de documentos (7), Cada rol ve lo suyo (2) | 02b2-app-sesion-lucia, 02c-jefe-javier, 02d-admin, 04a-documentos-javier |
| Formación en el puesto | Formación contextualizada en el puesto | ✓ | Modo planta paso a paso (13) | 06-planta-lucia |
| Formación en el puesto | Itinerarios personalizados | ✓ | Itinerario y micro-lecciones (9), Formación cruzada (11) | 07a-itinerario-lucia, 07b-microleccion-tutor-lucia, 07c-formacion-cruzada-marta |
| Formación en el puesto | Micro-learning industrial | ✓ | Itinerario y micro-lecciones (9) | 07a-itinerario-lucia, 07b-microleccion-tutor-lucia |
| Formación en el puesto | Tutorización inteligente | ✓ | Tutor socrático (10), Itinerario y micro-lecciones (9) | 05b-socratico-marta, 07a-itinerario-lucia, 07b-microleccion-tutor-lucia |
| Formación en el puesto | Adaptado al perfil | ◐ | Cada rol ve lo suyo (2), Búsqueda con permisos (8), Itinerario y micro-lecciones (9), Mi perfil: contraseña y memoria personal (3) | 02b2-app-sesion-lucia, 02c-jefe-javier, 02d-admin, 02e-perfil-lucia, 04b-probar-busqueda-ana, 04c-luis-sin-acceso, 07a-itinerario-lucia, 07b-microleccion-tutor-lucia |
| Formación en el puesto | Acceso inmediato a contenidos | ✓ | Copiloto con fuentes, por voz (12), App de escritorio y acceso público (1) | 02a2-app-invitado, 05a-copiloto-voz-marta |
| Acompañamiento | Asistencia guiada paso a paso | ✓ | Modo planta paso a paso (13) | 06-planta-lucia |
| Acompañamiento | Apoyo a la toma de decisiones | ◐ | Copiloto con fuentes, por voz (12) | 05a-copiloto-voz-marta |
| Acompañamiento | Recomendaciones según el contexto | ◐ | Itinerario y micro-lecciones (9), Modo planta paso a paso (13) | 06-planta-lucia, 07a-itinerario-lucia, 07b-microleccion-tutor-lucia |
| Acompañamiento | Validación de tareas realizadas | ✓ | Modo planta paso a paso (13), Foto del resultado, revisada (14) | 06-planta-lucia, 06c-foto-javier |
| Acompañamiento | Seguimiento de progresos individuales | ✓ | Pasaporte de habilidades (19) | 09a-pasaporte-marta |
| Acompañamiento | Necesidades formativas | ✓ | Lagunas de conocimiento (15) | 05c-laguna-marta, 05d-lagunas-javier |
| Evaluación objetiva | Evaluación continua | ✓ | Pasaporte de habilidades (19) | 09a-pasaporte-marta |
| Evaluación objetiva | Seguimiento de hitos | ✓ | Cuestionario aprobado por un experto (17), Pasaporte de habilidades (19) | 08a-cuestionario-lucia, 08b-revisar-preguntas-nuria, 09a-pasaporte-marta |
| Evaluación objetiva | Registro de actividades | ✓ | Registro xAPI, auditoría y estado (25) | 12d-registro-admin, 12e-sistema-admin |
| Evaluación objetiva | Trazabilidad hasta versión y autor | ✓ | Copiloto con fuentes, por voz (12), Aportaciones desde la planta (16), Versiones nuevas y reevaluación (21) | 03c-publicar-carmen, 05a-copiloto-voz-marta, 10a-aportar-voz-pedro, 10b-validar-javier, 10c-cita-marta |
| Evaluación objetiva | Indicadores de desempeño | ✓ | Matriz ILUO del equipo (20) | 09b-matriz-javier |
| Evaluación objetiva | Validación (cuestionario y observación) | ✓ | Cuestionario aprobado por un experto (17), Observación en el puesto (18) | 08a-cuestionario-lucia, 08b-revisar-preguntas-nuria, 08c-observacion-javier |
| Certificación | Evidencias de competencia | ✓ | Observación en el puesto (18), Pasaporte de habilidades (19) | 08c-observacion-javier, 09a-pasaporte-marta |
| Certificación | Pasaporte digital de habilidades | ✓ | Pasaporte de habilidades (19) | 09a-pasaporte-marta |
| Certificación | Certificación por puesto o tarea | ✓ | Observación en el puesto (18), Matriz ILUO del equipo (20) | 08c-observacion-javier, 09b-matriz-javier |
| Certificación | Gestión de niveles | ✓ | Matriz ILUO del equipo (20), Organización, personas e identidad (23) | 09b-matriz-javier, 12a-organizacion-admin, 12b-empleados-admin |
| Certificación | Renovación y actualización | ✓ | Matriz ILUO del equipo (20), Versiones nuevas y reevaluación (21) | 03c-publicar-carmen, 09b-matriz-javier |
| Certificación | Auditoría y trazabilidad | ✓ | Registro xAPI, auditoría y estado (25) | 12d-registro-admin, 12e-sistema-admin |
| Requisitos generales | Base tecnológica e IA relevante | ✓ | Del vídeo a la instrucción (4), Copiloto con fuentes, por voz (12), Espacio de trabajo aislado (22), Agente de escritorio con herramientas (por grabar) | 03a-captura-video-carmen, 03b-borrador-carmen, 05a-copiloto-voz-marta, 11a-espacio-javier |
| Requisitos generales | Aplicable en entorno real | ○ | Registro xAPI, auditoría y estado (25) | 12d-registro-admin, 12e-sistema-admin |
| Requisitos generales | Escalabilidad | ◐ | Registro xAPI, auditoría y estado (25) | 12d-registro-admin, 12e-sistema-admin |
| Requisitos generales | Integración | ◐ | Organización, personas e identidad (23), Registro xAPI, auditoría y estado (25), Espacio de trabajo aislado (22), Agente de escritorio con herramientas (por grabar) | 11a-espacio-javier, 12a-organizacion-admin, 12b-empleados-admin, 12d-registro-admin, 12e-sistema-admin |
| Requisitos generales | Implantación sencilla y económica | ✓ | App de escritorio y acceso público (1), Modelos solo locales (24) | 02a2-app-invitado, 12c2-modelos-admin |

Criterios de valoración y qué los demuestra:

* **40 % · Cobertura funcional**: El ciclo completo funciona: 27 de los 30 puntos del alcance se demuestran y 3 aparecen simplificados. Funcionalidades: Del vídeo a la instrucción, Nota de voz convertida en ficha, Entrevista guiada, Biblioteca de documentos, Búsqueda con permisos, Itinerario y micro-lecciones, Tutor socrático, Formación cruzada, Copiloto con fuentes, por voz, Modo planta paso a paso, Foto del resultado, revisada, Lagunas de conocimiento, Aportaciones desde la planta, Cuestionario aprobado por un experto, Observación en el puesto, Pasaporte de habilidades, Matriz ILUO del equipo, Versiones nuevas y reevaluación.
* **20 % · Adaptación a cada empresa**: Organización, niveles y reglas ILUO configurables, y tres perfiles de servidor preparados: del PC de una pyme a un servidor con GPU. Funcionalidades: Organización, personas e identidad, Cada rol ve lo suyo, Formación cruzada.
* **15 % · Bajo coste**: Todo en local y sobre software libre: sin pago por consulta ni por usuario. Funcionalidades: Modelos solo locales, App de escritorio y acceso público.
* **15 % · Mejoras añadidas**: Tutor socrático, lagunas, aportaciones validadas desde la planta y espacio de trabajo aislado. Funcionalidades: Tutor socrático, Lagunas de conocimiento, Aportaciones desde la planta, Espacio de trabajo aislado.
* **10 % · Grado de innovación**: La combinación: el ciclo completo con IA en local, niveles basados en evidencias y un saber que crece desde la planta. Funcionalidades: Del vídeo a la instrucción, Modo planta paso a paso, Aportaciones desde la planta, Matriz ILUO del equipo.

## 6. Tomas que requieren grabación

Todas con datos recién sembrados (P1). Hasta grabarlas, van en el proyecto con `"omitir": true` y el vídeo usa las tomas de la v1. El grabador y `voz.py` se saltan las piezas omitidas, así que cada toma está también como escena suelta en `docs/video/v2/tomas-por-grabar/` (copias que escribe `guion_v2.py --extraer-tomas`; la fuente es la pieza de `recorrido.json`):

```powershell
python herramientas\video\voz.py narrar docs\video\v2\tomas-por-grabar\02e-perfil-lucia.json --salida $V2\voces
node herramientas\video\grabador.mjs docs\video\v2\tomas-por-grabar\02e-perfil-lucia.json --salida $V2\grabaciones --voces $V2\voces --secretos <fichero de secretos>
```

Con la toma buena: quitar su `omitir` en `recorrido.json`, poner `"omitir": true` en las piezas de `sustituye`, ajustar los recortes al informe nuevo (y montar con `--grabaciones` apuntando a una carpeta que tenga las tomas viejas y las nuevas) y ejecutar `guion_v2.py --renumerar` si entra una funcionalidad nueva.

### `11b-agente-app` · El agente de la app usa el espacio de trabajo por MCP (con el modelo del MSI)

* Funcionalidad: Agente de escritorio con herramientas (Jefe de equipo, en la app de escritorio).
* Estado: Probado el 10/10 en la app con Lucía: con qwen3:0.6b el agente no llama a las herramientas MCP ni siquiera nombrándolas y responde sin fuentes (inventa). Se deja fuera del vídeo; la frase de 11a dice solo lo que hay (el espacio se ofrece al agente por MCP).
* Notas: Solo si sale bien en un ensayo. Si no, se queda fuera y basta la frase final de 11a.
* Narración prevista (unos 10 s de voz):
  * Desde la app, el agente lista los ficheros de la carpeta de Javier con la herramienta del servidor.
  * Un agente que trabaja con los datos de la planta sin sacarlos de ella.

```json
{
  "id": "11b-agente-app",
  "titulo": "El agente de la app usa el espacio por MCP",
  "bases": "Bases: integración (MCP y API compatible con OpenAI)",
  "rol": "Jefe de equipo (javier) en la app de escritorio",
  "contexto": "app",
  "conectar": {"puerto": 9333, "objetivo": "dsh-app://app/"},
  "usuario": null,
  "ruta": null,
  "escala": 1,
  "acciones": [
    {"clicTexto": "Nueva conversación"},
    {"escribir": ["textarea, [contenteditable=true]", "Usa la herramienta mcp__cidia__espacio_listar y dime qué ficheros hay en mi carpeta de trabajo."], "ms_tecla": 35},
    {"tecla": "Enter"},
    {"esperarTexto": "paradas-prensa3", "max": 180000, "acelerar": "El agente llama a la herramienta del servidor"}
  ],
  "cola_voz_s": 0.7,
  "cola_accion_s": 0.7,
  "fuente": "docs/video/v2/recorrido.json (toma por grabar)",
  "grabacion_v3": "04_VIDEO/material-v3/grabaciones (11/10/2026)"
}
```

Sin toma y sin formato de grabador (fuera del navegador): la instalación de `CidIA-Setup.exe` en un portátil y la de `instalar-servidor.sh`. Se cuentan en la tarjeta de implantación del cierre; si se quieren enseñar, grabar la pantalla de Windows con ffmpeg (gdigrab) y la terminal del servidor en modo comprobación, unos 10 s cada una, y añadirlas como escenas antes de `cierre-implantacion`.

## 7. Resumen para el jurado

`docs/video/v2/resumen.json`, **4:21**: el mismo patrón con una funcionalidad de cada paso del ciclo. Comparte grabaciones, ids y narración con el completo (mismas voces); solo `r-mapa` es propia.

| Empieza | Pieza | Dura |
|---|---|---|
| 0:00 | `v2-portada` · V DESAFÍO industrial · POLO positivo | 9.3 s |
| 0:09 | `r-mapa` · Mapa de funcionalidades | 10.1 s |
| 0:18 | `func-captura-video` · Funcionalidad 4 · Capturar · Experta | 4.7 s |
| 0:22 | `03a-captura-video-carmen` · Carmen Díaz, experta · captura en vídeo de la brida B | 14.0 s |
| 0:36 | `03b-borrador-carmen` · El borrador: la IA propone, la experta decide | 38.9 s |
| 1:14 | `func-busqueda-permisos` · Funcionalidad 8 · Estructurar · Responsable y recién llegado | 4.0 s |
| 1:18 | `04b-probar-busqueda-ana` · Probar búsqueda · Ana López, responsable de Oficina técnica (nivel 3) | 24.3 s |
| 1:42 | `func-itinerario` · Funcionalidad 9 · Formar · Operaria recién llegada | 4.5 s |
| 1:46 | `07b-microleccion-tutor-lucia` · Micro-lecciones y tutor socrático de la tarea | 15.7 s |
| 2:01 | `func-modo-planta` · Funcionalidad 13 · Acompañar · Operaria recién llegada | 4.2 s |
| 2:05 | `06-planta-lucia-r` · Lucía Herrero · modo planta en la estación E2, de principio a fin | 35.1 s |
| 2:39 | `func-observacion` · Funcionalidad 18 · Evaluar · Jefe de equipo | 3.2 s |
| 2:42 | `08c-observacion-javier` · Observación en el puesto · Javier observa a Pedro | 17.8 s |
| 2:59 | `func-matriz-iluo` · Funcionalidad 20 · Certificar · Jefe de equipo | 4.5 s |
| 3:03 | `09b-matriz-javier-r` · Matriz ILUO del equipo de Producción · Javier Martín | 23.4 s |
| 3:26 | `cierre-criterios-r` · Cómo cubre las bases | 32.3 s |
| 3:58 | `cierre-implantacion-r` · Implantación sencilla y licencias libres | 15.3 s |
| 4:13 | `cierre-final` · Rodrigo Pascual · Lydia Blanco · Gadea Lucas · Universidad de Burgos | 7.8 s |

## 8. Cómo se monta

Desde `cidia/`, con las tomas de `04_VIDEO/material-v3` y la voz final en `04_VIDEO/v2/voces-final` (montaje v2 con HyperFrames; detalle en `herramientas/video/README.md`, apartado 10, y en `04_VIDEO/v2/final/LEEME.md`):

```powershell
$M = (Resolve-Path "..\04_VIDEO\material-v3").Path; $V2 = (Resolve-Path "..\04_VIDEO\v2").Path
python herramientas\video\voz.py narrar docs\video\v2\recorrido.json --perfil v2 --semilla 1234 --salida $V2\voces-final
python herramientas\video\guion_v2.py docs\video\v2\recorrido.json --resumen docs\video\v2\resumen.json --grabaciones $M\grabaciones --voces $V2\voces-final
python herramientas\video\hyperframes.py todo docs\video\v2\recorrido.json --grabaciones $M\grabaciones --voces $V2\voces-final --trabajo $V2\trabajo\recorrido --salida $V2\final\CidIA-recorrido.mp4
python herramientas\video\hyperframes.py todo docs\video\v2\resumen.json --grabaciones $M\grabaciones --voces $V2\voces-final --trabajo $V2\trabajo\resumen --salida $V2\final\CidIA-resumen.mp4
```

Las duraciones de este guion salen de `montaje.planificar` sin rampas ni recortes automáticos: el montaje v2 (`montaje.py --limpio`) añade rampas de 0,3 s a las aceleraciones y quita los ratos con la pantalla quieta y sin voz, así que sus escenas pueden durar unas décimas menos. Las tarjetas de funcionalidad del montaje v2 duran al menos 6,5 s (7,5 en el resumen) y lo que pida la lectura de su «para qué sirve» (palabras / 3 + 1 s), y una escena se alarga con su último fotograma si el panel de resultado no cabe después de la última acción: el recorrido montado dura unos 17 min y el resumen, unos 5.

## 9. Si hay que acortar

El objetivo es de 12 a 14 minutos para el completo y de 3 a 4 para el resumen. Si la voz definitiva es más lenta que la medida, estos recortes no quitan ninguna funcionalidad (en orden de preferencia):

* quitar la tarjeta de quién es quién (las personas ya salen en cada tarjeta de funcionalidad): unos 5 s (`v2-reparto`).
* quitar el estado del servidor (el panel de resultado de la funcionalidad pasa a 12d): unos 4 s (`12e-sistema-admin`).
* quitar el itinerario y dejar solo la micro-lección (la tarjeta ya dice qué le falta): unos 8 s (`07a-itinerario-lucia`).
* dejar solo a Lucía en «Cada rol ve lo suyo» y contar los otros roles en su narración: unos 11 s (`02c-jefe-javier`, `02d-admin`).
* Subir el narrador de 0,95 a 1,0: unos 34 s, repartidos (la voz suma 11.3 min).

## 10. Avisos de la comprobación

* Aviso: 01d-planta-admin: 4.2 s de imagen congelada (la voz es más larga que la imagen)

