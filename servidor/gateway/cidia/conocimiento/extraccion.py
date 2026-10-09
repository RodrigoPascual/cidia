"""Extracción de texto de ficheros y troceado en fragmentos."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

EXT_TEXTO = {".txt", ".md", ".csv", ".json", ".log"}
EXT_PDF = {".pdf"}
EXT_OFFICE = {".docx", ".xlsx", ".pptx"}
EXT_AUDIO = {".mp3", ".wav", ".m4a", ".ogg", ".oga", ".opus", ".webm", ".flac", ".aac"}
EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".webp"}
EXT_VIDEO = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def tipo_por_extension(nombre: str) -> str:
    ext = Path(nombre).suffix.lower()
    if ext in EXT_PDF:
        return "pdf"
    if ext in EXT_OFFICE:
        return "office"
    if ext in EXT_AUDIO:
        return "audio"
    if ext in EXT_IMAGEN:
        return "imagen"
    if ext in EXT_TEXTO:
        return "texto"
    return "otro"


def extraer(ruta: Path) -> list[tuple[str, dict[str, Any]]]:
    """Devuelve una lista de (texto, metadatos) por página, hoja o diapositiva.

    El audio y las imágenes no se tratan aquí (necesitan modelos): ver servicios/documentos.py.
    """
    ext = ruta.suffix.lower()
    if ext in EXT_TEXTO:
        return [(ruta.read_text(encoding="utf-8", errors="ignore"), {})]
    if ext in EXT_PDF:
        from pypdf import PdfReader

        lector = PdfReader(str(ruta))
        return [((p.extract_text() or ""), {"pagina": i}) for i, p in enumerate(lector.pages, start=1)]
    if ext == ".docx":
        import docx

        d = docx.Document(str(ruta))
        partes = [p.text for p in d.paragraphs]
        for t in d.tables:
            for fila in t.rows:
                partes.append(" | ".join(c.text.strip() for c in fila.cells))
        return [("\n".join(partes), {})]
    if ext == ".xlsx":
        import openpyxl

        libro = openpyxl.load_workbook(str(ruta), read_only=True, data_only=True)
        salida = []
        for hoja in libro.worksheets:
            filas = []
            for fila in hoja.iter_rows(values_only=True):
                celdas = [str(c) for c in fila if c is not None]
                if celdas:
                    filas.append(" | ".join(celdas))
            salida.append(("\n".join(filas), {"hoja": hoja.title}))
        return salida
    if ext == ".pptx":
        from pptx import Presentation

        pres = Presentation(str(ruta))
        salida = []
        for i, diapo in enumerate(pres.slides, start=1):
            textos = [sh.text_frame.text for sh in diapo.shapes if getattr(sh, "has_text_frame", False)]
            salida.append(("\n".join(textos), {"diapositiva": i}))
        return salida
    raise ValueError(f"Formato no soportado: {ext}")


def normalizar(texto: str) -> str:
    texto = texto.replace("\r", "")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def trocear(texto: str, maximo: int = 900, solape: int = 150) -> list[str]:
    """Trocea por párrafos respetando un tamaño máximo aproximado (en caracteres)."""
    texto = normalizar(texto)
    if not texto:
        return []
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    trozos: list[str] = []
    actual = ""
    for p in parrafos:
        if len(p) > maximo:
            frases = re.split(r"(?<=[.!?;:])\s+", p)
        else:
            frases = [p]
        for f in frases:
            while len(f) > maximo:  # frase enorme: corte duro
                trozos.append((actual + " " + f[:maximo]).strip() if actual else f[:maximo])
                actual = ""
                f = f[maximo - solape :]
            if len(actual) + len(f) + 2 <= maximo:
                actual = f"{actual}\n\n{f}" if actual else f
            else:
                if actual:
                    trozos.append(actual)
                cola = actual[-solape:] if actual and solape else ""
                actual = (cola + " " + f).strip() if cola else f
    if actual:
        trozos.append(actual)
    return trozos
