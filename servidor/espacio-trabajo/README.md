# Espacio de trabajo del agente

Aquí vive lo que permite al agente de CidIA usar una terminal y crear ficheros **en el servidor**,
nunca en el portátil: cada orden se ejecuta en un contenedor efímero, sin red y con límites, que
solo ve la carpeta de su usuario (`datos/generador-de-contenido/<usuario>/`, montada en `/trabajo`).
La persona ve y descarga lo generado en la sección «Espacio de trabajo» de la app.

| Pieza | Qué es |
|---|---|
| `ejecutor.py` | Servicio `espacio-trabajo` (puerto 8090, solo red interna). Biblioteca estándar de Python, sin dependencias. |
| `Dockerfile` | Imagen del ejecutor: `cidia-espacio:local`. |
| `sandbox/Dockerfile` | Imagen de la caja de arena donde corren las órdenes: `cidia-sandbox:local` (Python 3.12, bash, pandas, openpyxl, python-docx, matplotlib y reportlab; usuario 1000). |
| `sandbox/licencias.py` | Comprobación de licencias que se ejecuta al construir la caja de arena. |

El gateway (`cidia/servicios/espacio.py`) gestiona los ficheros directamente y solo llama al
ejecutor para ejecutar órdenes (`POST /ejecutar`, cabecera `X-Espacio-Secreto`). Si el ejecutor
no está configurado o no responde, la app lo dice («El espacio de trabajo no está disponible en
este servidor») y oculta la consola; los ficheros siguen funcionando.

## Construir las imágenes en el servidor

```bash
cd /home/ubuntu/CidIA/cidia/servidor/espacio-trabajo

# 1) Caja de arena (una vez, y al cambiar sandbox/). Tarda 1-2 minutos y ocupa unos 420 MB.
docker build -t cidia-sandbox:local sandbox
#    Al final del registro debe aparecer «Licencias correctas: todas permisivas.»

# 2) Ejecutor (lo construye también el compose con el perfil «espacio»)
docker build -t cidia-espacio:local .
```

Arranque con el compose (`servidor/despliegue/docker-compose.yml`, perfil `espacio`):

```bash
cd /home/ubuntu/CidIA/cidia/servidor/despliegue
docker compose --env-file <secretos>/cidia.env --profile espacio up -d espacio-trabajo
```

`CIDIA_ESPACIO_SECRETO` tiene que estar en el fichero de secretos (lo leen el gateway y el ejecutor):
`openssl rand -hex 32`. Sin él, el gateway no ofrece la consola.

### Permisos de la carpeta de datos

El gateway y la caja de arena trabajan con el uid **1000**: los ficheros de `/trabajo` tienen que
poder leerlos y escribirlos los dos. La carpeta `datos/` del host debe ser de 1000:1000 (en el
Oracle el usuario `ubuntu` es el 1001, así que hay que darla a 1000):

```bash
sudo chown -R 1000:1000 /home/ubuntu/CidIA/datos
```

Si se prefiere otro uid, cámbiese a la vez en el gateway (`user:` del compose) y aquí
(`ESPACIO_UID` y `ESPACIO_GID`).

### Endurecimiento recomendado en el compose

El ejecutor arranca como root solo para leer el grupo del socket de Docker y pasa enseguida a
1000:1000 con ese grupo. Es más limpio fijarlo desde el compose (probado en el Oracle):

```yaml
  espacio-trabajo:
    user: "1000:1000"
    group_add: ["${CIDIA_DOCKER_GID:-120}"]   # grupo del socket: stat -c %g /var/run/docker.sock
    read_only: true
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
```

## Seguridad

Montar `/var/run/docker.sock` equivale a ser root en el servidor, que además es compartido con
otros proyectos (docs/investigacion/05_servidor_oracle.md §6.9). Por eso:

* **Solo** este servicio monta el socket; el gateway nunca. No publica puertos: solo se le llega
  desde la red `cidia-interna` y con el secreto compartido.
* La API que expone no permite elegir nada peligroso: ni imagen, ni montajes, ni opciones. Solo
  usuario (validado con `[a-z0-9._-]+`), orden y tiempo máximo (≤ 120 s). Todo lo demás se rechaza.
* Solo crea, consulta y borra contenedores propios (etiqueta `cidia.espacio=1`), siempre con:
  `--network none`, raíz de solo lectura con `/tmp` en memoria (64 MB, `noexec`), `--cap-drop ALL`,
  `no-new-privileges`, `--pids-limit 128`, 256 MB de memoria sin swap, 0,5 CPU, usuario 1000:1000,
  tamaño máximo por fichero (`ulimit fsize`) y el montaje de la carpeta del usuario y nada más.
* Mientras corre la orden vigila el tiempo y el espacio de la carpeta (cuota por usuario: la envía
  el gateway); si se pasa, mata el contenedor. Siempre lo borra al terminar, y al arrancar borra
  los que pudieran quedar de una caída. Como mucho 2 órdenes a la vez en el servidor y una por usuario.
* La salida se recorta a 64 KB. En el registro solo constan usuario, código, duración y longitud
  de la orden (no su contenido).
* El gateway, por su parte, nunca sigue rutas fuera de la carpeta del usuario (ni con `..`, ni con
  rutas absolutas, ni con enlaces simbólicos que haya creado una orden), **tampoco si una orden
  cambia un fichero o una carpeta por un enlace justo mientras el gateway trabaja** (carrera entre
  comprobar y abrir): en Linux recorre la carpeta con descriptores y `O_NOFOLLOW` y opera con
  `openat`, `renameat`, `unlinkat`... sobre la carpeta ya abierta (`cidia/servicios/espacio.py`).
  Lee con `O_NONBLOCK` y solo ficheros normales (una FIFO no deja colgado un hilo) y sirve las
  descargas desde el fichero ya abierto. Los nombres que crea una orden y no son portables
  (p. ej. con «:») se pueden ver, descargar, renombrar y borrar desde la app; los que no son
  UTF-8 no se listan (bórralos desde la consola).

Para más aislamiento, en un servidor con gVisor instalado: `ESPACIO_RUNTIME=runsc`.

## Prueba manual

Con el ejecutor en marcha en la red `cidia-interna` (por ejemplo, levantado con el compose):

```bash
docker run --rm --network cidia-interna -e S="$CIDIA_ESPACIO_SECRETO" python:3.12-slim-bookworm python -c '
import json, os, urllib.request as u
r = u.Request("http://espacio-trabajo:8090/ejecutar", method="POST",
              data=json.dumps({"usuario": "luis", "orden": "id; ls -la", "tiempo_max": 30}).encode(),
              headers={"Content-Type": "application/json", "X-Espacio-Secreto": os.environ["S"]})
print(json.load(u.urlopen(r)))'
```

(La carpeta `datos/generador-de-contenido/luis/` tiene que existir: la crea el gateway la primera
vez que Luis abre su espacio de trabajo.)

Comprobado en el Oracle (9-10-2026): sin red (solo `lo`, sin DNS), raíz de solo lectura,
`CapEff` a cero, `NoNewPrivs`, límite de 128 procesos, memoria (OOM a los 256 MB), tiempo
máximo, `ulimit fsize`, cuota vigilada, salida recortada, una orden a la vez por usuario y un
informe real con pandas, matplotlib, python-docx, openpyxl y reportlab.

## Licencias

* `ejecutor.py`: código propio, solo biblioteca estándar de Python (PSF).
* Imágenes base `python:3.12-slim-bookworm` (Debian): incluyen programas del sistema con licencia
  GPL (bash, coreutils...) como programas independientes, igual que el resto de imágenes del
  proyecto; no se enlazan con nuestro código.
* Paquetes de Python de la caja de arena (comprobados al construir con `sandbox/licencias.py`):

| Paquete | Licencia |
|---|---|
| pandas, numpy, contourpy, lxml | BSD-3-Clause (numpy además 0BSD, MIT, Zlib y CC0 por partes incluidas) |
| matplotlib | Licencia de Matplotlib (tipo PSF/BSD) |
| pillow | MIT-CMU |
| openpyxl, et_xmlfile, python-docx, fonttools, pyparsing, pytz, six, charset-normalizer | MIT |
| reportlab, cycler, kiwisolver | BSD |
| python-dateutil | BSD / Apache-2.0 |
| packaging | Apache-2.0 o BSD-2-Clause |
| tzdata | Apache-2.0 |
| typing_extensions | PSF-2.0 |

Las ruedas de numpy y pillow traen bibliotecas nativas con licencias permisivas (OpenBLAS BSD,
libjpeg-turbo, libpng, zlib, FreeType con licencia FTL...) y numpy además `libgfortran`, que es
GPL-3 con la excepción de bibliotecas de ejecución de GCC (permite su uso sin condiciones).
reportlab se exige en la versión 4.5 o posterior porque las anteriores dependían de `chardet`
(LGPL); la construcción falla si `chardet` llega a instalarse.
