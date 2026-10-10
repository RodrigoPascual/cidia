"""Preparación al arrancar: tablas, valores por defecto, administrador inicial y semilla."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cidia import trabajos
from cidia.config import ajustes
from cidia.db import inicializar_bd, sesion_bd
from cidia.modelos import Empresa, ModeloIA, Nivel, Usuario
from cidia.seguridad import hash_contrasena

log = logging.getLogger("cidia.arranque")

NIVELES_POR_DEFECTO = [
    (1, "Operario", "Ejecuta tareas en el puesto."),
    (2, "Técnico", "Prepara, ajusta y resuelve incidencias."),
    (3, "Responsable", "Responde de un área o un equipo."),
    (4, "Dirección", "Dirige el departamento."),
]

CONFIG_ILUO_POR_DEFECTO = {
    "ejecuciones_para_L": 3,
    "umbral_cuestionario": 0.8,
    "meses_validez": 12,
}

# Ejemplos de modelos en la nube que salen bloqueados en el panel de Modelos.
PROVEEDORES_NUBE = (("OpenAI", "openai"), ("Anthropic Claude", "anthropic"), ("Google Gemini", "google"),
                    ("OpenRouter", "openrouter"))


def valores_por_defecto() -> None:
    with sesion_bd() as bd:
        if bd.scalar(select(func.count(Empresa.id))) == 0:
            bd.add(Empresa(nombre="Mi empresa", config_iluo=CONFIG_ILUO_POR_DEFECTO, config={}))
        if bd.scalar(select(func.count(Nivel.id))) == 0:
            for orden, nombre, desc in NIVELES_POR_DEFECTO:
                bd.add(Nivel(orden=orden, nombre=nombre, descripcion=desc))
        if bd.scalar(select(func.count(ModeloIA.id))) == 0:
            a = ajustes()
            bd.add(ModeloIA(nombre=a.llm_modelo_chat, ref=a.llm_modelo_chat, tipo="chat", permitido=True,
                            predeterminado=True, soporta_vision=a.llm_modelo_vision == a.llm_modelo_chat,
                            descripcion="Modelo de chat configurado en el servidor"))
            bd.add(ModeloIA(nombre=a.llm_modelo_embeddings, ref=a.llm_modelo_embeddings, tipo="embeddings",
                            permitido=True, predeterminado=True, descripcion="Modelo de búsqueda por significado"))
            if a.llm_modelo_vision and a.llm_modelo_vision != a.llm_modelo_chat:
                bd.add(ModeloIA(nombre=a.llm_modelo_vision, ref=a.llm_modelo_vision, tipo="vision", permitido=True,
                                predeterminado=True, soporta_vision=True, descripcion="Modelo con visión"))
            for nombre, prov in PROVEEDORES_NUBE:
                bd.add(ModeloIA(nombre=nombre, ref=prov, tipo="chat", ubicacion="nube", proveedor=prov,
                                permitido=False, descripcion="Modelo en la nube: bloqueado por política de la empresa"))
        # Instalaciones anteriores: la fila de ejemplo de DeepSeek pasa a Anthropic (sin marcas chinas en la interfaz).
        for m in bd.scalars(select(ModeloIA).where(ModeloIA.ubicacion == "nube", ModeloIA.proveedor == "deepseek")):
            if bd.scalar(select(ModeloIA.id).where(ModeloIA.ref == "anthropic", ModeloIA.tipo == m.tipo)):
                bd.delete(m)
            else:
                m.nombre, m.ref, m.proveedor = "Anthropic Claude", "anthropic", "anthropic"
        sincronizar_modelo_busqueda(bd)


def sincronizar_modelo_busqueda(bd: Session) -> None:
    """La fila predeterminada de búsqueda sigue a CIDIA_LLM_MODELO_EMBEDDINGS.

    Los vectores los calcula siempre el modelo de la configuración, y no se guarda con ellos qué
    modelo los hizo. Si la configuración cambia de nombre (por ejemplo, de qwen3-embedding:0.6b a
    qwen3-embedding-cidia:0.6b, el mismo con contexto propio), la fila del anterior pasa a ser la
    del nuevo: así el panel de Modelos lo muestra como el que indexa los documentos.
    """
    ref = ajustes().llm_modelo_embeddings
    filas = bd.scalars(select(ModeloIA).where(ModeloIA.tipo == "embeddings", ModeloIA.ubicacion == "local")).all()
    if not filas:
        return
    actual = next((m for m in filas if m.ref.removesuffix(":latest") == ref.removesuffix(":latest")), None)
    if actual is None:
        actual = next((m for m in filas if m.predeterminado), None)
        if actual is None:
            actual = ModeloIA(nombre=ref, ref=ref, tipo="embeddings", descripcion="Modelo de búsqueda por significado")
            bd.add(actual)
        else:
            log.info("Modelo de búsqueda: «%s» pasa a «%s» (CIDIA_LLM_MODELO_EMBEDDINGS)", actual.ref, ref)
            if actual.nombre == actual.ref:
                actual.nombre = ref
            actual.ref = ref
    actual.permitido = True
    for m in filas:
        m.predeterminado = m is actual
    actual.predeterminado = True


def administrador_inicial() -> None:
    a = ajustes()
    if not a.admin_contrasena:
        return
    with sesion_bd() as bd:
        if bd.scalar(select(func.count(Usuario.id)).where(Usuario.rol == "admin")) > 0:
            return
        nivel = bd.scalar(select(Nivel).order_by(Nivel.orden.desc()))
        bd.add(Usuario(usuario=a.admin_usuario, nombre="Administración", rol="admin",
                       hash_contrasena=hash_contrasena(a.admin_contrasena), nivel_id=nivel.id if nivel else None))
        log.info("Creado el administrador inicial «%s»", a.admin_usuario)


def preparar() -> None:
    inicializar_bd()
    valores_por_defecto()
    administrador_inicial()
    trabajos.marcar_interrumpidos()
    from cidia.servicios.documentos import marcar_interrumpidos as documentos_interrumpidos

    with sesion_bd() as bd:
        documentos_interrumpidos(bd)
    if ajustes().crear_semilla:
        try:
            from cidia.semilla import sembrar_si_vacio

            sembrar_si_vacio()
        except ImportError:
            log.warning("No hay módulo de semilla")
