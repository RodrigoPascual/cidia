# Manual del servidor CidIA

Cómo poner un equipo con Ubuntu como servidor de CidIA y dejarlo listo para los portátiles: el portátil MSI de la demo, un PC de una pyme o un servidor de una gran empresa. Está escrito para quien prepara el equipo, aunque no sea especialista en Linux. La referencia técnica (opciones, variables, garantías) está en [`servidor/despliegue/README.md`](../servidor/despliegue/README.md).

En resumen:

1. Ubuntu 24.04 (o 22.04) instalado, enchufado, con cable de red y sin suspenderse.
2. `sudo bash instalar-servidor.sh` desde la carpeta `servidor/despliegue` del repositorio.
3. Abrir `http://<ip-del-servidor>:18700/app/` desde otro equipo y entrar con la cuenta de administración.
4. Escribir `http://<ip-del-servidor>:18700` en el instalador de CidIA de los portátiles.

## 1. Qué se instala

```
Portátiles Windows (app CidIA)                Servidor CidIA (Ubuntu + Docker)
┌─────────────────────────────┐               ┌──────────────────────────────────────────┐
│ CidIA-Setup.exe             │  red local    │ gateway   puerto 18700 (único publicado) │
│ dirección del servidor:     │ ────────────▶ │ postgres  base de datos (solo interna)   │
│ http://192.168.1.50:18700   │               │ ollama    modelos de IA (127.0.0.1)      │
└─────────────────────────────┘               │ asr       voz a texto (127.0.0.1)        │
                                              └──────────────────────────────────────────┘
```

Todo corre en contenedores de Docker dentro del proyecto `cidia`. Los datos de la empresa (documentos, vídeos, base de datos) se quedan en el servidor y nunca salen a Internet: Internet solo hace falta para instalar y para actualizar.

## 2. Requisitos por tipo de empresa

Las cifras de capacidad son orientativas y hay que medirlas en cada equipo.

| | Pyme pequeña, sin GPU | Pyme o mediana, con GPU de 12-16 GB (el MSI) | Gran empresa |
|---|---|---|---|
| Perfil del instalador | `generico` | `msi` | perfil a medida desde `perfiles/plantilla.env` |
| Procesador | 8 núcleos modernos (4 como mínimo) | 8 núcleos o más | 16 núcleos o más |
| Memoria | 16 GB (8 como mínimo, con modelos pequeños) | 32 GB | 64-128 GB |
| GPU | No | NVIDIA con 12-16 GB (RTX 4080 Laptop, 4070 Ti, 4060 Ti 16 GB…) | NVIDIA con 24-48 GB o varias |
| Disco | SSD con 100 GB libres (50 como mínimo) | SSD con 150 GB libres | NVMe con 1 TB o más |
| Modelos | `ministral-3:3b` (con menos de 16 GB: `qwen3:1.7b` y `qwen3.5:0.8b`) y `qwen3-embedding:0.6b` | `ministral-3:8b` y `qwen3-embedding:0.6b`, contexto 32K | modelos mayores, más contexto y varias peticiones en paralelo |
| Qué esperar | Funciona, con respuestas lentas. Bien para captura, consulta e instrucciones de los puestos críticos | Todo CidIA para un centro y varios puestos, del orden de 40 a 60 tokens por segundo con un usuario, más rápido de lo que se lee | Muchos usuarios a la vez y varias plantas; directorio de la empresa, MES, GMAO y LMS |
| Sistema | Ubuntu 24.04 o 22.04 (escritorio o servidor), amd64 o arm64 | Ubuntu 24.04 en arranque dual con Windows | Ubuntu Server 24.04 |

Todos los perfiles usan el mismo modelo de búsqueda por significado (`qwen3-embedding:0.6b`), así que se puede empezar sin GPU y pasar a un equipo con GPU sin volver a procesar los documentos. Para la gran empresa, el MVP instala Ollama; servir los modelos con vLLM queda para una fase posterior.

Además, en todos los casos: conexión por cable a la red de la empresa, una IP fija (o reservada en el router) y acceso a Internet durante la instalación (`download.docker.com`, Docker Hub, `registry.ollama.ai`, GitHub, PyPI, npm y Hugging Face).

## 3. Preparar el MSI con Ubuntu en arranque dual

El MSI conserva Windows y arranca Ubuntu para hacer de servidor.

### 3.1 En Windows, antes de empezar

1. Haz una copia de seguridad de lo importante.
2. **BitLocker**: si el disco está cifrado, apunta la clave de recuperación (cuenta de Microsoft, «Dispositivos», «Claves de recuperación de BitLocker») o suspende la protección. Cambiar el orden de arranque puede pedirla.
3. **Inicio rápido**: Panel de control › Opciones de energía › «Elegir el comportamiento de los botones de inicio/apagado» › desmarca «Activar inicio rápido». Evita que Windows deje el disco bloqueado.
4. **Espacio para Ubuntu**: Administración de discos › clic derecho en `C:` › «Reducir volumen» y libera al menos 250 GB. Deja ese espacio sin asignar.
5. Graba Ubuntu 24.04 LTS (versión de escritorio) en una memoria USB con Rufus o balenaEtcher.

### 3.2 BIOS del MSI

Se entra con **Supr** al encender; el menú de arranque sale con **F11**.

* **Secure Boot** puede quedarse activado: Ubuntu lo admite. El controlador de NVIDIA pedirá registrar una clave al reiniciar (ver 3.3).
* Si el instalador de Ubuntu no ve el disco, desactiva **Intel VMD/RST**. Antes, prepara Windows para el cambio (arranque en modo seguro una vez) o dejará de arrancar.
* Si la BIOS ofrece el modo de gráfica (híbrido o solo discreta), cualquiera sirve: CUDA funciona en modo híbrido.

### 3.3 Instalar Ubuntu

1. Arranca desde la memoria USB (F11) y elige «Instalar Ubuntu».
2. Marca **«Instalar software de terceros para gráficos y Wi-Fi»**: instala el controlador de NVIDIA. Con Secure Boot te pedirá una contraseña; apúntala.
3. Tipo de instalación: **«Instalar Ubuntu junto a Windows»** (usa el espacio libre).
4. Usuario: por ejemplo `cidia`, con una contraseña fuerte. Nombre del equipo: `cidia-servidor`.
5. Al reiniciar, si aparece la pantalla azul **«Perform MOK management»**: «Enroll MOK» › «Continue» › «Yes» › la contraseña del paso 2 › «Reboot».
6. Ya en Ubuntu, abre una terminal (Ctrl+Alt+T):

   ```bash
   sudo apt update && sudo apt full-upgrade -y
   nvidia-smi                       # debe mostrar la RTX y su memoria
   ```

   Si `nvidia-smi` no responde: `sudo ubuntu-drivers install`, reinicia y repite. Comprueba Secure Boot con `mokutil --sb-state`.
7. Arranque por defecto: Ubuntu aparece primero en el menú de GRUB y arranca solo a los pocos segundos, así que tras un corte de luz vuelve como servidor.
8. Si después la hora de Windows sale cambiada: `timedatectl set-local-rtc 1 --adjust-system-clock`.

### 3.4 Energía: que no se suspenda nunca

Un servidor dormido no responde a los portátiles.

* **Siempre enchufado** al cargador original.
* El instalador ofrece desactivar la suspensión y la hibernación, y que cerrar la tapa no haga nada. A mano:

  ```bash
  sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
  ```

  Y en Configuración › Energía: «Suspensión automática» desactivada y «Pantalla en blanco» a tu gusto. Para volver atrás: `sudo systemctl unmask …` con los mismos nombres.
* Perfil de rendimiento: `powerprofilesctl set performance`.
* En un PC de sobremesa, activa en la BIOS «Restore on AC power loss: Power On» para que arranque solo tras un corte de luz.
* Actualizaciones automáticas: Ubuntu solo instala parches de seguridad. Docker Engine, al venir del repositorio de Docker, no se actualiza solo. La semana de la demo, mejor no actualizar nada.

### 3.5 Red

* Cable de red mejor que Wi-Fi.
* **IP fija**: lo más sencillo es reservar en el router (DHCP) la IP del MSI. Si no se puede, en Ubuntu de escritorio:

  ```bash
  nmcli con show                                   # nombre de la conexión de cable
  sudo nmcli con mod "Conexión cableada 1" ipv4.method manual \
    ipv4.addresses 192.168.1.50/24 ipv4.gateway 192.168.1.1 ipv4.dns 192.168.1.1
  sudo nmcli con up "Conexión cableada 1"
  ```

  En Ubuntu Server se hace con netplan (`/etc/netplan/*.yaml`).
* Comprueba la IP con `ip -4 addr` y que otro equipo la alcanza (`ping 192.168.1.50` desde Windows).
* Opcional, para administrarlo desde otro equipo: `sudo apt install openssh-server`.

## 4. Instalar CidIA

### 4.1 Traer el código

Desde el repositorio privado (git pedirá usuario y un token de acceso):

```bash
sudo apt install -y git
git clone https://github.com/ORGANIZACION/cidia.git ~/cidia
```

O copia la carpeta `cidia` del repositorio con una memoria USB a `~/cidia`.

### 4.2 Comprobar el equipo

```bash
cd ~/cidia/servidor/despliegue
bash instalar-servidor.sh --comprobar
```

No cambia nada: revisa sistema, procesador, memoria, disco, GPU, Docker y conexión, y dice qué haría. Si algo sale con ✘, corrígelo antes de seguir.

### 4.3 Instalar

```bash
sudo bash instalar-servidor.sh
```

Te preguntará, con una propuesta que puedes aceptar con Intro:

| Pregunta | Qué responder |
|---|---|
| Perfil | `msi` en el MSI (lo propone solo si ve la GPU); `generico` en un PC sin gráfica. |
| Puerto | 18700 salvo que esté ocupado. |
| IP o nombre para los portátiles | La IP fija del apartado 3.5 o un nombre del DNS de la empresa. |
| ¿Publicar en la red local? | Sí, para que lleguen los portátiles (lee el aviso y el apartado 6). |
| ¿Desactivar la suspensión? | Sí. |

Después trabaja sola: instala Docker y el soporte de GPU, copia el código a `/opt/cidia`, genera los secretos, construye las imágenes (la primera vez, de 5 a 15 minutos), arranca los servicios, descarga los modelos (unos 7 GB en el MSI, con barra de progreso) y crea la cuenta de administración. Todo queda registrado en `/opt/cidia/registros/`.

Al terminar muestra algo así:

```
CidIA está instalado y en marcha.

  Dirección para el instalador de los portátiles:  http://192.168.1.50:18700
  Desde un navegador:                              http://192.168.1.50:18700/app/

  Cuenta de administración (se muestra solo esta vez):
    Usuario:     admin
    Contraseña:  Xk7m-Qa9t-Hb4w-Pz2r
```

La contraseña también queda en `/opt/cidia/secretos/admin-inicial.txt` (solo la puede leer root). Entra, cámbiala desde el menú de tu cuenta y borra ese fichero (`sudo rm /opt/cidia/secretos/admin-inicial.txt`).

Opciones útiles: `--perfil`, `--ip`, `--puerto`, `--lan` o `--solo-local`, `--con-weknora`, `--con-espacio`, `--sin-modelos` y `--si` para no preguntar. Volver a ejecutar el instalador es seguro: conserva datos, secretos, modelos y la cuenta de administración.

## 5. Comprobar que funciona

```bash
sudo cidia estado
```

Debe salir todo con ✔: servicios en marcha, gateway, Ollama, voz y base de datos respondiendo, y los modelos del perfil descargados. En el MSI, la línea «GPU» muestra la memoria usada de la gráfica cuando hay un modelo cargado.

Desde un portátil de la red:

1. Abre `http://192.168.1.50:18700/app/` en el navegador y entra con la cuenta de administración.
2. Haz una pregunta en el chat: la primera tarda más porque el modelo se carga en memoria.

Si no llega, mira «Solución de problemas».

## 6. Cortafuegos

CidIA solo publica un puerto, el del gateway (18700). Ollama, la voz y la base de datos escuchan únicamente en el propio servidor. **Nunca abras el puerto en el router hacia Internet.**

### 6.1 Proteger el equipo con ufw

```bash
RED=192.168.1.0/24                     # la red de la empresa
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from $RED to any port 22 proto tcp      # solo si usas SSH
sudo ufw allow from $RED to any port 18700 proto tcp
sudo ufw enable
sudo ufw status verbose
```

### 6.2 Limitar el puerto de CidIA a la red de la empresa

Ojo: los puertos que publica Docker **no pasan por las reglas normales de ufw** (Docker los encamina antes). La regla `allow` de arriba documenta la intención, pero para que el puerto 18700 solo acepte la red de la empresa hay que filtrar en la cadena `DOCKER-USER`. Añade al final de `/etc/ufw/after.rules`:

```
# BEGIN CIDIA: solo la red de la empresa llega al puerto 18700 de CidIA
*filter
:DOCKER-USER - [0:0]
-A DOCKER-USER -p tcp -m conntrack --ctorigdstport 18700 --ctdir ORIGINAL -s 192.168.1.0/24 -j RETURN
-A DOCKER-USER -p tcp -m conntrack --ctorigdstport 18700 --ctdir ORIGINAL -j DROP
-A DOCKER-USER -j RETURN
COMMIT
# END CIDIA
```

Aplica con `sudo ufw reload` y comprueba con `sudo iptables -L DOCKER-USER -n`. Prueba desde un equipo de la red (debe entrar) y, si puedes, desde otra red (no debe). Si cambias el puerto o la red, cambia también estas líneas.

Alternativa más sencilla: que CidIA escuche solo en la IP de la red de la empresa y no en todas las interfaces: `sudo cidia abrir-puerto 192.168.1.50`. Requiere que esa IP sea fija.

Para dejar CidIA solo en el propio equipo (por ejemplo, para mantenimiento): `sudo cidia cerrar-puerto`.

## 7. Dejarlo listo para los portátiles

1. En Administración (desde el navegador): crea departamentos, niveles y personas, y sube los primeros documentos.
2. En cada portátil, instala `CidIA-Setup.exe` y, cuando lo pida, escribe la dirección del servidor: `http://192.168.1.50:18700`.
3. Cada persona entra con su usuario. La interfaz se actualiza desde el servidor: actualizar el servidor no obliga a reinstalar los portátiles.

## 8. Administración diaria

Todo con la orden `cidia` (siempre con `sudo`):

| Orden | Para qué |
|---|---|
| `sudo cidia estado` | Ver si todo funciona, cuánta memoria y disco se usa y qué modelos hay. |
| `sudo cidia registros gateway -f` | Ver qué pasa en el gateway en directo (Ctrl+C para salir). También `postgres`, `ollama`, `asr`. |
| `sudo cidia reiniciar [servicio]` | Reiniciar todo o un servicio. |
| `sudo cidia parar` / `sudo cidia arrancar` | Parar o arrancar CidIA sin perder datos. |
| `sudo cidia modelos` | Modelos descargados y los que faltan. `modelos descargar` baja los que falten. |
| `sudo cidia admin-restablecer` | Nueva contraseña para la cuenta de administración si se ha olvidado. |
| `sudo cidia abrir-puerto` / `cerrar-puerto` | Publicar CidIA en la red local o dejarlo solo en el equipo. |
| `sudo cidia demo preparar` / `demo restaurar` | Dejar el servidor listo para una demostración y volver después a lo normal (apartado 8.1). |
| `sudo cidia ayuda` | Todas las órdenes. |

### 8.1 Modo demo

Para una demostración en el MSI. La guía completa (preparación, guion, planes B y vídeo de respaldo) está en [`docs/guia-demo.md`](guia-demo.md).

```bash
sudo cidia demo preparar           # una hora antes: tiene que terminar con «Listo para la demo»
sudo cidia demo reiniciar-datos    # entre ensayos: vuelve a sembrar los datos sintéticos
sudo cidia demo restaurar          # al terminar
```

* **`demo preparar`** carga en la GPU los modelos de chat y de búsqueda del perfil para que no caduquen, carga el modelo de voz (la primera vez lo descarga: necesita Internet), para WeKnora y el espacio de trabajo si están en marcha (`--con-weknora` y `--con-espacio` los dejan), comprueba que están las cuentas del guion y muestra la corriente, la suspensión, la memoria, la GPU y la dirección para los portátiles. Si un modelo no cabe entero en los 12 GB de la gráfica, lo dice: baja `OLLAMA_CONTEXT_LENGTH` (por ejemplo, a 16384) en `/opt/cidia/secretos/cidia.env` y repite. Tras reiniciar el equipo hay que volver a ejecutarlo.
* **`demo restaurar`** vuelve a la configuración que había (los modelos vuelven a salir de la memoria tras 30 minutos sin uso) y arranca de nuevo los servicios opcionales. Mientras el modo demo está activo, `sudo cidia estado` lo recuerda.
* **`demo reiniciar-datos`** borra todo el contenido de demostración, también lo añadido después (por ejemplo, la captura del ensayo), y vuelve a sembrar los datos sintéticos. Pide escribir `REINICIAR` y solo funciona en un servidor marcado como de demostración. Para marcar el MSI: `CIDIA_CREAR_SEMILLA=true` en `/opt/cidia/cidia/servidor/despliegue/perfiles/msi.env` y `sudo cidia arrancar`. La semilla se niega en una base con datos propios.

## 9. Copias de seguridad

```bash
sudo cidia copia
```

Crea `/opt/cidia/copias/cidia-AAAAMMDD-HHMMSS/` con la base de datos (`pg_dump`), la carpeta `datos/` (documentos, imágenes y clips), la configuración con los secretos y sumas de comprobación. Los modelos no se copian: se vuelven a descargar.

**Copia diaria automática** a las 02:30, conservando las 14 últimas:

```bash
echo '30 2 * * * root /usr/local/bin/cidia --si copia --conservar 14 >> /opt/cidia/registros/copias.log 2>&1' \
  | sudo tee /etc/cron.d/cidia-copia
```

**Fuera del equipo**: las copias contienen datos de la empresa y secretos. Llévalas a un disco USB cifrado o a un NAS de la empresa, por ejemplo `sudo rsync -a /opt/cidia/copias/ /media/cidia/USB/cidia-copias/`.

**Restaurar** en el mismo equipo:

```bash
sudo cidia copias                                   # lista
sudo cidia restaurar cidia-20261020-023000          # pide escribir RESTAURAR
```

Antes de restaurar hace una copia del estado actual; restaura en una base temporal y solo si sale bien sustituye la actual; la carpeta `datos/` anterior queda como `datos.previo-FECHA`.

**Restaurar en un equipo nuevo** (por avería del servidor):

1. Instala CidIA en el equipo nuevo como en el apartado 4.
2. Copia la carpeta de la copia a `/opt/cidia/copias/`.
3. `sudo cidia restaurar <copia>`. Las cuentas pasan a ser las de la copia: la contraseña de `secretos/admin-inicial.txt` del equipo nuevo deja de valer (bórralo) y se entra con las de siempre.
4. Si usabas WeKnora, copia el valor de `WEKNORA_AES_KEY` del `configuracion.tar.gz` de la copia a `/opt/cidia/secretos/cidia.env` y `sudo cidia reiniciar`. Si usabas un perfil a medida, también va en ese fichero (`cidia/servidor/despliegue/perfiles/<nombre>.env`): instala el equipo nuevo con él (`--perfil <nombre>`).

## 10. Actualizar

```bash
sudo cidia actualizar
```

Hace una copia de seguridad (pregunta), descarga el código nuevo (`git pull`), reconstruye las imágenes, aplica la nueva versión y comprueba que responde. Si el código se copió sin git, copia la versión nueva encima ejecutando su instalador: `sudo bash <carpeta-nueva>/servidor/despliegue/instalar-servidor.sh` (conserva datos y secretos).

Ubuntu se actualiza como siempre (`sudo apt update && sudo apt upgrade`). Si se actualiza Docker, los contenedores se reinician solos.

## 11. Solución de problemas

| Síntoma | Qué mirar y cómo arreglarlo |
|---|---|
| Un portátil no conecta | `sudo cidia estado`: ¿dice «Solo local»? Entonces `sudo cidia abrir-puerto`. ¿Ha cambiado la IP del servidor? Reserva la IP en el router. Desde el portátil: `curl http://IP:18700/salud` (o la URL en el navegador). Revisa el cortafuegos (apartado 6). |
| El gateway no responde tras instalar | `sudo cidia registros gateway`. Si falla la base de datos, `sudo cidia registros postgres`. |
| «permission denied» al guardar documentos | `datos/` debe ser del uid 1000: `sudo chown -R 1000:1000 /opt/cidia/datos` y `sudo cidia reiniciar gateway`. |
| La GPU no se usa (respuestas lentas en el MSI) | `nvidia-smi` debe responder. Si no: controlador (apartado 3.3) y Secure Boot (`mokutil --sb-state`, clave MOK registrada). `docker info \| grep -i nvidia` debe mostrar el runtime; si no, vuelve a ejecutar el instalador. `sudo cidia estado` muestra «100% GPU» con el modelo cargado. |
| Ollama se queda sin memoria o los modelos tardan mucho | Baja `OLLAMA_CONTEXT_LENGTH` o sube `CIDIA_MEM_OLLAMA` en `/opt/cidia/secretos/cidia.env` y `sudo cidia arrancar`. Con cgroups v1 (Ubuntu 20.04) Ollama no ve el límite de su contenedor: usa modelos pequeños o Ubuntu 22.04/24.04. |
| Faltan modelos | `sudo cidia modelos descargar` (necesita Internet). |
| Puerto ocupado | El instalador lo detecta: usa `--puerto 18800` (y cámbialo en el cortafuegos). |
| Red de la empresa en 172.29.x.x | El instalador elige otras subredes para Docker. A mano: `CIDIA_RED_BORDE` y `CIDIA_RED_INTERNA` en `cidia.env`. |
| Sin Internet o con proxy de empresa | Docker necesita el proxy en `/etc/systemd/system/docker.service.d/http-proxy.conf` (`Environment="HTTPS_PROXY=http://proxy:3128"`), `sudo systemctl daemon-reload && sudo systemctl restart docker`, y para construir, `~/.docker/config.json` con `"proxies"`. |
| `$'\r': orden no encontrada` | El script tiene finales de línea de Windows: `sed -i 's/\r$//' instalar-servidor.sh cidia`. |
| «Hay una base de datos de una instalación anterior pero no sus secretos» | Recupera `secretos/cidia.env` de una copia (`configuracion.tar.gz`) o empieza de cero con `--desinstalar`. |
| Disco lleno | `sudo cidia estado` muestra el uso. Borra modelos que no uses (`sudo cidia modelos borrar <modelo>`) y copias antiguas (`sudo cidia copia --conservar 7`). No uses `docker system prune`: puede borrar datos de otros proyectos. |
| Contraseña de administración olvidada | `sudo cidia admin-restablecer`. |
| El espacio de trabajo del agente no ejecuta órdenes | `sudo cidia estado` avisa si `CIDIA_DOCKER_GID` no es el grupo del socket de Docker (`stat -c %g /var/run/docker.sock`). Corrígelo en `cidia.env` o vuelve a ejecutar el instalador, y `sudo cidia arrancar`. |
| Tras restaurar, nadie puede entrar | Es normal: se cierran todas las sesiones. Cada persona vuelve a entrar con su contraseña. |

## 12. Desinstalar

```bash
sudo bash /opt/cidia/cidia/servidor/despliegue/instalar-servidor.sh --desinstalar
```

Enseña qué va a borrar, pide escribir `BORRAR` y ofrece conservar las copias. Borra contenedores, volúmenes (base de datos y modelos), redes e imágenes de CidIA, y las carpetas que creó la instalación. No toca Docker, el NVIDIA Container Toolkit, otros contenedores ni las imágenes de terceros (dice cómo borrarlas si no las usa nadie).

## 13. Cómo se probó en Oracle

El servidor de pruebas (Oracle Cloud, ARM Neoverse-N1 de 4 núcleos, 23 GB, Ubuntu 20.04, Docker 26.1.3 del paquete `docker.io`, Compose 2.35.1, cgroups v1) ya tenía CidIA funcionando en `/home/ubuntu/CidIA`, instalado a mano y compartiendo equipo con otros 12 contenedores. Allí solo se ejecutaron órdenes que no cambian nada:

1. **shellcheck 0.11.0** (`docker run --rm -v …:/mnt koalaman/shellcheck:stable -x -S style`) sobre `instalar-servidor.sh` y `cidia`: sin avisos. La imagen de shellcheck se retiró después.
2. **`instalar-servidor.sh --comprobar`**, con `--dir /home/ubuntu/CidIA` y sin opciones (detecta la carpeta por el proyecto `cidia` en marcha). Resultado: sin problemas y 5 avisos esperables: Ubuntu 20.04 no verificado, cgroups v1, Docker 26 (se recomienda 28 o superior si se publica en una red local), `datos/` del usuario `ubuntu` y no del uid 1000, y CidIA publicado solo en 127.0.0.1. Reconoció los 4 servicios, los ficheros de compose en uso (`docker-compose.yml` y `compose.debug.yml`), los secretos (sin mostrarlos), el perfil `oracle` con sus 3 modelos ya descargados y la cuenta de administración existente, e indicó que no instalaría nada.
3. **`cidia estado`** con `--dir`, con `CIDIA_DIR=/home/ubuntu/CidIA` y sin nada (la herramienta encuentra la instalación por su propia ubicación): servicios, salud (gateway en 10 ms, Ollama 0.40.2, voz y base de datos), recursos, disco, modelos y copias. También `cidia modelos listar`, `cidia copias`, `cidia ayuda` y los errores de orden desconocida y carpeta inexistente.
4. Se tomó una instantánea antes y después (permisos, tamaños y fechas de `secretos/` y `datos/`, contenedores con su fecha de creación, volúmenes, registros y copias): **idéntica**.

No se ejecutaron en Oracle, por cambiar el estado del servidor compartido: la instalación desde cero, `copia`, `restaurar`, `admin-restablecer`, `actualizar`, `abrir-puerto` ni `--desinstalar`. Su primera ejecución real será en el MSI. Lista de comprobación para ese día:

- [ ] `bash instalar-servidor.sh --comprobar` sin ✘.
- [ ] `sudo bash instalar-servidor.sh --perfil msi --ip <IP> --lan` y resumen final con la contraseña.
- [ ] `sudo cidia estado` todo en ✔ y, tras una pregunta en el chat, «100% GPU».
- [ ] Desde un portátil: `http://<IP>:18700/app/`, entrar y preguntar.
- [ ] `sudo cidia copia` y `sudo cidia restaurar <copia>` (con datos de prueba).
- [ ] `sudo cidia admin-restablecer` y entrar con la nueva contraseña.
- [ ] Reiniciar el MSI y comprobar que CidIA vuelve solo.
- [ ] Volver a ejecutar el instalador: no debe cambiar secretos ni datos.
- [ ] `sudo cidia demo preparar`: «Listo para la demo», los dos modelos «100 % en la GPU» y la voz transcribiendo; después `sudo cidia demo restaurar` (ver [`docs/guia-demo.md`](guia-demo.md)).
