# Servicio de transcripción de CidIA: faster-whisper sin PyAV + ffmpeg LGPL externo.
FROM debian:bookworm-slim AS ffmpeg
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
 && rm -rf /var/lib/apt/lists/*
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in amd64) A=linux64 ;; arm64) A=linuxarm64 ;; *) exit 1 ;; esac; \
    curl -fsSL "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n9.0-latest-${A}-lgpl-9.0.tar.xz" \
      | tar -xJ -C /opt; \
    mv /opt/ffmpeg-* /opt/ffmpeg

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HUB_DISABLE_TELEMETRY=1
COPY --from=ffmpeg /opt/ffmpeg/bin/ffmpeg /usr/local/bin/
# faster-whisper sin su dependencia `av` (las ruedas de PyAV traen x264/x265, GPL).
RUN pip install "ctranslate2>=4.5,<5" "huggingface-hub>=0.23" "tokenizers>=0.19" "onnxruntime>=1.18" numpy \
      "fastapi>=0.115" "uvicorn>=0.30" "python-multipart>=0.0.9" \
 && pip install --no-deps "faster-whisper==1.2.1" \
 && ! pip show av >/dev/null 2>&1
WORKDIR /srv/asr
COPY app.py .
RUN useradd -u 1000 -m asr && mkdir -p /modelos && chown asr:asr /modelos
USER asr
ENV ASR_DIR_MODELOS=/modelos
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
