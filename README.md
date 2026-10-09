# CidIA

Copiloto de IA en local para capturar, estructurar, formar, acompañar, evaluar y certificar el conocimiento de una planta industrial. Candidatura al V DESAFÍO industrial de POLO positivo (Rodrigo Pascual, Lydia Blanco y Gadea Lucas, Universidad de Burgos).

El conocimiento experto se queda en la empresa: modelos, documentos, audios y vídeos viven en un servidor de la propia empresa, y cada persona encuentra solo lo que le corresponde por departamento, nivel y formación.

## Qué hay en el repositorio

```
app/                 lo que se instala en los portátiles (CidIA-Setup.exe)
  plugins/cidia/     plugin de la app de escritorio: paneles, sesión, marca y proxy al servidor
  perfil/            configuración bloqueada de la app (proveedor único, sin telemetría...)
  marca/             logos e iconos
  instalador/        construcción de CidIA-Setup.exe y del lanzador CidIA.exe
servidor/            lo que corre en el servidor de la empresa
  gateway/           servicio CidIA (FastAPI): API de la interfaz, API compatible con OpenAI y MCP
  web/               interfaz web (React), servida por el gateway en /app/
  asr/               servicio de transcripción de voz
  espacio-trabajo/   ejecutor de contenedores aislados para el agente
  weknora/           motor de conocimiento opcional
  despliegue/        docker compose, perfiles por equipo e instalador del servidor
datos-demo/          datos sintéticos de demostración
docs/                arquitectura, investigación y manuales
```

## Cómo se usa

* **Servidor** (portátil MSI con Ubuntu o cualquier equipo de la empresa): `servidor/despliegue/instalar-servidor.sh`. Detalles en `docs/manual-servidor.md`.
* **Portátiles de los trabajadores**: `CidIA-Setup.exe`. Detalles en `app/README.md`.
* **Desde un navegador**: `http://<servidor>:<puerto>/app/`.

## Desarrollo

```bash
# gateway
cd servidor/gateway
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
CIDIA_TEST_BD=mio .venv/Scripts/python -m pytest -q        # necesita un PostgreSQL con pgvector (ver tests/conftest.py)

# interfaz
cd servidor/web
npm install && npm run dev                                  # proxy de /api al gateway (CIDIA_GATEWAY)
```

Arquitectura y contratos entre módulos: `docs/arquitectura.md` y `servidor/gateway/cidia/servicios/contratos.md`.

## Licencias

El código de CidIA es propiedad de sus autores. Los componentes de terceros y sus licencias están en `THIRD_PARTY_NOTICES.md`: solo se usan licencias permisivas (MIT, Apache-2.0, BSD, ISC, PostgreSQL) y FFmpeg LGPL como programa externo.
