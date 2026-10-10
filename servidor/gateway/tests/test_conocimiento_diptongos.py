"""Formas con y sin diptongo («aprieta» y «apretar»): raíces, búsqueda de texto y copiloto.

Visto al grabar el vídeo de recorrido: «¿Qué llave uso para apretar los tornillos?» no encontraba respaldo
porque el paso 3 de IT-023 dice «aprieta». Las pruebas usan el texto real de IT-023 de la semilla.
"""

from __future__ import annotations

import pytest
from fabrica import cab
from sqlalchemy import delete, func, select

from cidia.conocimiento.lexico import raiz, sin_diptongo, variante
from cidia.conocimiento.pgvector import MotorPgvector, terminos_texto
from cidia.modelos import Ejecucion, Instruccion, Paso
from cidia.permisos import Alcance
from cidia.semilla_datos.instrucciones import INSTRUCCIONES
from cidia.servicios import documentos
from cidia.servicios.consulta import (
    Preparada, _normal, _tiene_numero, coincidencia_significativa, evidencia, respuesta_extractiva, terminos, unidades,
)
from cidia.servicios.instrucciones import texto_indexable

PREGUNTA_LLAVE = "¿Qué llave uso para apretar los tornillos?"
FRASE_LLAVE = "Con la llave dinamométrica de media pulgada (1/2\"), aprieta en cruz"
IT023 = next(i for i in INSTRUCCIONES if i["codigo"] == "IT-023")


# --------------------------------------------------------------------------- raíces


@pytest.mark.parametrize("formas", [
    ("aprieta", "aprieto", "aprietan", "apretar", "apretados", "apriete"),
    ("cuelga", "cuelgan", "colgar"),
    ("suelta", "sueltan", "soltar"),
    ("prueba", "pruebas", "probar"),
    ("mueve", "mueven", "mover"),
    ("cierra", "cierre", "cerrar"),
    ("comprueba", "comprobar"),
    ("puesto", "puestos"),
])
def test_formas_con_y_sin_diptongo_tienen_la_misma_raiz(formas):
    assert len({raiz(f) for f in formas}) == 1, {f: raiz(f) for f in formas}


def test_lo_que_no_cambia():
    # La «u» que no suena detrás de «q» o «g» no es un diptongo.
    for palabra in ("que", "quiza", "guerra", "sigue", "manguera", "estanqueidad"):
        assert sin_diptongo(palabra) == palabra
    # Las raíces que ya se distinguían siguen distinguiéndose.
    assert raiz("responsable") != raiz("responde") and raiz("plantilla") != raiz("planta")
    # Un infinitivo corto solo se queda en 3 letras si puede diptongar (mover/mueve); «lugar» no.
    assert raiz("lugar") == raiz("lugares") == "lugar" and raiz("medir") == "medir"
    assert raiz("llave") == raiz("llaves") and raiz("tornillo") == raiz("tornillos")
    # Nombres que no se reducen: chocarían con otras palabras frecuentes en planta.
    for con, sin in (("puerta", "porte"), ("puesto", "poste"), ("vuelta", "voltaje"), ("viento", "venta"),
                     ("pies", "pesar")):
        assert raiz(con) != raiz(sin), (con, sin)
        assert variante(con) is None and variante(sin) is None, (con, sin)


def test_variante_para_la_busqueda_de_texto():
    assert variante("apretar") == "aprietar" and variante("aprieta") == "apreta"
    assert variante("Cierra") == "cerra" and variante("cerrar") == "cierrar"
    assert variante("mover") == "muever" and variante("mueve") == "move"
    for sin_variante in ("tornillos", "llave", "presión", "IT-023", "25", "que", "uso", "estanqueidad"):
        assert variante(sin_variante) is None, sin_variante
    assert terminos_texto("¿Qué llave uso para apretar los tornillos de IT-023?") == [
        "Qué", "llave", "uso", "para", "apretar", "los", "tornillos", "de", "IT-023", "aprietar"]


def test_tiene_numero_con_raices_sin_diptongo():
    """«¿Cuántos puestos…?»: lo contado va como raíz («puest», que no se reduce) y el texto dice «puestos». Con
    diptongo, la raíz va sin él («pruebas» → «prob») y cada palabra del texto se mira tal cual y sin él."""
    contado = raiz("puestos")
    assert contado == "puest"
    assert _tiene_numero(_normal("Se hacen tres pruebas de presión"), raiz("pruebas"))
    assert _tiene_numero(_normal("Producción tiene tres puestos: Prensas…"), contado)
    assert _tiene_numero(_normal("Entre veinte o treinta puestos de trabajo"), contado)
    assert _tiene_numero(_normal("Hay 3 series de 10"), raiz("series"))
    assert not _tiene_numero(_normal("Tres turnos y un puesto"), contado)


# --------------------------------------------------------------------------- búsqueda de texto (PostgreSQL)


def test_el_lematizador_de_postgres_no_une_los_diptongos(bd):
    """Por qué hace falta la variante: Snowball da «apriet» para «aprieta» y «apret» para «apretar»."""
    def casa(texto: str, consulta: str) -> bool:
        return bool(bd.scalar(select(func.to_tsvector("spanish", texto).op("@@")(
            func.websearch_to_tsquery("spanish", consulta)))))

    assert not casa("Aprieta en cruz.", "apretar") and not casa("Hay que apretar en cruz.", "aprieta")
    for texto, pregunta in (("Aprieta en cruz.", "apretar"), ("Hay que apretar en cruz.", "aprieta"),
                            ("Cuelga la llave en el panel.", "colgar"), ("Suelta el freno.", "soltar"),
                            ("Prueba la estanqueidad.", "probar"), ("Mueve el carro.", "mover"),
                            ("Cierra la tapa.", "cerrar"), ("Cerrar la tapa.", "cierra")):
        assert casa(texto, " or ".join(terminos_texto(pregunta))), (texto, pregunta)


def test_busqueda_encuentra_la_otra_forma(bd, planta):
    """El motor propio marca coincidencia de texto con la otra forma, sin reindexar nada."""
    doc = documentos.crear_desde_texto(bd, "Fijación del colector", "Aprieta la abrazadera del colector a mano.",
                                       departamento_id=planta.deps["prod"].id, en_segundo_plano=False)
    bd.commit()
    try:
        encontrados = MotorPgvector().buscar(bd, "apretar", Alcance(todo=True), k=5)
        mio = [e for e in encontrados if e.documento_id == doc.id]
        assert mio and mio[0].metadatos["coincidencia_texto"] is True
    finally:
        documentos.borrar(bd, bd.get(type(doc), doc.id))
        bd.commit()


# --------------------------------------------------------------------------- evidencia con IT-023 de la semilla


def _it023() -> Instruccion:
    """IT-023 de la semilla (sin guardar), con sus pasos como los crea la siembra."""
    ins = Instruccion(codigo=IT023["codigo"], titulo=IT023["titulo"], version=IT023["version"],
                      **{k: IT023[k] for k in ("resumen", "riesgos", "epis", "herramientas")})
    ins.pasos = [Paso(orden=n, titulo=p["titulo"], texto=p["texto"], criterio_aceptacion=p.get("criterio"),
                      es_critico=bool(p.get("critico")), es_seguridad=bool(p.get("seguridad")))
                 for n, p in enumerate(IT023["pasos"], start=1)]
    return ins


def _fuentes_y_textos(partes):
    titulo = f"{IT023['codigo']} · {IT023['titulo']} (v{IT023['version']})"
    fuentes = [{"n": n, "documento_id": 1, "titulo": titulo, "codigo": "IT-023", "version": IT023["version"],
                "paso": meta.get("paso"), "similitud": 0.6} for n, (_, meta) in enumerate(partes, start=1)]
    return fuentes, [t for t, _ in partes]


def test_evidencia_de_it023_con_apretar():
    _, partes = texto_indexable(_it023())
    fuentes, textos = _fuentes_y_textos(partes)
    paso3 = next(f["n"] for f in fuentes if f["paso"] == 3)
    # El título del paso hace de apartado de sus frases (los tornillos solo salen en él).
    assert all(a.startswith("Paso 3. Apretar los 4 tornillos") for a, _ in unidades(textos[paso3 - 1])[1:])
    for pregunta in (PREGUNTA_LLAVE, "¿Con qué llave aprieto?", "¿Con qué llave se aprietan los tornillos?"):
        ev = evidencia(fuentes, textos, pregunta, "Metalúrgica Arlanza, S. L.")
        assert ev and ev[0].n == paso3 and ev[0].texto.startswith(FRASE_LLAVE), (pregunta, ev[:1])
    prep = Preparada(pregunta=PREGUNTA_LLAVE, modo="planta", mensajes=[], fuentes=fuentes, con_contexto=True,
                     modelo="m", temperatura=0.2, max_tokens=None, pregunta_terminos=PREGUNTA_LLAVE,
                     evidencia=evidencia(fuentes, textos, PREGUNTA_LLAVE), textos_evidencia={paso3: textos[paso3 - 1]})
    assert respuesta_extractiva(prep) == (
        f"Según «IT-023 · Montaje de la brida B (v1)»: {FRASE_LLAVE}: 1 arriba, 2 abajo, 3 derecha y 4 izquierda "
        f"[{paso3}].")
    # «cierra la tapa» (paso 5) responde a «cerrar la tapa».
    ev = evidencia(fuentes, textos, "¿Hay que cerrar la tapa antes de presurizar?")
    assert ev and "cierra la tapa de protección antes de presurizar" in ev[0].texto


def test_sin_falsos_positivos_en_it023():
    """La normalización no inventa respaldo: lo que IT-023 no dice sigue sin evidencia."""
    _, partes = texto_indexable(_it023())
    fuentes, textos = _fuentes_y_textos(partes)
    for pregunta in ("¿Qué llave uso para apretar la tuerca del sensor?",  # tuerca y sensor no salen en IT-023
                     "¿Cuántas veces se prueba la presión del banco?",  # no da ninguna cantidad de pruebas
                     "¿Se puede mover el colector con la brida puesta?",
                     # Pregunta de la semilla (paso 5): con una sola palabra en la frase, el título del paso
                     # («Hacer la prueba de estanqueidad») no la completa; si no, valdría «La caída de presión
                     # máxima admitida es de 0,05 bar», que no dice a qué presión se hace.
                     "¿A qué presión se hace la prueba?"):
        assert not evidencia(fuentes, textos, pregunta), pregunta
    # A igualdad de palabras, va antes la frase que no necesita el título del paso: «Presenta la brida… los 4
    # tornillos…» (la brida y los tornillos, «apretar» solo en el título) no dice el par.
    ev = evidencia(fuentes, textos, "¿A cuánto se aprietan los tornillos de la brida B?")
    assert ev and ev[0].texto.startswith("Criterio de aceptación: Los 4 tornillos a 25 N·m, apretados en cruz")


def test_coincidencia_significativa_con_diptongo():
    from cidia.conocimiento import Encontrado

    frag = Encontrado(documento_id=1, titulo="Fijación del colector", puntuacion=1.0, similitud=0.1,
                      texto="Aprieta la abrazadera del colector a mano y cuelga la llave en el panel.",
                      metadatos={"coincidencia_texto": True})
    assert coincidencia_significativa(terminos("¿Cómo se debe apretar la abrazadera?"), frag)
    assert coincidencia_significativa(terminos("¿Dónde colgar la llave?"), frag)
    assert not coincidencia_significativa(terminos("¿Qué presión lleva el cilindro?"), frag)


# --------------------------------------------------------------------------- de punta a punta


@pytest.fixture
def it023(bd, planta):
    """IT-023 de la semilla indexada como al publicarla, y una ejecución en curso de Pedro (todo se borra al
    terminar)."""
    tarea = planta.tareas["prod"]
    ins = _it023()
    ins.tarea_id, ins.estado = tarea.id, "publicada"
    bd.add(ins)
    bd.flush()
    texto, partes = texto_indexable(ins)
    doc = documentos.crear_desde_texto(
        bd, titulo=f"{ins.codigo} · {ins.titulo} (v{ins.version})", texto=texto, tipo="instruccion",
        departamento_id=planta.deps["prod"].id, es_formacion=True, origen="instruccion", origen_id=ins.id,
        version=ins.version, partes=partes, en_segundo_plano=False)
    ej = Ejecucion(usuario_id=planta.personas["pedro"].id, tarea_id=tarea.id, instruccion_id=ins.id)
    bd.add(ej)
    bd.commit()
    yield ins, ej
    bd.rollback()
    documentos.borrar(bd, bd.get(type(doc), doc.id))
    bd.execute(delete(Instruccion).where(Instruccion.id == ins.id))  # pasos y ejecuciones caen en cascada
    bd.commit()


@pytest.mark.parametrize("modo", ["normal", "planta"])
def test_la_llave_para_apretar_tiene_respaldo(cliente, it023, ia, modo):
    """La pregunta de la grabación, con el modelo pequeño que dice que no lo sabe: la respuesta se rehace con
    la frase del paso 3 («aprieta»), citada y sin laguna."""
    ins, ej = it023
    ia.respuesta = "SIN_RESPALDO, no lo sabes."
    cuerpo = {"pregunta": PREGUNTA_LLAVE, "modo": modo}
    if modo == "planta":
        cuerpo["contexto"] = {"tarea_id": ej.tarea_id, "ejecucion_id": ej.id,
                              "paso_id": next(p.id for p in ins.pasos if p.orden == 3)}
    d = cliente.post("/api/consulta/simple", json=cuerpo, headers=cab(cliente, "pedro")).json()
    assert FRASE_LLAVE in d["respuesta"] and "no lo sabes" not in d["respuesta"], d["respuesta"]
    assert d["con_respaldo"] is True and d["laguna_id"] is None
    assert [d["fuentes"][n - 1]["paso"] for n in d["citadas"]] == [3]
