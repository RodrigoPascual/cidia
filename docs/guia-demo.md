# Guía de la demostración de CidIA

La demostración de 3 minutos, paso a paso: qué preparar, qué hacer y qué decir en cada momento, qué hacer si algo falla en directo y cómo grabar el vídeo de respaldo. El guion sale de [`datos-demo/README.md`](../datos-demo/README.md), que explica también quién es quién en «Metalúrgica Arlanza, S. L.» (empresa ficticia; todos los datos son sintéticos). La instalación del servidor está en [`docs/manual-servidor.md`](manual-servidor.md).

## 1. Qué se enseña

| Paso | Minuto | Cuenta | Qué se ve |
|---|---|---|---|
| 1. El problema | 0:00 | `admin` | La empresa, sus cuatro departamentos y la tarea IT-023 (brida B de la línea 2). |
| 2. La captura | 0:25 | `carmen` | Se sube el vídeo de Carmen; mientras se procesa, la instrucción IT-023 ya publicada. |
| 3. La validación | 0:55 | `carmen` | El borrador que ha salido del vídeo: la experta corrige y marca el paso crítico. |
| 4. El aprendizaje | 1:25 | `lucia` (app) y `marta` | Modo planta con pregunta por voz y copiloto que cita la solución de un compañero. |
| 5. El progreso | 2:05 | `javier` | Niveles ILUO, curva de autonomía, aportaciones por validar y lagunas. |
| 6. Permisos y cierre | 2:35 | `luis`, `ana`, `marta`, `admin` | La misma pregunta con dos niveles distintos, la formación cruzada y el registro xAPI. |

## 2. Equipos y material

* **Servidor**: el MSI (RTX 4080 Laptop de 12 GB) con Ubuntu y CidIA instalado con el perfil `msi` (manual del servidor, apartados 3 y 4), con su cargador.
* **Portátil de presentación**: Windows con `CidIA-Setup.exe` instalado y la dirección del MSI (`http://<IP-del-MSI>:18700`), con su cargador, salida HDMI para el proyector y un micrófono que funcione bien en una sala con ruido (mejor unos auriculares con micrófono USB que el del portátil).
* **Red propia**: un router o un switch pequeño y dos cables de red. No dependas de la wifi del recinto: el MSI y el portátil se ven entre sí sin Internet. Reserva en ese router la IP del MSI.
* **Ficheros en el portátil**: `datos-demo/video/brida-b-sintetico.mp4` en el Escritorio y el vídeo de respaldo (apartado 7), también en una memoria USB y en el móvil.
* **Contraseñas**: la común de las cuentas de demostración y la de `admin`, en tu gestor de contraseñas. No las escribas en papel ni en la pantalla compartida.
* Opcional: un cable HDMI para conectar el MSI al proyector (plan B de red, apartado 6) y una regleta.

## 3. El día antes

### 3.1 Servidor (MSI)

1. **Marcar el MSI como servidor de demostración.** La semilla de datos sintéticos solo se carga con `CIDIA_CREAR_SEMILLA=true`, que en el perfil `msi` viene a `false`:

   ```bash
   sudo sed -i 's/^CIDIA_CREAR_SEMILLA=.*/CIDIA_CREAR_SEMILLA=true/' /opt/cidia/cidia/servidor/despliegue/perfiles/msi.env
   sudo cidia arrancar
   ```

   En uno o dos minutos aparecen los datos (Administración › Sistema muestra el estado de la semilla). Solo se siembra en una base vacía: si el MSI tiene ya departamentos, documentos o personas de otras pruebas, la semilla se niega (nunca mezcla datos de demostración con datos propios) y hay que partir de una instalación limpia. Es un cambio local: la semana de la demo no ejecutes `cidia actualizar`.
2. **Contraseña de las cuentas de demostración** (opcional): si quieres una que recuerdes, añade `CIDIA_DEMO_CONTRASENA=<la que elijas>` a `/opt/cidia/secretos/cidia.env` antes de sembrar (o vuelve a sembrar después, paso 5). Si no, la semilla genera una y la guarda en `/opt/cidia/datos/usuarios-demo.txt` (`sudo cat` para verla). `admin` conserva la suya.
3. **Energía**: siempre enchufado, sin suspensión y con la tapa sin efecto (el instalador lo ofrece; a mano, manual del servidor, apartado 3.4) y `powerprofilesctl set performance`. Nada de actualizaciones de Ubuntu ni de Docker esa semana.
4. **Primera preparación**: `sudo cidia demo preparar`. La primera vez descarga el modelo de voz, así que hace falta Internet. Debe terminar con «Listo para la demo» y los dos modelos «100 % en la GPU».
5. **Ensayos**: dos o tres pasadas completas con cronómetro, siguiendo el apartado 5. Después de cada una, deja los datos como al principio:

   ```bash
   sudo cidia demo reiniciar-datos     # pide escribir REINICIAR; tarda uno o dos minutos
   ```

6. **Copia limpia**: con los datos recién sembrados, `sudo cidia copia` y apunta su nombre (`cidia-AAAAMMDD-HHMMSS`). Es el plan C si la base queda en mal estado.

### 3.2 Portátil Windows

1. Abre CidIA y entra una vez con cada cuenta del guion para comprobar las contraseñas: `admin`, `carmen`, `lucia`, `marta`, `javier`, `luis` y `ana`.
2. **Voz**: las preguntas por voz se hacen desde la **app CidIA**. En un navegador con `http://` y una IP el micrófono no está disponible (los navegadores solo lo permiten con `https` o en `localhost`). Prueba el micrófono en Modo planta con `lucia`.
3. **Una ventana por cuenta**, con la sesión ya iniciada y en el orden del guion, para no perder tiempo entrando y saliendo: la app CidIA con `lucia` y, para las demás, un perfil de Edge por cuenta (Edge › Perfiles › Agregar perfil, con el nombre de la persona) abierto en `http://<IP-del-MSI>:18700/app/`. Ancla las ventanas en la barra de tareas en ese orden.
4. **Windows tranquilo**: «No molestar» activado, Windows Update en pausa, plan de energía de máximo rendimiento y sin suspensión con el cargador, aplicaciones de chat cerradas y un fondo de escritorio neutro.
5. **Pantalla**: prueba con un proyector o una pantalla externa en modo «Duplicar» y sube el zoom del navegador al 110 o 125 % para que se lea desde el fondo de la sala.
6. Graba el **vídeo de respaldo** (apartado 7).

## 4. Una hora antes

1. **MSI**: enchufado, con el cable de red conectado al router de la demo y arrancado en Ubuntu.
2. Si has ensayado hoy: `sudo cidia demo reiniciar-datos`.
3. `sudo cidia demo preparar`: deja los modelos cargados en la GPU sin caducidad, el modelo de voz cargado, para WeKnora y el espacio de trabajo si estaban en marcha (no se enseñan) y muestra la memoria, la GPU y la dirección para los portátiles. Tiene que decir **«Listo para la demo»**. Si sale algún ✘, corrígelo con lo que indica y repítelo.
4. **Borrador de respaldo**: con `carmen`, sube una vez `brida-b-sintetico.mp4` en Captura y deja que se procese, sin publicar. Si en directo el procesado tarda, abres este.
5. **Portátil**: enchufado y en la red de la demo. Abre `http://<IP-del-MSI>:18700/salud` en el navegador (debe responder), abre las ventanas del apartado 3.2 y comprueba que ninguna ha perdido la sesión.
6. Haz una pregunta de calentamiento en el copiloto con `marta` («¿Cómo se monta la brida B?»): comprueba toda la cadena y la respuesta debe llegar en pocos segundos.
7. El vídeo de respaldo abierto en el reproductor, en pausa en 0:00, en una ventana aparte.
8. Sonido del portátil y micrófono probados, móvil en silencio y cronómetro a mano.

## 5. La demostración paso a paso

Cada paso dice qué hacer, una propuesta de qué decir y el plan B. Regla general: **si algo tarda más de 15 segundos, no esperes**: sigue hablando, pasa al plan B del paso o al vídeo de respaldo en ese minuto.

### Paso 1 · 0:00 · El problema (`admin`)

**Hacer.** Inicio: «Metalúrgica Arlanza». Abre Organización: los cuatro departamentos con su color y, en Producción, la tarea IT-023 de la línea 2.

**Decir.** «Esta es Metalúrgica Arlanza, una empresa de Burgos con cuatro departamentos. Carmen es la que sabe montar la brida B de la línea 2. Cuando se jubile, eso se pierde. CidIA captura ese conocimiento, lo enseña en el puesto y mide quién lo domina, y todo corre dentro de la empresa, en este portátil.»

**Plan B.** Si la página no carga, recarga (F5). Si sigue sin cargar, problema de red o del servidor: apartado 6.

### Paso 2 · 0:25 · La captura (`carmen`)

**Hacer.** Captura › subir vídeo: `brida-b-sintetico.mp4` (un minuto, siete escenas narradas). Mientras se procesa, Instrucciones › IT-023: siete pasos con su imagen y el paso 3 marcado como crítico.

**Decir.** «Carmen graba con el móvil cómo monta la brida y lo sube. CidIA transcribe lo que explica, detecta los cambios de escena y propone los pasos, cuáles son críticos y los riesgos. Así queda una instrucción ya publicada: siete pasos, cada uno con su imagen, y el 3 es crítico: cuatro tornillos en cruz a 25 newton metro con llave dinamométrica.»

**Plan B.** Si la subida falla o va lenta, no esperes: enseña IT-023 y en el paso 3 abre el borrador de respaldo.

### Paso 3 · 0:55 · La validación (`carmen`)

**Hacer.** Abre el borrador generado por el vídeo, corrige un texto y marca el paso 3 como crítico. En la versión de 3 minutos, mejor no publicar: ahorra tiempo y el paso 5 sale como se ha ensayado. Si publicas, queda como versión 2, la 1 pasa a obsoleta y Marta y Carmen quedan marcadas para reevaluación (se ve en el paso 5).

**Decir.** «La IA propone, pero decide la experta: Carmen corrige lo que haga falta y marca lo crítico. Cuando publica, la versión anterior queda obsoleta y CidIA avisa de quién tiene que volver a demostrar que sabe hacerlo.»

**Plan B.** Si el borrador del directo no está, abre el de respaldo. Si tampoco, enseña la diferencia entre versiones con IT-061: la versión 2 añadió «Aclimatar la pieza» y David quedó pendiente de reevaluación.

### Paso 4 · 1:25 · El aprendizaje (`lucia` en la app, `marta`)

**Hacer.** En la app, con `lucia`: Modo planta › IT-023. Avanza hasta el paso 3 y pregunta por voz «¿Qué llave uso?»: la respuesta cita IT-023, paso 3 (llave dinamométrica de media pulgada). Confirma el paso crítico. Después, en el Copiloto con `marta`: «La prensa 3 se ha atascado al cambiar el molde, ¿qué hago?»: cita la solución de Pedro validada por Javier.

**Decir.** «Lucía acaba de incorporarse. En el puesto, CidIA le enseña un paso cada vez y no la deja seguir sin confirmar los críticos. Pregunta por voz, con las manos ocupadas, y la respuesta dice de dónde sale. Y lo que aprende la planta vuelve a la planta: la solución que dio Pedro, validada por su jefe, ya la usa Marta.»

**Plan B.** Si la voz no entiende la pregunta o no responde, escríbela: la respuesta es la misma. Si la respuesta tarda, explica las citas mientras llega; pasados 15 segundos, sigue con Marta o pasa al vídeo en el minuto 1:25.

### Paso 5 · 2:05 · El progreso (`javier`)

**Hacer.** Progreso del equipo: Marta con nivel U en la brida B y su curva de autonomía (de 8 consultas a 0); el nivel O del propio Javier en IT-031 avisa de que caduca pronto. Validar aportaciones: dos pendientes, una es la nota de voz de Lucía de hace dos horas. Lagunas: «¿Qué presión lleva el cilindro de la prensa 2?», preguntada tres veces.

**Decir.** «El jefe ve quién domina cada tarea con la escala ILUO, con evidencias y no con una matriz en papel: Marta ya no necesita consultar nada en la brida B. Valida lo que aporta su gente antes de que se publique. Y ve lo que la planta pregunta y nadie ha documentado: esa es la siguiente captura.»

**Plan B.** Si una página tarda, recarga. Si vas tarde, salta las lagunas.

### Paso 6 · 2:35 · Permisos y cierre (`luis`, `ana`, `marta`, `admin`)

**Hacer.** Con `luis`: «¿Quién aprueba la compra de un utillaje de más de 3.000 €?». No ve el documento de costes (es de nivel 3): CidIA no lo cita ni dice que existe y la pregunta queda como laguna. Con `ana`, la misma pregunta se responde con el documento de costes. Con `marta`, el Manual de iniciación a Oficina técnica aparece porque se está formando allí. Cierra con Registro de actividad (xAPI) de `admin`.

**Decir.** «Cada persona encuentra solo lo que le corresponde por departamento y nivel: para Luis ese documento no existe. Ana, la responsable, sí lo ve. Marta, que se forma en Oficina técnica, ve su material de iniciación. Y todo queda registrado en xAPI, el estándar de la formación. CidIA: el conocimiento de la planta, capturado, enseñado y medido, sin que salga de la empresa.»

**Plan B.** Si vas tarde, quédate con Luis y Ana y cierra con la frase final. Si la respuesta de Ana tarda, cierra igualmente con el registro xAPI.

## 6. Si algo falla en directo

| Síntoma | En el momento | Después (o en el MSI, si hay una segunda persona) |
|---|---|---|
| Nada carga en el portátil | Mira el cable y el router. Si no se arregla en 15 s, vídeo de respaldo. | Conecta el MSI al proyector por HDMI y sigue en su navegador con `http://127.0.0.1:18700/app/`: en `localhost` el micrófono sí funciona en el navegador. |
| Respuestas muy lentas | Sigue hablando; pasados 15 s, siguiente paso o vídeo. | `sudo cidia estado`: los modelos deben estar «100% GPU». Si no, `sudo cidia demo preparar`. |
| Una ventana pide la sesión | Entra de nuevo (contraseña desde el gestor de contraseñas, sin mostrarla). | Antes de la siguiente pasada, comprueba todas las ventanas. |
| La voz no responde | Escribe la pregunta. | `sudo cidia registros asr` y `sudo cidia demo preparar`. |
| Los datos no son los del guion (restos de un ensayo) | Sigue con lo que haya o pasa al vídeo. | `sudo cidia demo reiniciar-datos` (uno o dos minutos; nunca durante la demo). |
| El servidor no responde | Vídeo de respaldo. | `sudo cidia reiniciar` (uno o dos minutos) y `sudo cidia demo preparar`. Si la base quedó mal: `sudo cidia restaurar <copia limpia>`. |
| El MSI se ha apagado o suspendido | Vídeo de respaldo. | Enciéndelo, espera a Ubuntu (CidIA arranca solo) y `sudo cidia demo preparar`. |

Con el vídeo de respaldo, avisa con naturalidad: «Os lo enseño en la grabación que hicimos ayer con el mismo equipo», y narra encima.

## 7. Grabar el vídeo de respaldo

1. **Cuándo**: el día antes, después de `sudo cidia demo reiniciar-datos` y `sudo cidia demo preparar`, en el mismo portátil, con la misma resolución y las mismas ventanas que el día de la demo.
2. **Con qué**:
   * **OBS Studio** (gratuito): escena con la fuente «Captura de pantalla» y la fuente de audio del micrófono; en Ajustes › Salida, formato de grabación MP4; en Ajustes › Vídeo, 1920×1080 a 30 fps. «Iniciar grabación» y «Detener grabación».
   * O la **Herramienta Recortes** de Windows 11: Win+Mayús+R, elige la pantalla entera y pulsa «Iniciar». Comprueba antes que graba el micrófono.
   * La Xbox Game Bar (Win+Alt+R) no sirve: graba una sola ventana y la demo salta entre varias.
3. **Cómo**: sigue el guion del apartado 5 con tu narración, sin prisa, y repite hasta tener una toma limpia de unos 3 minutos. Incluye la pregunta por voz.
4. **Editar** (opcional, con Clipchamp, que viene con Windows 11): recorta las esperas, como el procesado del vídeo, y añade al principio un rótulo discreto «Grabación del ensayo».
5. **Apunta en qué segundo empieza cada paso** (0:00, 0:25, 0:55, 1:25, 2:05, 2:35) para poder saltar al punto exacto.
6. **Guárdalo en tres sitios**: Escritorio del portátil, memoria USB y móvil. Comprueba que se reproduce **sin Internet** con el reproductor de Windows.
7. Como último recurso, haz además una captura de pantalla de cada paso.

## 8. Después de la demo

```bash
sudo cidia demo restaurar          # caducidad normal de los modelos y servicios opcionales de vuelta
sudo cidia demo reiniciar-datos    # deja los datos listos para la siguiente
```

## 9. Lista de comprobación final

Servidor (MSI):

- [ ] Enchufado, con cable de red al router de la demo y la IP reservada.
- [ ] Suspensión desactivada y la tapa sin efecto.
- [ ] `CIDIA_CREAR_SEMILLA=true` en `perfiles/msi.env` y datos sembrados.
- [ ] Copia limpia hecha y su nombre apuntado.
- [ ] `sudo cidia demo preparar`: «Listo para la demo», los dos modelos «100 % en la GPU» y la voz transcribiendo.

Portátil:

- [ ] Enchufado y en la red de la demo; `http://<IP-del-MSI>:18700/salud` responde.
- [ ] App CidIA con `lucia` y micrófono probado.
- [ ] Ventanas de `admin`, `carmen`, `marta`, `javier`, `luis` y `ana` con la sesión iniciada y en orden.
- [ ] `brida-b-sintetico.mp4` en el Escritorio y borrador de respaldo procesado con `carmen`.
- [ ] Pregunta de calentamiento respondida en pocos segundos.
- [ ] «No molestar», Windows Update en pausa, pantalla duplicada y zoom subido.
- [ ] Vídeo de respaldo abierto en pausa, también en la memoria USB y en el móvil.

Al terminar:

- [ ] `sudo cidia demo restaurar` y, si va a haber otra, `sudo cidia demo reiniciar-datos`.
