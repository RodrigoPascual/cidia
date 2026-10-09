# Caja de arena del espacio de trabajo de CidIA (imagen cidia-sandbox:local).
# Aquí se ejecutan las órdenes del agente: un contenedor efímero por orden, sin red, solo
# lectura salvo /trabajo (la carpeta del usuario) y /tmp, sin privilegios y con límites.
# Construcción (desde servidor/espacio-trabajo):  docker build -t cidia-sandbox:local sandbox
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_ROOT_USER_ACTION=ignore

# Bibliotecas para crear tablas, gráficos, Word y PDF. Todas con licencia permisiva:
# pandas y numpy (BSD-3), openpyxl (MIT), python-docx (MIT) con lxml (BSD-3), matplotlib
# (licencia de Matplotlib, tipo PSF/BSD) con pillow (MIT-CMU) y reportlab (BSD).
# reportlab >= 4.5 usa charset-normalizer (MIT); versiones anteriores pedían chardet (LGPL):
# por eso se exige la 4.5 y se comprueba que chardet no se instala.
RUN pip install "pandas>=2.2,<3" "openpyxl>=3.1,<4" "python-docx>=1.1,<2" "matplotlib>=3.9,<4" \
      "reportlab>=4.5,<5" \
 && ! pip show chardet >/dev/null 2>&1

# Comprobación de licencias al construir: falla si se cuela algún paquete GPL/LGPL/AGPL.
COPY licencias.py /tmp/licencias.py
RUN python /tmp/licencias.py && rm /tmp/licencias.py

# Usuario sin privilegios (el mismo uid que el gateway, para que los ficheros sean de los dos).
# bash ya viene en la imagen base de Debian.
RUN useradd -u 1000 -m -s /bin/bash cidia && mkdir -p /trabajo && chown 1000:1000 /trabajo \
 && MPLCONFIGDIR=/tmp/mpl python -c "import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot, pandas, openpyxl, docx, reportlab; from reportlab.pdfgen import canvas" \
 && rm -rf /tmp/mpl
USER 1000:1000
WORKDIR /trabajo
ENV HOME=/tmp MPLCONFIGDIR=/tmp/.matplotlib MPLBACKEND=Agg LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUNBUFFERED=1
CMD ["bash"]
