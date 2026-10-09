"""Comprobación de licencias de la caja de arena (se ejecuta al construir la imagen).

Lista todos los paquetes de Python instalados con su licencia y falla si alguno es GPL, LGPL o
AGPL sin alternativa permisiva (docs/arquitectura.md §9: solo licencias permisivas).
"""

from __future__ import annotations

import re
import sys
from importlib import metadata

COPYLEFT = re.compile(r"\b(A|L)?GPL|General Public License", re.I)
# Doble licencia o excepción que lo hace aceptable (p. ej. «BSD OR GPL», «GPL WITH ...-exception»)
SALVEDAD = re.compile(r"\bOR\b.*\b(MIT|BSD|Apache|ISC|PSF)|\b(MIT|BSD|Apache|ISC|PSF)\b.*\bOR\b|exception", re.I)


def licencia(d: metadata.Distribution) -> str:
    m = d.metadata
    expresion = m.get("License-Expression")
    if expresion:
        return expresion.strip()
    clasificadores = [c.split("::")[-1].strip() for c in (m.get_all("Classifier") or []) if c.startswith("License ::")]
    if clasificadores:
        return "; ".join(dict.fromkeys(clasificadores))
    texto = (m.get("License") or "").strip().splitlines()
    return texto[0][:80] if texto else "desconocida"


def principal() -> int:
    malas = []
    for d in sorted(metadata.distributions(), key=lambda d: (d.metadata.get("Name") or "").lower()):
        nombre, version, lic = d.metadata.get("Name") or "?", d.version, licencia(d)
        print(f"{nombre:28} {version:14} {lic}")
        if COPYLEFT.search(lic) and not SALVEDAD.search(lic):
            malas.append(f"{nombre} ({lic})")
    if malas:
        print("\nPaquetes con licencia no permitida: " + ", ".join(malas), file=sys.stderr)
        return 1
    print("\nLicencias correctas: todas permisivas.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
