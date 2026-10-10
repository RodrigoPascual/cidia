"""Textos de la API que la interfaz enseña tal cual: «Mi perfil», errores de indexado y pasos de la formación."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from types import SimpleNamespace

from fabrica import cab
from sqlalchemy import select

from cidia.conocimiento.weknora import ErrorWeKnora
from cidia.ia import asr, llm
from cidia.modelos import Usuario
from cidia.servicios import documentos, formacion
from cidia.servicios.iluo import Evidencias


def test_perfil_dice_si_la_contrasena_se_cambia_en_cidia(cliente, bd, planta):
    h = cab(cliente, "pedro")
    assert cliente.get("/api/auth/yo", headers=h).json()["contrasena_gestionable"] is True
    assert cliente.get("/api/auth/yo", headers=cab(cliente, "invitado")).json().get("contrasena_gestionable") is None

    # Una cuenta del directorio de la empresa: «Mi perfil» no ofrece cambiar la contraseña y la API lo explica.
    pedro = bd.scalar(select(Usuario).where(Usuario.usuario == "pedro"))
    pedro.origen_identidad = "ldap"
    bd.commit()
    try:
        assert cliente.get("/api/auth/yo", headers=h).json()["contrasena_gestionable"] is False
        r = cliente.post("/api/auth/contrasena", headers=h, json={"actual": "lo-que-sea", "nueva": "una frase larga"})
        assert r.status_code == 400 and "directorio de la empresa" in r.json()["detail"]
    finally:
        pedro.origen_identidad = "local"
        bd.commit()


def test_documento_ilegible_explica_el_error_en_castellano(cliente, planta):
    r = cliente.post("/api/documentos", headers=cab(cliente, "javier"),
                     files={"fichero": ("roto.pdf", b"esto no es un PDF")}, data={"titulo": "PDF roto (textos)"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["estado"] == "error"
    assert d["mensaje_estado"].startswith("No se ha podido leer el documento")


def test_motivo_de_error_de_indexado():
    # Los fallos de las librerías que leen ficheros (en inglés, con detalles internos) se explican con una frase.
    generico = documentos.motivo_error(KeyError("/Root"))
    assert generico.startswith("No se ha podido leer el documento") and "Root" not in generico
    assert documentos.motivo_error(ValueError("invalid literal for int()")) == generico
    # Los modelos caídos no enseñan la dirección interna del servidor de modelos.
    texto = documentos.motivo_error(llm.ErrorModelo("No se puede contactar con el modelo: http://10.0.0.5:11434 refused"))
    assert "modelo de IA no está disponible" in texto and "10.0.0.5" not in texto
    assert "servicio de voz" in documentos.motivo_error(asr.ErrorVoz("No se puede contactar con el servicio de voz: x"))
    # Los errores propios de CidIA ya vienen en castellano y se muestran tal cual.
    assert documentos.motivo_error(ErrorWeKnora("WeKnora no ha podido procesar el documento.")) == \
        "WeKnora no ha podido procesar el documento."
    assert documentos.motivo_error(ValueError("Formato no soportado: .xyz")) == "Formato no soportado: .xyz"
    assert documentos.motivo_error(RuntimeError("No hay un modelo con visión permitido.")) == "No hay un modelo con visión permitido."


def test_pasos_de_la_formacion_con_el_vocabulario_de_la_interfaz():
    """La interfaz habla de «tu responsable» y de «una persona experta» (no de «el supervisor» ni «el experto»)."""
    base = {"nivel": 2, "requiere_reevaluacion": False, "caducado": False}
    ins = SimpleNamespace(version=1)
    textos = [
        formacion._siguiente(1, None, base, [], set(), False, False, 0, 3, False)["texto"],
        formacion._siguiente(1, ins, base, [], set(), False, False, 3, 3, False)["texto"],
        formacion._siguiente(1, ins, base, [], set(), True, True, 3, 3, False)["texto"],
        formacion._siguiente(1, ins, {**base, "nivel": 3}, [], set(), True, True, 3, 3, True)["texto"],
    ]
    assert "persona experta" in textos[0] and "persona experta" in textos[1]
    assert textos[2] == "Pide a tu responsable la observación en el puesto."
    assert "responsable" in textos[3]
    requisitos = Evidencias(ventana=datetime.now(timezone.utc), necesarias=3).requisitos()
    todos = textos + [r[k] for r in requisitos for k in ("texto", "falta")]
    assert not [t for t in todos if re.search(r"supervisor|el experto\b", t)]
