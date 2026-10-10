"""Descarga lo que necesitan las herramientas de vídeo y que no va en el repositorio.

    python herramientas/video/preparar.py            # Kokoro (voz elegida) y Piper (comparación)
    python herramientas/video/preparar.py --solo kokoro

Todo queda en herramientas/video/.herramientas/ (ignorado por git):
  * Kokoro-82M en ONNX (pesos Apache-2.0 de hexgrad/Kokoro-82M, conversión de kokoro-onnx, MIT)
    y un entorno virtual propio (.venv) con kokoro-onnx, onnxruntime y soundfile.
  * Fira Sans (SIL Open Font License 1.1, la tipografía de la interfaz) en TTF, de google/fonts.
  * Piper 2023.11.14-2 para Windows (rhasspy/piper, MIT; incluye espeak-ng, GPL-3.0, sin modificar)
    con la voz es_ES-carlfm-x_low (datos de dominio público, entrenada desde cero).

Cada fichero se comprueba con su sha256: si no coincide, se borra y el script se detiene.
Solo usa la biblioteca estándar; el entorno de la voz se crea con el Python que lo ejecuta.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
HERR = AQUI / '.herramientas'

KOKORO = [
    ('kokoro/kokoro-v1.0.onnx',
     'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx',
     '7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5'),
    ('kokoro/voices-v1.0.bin',
     'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin',
     'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d'),
]
PIPER = [
    ('piper/piper_windows_amd64.zip',
     'https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip',
     'f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea'),
    ('piper/voces/es_ES-carlfm-x_low.onnx',
     'https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/carlfm/x_low/es_ES-carlfm-x_low.onnx',
     'd69677323a907cd4963f42b29c20a98b5d6bfa7f3e64df339915e4650c00d125'),
    ('piper/voces/es_ES-carlfm-x_low.onnx.json',
     'https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/carlfm/x_low/es_ES-carlfm-x_low.onnx.json',
     'd9bdfa9ff01eb2bc9e62e7d2593939d1e4c4d8eb7cf75f972731539d12399966'),
]
# Solo para la comparación de calidad (licencia dudosa para uso comercial: ver README).
PIPER_COMPARAR = [
    ('piper/voces/es_ES-davefx-medium.onnx',
     'https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx',
     '6658b03b1a6c316ee4c265a9896abc1393353c2d9e1bca7d66c2c442e222a917'),
    ('piper/voces/es_ES-davefx-medium.onnx.json',
     'https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json',
     '0e0dda87c732f6f38771ff274a6380d9252f327dca77aa2963d5fbdf9ec54842'),
]
_FIRA = {
    'Regular': 'c29556a2719bf613ef3d5e070e40d903a8965d9c081beca1375dc1e6e0f93c23',
    'Medium': 'cbc1842cbed8c1d1146ba7c9db97d8f28c9bedfd25f41c5b0e1259ca48622328',
    'SemiBold': 'db0321f83eb3e9f527b8af384a1b3fefdc1039cf2b06fd39b3f61492bda9561c',
    'Bold': 'a4d8e149ecdd4874a0726eb0af894488b3b31c423d6b0017c8f415ed1b795b45',
}
FUENTES = [(f'fuentes/FiraSans-{p}.ttf', f'https://github.com/google/fonts/raw/main/ofl/firasans/FiraSans-{p}.ttf', h)
           for p, h in _FIRA.items()] + [
    ('fuentes/OFL.txt', 'https://github.com/google/fonts/raw/main/ofl/firasans/OFL.txt',
     '8f24842e9174beda18a556c2ae7d54f5dc444340c19a3a9ef77e23bca366adbd')]
PAQUETES_VOZ = ['kokoro-onnx==0.6.1', 'soundfile==0.14.0', 'pillow==12.3.0']


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def bajar(rel: str, url: str, esperado: str | None) -> Path:
    destino = HERR / rel
    if destino.exists() and (esperado is None or sha256(destino) == esperado):
        print(f'ya está  {rel}')
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + '.parcial')
    print(f'bajando  {rel}')
    req = urllib.request.Request(url, headers={'User-Agent': 'cidia-herramientas-video'})
    with urllib.request.urlopen(req, timeout=120) as r, tmp.open('wb') as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    h = sha256(tmp)
    if esperado and h != esperado:
        tmp.unlink()
        sys.exit(f'sha256 distinto en {rel}: {h}')
    tmp.replace(destino)
    print(f'         sha256 {h}')
    return destino


def preparar_kokoro() -> None:
    for rel, url, h in KOKORO:
        bajar(rel, url, h)
    venv = HERR / '.venv'
    py = venv / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not py.exists():
        print('creando el entorno de la voz')
        subprocess.run([sys.executable, '-m', 'venv', str(venv)], check=True)
    subprocess.run([str(py), '-m', 'pip', 'install', '-q', '--disable-pip-version-check', *PAQUETES_VOZ], check=True)
    print('Kokoro listo:', py)


def preparar_fuentes() -> None:
    for rel, url, h in FUENTES:
        bajar(rel, url, h)


def preparar_piper(comparar: bool) -> None:
    for rel, url, h in PIPER + (PIPER_COMPARAR if comparar else []):
        bajar(rel, url, h)
    exe = HERR / 'piper' / 'piper' / 'piper.exe'
    if not exe.exists():
        with zipfile.ZipFile(HERR / 'piper' / 'piper_windows_amd64.zip') as z:
            z.extractall(HERR / 'piper')
    print('Piper listo:', exe)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--solo', choices=['kokoro', 'piper', 'fuentes'])
    ap.add_argument('--comparar', action='store_true', help='baja también la voz davefx de Piper (solo para comparar)')
    a = ap.parse_args()
    if a.solo in (None, 'fuentes'):
        preparar_fuentes()
    if a.solo in (None, 'kokoro'):
        preparar_kokoro()
    if a.solo in (None, 'piper'):
        preparar_piper(a.comparar)
