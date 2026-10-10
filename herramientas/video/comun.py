"""Piezas comunes de las herramientas de vídeo (voz y montaje)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
REPO = AQUI.parent.parent
HERR = AQUI / '.herramientas'
PY_VENV = HERR / '.venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')

# Marca CidIA
TINTA = '#1F2328'
TINTA_2 = '#2B3036'
ACENTO = '#F2C200'
PIZARRA = '#9AA3AE'
BLANCO = '#FFFFFF'


def en_entorno(modulos: list[str]) -> None:
    """Si falta algún módulo y existe el entorno de las herramientas, se vuelve a lanzar con él."""
    import importlib.util
    if all(importlib.util.find_spec(m) for m in modulos):
        return
    if PY_VENV.exists() and Path(sys.executable).resolve() != PY_VENV.resolve():
        sys.exit(subprocess.call([str(PY_VENV), *sys.argv]))
    sys.exit(f'Faltan {", ".join(modulos)}: ejecuta antes  python {AQUI / "preparar.py"}')


def ffmpeg(nombre: str = 'ffmpeg') -> str:
    var = os.environ.get('CIDIA_FFMPEG')
    if var:
        return str(Path(var).with_name(nombre + Path(var).suffix)) if nombre != 'ffmpeg' else var
    h = REPO / 'servidor' / 'gateway' / '.herramientas'
    if h.exists():
        for d in sorted((x for x in h.iterdir() if x.name.startswith('ffmpeg-')), reverse=True):
            p = d / 'bin' / (nombre + ('.exe' if sys.platform == 'win32' else ''))
            if p.exists():
                return str(p)
    return nombre


FUENTES = HERR / 'fuentes'


def fuente(peso: str = 'bold') -> str:
    """Fira Sans (OFL, la de la interfaz; la baja preparar.py) y, si no está, DejaVu Sans."""
    nombres = {'regular': 'Regular', 'medium': 'Medium', 'semibold': 'SemiBold', 'bold': 'Bold'}
    p = FUENTES / f'FiraSans-{nombres.get(peso, "Bold")}.ttf'
    if p.exists():
        return str(p)
    for d in (Path('C:/Windows/Fonts'), Path('/usr/share/fonts/truetype/dejavu')):
        f = d / ('DejaVuSans-Bold.ttf' if peso in ('bold', 'semibold') else 'DejaVuSans.ttf')
        if f.exists():
            return str(f)
    raise FileNotFoundError('No encuentro Fira Sans ni DejaVu Sans')


def resolver(ruta: str, base: Path, extra: dict[str, str] | None = None) -> Path:
    r = ruta.replace('{repo}', str(REPO))
    for k, v in (extra or {}).items():
        r = r.replace('{' + k + '}', v)
    p = Path(r)
    return p if p.is_absolute() else (base / p).resolve()


def cargar_proyecto(fichero: str | Path) -> tuple[dict, list[dict]]:
    """Devuelve (proyecto, piezas). Cada pieza lleva '_dir' y, si es escena, sus datos completos.
    Un fichero de escena suelto se trata como un proyecto de una sola pieza."""
    f = Path(fichero).resolve()
    datos = json.loads(f.read_text(encoding='utf-8'))
    if 'piezas' not in datos:
        return {'titulo': datos.get('titulo', datos['id']), '_dir': f.parent}, [{**datos, 'tipo': 'escena', '_dir': f.parent}]
    piezas = []
    for p in datos['piezas']:
        if p.get('omitir'):
            continue  # pieza apartada del montaje (opcional o sin grabar)
        if isinstance(p.get('escena'), dict):
            # Escena en línea, dentro de la propia pieza.
            piezas.append({**p['escena'], **{k: v for k, v in p.items() if k not in ('escena', 'tipo')}, 'tipo': 'escena', '_dir': f.parent})
        elif p.get('escena'):
            fe = resolver(p['escena'], f.parent)
            e = json.loads(fe.read_text(encoding='utf-8'))
            piezas.append({**e, **{k: v for k, v in p.items() if k != 'escena'}, 'tipo': 'escena', '_dir': fe.parent})
        else:
            piezas.append({**p, 'tipo': p.get('tipo', 'tarjeta'), '_dir': f.parent})
    return {**datos, '_dir': f.parent}, piezas


def correr(args: list[str], **kw) -> subprocess.CompletedProcess:
    r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', **kw)
    if r.returncode != 0:
        raise RuntimeError(f'{Path(args[0]).name} falló ({r.returncode}):\n{r.stderr[-2500:]}')
    return r
