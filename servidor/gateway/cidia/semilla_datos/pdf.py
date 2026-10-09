"""Generador mínimo de PDF con texto real (sin dependencias externas).

Convierte un subconjunto de Markdown (títulos, párrafos, listas, tablas, notas y negritas
con **...**) en un PDF A4 con las fuentes estándar Helvetica y codificación WinAnsi, de modo
que el texto se puede extraer (pypdf) y la búsqueda híbrida lo encuentra. Basta para los
documentos sintéticos de la demostración; no pretende ser un maquetador general.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

ANCHO, ALTO = 595.28, 841.89  # A4 en puntos
MARGEN_X, MARGEN_SUP, MARGEN_INF = 56.0, 64.0, 62.0
AREA = ANCHO - 2 * MARGEN_X

# Anchos de Helvetica y Helvetica-Bold (métricas AFM, milésimas de em) para ASCII 32..126.
_ANCHOS_N = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]
_ANCHOS_B = [
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
]
_ESPECIALES = {"·": 278, "•": 350, "€": 556, "°": 400, "º": 365, "ª": 370, "±": 584, "¿": 611, "¡": 333,
               "«": 556, "»": 556, "×": 584, "½": 834, "–": 556, "µ": 556, "²": 333, "³": 333, "Ø": 778}
# Caracteres fuera de WinAnsi que pueden aparecer en los textos.
_SUSTITUCIONES = {"≥": ">=", "≤": "<=", "→": "->", "←": "<-", "≈": "~", "—": "-", "‑": "-", " ": " ",
                  " ": " ", "’": "'", "‘": "'", "“": '"', "”": '"', "✓": "OK"}


def _limpiar(texto: str) -> str:
    for a, b in _SUSTITUCIONES.items():
        texto = texto.replace(a, b)
    return texto


def ancho_texto(texto: str, tam: float, negrita: bool = False) -> float:
    tabla = _ANCHOS_B if negrita else _ANCHOS_N
    total = 0
    for c in texto:
        o = ord(c)
        if 32 <= o <= 126:
            total += tabla[o - 32]
        elif c in _ESPECIALES:
            total += _ESPECIALES[c]
        else:
            base = unicodedata.normalize("NFKD", c)[:1]
            total += tabla[ord(base) - 32] if base and 32 <= ord(base) <= 126 else 556
    return total * tam / 1000.0


def _cadena(texto: str) -> str:
    """Literal de cadena PDF en WinAnsi (cp1252), con los caracteres especiales escapados."""
    datos = _limpiar(texto).encode("cp1252", errors="replace")
    salida = []
    for b in datos:
        if b in (0x28, 0x29, 0x5C):  # ( ) \
            salida.append("\\" + chr(b))
        elif b < 32 or b > 126:
            salida.append(f"\\{b:03o}")
        else:
            salida.append(chr(b))
    return "(" + "".join(salida) + ")"


# --------------------------------------------------------------------------- maquetación


@dataclass
class _Pagina:
    ops: list[str] = field(default_factory=list)


class _Lienzo:
    def __init__(self, cabecera: str) -> None:
        self.cabecera = cabecera
        self.paginas: list[_Pagina] = []
        self.y = 0.0
        self.nueva_pagina()

    @property
    def ops(self) -> list[str]:
        return self.paginas[-1].ops

    def nueva_pagina(self) -> None:
        self.paginas.append(_Pagina())
        self.y = ALTO - MARGEN_SUP
        if self.cabecera:
            self.texto(MARGEN_X, ALTO - 36, [(self.cabecera, "F1")], 8, gris=0.45)
            self.linea(MARGEN_X, ALTO - 42, ANCHO - MARGEN_X, ALTO - 42, gris=0.8)

    def sitio(self, alto: float) -> None:
        if self.y - alto < MARGEN_INF:
            self.nueva_pagina()

    def texto(self, x: float, y: float, runs: list[tuple[str, str]], tam: float, gris: float = 0.12) -> None:
        partes = [f"BT {gris:.2f} g {x:.2f} {y:.2f} Td"]
        fuente_actual = None
        for t, fuente in runs:
            if fuente != fuente_actual:
                partes.append(f"/{fuente} {tam:.1f} Tf")
                fuente_actual = fuente
            partes.append(f"{_cadena(t)} Tj")
        partes.append("ET")
        self.ops.append(" ".join(partes))

    def linea(self, x1: float, y1: float, x2: float, y2: float, gris: float = 0.7, grosor: float = 0.6) -> None:
        self.ops.append(f"{gris:.2f} G {grosor:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def rect(self, x: float, y: float, w: float, h: float, relleno: tuple[float, float, float] | None = None,
             borde: float | None = 0.75) -> None:
        if relleno:
            r, g, b = relleno
            self.ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")
        if borde is not None:
            self.ops.append(f"{borde:.2f} G 0.5 w {x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")


def _runs_inline(texto: str, negrita_base: bool = False) -> list[tuple[str, bool]]:
    """Divide un texto con **negritas** en tramos (texto, negrita)."""
    trozos = re.split(r"(\*\*[^*]+\*\*)", texto)
    salida = []
    for t in trozos:
        if not t:
            continue
        if t.startswith("**") and t.endswith("**"):
            salida.append((t[2:-2], True))
        else:
            salida.append((t, negrita_base))
    return salida


def _envolver(runs: list[tuple[str, bool]], tam: float, ancho: float) -> list[list[tuple[str, bool]]]:
    """Reparte tramos en líneas que caben en `ancho` (por palabras)."""
    palabras: list[tuple[str, bool]] = []
    for t, b in runs:
        for p in re.split(r"(\s+)", t):
            if p and not p.isspace():
                palabras.append((p, b))
            elif p and palabras:
                palabras.append((" ", b))
    lineas: list[list[tuple[str, bool]]] = [[]]
    actual = 0.0
    for p, b in palabras:
        w = ancho_texto(p, tam, b)
        if p == " ":
            if lineas[-1]:
                lineas[-1].append((p, b))
                actual += w
            continue
        if actual + w > ancho and lineas[-1]:
            while lineas[-1] and lineas[-1][-1][0] == " ":
                lineas[-1].pop()
            lineas.append([])
            actual = 0.0
        lineas[-1].append((p, b))
        actual += w
    # une palabras consecutivas del mismo estilo en un solo tramo
    salida = []
    for linea in lineas:
        while linea and linea[-1][0] == " ":
            linea.pop()
        fusion: list[tuple[str, bool]] = []
        for t, b in linea:
            if fusion and fusion[-1][1] == b:
                fusion[-1] = (fusion[-1][0] + t, b)
            else:
                fusion.append((t, b))
        salida.append(fusion)
    return [linea for linea in salida if linea] or [[("", False)]]


def _parrafo(c: _Lienzo, texto: str, tam: float = 10.0, sangria: float = 0.0, interlineado: float = 1.38,
             negrita: bool = False, cursiva: bool = False, vineta: str | None = None, espacio_despues: float = 6.0) -> None:
    lineas = _envolver(_runs_inline(texto, negrita), tam, AREA - sangria)
    alto_linea = tam * interlineado
    for i, linea in enumerate(lineas):
        c.sitio(alto_linea)
        c.y -= alto_linea
        if i == 0 and vineta:
            c.texto(MARGEN_X + sangria - ancho_texto(vineta + " ", tam), c.y, [(vineta, "F1")], tam)
        runs = [(t, "F3" if cursiva and not b else ("F2" if b else "F1")) for t, b in linea]
        c.texto(MARGEN_X + sangria, c.y, runs, tam)
    c.y -= espacio_despues


def _tabla(c: _Lienzo, filas: list[list[str]], tam: float = 8.6) -> None:
    ncol = max(len(f) for f in filas)
    filas = [f + [""] * (ncol - len(f)) for f in filas]
    # ancho de columna proporcional al texto más largo (con mínimos)
    pesos = []
    for j in range(ncol):
        largo = max(min(ancho_texto(f[j], tam, i == 0), 220) for i, f in enumerate(filas))
        pesos.append(max(largo, 40))
    total = sum(pesos)
    anchos = [AREA * p / total for p in pesos]
    pad = 4.0
    alto_linea = tam * 1.3
    c.y -= 4
    for i, fila in enumerate(filas):
        celdas = [_envolver(_runs_inline(t, i == 0), tam, anchos[j] - 2 * pad) for j, t in enumerate(fila)]
        alto = max(len(c) for c in celdas) * alto_linea + 2 * pad
        c.sitio(alto)
        y0 = c.y - alto
        x = MARGEN_X
        for j, lineas in enumerate(celdas):
            c.rect(x, y0, anchos[j], alto, relleno=(0.93, 0.94, 0.95) if i == 0 else None, borde=0.72)
            yy = c.y - pad
            for linea in lineas:
                yy -= alto_linea
                c.texto(x + pad, yy + 2.5, [(t, "F2" if b else "F1") for t, b in linea], tam)
            x += anchos[j]
        c.y = y0
    c.y -= 10


def markdown_a_pdf(md: str, titulo_doc: str = "", cabecera: str = "", pie: str = "") -> bytes:
    """Convierte el Markdown sencillo de la semilla en un PDF (bytes)."""
    c = _Lienzo(cabecera)
    lineas = md.replace("\r", "").split("\n")
    i = 0
    parrafo: list[str] = []

    def volcar() -> None:
        if parrafo:
            _parrafo(c, " ".join(s.strip() for s in parrafo))
            parrafo.clear()

    while i < len(lineas):
        ln = lineas[i].rstrip()
        if not ln.strip():
            volcar()
        elif ln.startswith("# "):
            volcar()
            c.sitio(40)
            _parrafo(c, ln[2:].strip(), tam=17, negrita=True, interlineado=1.25, espacio_despues=4)
            c.linea(MARGEN_X, c.y, ANCHO - MARGEN_X, c.y, gris=0.25, grosor=1.2)
            c.y -= 12
        elif ln.startswith("## "):
            volcar()
            c.sitio(48)
            c.y -= 6
            _parrafo(c, ln[3:].strip(), tam=12.5, negrita=True, interlineado=1.3, espacio_despues=3)
        elif ln.startswith("### "):
            volcar()
            c.sitio(36)
            _parrafo(c, ln[4:].strip(), tam=10.5, negrita=True, espacio_despues=2)
        elif ln.lstrip().startswith(("- ", "* ")):
            volcar()
            _parrafo(c, ln.lstrip()[2:].strip(), sangria=16, vineta="•", espacio_despues=2)
        elif re.match(r"^\s*\d+[.)] ", ln):
            volcar()
            num, resto = ln.strip().split(" ", 1)
            _parrafo(c, resto.strip(), sangria=20, vineta=num, espacio_despues=2)
        elif ln.startswith(">"):
            volcar()
            _parrafo(c, ln.lstrip("> ").strip(), sangria=12, cursiva=True, espacio_despues=6)
        elif ln.startswith("|"):
            volcar()
            filas = []
            while i < len(lineas) and lineas[i].startswith("|"):
                celdas = [x.strip() for x in lineas[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", x) for x in celdas if x):
                    filas.append(celdas)
                i += 1
            if filas:
                _tabla(c, filas)
            continue
        else:
            parrafo.append(ln)
        i += 1
    volcar()

    # pies de página con numeración
    n = len(c.paginas)
    for k, pag in enumerate(c.paginas, start=1):
        txt = f"{pie} · Página {k} de {n}" if pie else f"Página {k} de {n}"
        pag.ops.append(f"0.80 G 0.5 w {MARGEN_X:.2f} 44 m {ANCHO - MARGEN_X:.2f} 44 l S")
        pag.ops.append(f"BT 0.45 g {MARGEN_X:.2f} 32 Td /F1 7.5 Tf {_cadena(txt)} Tj ET")
    return _ensamblar([p.ops for p in c.paginas], titulo_doc)


def _ensamblar(paginas: list[list[str]], titulo: str) -> bytes:
    objetos: list[bytes] = []

    def nuevo(contenido: bytes) -> int:
        objetos.append(contenido)
        return len(objetos)

    nuevo(b"")  # 1: catálogo (se rellena al final)
    nuevo(b"")  # 2: árbol de páginas
    fuentes = {
        "F1": nuevo(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"),
        "F2": nuevo(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"),
        "F3": nuevo(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>"),
    }
    recursos = "<< /Font << " + " ".join(f"/{k} {v} 0 R" for k, v in fuentes.items()) + " >> >>"
    hijos = []
    for ops in paginas:
        flujo = "\n".join(ops).encode("latin-1")
        cont = nuevo(b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"\nendstream")
        hijos.append(nuevo(
            (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {ANCHO:.2f} {ALTO:.2f}] "
             f"/Resources {recursos} /Contents {cont} 0 R >>").encode("latin-1")
        ))
    info = nuevo(f"<< /Title {_cadena(titulo)} /Producer (CidIA semilla) /Creator (CidIA) >>".encode("latin-1"))
    objetos[0] = b"<< /Type /Catalog /Pages 2 0 R /Lang (es-ES) >>"
    objetos[1] = (f"<< /Type /Pages /Kids [{' '.join(f'{h} 0 R' for h in hijos)}] /Count {len(hijos)} >>").encode()

    salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    posiciones = []
    for n, obj in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += f"{n} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for p in posiciones:
        salida += f"{p:010d} 00000 n \n".encode()
    salida += (f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    return bytes(salida)
