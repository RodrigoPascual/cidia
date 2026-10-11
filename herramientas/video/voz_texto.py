"""Texto que se dice: diccionario de pronunciación (pronunciacion.json) y números en letras.

Lo usan voz.py y voz_banco.py. Solo cambia lo que dice la voz, nunca los subtítulos.

* `reemplazos`: reglas comunes a todos los motores (CidIA, IT-023, N·m, ILUO, xAPI, MCP...).
* `por_motor`: reglas que se aplican antes de las comunes, solo para ese motor.
* `numeros_en_letras`: motores que reciben los números ya escritos en letras (los que no los leen bien
  por sí mismos o los leen en inglés). Kokoro los lee bien con espeak-ng en castellano.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

AQUI = Path(__file__).resolve().parent

UNIDADES = ('cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince '
            'dieciséis diecisiete dieciocho diecinueve veinte').split()
VEINTI = 'veinte veintiuno veintidós veintitrés veinticuatro veinticinco veintiséis veintisiete veintiocho veintinueve'.split()
DECENAS = {3: 'treinta', 4: 'cuarenta', 5: 'cincuenta', 6: 'sesenta', 7: 'setenta', 8: 'ochenta', 9: 'noventa'}
CIENTOS = {1: 'ciento', 2: 'doscientos', 3: 'trescientos', 4: 'cuatrocientos', 5: 'quinientos', 6: 'seiscientos',
           7: 'setecientos', 8: 'ochocientos', 9: 'novecientos'}


def en_letras(n: int) -> str:
    """Entero en letras (castellano), hasta 999.999.999."""
    if n <= 20:
        return UNIDADES[n]
    if n < 30:
        return VEINTI[n - 20]
    if n < 100:
        d, u = divmod(n, 10)
        return DECENAS[d] + ('' if u == 0 else ' y ' + UNIDADES[u])
    if n < 1000:
        c, r = divmod(n, 100)
        return ('cien' if n == 100 else CIENTOS[c]) + ('' if r == 0 else ' ' + en_letras(r))
    if n < 1_000_000:
        m, r = divmod(n, 1000)
        miles = 'mil' if m == 1 else en_letras(m).replace('uno', 'un') + ' mil'
        return miles + ('' if r == 0 else ' ' + en_letras(r))
    m, r = divmod(n, 1_000_000)
    millones = 'un millón' if m == 1 else en_letras(m).replace('uno', 'un') + ' millones'
    return millones + ('' if r == 0 else ' ' + en_letras(r))


def numeros_en_letras(t: str) -> str:
    t = re.sub(r'(\d+),(\d+)', lambda m: f'{en_letras(int(m.group(1)))} coma {en_letras(int(m.group(2)))}', t)
    t = re.sub(r'(\d{1,3})\.(\d{3})\b', r'\1\2', t)
    t = re.sub(r'(\d+) ?%', lambda m: f'{en_letras(int(m.group(1)))} por ciento', t)
    return re.sub(r'\d+', lambda m: en_letras(int(m.group(0))), t)


@lru_cache(maxsize=1)
def reglas() -> dict:
    return json.loads((AQUI / 'pronunciacion.json').read_text(encoding='utf-8'))


def pronunciar(texto: str, motor: str = 'kokoro') -> str:
    r = reglas()
    for patron, por in r.get('por_motor', {}).get(motor, []):
        texto = re.sub(patron, por, texto)
    for patron, por in r['reemplazos']:
        texto = re.sub(patron, por, texto)
    if motor in r.get('numeros_en_letras', []):
        texto = numeros_en_letras(texto)
    return re.sub(r'\s+', ' ', texto).strip()


if __name__ == '__main__':
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    motor = sys.argv[2] if len(sys.argv) > 2 else 'kokoro'
    print(pronunciar(sys.argv[1], motor))
