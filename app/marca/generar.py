"""Genera los iconos de CidIA a partir del diseño del logo (cidia.svg).

Salida (en esta carpeta):
  png/cidia-<n>.png      logo cuadrado en 16, 24, 32, 48, 64, 128, 256 y 512 px
  cidia.ico              icono de Windows con 16, 20, 24, 32, 40, 48, 64, 128 y 256 px
  instalador-bienvenida.bmp   164 x 314 (páginas de bienvenida y final del instalador)
  instalador-cabecera.bmp     150 x 57  (cabecera de las páginas del instalador)

Uso (Pillow en un entorno aparte, no es dependencia del proyecto):
  python -m venv .venv-marca && .venv-marca/Scripts/python -m pip install Pillow==11.0.0
  .venv-marca/Scripts/python app/marca/generar.py

El logo se dibuja con geometría, igual que el SVG: cuadrado redondeado amarillo (#F2C200,
radio 11/40), una C oscura (#1F2328, arco de radio 9,2 y trazo 4,4 con extremos redondeados)
y un punto (radio 2,7). Se dibuja a 8 aumentos y se reduce con Lanczos para suavizar bordes.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

AQUI = Path(__file__).resolve().parent
AMARILLO = (0xF2, 0xC2, 0x00, 255)
TINTA = (0x1F, 0x23, 0x28, 255)
GRIS = (0x9A, 0xA3, 0xAE, 255)
AUMENTO = 8

# Geometría del SVG (lienzo 40 x 40): arco de (27.4, 13.6) a (27.4, 26.4) con radio 9.2.
RADIO_C = 9.2
TRAZO_C = 4.4
_MEDIA_CUERDA = 6.4
CENTRO_C = (27.4 - math.sqrt(RADIO_C**2 - _MEDIA_CUERDA**2), 20.0)
ANGULO_C = math.degrees(math.atan2(_MEDIA_CUERDA, 27.4 - CENTRO_C[0]))  # ~44 grados
PUNTO = (29.2, 20.0, 2.7)


def logo(lado: int, margen: float = 0.0) -> Image.Image:
    """Logo cuadrado de `lado` píxeles con fondo transparente. `margen` en unidades del SVG."""
    grande = lado * AUMENTO
    img = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    e = grande / (40.0 + 2 * margen)  # píxeles por unidad del SVG
    o = margen * e

    def p(x: float, y: float) -> tuple[float, float]:
        return (o + x * e, o + y * e)

    d.rounded_rectangle([p(0, 0), p(40, 40)], radius=11 * e, fill=AMARILLO)
    # Arco: Pillow pinta el grosor hacia dentro de la caja; se centra en el radio 9.2.
    r_ext = RADIO_C + TRAZO_C / 2
    cx, cy = CENTRO_C
    d.arc([p(cx - r_ext, cy - r_ext), p(cx + r_ext, cy + r_ext)], start=ANGULO_C, end=360 - ANGULO_C,
          fill=TINTA, width=round(TRAZO_C * e))
    # Extremos redondeados del trazo.
    for signo in (-1, 1):
        a = math.radians(signo * ANGULO_C)
        ex, ey = cx + RADIO_C * math.cos(a), cy + RADIO_C * math.sin(a)
        rr = TRAZO_C / 2
        d.ellipse([p(ex - rr, ey - rr), p(ex + rr, ey + rr)], fill=TINTA)
    px, py, pr = PUNTO
    d.ellipse([p(px - pr, py - pr), p(px + pr, py + pr)], fill=TINTA)
    return img.resize((lado, lado), Image.LANCZOS)


def fuente(tam: int, negrita: bool = True) -> ImageFont.ImageFont:
    """Fuente del sistema para los mapas de bits del instalador (Segoe UI en Windows)."""
    candidatas = ["segoeuib.ttf", "seguisb.ttf", "arialbd.ttf"] if negrita else ["segoeui.ttf", "arial.ttf"]
    for nombre in candidatas:
        for carpeta in (Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")):
            ruta = carpeta / nombre
            if ruta.exists():
                return ImageFont.truetype(str(ruta), tam)
    return ImageFont.load_default()


def bienvenida() -> Image.Image:
    """Panel lateral de las páginas de bienvenida y final (164 x 314, fondo oscuro)."""
    img = Image.new("RGB", (164, 314), TINTA[:3])
    d = ImageDraw.Draw(img)
    marca = logo(72)
    img.paste(marca, ((164 - 72) // 2, 84), marca)
    f1 = fuente(26)
    ancho = d.textlength("CidIA", font=f1)
    d.text(((164 - ancho) / 2, 172), "CidIA", font=f1, fill=(255, 255, 255))
    f2 = fuente(11, negrita=False)
    for i, linea in enumerate(["el conocimiento", "se queda"]):
        w = d.textlength(linea, font=f2)
        d.text(((164 - w) / 2, 210 + i * 15), linea, font=f2, fill=GRIS[:3])
    d.rectangle([0, 310, 164, 314], fill=AMARILLO[:3])
    return img


def cabecera() -> Image.Image:
    """Imagen de la cabecera de las páginas interiores (150 x 57, fondo blanco)."""
    img = Image.new("RGB", (150, 57), (255, 255, 255))
    marca = logo(34)
    img.paste(marca, (108, 11), marca)
    return img


def principal() -> None:
    carpeta_png = AQUI / "png"
    carpeta_png.mkdir(exist_ok=True)
    for lado in (16, 24, 32, 48, 64, 128, 256, 512):
        logo(lado).save(carpeta_png / f"cidia-{lado}.png", optimize=True)
    tamanos = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    base = logo(256)
    base.save(AQUI / "cidia.ico", sizes=[(t, t) for t in tamanos],
              append_images=[logo(t) for t in tamanos if t != 256])
    bienvenida().save(AQUI / "instalador-bienvenida.bmp")
    cabecera().save(AQUI / "instalador-cabecera.bmp")
    print("Iconos de CidIA generados en", AQUI)


if __name__ == "__main__":
    principal()
