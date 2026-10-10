"""Qué imagen del experto se usa como referencia para comparar la foto del resultado."""

from __future__ import annotations

from types import SimpleNamespace

from cidia.servicios.planta import _paso_referencia


def _ins(*pasos: tuple[str, bool]) -> SimpleNamespace:
    return SimpleNamespace(pasos=[SimpleNamespace(orden=i + 1, titulo=t, imagen_ruta=f"p{i + 1}.png" if img else None)
                                  for i, (t, img) in enumerate(pasos)])


def test_salta_el_registro_final():
    """IT-023 termina en «Registrar y etiquetar el conjunto», cuya imagen es un esquema del registro:
    la pieza terminada es la de la inspección visual final."""
    ins = _ins(("Apretar los 4 tornillos en cruz a 25 N·m", True), ("Inspección visual final", True),
               ("Registrar y etiquetar el conjunto", True))
    assert _paso_referencia(ins).titulo == "Inspección visual final"
    ins = _ins(("Reviso las marcas", True), ("Registro el número de serie", True))
    assert _paso_referencia(ins).titulo == "Reviso las marcas"


def test_ultimo_paso_con_imagen_si_no_es_papeleo():
    ins = _ins(("Fijar el sensor", True), ("Prueba funcional y registro", True), ("Avisar al jefe", False))
    assert _paso_referencia(ins).titulo == "Prueba funcional y registro"


def test_si_solo_hay_papeleo_con_imagen_se_usa_ese():
    ins = _ins(("Preparar", False), ("Registrar los resultados", True))
    assert _paso_referencia(ins).titulo == "Registrar los resultados"
    assert _paso_referencia(_ins(("Preparar", False))) is None
