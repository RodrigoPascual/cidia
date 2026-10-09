# Ejecutor del espacio de trabajo de CidIA (servicio `espacio-trabajo` del compose).
# Solo biblioteca estándar de Python: sin dependencias de terceros.
# Construcción (desde esta carpeta):  docker build -t cidia-espacio:local .
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/espacio
COPY ejecutor.py .
RUN useradd -u 1000 -m -s /usr/sbin/nologin espacio \
 && python -m py_compile ejecutor.py
# Arranca como root solo para leer el grupo del socket de Docker (distinto en cada servidor) y,
# si hace falta, dar generador-de-contenido/ a 1000:1000; después el propio ejecutor pasa a
# 1000:1000 con ese grupo (ver bajar_privilegios en ejecutor.py).
EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=6s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:8090/salud', headers={'X-Espacio-Secreto': os.environ['ESPACIO_SECRETO']}), timeout=5)"
CMD ["python", "ejecutor.py"]
