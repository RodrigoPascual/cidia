# Imagen del servicio CidIA: gateway (FastAPI) + interfaz web compilada + ffmpeg LGPL.
# Contexto de construcción: servidor/  (docker build -f gateway/Dockerfile ..)

# 1) Interfaz web
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# 2) ffmpeg con licencia LGPL (BtbN/FFmpeg-Builds). El de Debian/Ubuntu es GPL: no se usa.
FROM debian:bookworm-slim AS ffmpeg
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
 && rm -rf /var/lib/apt/lists/*
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in amd64) A=linux64 ;; arm64) A=linuxarm64 ;; *) echo "arquitectura no soportada"; exit 1 ;; esac; \
    curl -fsSL "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n9.0-latest-${A}-lgpl-9.0.tar.xz" \
      | tar -xJ -C /opt; \
    mv /opt/ffmpeg-* /opt/ffmpeg; \
    /opt/ffmpeg/bin/ffmpeg -hide_banner -buildconf | grep -q -- "--enable-gpl" && { echo "ffmpeg GPL: rechazado"; exit 1; } || true

# 3) Servicio
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY --from=ffmpeg /opt/ffmpeg/bin/ffmpeg /opt/ffmpeg/bin/ffprobe /usr/local/bin/
COPY --from=ffmpeg /opt/ffmpeg/LICENSE.txt /usr/share/doc/ffmpeg-lgpl/LICENSE.txt
WORKDIR /srv/cidia
COPY gateway/pyproject.toml ./
COPY gateway/cidia ./cidia
RUN pip install .
COPY --from=web /web/dist /srv/web
RUN useradd -u 1000 -m cidia && mkdir -p /datos && chown cidia:cidia /datos
USER cidia
# X-Forwarded-For solo se cree a un proxy de confianza: con «*» cualquier equipo de la red podría
# falsear su dirección (registro de sesiones y límites por dirección). El gateway se publica sin
# proxy delante; si se pone uno, su dirección va en FORWARDED_ALLOW_IPS (variable de uvicorn).
ENV CIDIA_DIR_DATOS=/datos CIDIA_DIR_WEB=/srv/web FORWARDED_ALLOW_IPS=127.0.0.1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/salud', timeout=4).status==200 else 1)"
CMD ["uvicorn", "cidia.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
