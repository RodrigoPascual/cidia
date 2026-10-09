"""Imágenes esquemáticas de los pasos de las instrucciones sintéticas (Pillow).

Cada imagen (1280×720) lleva la cabecera con el código de la instrucción, un dibujo sencillo
del paso (pictograma vectorial dibujado a mano), el número del paso, su título y las marcas de
paso crítico o de seguridad. Las usa el modo planta y el vídeo sintético de datos-demo.

Si el sistema no tiene una fuente TrueType con tildes (p. ej. una imagen Docker mínima), se
usa la fuente integrada de Pillow y se quitan las tildes del texto dibujado.
"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ANCHO, ALTO = 1280, 720

TINTA = "#1f2328"
PIZARRA = "#5b6573"
LINEA = "#d9dce1"
PAPEL = "#f5f6f8"
ACERO = "#9aa3ae"
ACERO_CLARO = "#c9cfd6"
ACERO_OSCURO = "#6b7480"
ACENTO = "#f2c200"
VERDE = "#1f8a70"
ALERTA = "#c8442f"
AVISO = "#d97a00"
INFO = "#2f6fbf"
BLANCO = "#ffffff"

_CANDIDATAS = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]


@lru_cache
def _rutas_fuente() -> tuple[str, str] | None:
    for normal, negrita in _CANDIDATAS:
        if Path(normal).is_file() and Path(negrita).is_file():
            return normal, negrita
    return None


@lru_cache
def fuente(tam: int, negrita: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    rutas = _rutas_fuente()
    if rutas:
        return ImageFont.truetype(rutas[1] if negrita else rutas[0], tam)
    return ImageFont.load_default(size=tam)


def texto_seguro(t: str) -> str:
    """Sin fuente con tildes, las quita (la fuente integrada de Pillow no las tiene)."""
    if _rutas_fuente():
        return t
    t = t.replace("ñ", "n").replace("Ñ", "N").replace("·", "-").replace("º", "o").replace("×", "x")
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def _envolver(d: ImageDraw.ImageDraw, texto: str, f, ancho: int) -> list[str]:
    lineas: list[str] = []
    actual = ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if d.textlength(prueba, font=f) <= ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


# --------------------------------------------------------------------------- lienzo del pictograma


class Lienzo:
    """Coordenadas relativas 0..100 dentro de la caja del dibujo (cuadrada y centrada)."""

    def __init__(self, d: ImageDraw.ImageDraw, caja: tuple[int, int, int, int], color: str) -> None:
        self.d = d
        x0, y0, x1, y1 = caja
        self.s = min(x1 - x0, y1 - y0) / 100.0
        self.cx, self.cy = (x0 + x1) / 2, (y0 + y1) / 2
        self.color = color

    def p(self, x: float, y: float) -> tuple[float, float]:
        return self.cx + (x - 50) * self.s, self.cy + (y - 50) * self.s

    def r(self, v: float) -> float:
        return v * self.s

    def caja(self, x0: float, y0: float, x1: float, y1: float) -> list[float]:
        a, b = self.p(x0, y0)
        c, e = self.p(x1, y1)
        return [a, b, c, e]

    def circulo(self, x: float, y: float, radio: float, relleno=None, borde=TINTA, grosor: float = 0.8) -> None:
        cx, cy = self.p(x, y)
        r = self.r(radio)
        self.d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=relleno, outline=borde,
                       width=max(1, int(self.r(grosor))) if borde else 0)

    def rect(self, x0, y0, x1, y1, relleno=None, borde=TINTA, grosor: float = 0.8, radio: float = 0) -> None:
        self.d.rounded_rectangle(self.caja(x0, y0, x1, y1), radius=int(self.r(radio)), fill=relleno, outline=borde,
                                 width=max(1, int(self.r(grosor))) if borde else 0)

    def linea(self, puntos: list[tuple[float, float]], color=TINTA, grosor: float = 0.8) -> None:
        self.d.line([self.p(x, y) for x, y in puntos], fill=color, width=max(1, int(self.r(grosor))), joint="curve")

    def poligono(self, puntos: list[tuple[float, float]], relleno=None, borde=TINTA, grosor: float = 0.8) -> None:
        self.d.polygon([self.p(x, y) for x, y in puntos], fill=relleno, outline=borde,
                       width=max(1, int(self.r(grosor))) if borde else 0)

    def flecha(self, x0, y0, x1, y1, color=TINTA, grosor: float = 1.0, punta: float = 3.5) -> None:
        self.linea([(x0, y0), (x1, y1)], color, grosor)
        ang = math.atan2(y1 - y0, x1 - x0)
        a = (x1 - punta * math.cos(ang - 0.45), y1 - punta * math.sin(ang - 0.45))
        b = (x1 - punta * math.cos(ang + 0.45), y1 - punta * math.sin(ang + 0.45))
        self.poligono([(x1, y1), a, b], relleno=color, borde=None)

    def arco(self, x, y, radio, inicio, fin, color=TINTA, grosor: float = 0.8) -> None:
        cx, cy = self.p(x, y)
        r = self.r(radio)
        self.d.arc([cx - r, cy - r, cx + r, cy + r], inicio, fin, fill=color, width=max(1, int(self.r(grosor))))

    def texto(self, x, y, t: str, tam: float = 5, color=TINTA, negrita: bool = True, ancla: str = "mm") -> None:
        self.d.text(self.p(x, y), texto_seguro(t), font=fuente(max(10, int(self.r(tam))), negrita), fill=color,
                    anchor=ancla)

    def hexagono(self, x, y, radio, relleno=ACERO_CLARO, borde=TINTA) -> None:
        pts = [(x + radio * math.cos(math.radians(60 * k)), y + radio * math.sin(math.radians(60 * k))) for k in range(6)]
        self.poligono(pts, relleno=relleno, borde=borde)

    def check(self, x, y, tam=10, color=VERDE) -> None:
        self.circulo(x, y, tam, relleno=color, borde=None)
        self.linea([(x - tam * 0.45, y), (x - tam * 0.1, y + tam * 0.38), (x + tam * 0.5, y - tam * 0.35)], BLANCO,
                   tam * 0.18)

    def brida(self, x, y, radio, tornillos: bool = False) -> None:
        self.circulo(x, y, radio, relleno=ACERO_CLARO)
        self.circulo(x, y, radio * 0.42, relleno=PAPEL)
        for k in range(4):
            ang = math.radians(90 * k - 90)
            bx, by = x + radio * 0.72 * math.cos(ang), y + radio * 0.72 * math.sin(ang)
            if tornillos:
                self.hexagono(bx, by, radio * 0.13, relleno=ACERO)
            else:
                self.circulo(bx, by, radio * 0.09, relleno=PAPEL)

    def prensa(self, molde: str | None = ACERO) -> None:
        self.rect(14, 8, 86, 20, relleno=ACERO_OSCURO, radio=1.5)  # cabezal
        self.rect(16, 20, 26, 88, relleno=ACERO, radio=1)  # columnas
        self.rect(74, 20, 84, 88, relleno=ACERO, radio=1)
        self.rect(28, 22, 72, 34, relleno=ACERO_CLARO)  # carro
        self.rect(10, 82, 90, 92, relleno=ACERO_OSCURO, radio=1.5)  # mesa
        if molde:
            self.rect(34, 62, 66, 82, relleno=molde, radio=1)
            self.rect(36, 34, 64, 46, relleno=molde, radio=1)


# --------------------------------------------------------------------------- pictogramas


def _material(lz: Lienzo, dato: str) -> None:
    lz.rect(6, 64, 94, 90, relleno=ACERO_CLARO, radio=3)
    lz.brida(26, 50, 18)
    lz.circulo(56, 52, 11, relleno=None, borde=TINTA, grosor=2.4)
    lz.texto(56, 70, "junta", 4, PIZARRA, False)
    for k in range(4):
        x = 74 + k * 5.5
        lz.rect(x - 1.2, 38, x + 1.2, 60, relleno=ACERO)
        lz.hexagono(x, 36, 2.6)
    lz.texto(26, 76, "brida B", 4, PIZARRA, False)
    lz.texto(82, 70, "4 × M10", 4, PIZARRA, False)


def _junta(lz: Lienzo, dato: str) -> None:
    lz.brida(44, 52, 32)
    lz.circulo(44, 52, 20, relleno=None, borde=TINTA, grosor=3.2)
    lz.poligono([(70, 14), (92, 20), (88, 36), (66, 30)], relleno="#e8eaee")
    for k in range(3):
        lz.linea([(72 + k * 6, 40), (68 + k * 6, 46)], ACERO_OSCURO, 0.7)
    lz.texto(44, 92, dato or "junta centrada, sin pliegues", 4.4, PIZARRA, False)


def _par_cruz(lz: Lienzo, dato: str) -> None:
    lz.brida(40, 44, 30, tornillos=True)
    posiciones = {1: (40, 22.4), 2: (40, 65.6), 3: (61.6, 44), 4: (18.4, 44)}
    for n, (x, y) in posiciones.items():
        dx = 7 if x >= 40 else -7
        lz.circulo(x + dx, y - 7, 4.2, relleno=ALERTA, borde=None)
        lz.texto(x + dx, y - 7, str(n), 5, BLANCO)
    lz.flecha(40, 27, 40, 60, ALERTA, 0.9)
    lz.flecha(44, 44, 57, 44, ALERTA, 0.9)
    lz.flecha(36, 44, 23, 44, ALERTA, 0.9)
    # llave dinamométrica
    lz.poligono([(58, 86), (95, 70), (96.5, 73.5), (59.5, 89.5)], relleno=TINTA, borde=None)
    lz.circulo(56, 88, 5, relleno=ACERO_OSCURO, borde=TINTA)
    lz.rect(70, 74.5, 80, 79.5, relleno=ACENTO, borde=None, radio=1)
    lz.texto(78, 64, dato or "25 N·m", 6.5, ALERTA)


def _marcado(lz: Lienzo, dato: str) -> None:
    lz.rect(8, 30, 92, 78, relleno=ACERO_CLARO, radio=3)
    for k in range(3):
        x = 24 + k * 26
        lz.hexagono(x, 54, 9, relleno=ACERO)
        lz.poligono([(x - 2, 40), (x + 2, 40), (x + 2, 70), (x - 2, 70)], relleno=ACENTO, borde=None)
    lz.poligono([(64, 8), (70, 6), (86, 30), (80, 33)], relleno=ACENTO)
    lz.poligono([(80, 33), (86, 30), (88, 36)], relleno=TINTA, borde=None)
    lz.texto(50, 90, dato or "marca de testigo", 4.6, PIZARRA, False)


def _manometro(lz: Lienzo, dato: str) -> None:
    lz.circulo(46, 46, 32, relleno=BLANCO, grosor=1.6)
    for k in range(7):
        ang = math.radians(135 + k * 45)
        x0, y0 = 46 + 26 * math.cos(ang), 46 + 26 * math.sin(ang)
        x1, y1 = 46 + 30 * math.cos(ang), 46 + 30 * math.sin(ang)
        lz.linea([(x0, y0), (x1, y1)], TINTA, 0.8)
        lz.texto(46 + 21 * math.cos(ang), 46 + 21 * math.sin(ang), str(k), 4, PIZARRA, False)
    lz.arco(46, 46, 28, 270, 315, VERDE, 2.2)
    ang = math.radians(135 + 3 * 45)
    lz.linea([(46, 46), (46 + 22 * math.cos(ang), 46 + 22 * math.sin(ang))], ALERTA, 1.6)
    lz.circulo(46, 46, 2.5, relleno=TINTA, borde=None)
    lz.texto(46, 64, "bar", 4, PIZARRA, False)
    lz.rect(44, 78, 48, 92, relleno=ACERO, borde=None)
    lz.circulo(82, 74, 10, relleno=BLANCO, grosor=1)
    lz.linea([(82, 74), (82, 67)], TINTA, 0.9)
    lz.linea([(82, 74), (87, 76)], TINTA, 0.9)
    lz.texto(82, 90, dato or "3 bar · 60 s", 4.6, TINTA)


def _lupa(lz: Lienzo, dato: str) -> None:
    lz.brida(40, 50, 30, tornillos=True)
    lz.circulo(62, 38, 17, relleno=None, borde=TINTA, grosor=2.4)
    lz.linea([(74, 50), (90, 66)], TINTA, 4.5)
    lz.check(84, 18, 8)
    lz.texto(50, 92, dato or "inspección visual", 4.6, PIZARRA, False)


def _etiqueta(lz: Lienzo, dato: str) -> None:
    lz.rect(14, 8, 62, 90, relleno=BLANCO, radio=3, grosor=1.2)
    lz.rect(28, 4, 48, 12, relleno=ACERO, radio=1.5)
    for k in range(6):
        lz.linea([(20, 24 + k * 9), (56 - (k % 3) * 6, 24 + k * 9)], ACERO, 1)
    lz.rect(58, 52, 94, 80, relleno=VERDE, borde=None, radio=2)
    lz.texto(76, 61, "OK", 7, BLANCO)
    for k in range(10):
        x = 62 + k * 3
        lz.linea([(x, 70), (x, 77)], BLANCO, 0.5 + (k % 3) * 0.4)
    lz.texto(50, 96, dato or "registrar y etiquetar", 4.4, PIZARRA, False)


def _candado(lz: Lienzo, dato: str) -> None:
    lz.rect(8, 18, 40, 86, relleno=ACERO_CLARO, radio=2)
    lz.circulo(24, 44, 9, relleno=ALERTA, borde=TINTA)
    lz.rect(22.5, 32, 25.5, 50, relleno=ACENTO, borde=TINTA, grosor=0.5)
    lz.texto(24, 64, "OFF", 6, TINTA)
    lz.arco(62, 34, 10, 180, 360, TINTA, 2.6)
    lz.rect(49, 34, 75, 58, relleno=ALERTA, radio=2)
    lz.circulo(62, 44, 2.5, relleno=TINTA, borde=None)
    lz.poligono([(54, 62), (88, 62), (92, 72), (88, 92), (54, 92)], relleno=ACENTO)
    lz.texto(72, 72, "NO", 5, TINTA)
    lz.texto(72, 81, "OPERAR", 4.2, TINTA)


def _prensa_sacar(lz: Lienzo, dato: str) -> None:
    lz.prensa(molde=ACERO_OSCURO)
    lz.flecha(70, 72, 98, 72, ALERTA, 1.6, 5)
    lz.texto(50, 98, dato or "sacar el molde con el carro", 4.4, PIZARRA, False)


def _prensa_meter(lz: Lienzo, dato: str) -> None:
    lz.prensa(molde=INFO)
    lz.flecha(98, 72, 70, 72, VERDE, 1.6, 5)
    lz.circulo(34, 84, 2.2, relleno=ACENTO, borde=TINTA)
    lz.circulo(66, 84, 2.2, relleno=ACENTO, borde=TINTA)
    lz.texto(50, 98, dato or "centrar con los tacos de referencia", 4.4, PIZARRA, False)


def _aire(lz: Lienzo, dato: str) -> None:
    lz.rect(52, 50, 80, 64, relleno=ACERO, radio=2)  # cuerpo del sensor
    lz.rect(80, 52, 86, 62, relleno=TINTA, borde=None)
    lz.circulo(56, 47, 2, relleno=ACENTO, borde=TINTA)
    lz.poligono([(8, 28), (30, 28), (34, 34), (30, 40), (8, 40)], relleno=TINTA, borde=None)  # pistola
    lz.rect(14, 40, 22, 62, relleno=TINTA, borde=None, radio=1)
    lz.linea([(34, 34), (40, 36)], TINTA, 2)
    for k in range(4):
        y = 38 + k * 5
        lz.linea([(43, y), (49, y + 6)], INFO, 0.8)
    for x, y in ((60, 72), (66, 76), (72, 71), (58, 80)):
        lz.circulo(x, y, 1.2, relleno=ACERO_OSCURO, borde=None)
    lz.texto(50, 92, dato or "aire a baja presión", 4.6, PIZARRA, False)


def _amarre(lz: Lienzo, dato: str) -> None:
    lz.rect(8, 58, 92, 74, relleno=ACERO_OSCURO, radio=1.5)
    lz.rect(26, 36, 74, 58, relleno=INFO, radio=1)
    for x in (12, 78):
        lz.poligono([(x, 40), (x + 10, 40), (x + 10, 46), (x + 6, 46), (x + 6, 58), (x, 58)], relleno=ACENTO)
    lz.circulo(50, 20, 11, relleno=BLANCO, grosor=1.2)
    lz.arco(50, 20, 8, 200, 340, VERDE, 1.6)
    lz.linea([(50, 20), (56, 14)], ALERTA, 1)
    lz.texto(50, 88, dato or "amarres apretados", 4.6, TINTA)


def _panel(lz: Lienzo, dato: str) -> None:
    lz.rect(10, 12, 90, 80, relleno=TINTA, radio=3)
    lz.rect(16, 18, 84, 62, relleno="#2b3a4a", borde=None, radio=1.5)
    lineas = (dato or "Receta M-318 · Altura 412,5 mm").split(" · ")
    for k, t in enumerate(lineas[:3]):
        lz.texto(50, 30 + k * 11, t, 5, "#d6f5e9" if k else ACENTO, k == 0)
    lz.poligono([(28, 66), (34, 74), (22, 74)], relleno=VERDE, borde=None)
    lz.poligono([(44, 74), (50, 66), (56, 74)], relleno=None, borde=ACERO, grosor=0.6)
    lz.circulo(74, 70, 4, relleno=ALERTA, borde=None)


def _golpe(lz: Lienzo, dato: str) -> None:
    lz.prensa(molde=INFO)
    lz.flecha(50, 22, 50, 33, ALERTA, 1.4, 3)
    for k in range(3):
        x = 33 + k * 17
        lz.circulo(x, 104 - 6, 5, relleno=VERDE, borde=None)
        lz.poligono([(x - 1.5, 95.5), (x - 1.5, 100.5), (x + 2.5, 98)], relleno=BLANCO, borde=None)
    lz.texto(50, 4, dato or "3 golpes en vacío", 4.4, PIZARRA, False)


def _pieza_ok(lz: Lienzo, dato: str) -> None:
    lz.poligono([(10, 70), (10, 40), (18, 40), (18, 62), (52, 62), (52, 70)], relleno=ACERO_CLARO, grosor=1.2)
    lz.circulo(30, 66, 2, relleno=PAPEL)
    lz.check(74, 40, 14)
    lz.flecha(58, 76, 90, 76, INFO, 1.4, 4)
    lz.texto(50, 92, dato or "primera pieza a Calidad", 4.6, PIZARRA, False)


def _sensor(lz: Lienzo, dato: str) -> None:
    lz.rect(10, 42, 58, 58, relleno=ACERO, radio=2)
    for k in range(8):
        x = 16 + k * 5
        lz.linea([(x, 42), (x + 2, 58)], ACERO_OSCURO, 0.5)
    lz.rect(58, 44, 62, 56, relleno=TINTA, borde=None)
    lz.circulo(14, 38, 2.4, relleno=ACENTO, borde=TINTA)
    lz.rect(82, 30, 88, 70, relleno=ACERO_CLARO)
    lz.flecha(66, 72, 81, 72, ALERTA, 0.8, 2.5)
    lz.flecha(77, 72, 63, 72, ALERTA, 0.8, 2.5)
    lz.linea([(62, 60), (62, 76)], ALERTA, 0.4)
    lz.linea([(82, 70), (82, 76)], ALERTA, 0.4)
    lz.texto(72, 80, dato or "8 mm", 5.2, ALERTA)
    lz.texto(34, 66, "S4", 5, TINTA)


def _potenciometro(lz: Lienzo, dato: str) -> None:
    lz.rect(12, 30, 70, 70, relleno=ACERO, radio=3)
    lz.circulo(30, 50, 8, relleno=BLANCO)
    lz.linea([(25, 55), (35, 45)], TINTA, 1.2)
    lz.circulo(56, 42, 3.5, relleno=ACENTO, borde=TINTA)
    lz.texto(56, 58, "LED", 4, TINTA)
    lz.poligono([(36, 44), (40, 40), (84, 84), (80, 88)], relleno=ALERTA, borde=TINTA)
    lz.rect(78, 82, 94, 96, relleno=TINTA, borde=None, radio=2)
    lz.texto(50, 16, dato or "ajustar la sensibilidad", 4.6, PIZARRA, False)


def _plano(lz: Lienzo, dato: str) -> None:
    lz.rect(6, 10, 94, 90, relleno=BLANCO, grosor=1.2)
    lz.rect(60, 74, 94, 90, relleno=None, grosor=0.6)
    for k in range(3):
        lz.linea([(60, 78 + k * 4), (94, 78 + k * 4)], ACERO, 0.4)
    lz.rect(16, 24, 46, 52, relleno=None, borde=INFO, grosor=1)
    lz.circulo(31, 38, 6, relleno=None, borde=INFO, grosor=0.8)
    lz.rect(56, 24, 84, 52, relleno=None, borde=INFO, grosor=1)
    lz.linea([(16, 58), (46, 58)], ALERTA, 0.5)
    lz.texto(31, 63, "120", 4, ALERTA, False)
    lz.linea([(52, 24), (52, 52)], ALERTA, 0.5)
    lz.texto(28, 82, dato or "plano de la pieza", 4.4, PIZARRA, False)


def _referencias(lz: Lienzo, dato: str) -> None:
    lz.poligono([(20, 40), (60, 30), (90, 42), (50, 54)], relleno=ACERO_CLARO)
    lz.poligono([(20, 40), (50, 54), (50, 74), (20, 60)], relleno=ACERO)
    lz.poligono([(50, 54), (90, 42), (90, 62), (50, 74)], relleno=ACERO_OSCURO)
    for x, y in ((28, 70), (46, 82), (70, 76)):
        lz.poligono([(x, y - 4), (x - 3, y + 3), (x + 3, y + 3)], relleno=ALERTA, borde=None)
    for x, y in ((12, 50), (12, 62)):
        lz.poligono([(x + 4, y), (x - 2, y - 3), (x - 2, y + 3)], relleno=INFO, borde=None)
    lz.poligono([(96, 50), (100, 46), (100, 54)], relleno=VERDE, borde=None)
    lz.texto(50, 12, dato or "3 · 2 · 1", 7, TINTA)


def _cad(lz: Lienzo, dato: str) -> None:
    lz.rect(8, 10, 92, 72, relleno=TINTA, radio=3)
    lz.rect(13, 15, 87, 66, relleno="#eef2f6", borde=None)
    pts = {"a": (36, 36), "b": (56, 28), "c": (72, 36), "d": (52, 44)}
    lz.poligono([pts["a"], pts["b"], pts["c"], pts["d"]], relleno="#cfe0f3", borde=INFO)
    lz.poligono([pts["a"], pts["d"], (52, 60), (36, 52)], relleno="#a9c6e8", borde=INFO)
    lz.poligono([pts["d"], pts["c"], (72, 52), (52, 60)], relleno="#86acd8", borde=INFO)
    lz.rect(40, 72, 60, 80, relleno=ACERO, borde=None)
    lz.rect(30, 80, 70, 84, relleno=ACERO_OSCURO, borde=None, radio=1)
    lz.texto(50, 94, dato or "modelo 3D", 4.6, PIZARRA, False)


def _antorcha(lz: Lienzo, dato: str) -> None:
    lz.rect(8, 64, 92, 76, relleno=ACERO_CLARO)
    lz.rect(46, 30, 58, 64, relleno=ACERO)
    lz.poligono([(20, 14), (26, 10), (50, 58), (46, 62)], relleno=TINTA)
    lz.circulo(48, 61, 2.5, relleno=ACENTO, borde=None)
    lz.arco(48, 62, 18, 225, 270, ALERTA, 0.9)
    lz.texto(30, 40, dato or "45°", 5.5, ALERTA)
    lz.circulo(48, 62, 10, relleno=None, borde=VERDE, grosor=0.6)
    lz.texto(74, 88, "sin colisiones", 4.4, VERDE, False)


def _calibre(lz: Lienzo, dato: str, cero: bool = False) -> None:
    lz.rect(6, 40, 94, 50, relleno=ACERO_CLARO)
    for k in range(30):
        x = 10 + k * 2.8
        lz.linea([(x, 40), (x, 43 if k % 5 else 45)], TINTA, 0.3)
    lz.poligono([(8, 50), (16, 50), (16, 80), (12, 84), (8, 80)], relleno=ACERO)
    x2 = 18 if cero else 40
    lz.poligono([(x2, 50), (x2 + 8, 50), (x2 + 8, 80), (x2 + 4, 84), (x2, 80)], relleno=ACERO)
    lz.rect(x2 + 8, 34, x2 + 40, 56, relleno=ACERO, radio=2)
    lz.rect(x2 + 12, 38, x2 + 36, 48, relleno="#e3f4ee", borde=TINTA, grosor=0.4)
    lz.texto(x2 + 24, 43, "0,00" if cero else (dato or "24,98"), 5, TINTA)
    if not cero:
        lz.rect(17, 60, 39, 76, relleno=INFO, borde=TINTA, radio=1)
    lz.texto(50, 94, "calibre a cero" if cero else "medir sin forzar", 4.6, PIZARRA, False)


def _cero(lz: Lienzo, dato: str) -> None:
    _calibre(lz, dato, cero=True)


def _termometro(lz: Lienzo, dato: str) -> None:
    lz.rect(22, 12, 34, 70, relleno=BLANCO, radio=6)
    lz.circulo(28, 76, 9, relleno=ALERTA)
    lz.rect(26, 40, 30, 74, relleno=ALERTA, borde=None)
    for k in range(6):
        lz.linea([(34, 18 + k * 9), (38, 18 + k * 9)], TINTA, 0.5)
    lz.rect(52, 50, 90, 80, relleno=ACERO_CLARO, radio=2)
    lz.texto(71, 30, dato or "20 ± 2 °C", 6, TINTA)
    lz.texto(71, 92, "aclimatar la pieza", 4.4, PIZARRA, False)


def _spc(lz: Lienzo, dato: str) -> None:
    lz.rect(6, 10, 94, 86, relleno=BLANCO, grosor=1)
    lz.linea([(12, 26), (90, 26)], ALERTA, 0.5)
    lz.linea([(12, 70), (90, 70)], ALERTA, 0.5)
    lz.linea([(12, 48), (90, 48)], VERDE, 0.4)
    vals = [46, 52, 44, 50, 40, 55, 49, 45, 51, 47]
    pts = [(16 + k * 8, v) for k, v in enumerate(vals)]
    lz.linea(pts, INFO, 0.8)
    for x, y in pts:
        lz.circulo(x, y, 1.6, relleno=INFO, borde=None)
    lz.texto(50, 94, dato or "registrar en el control estadístico", 4.4, PIZARRA, False)


def _semaforo(lz: Lienzo, dato: str) -> None:
    for x, color, t in ((10, VERDE, "OK"), (54, ALERTA, "NOK")):
        lz.rect(x, 50, x + 36, 88, relleno=ACERO_CLARO, radio=2)
        lz.poligono([(x + 6, 20), (x + 30, 20), (x + 34, 30), (x + 30, 40), (x + 6, 40)], relleno=color, borde=None)
        lz.texto(x + 18, 30, t, 6, BLANCO)
    lz.texto(50, 96, dato or "identificar y segregar", 4.4, PIZARRA, False)


def _check(lz: Lienzo, dato: str) -> None:
    lz.check(50, 46, 26)
    if dato:
        lz.texto(50, 88, dato, 5, PIZARRA, False)


PICTOGRAMAS: dict[str, Callable[[Lienzo, str], None]] = {
    "material": _material, "junta": _junta, "par_cruz": _par_cruz, "marcado": _marcado, "manometro": _manometro,
    "lupa": _lupa, "etiqueta": _etiqueta, "candado": _candado, "prensa_sacar": _prensa_sacar,
    "prensa_meter": _prensa_meter, "aire": _aire, "amarre": _amarre, "panel": _panel, "golpe": _golpe,
    "pieza_ok": _pieza_ok, "sensor": _sensor, "potenciometro": _potenciometro, "plano": _plano,
    "referencias": _referencias, "cad": _cad, "antorcha": _antorcha, "calibre": _calibre, "cero": _cero,
    "termometro": _termometro, "spc": _spc, "semaforo": _semaforo, "check": _check,
}


# --------------------------------------------------------------------------- composición


def _marca(d: ImageDraw.ImageDraw, x: int, y: int, texto: str, fondo: str) -> int:
    f = fuente(24, True)
    t = texto_seguro(texto)
    w = int(d.textlength(t, font=f)) + 36
    d.rounded_rectangle([x, y, x + w, y + 44], radius=22, fill=fondo)
    d.text((x + 18, y + 22), t, font=f, fill=BLANCO, anchor="lm")
    return w


def imagen_paso(codigo: str, titulo_instruccion: str, version: int, orden: int, total: int, titulo: str,
                dibujo: str, color: str, dato: str = "", critico: bool = False, seguridad: bool = False,
                empresa: str = "Metalúrgica Arlanza, S. L.") -> Image.Image:
    """Compone la imagen de un paso: cabecera, pictograma, número, título y marcas."""
    im = Image.new("RGB", (ANCHO, ALTO), PAPEL)
    d = ImageDraw.Draw(im)
    # cabecera con el color del departamento
    d.rectangle([0, 0, ANCHO, 76], fill=color)
    d.text((40, 38), texto_seguro(f"{codigo} · {titulo_instruccion}"), font=fuente(30, True), fill=BLANCO, anchor="lm")
    d.text((ANCHO - 40, 38), texto_seguro(f"v{version} · paso {orden} de {total}"), font=fuente(24), fill=BLANCO,
           anchor="rm")
    # panel del dibujo
    d.rounded_rectangle([40, 104, 740, 668], radius=18, fill=BLANCO, outline=LINEA, width=2)
    PICTOGRAMAS.get(dibujo, _check)(Lienzo(d, (80, 130, 700, 646), color), dato)
    # número y título
    d.ellipse([784, 112, 924, 252], fill=ALERTA if critico else color)
    d.text((854, 182), str(orden), font=fuente(84, True), fill=BLANCO, anchor="mm")
    f = fuente(38, True)
    y = 290
    for linea in _envolver(d, texto_seguro(titulo), f, 440)[:5]:
        d.text((784, y), linea, font=f, fill=TINTA, anchor="la")
        y += 50
    x = 784
    y += 18
    if critico:
        x += _marca(d, x, y, "PASO CRÍTICO", ALERTA) + 12
    if seguridad:
        _marca(d, x, y, "SEGURIDAD", AVISO)
    d.text((40, 694), texto_seguro(f"{empresa} (empresa ficticia) · imagen esquemática sintética"), font=fuente(18),
           fill=PIZARRA, anchor="lm")
    return im


def tarjeta(titulo: str, subtitulo: str, color: str, pie: str = "") -> Image.Image:
    """Tarjeta de título (inicio y cierre del vídeo sintético)."""
    im = Image.new("RGB", (ANCHO, ALTO), TINTA)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 24, ALTO], fill=color)
    d.rectangle([0, ALTO - 12, ANCHO, ALTO], fill=ACENTO)
    y = 230
    for linea in _envolver(d, texto_seguro(titulo), fuente(64, True), 1100):
        d.text((90, y), linea, font=fuente(64, True), fill=BLANCO, anchor="la")
        y += 80
    for linea in _envolver(d, texto_seguro(subtitulo), fuente(34), 1100):
        d.text((90, y + 20), linea, font=fuente(34), fill="#cfd4da", anchor="la")
        y += 46
    if pie:
        d.text((90, ALTO - 60), texto_seguro(pie), font=fuente(22), fill="#9aa3ae", anchor="lm")
    return im
