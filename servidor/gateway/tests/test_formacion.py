"""Pruebas de formación: itinerario, micro-lecciones (LLM falso y JSON roto), vistas, respuestas y permisos."""

from __future__ import annotations

import uuid

import pytest
from fabrica import cab
from sqlalchemy import select
from test_planta import crear_tarea_con_instruccion

from cidia.ia import llm
from cidia.modelos import Microleccion, MicroleccionVista, SentenciaXapi
from cidia.servicios import formacion, iluo

LECCIONES_OK = {
    "microlecciones": [
        {
            "titulo": f"Lección {i}",
            "contenido": contenido,
            "punto_clave": clave,
            "pregunta": {"enunciado": enunciado, "opciones": opciones, "correcta": 0, "explicacion": explicacion},
        }
        for i, (contenido, clave, enunciado, opciones, explicacion) in enumerate([
            ("Antes de empezar revisa la brida y comprueba que tienes los cuatro tornillos M8 sobre el banco.",
             "Comprueba el material antes de empezar.", "¿Cómo se aprietan los tornillos?",
             ["En cruz", "En círculo", "Da igual"], "En cruz para repartir la presión."),
            ("Aprieta los tornillos en cruz con la llave dinamométrica: así la presión se reparte por igual.",
             "Apretar los tornillos en cruz es crítico.", "¿Qué se revisa antes de empezar?",
             ["La brida y los tornillos", "El turno siguiente", "La pintura"],
             "Antes de empezar se revisan la brida y los tornillos."),
            ("Al terminar revisa que la brida no tiene holgura y que todos los tornillos tienen el par correcto.",
             "Sin holgura y con el par correcto.", "¿Con qué se aprieta?",
             ["Con la llave dinamométrica", "Con un martillo", "A mano"],
             "Con la llave dinamométrica, para dar el par correcto."),
        ], start=1)
    ]
}

# Respuesta real de qwen3:0.6b con PASOS_REALES (resumida, con su errata «apertener»): las lecciones
# siguen los pasos, pero repiten la misma frase de relleno, el mismo punto clave y la misma pregunta
# en todas, son cortas y no tratan el paso crítico 4.
_PREGUNTA_REPETIDA = {"enunciado": "¿Qué se debe hacer al apertener los tornillos?", "correcta": 1, "explicacion": "",
                      "opciones": ["Apriete los tornillos en cruz sin retorcerlos", "Apriete los tornillos en cruz con la llave",
                                   "Apriete los tornillos en cruz sin usar la llave"]}
LECCIONES_QWEN = {"microlecciones": [
    {"titulo": titulo, "contenido": f"{propio} Aprende a usar la llave dinamométrica para apertener los tornillos. "
                                    "Por qué es importante usar la llave: para asegurar la precisión.",
     "punto_clave": "Usar la llave para asegurar la precisión.", "pregunta": dict(_PREGUNTA_REPETIDA)}
    for titulo, propio in [
        ("Comprobar EPI y zona de trabajo", "Pon guantes y gafas, retira piezas de otras órdenes."),
        ("Colocar la junta en la brida", "Centra la junta tórica en la ranura de la brida B sin retorcerla."),
        ("Presentar la brida sobre el cuerpo", "Alinea los cuatro taladros de la brida con los del cuerpo."),
        ("Marcar los tornillos", "Marca cada tornillo con rotulador amarillo tras el apriete final."),
        ("Verificar estanqueidad", "Haz la prueba de aire a 2 bar durante 30 segundos."),
    ]
]}

SIETE_PASOS = [{"titulo": f"Paso número {i}", "texto": f"Haz la operación {i}.", "es_critico": i == 4} for i in range(1, 8)]


@pytest.fixture(autouse=True)
def sin_iluo(monkeypatch, app) -> list[tuple[int, int]]:
    """El módulo ILUO es de otro equipo: aquí solo se comprueba que se le llama.

    Depende de `app` para que las tablas existan aunque se ejecute una prueba suelta."""
    llamadas: list[tuple[int, int]] = []
    monkeypatch.setattr(iluo, "recalcular", lambda bd, usuario_id, tarea_id: llamadas.append((usuario_id, tarea_id)))
    return llamadas


def _lecciones(bd, instruccion_id: int) -> list[Microleccion]:
    bd.expire_all()
    return list(bd.scalars(select(Microleccion).where(Microleccion.instruccion_id == instruccion_id)
                           .order_by(Microleccion.orden)))


# --------------------------------------------------------------------------- itinerario


def test_itinerario_con_formacion_activa(cliente, bd, planta):
    t_prod, _ = crear_tarea_con_instruccion(bd, planta, "prod")
    t_sin, _ = crear_tarea_con_instruccion(bd, planta, "prod", publicada=False)
    t_ot, _ = crear_tarea_con_instruccion(bd, planta, "ot")

    r = cliente.get("/api/formacion/itinerario", headers=cab(cliente, "marta"))
    assert r.status_code == 200, r.text
    datos = r.json()
    tareas = {t["tarea_id"]: t for t in datos["tareas"]}
    assert tareas[t_prod.id]["origen"] == "puesto"
    assert tareas[t_ot.id]["origen"] == "formacion"
    assert tareas[t_ot.id]["formacion"]["departamento"] == "Oficina técnica"
    assert tareas[t_ot.id]["departamento"] == "Oficina técnica"
    # Sin instrucción publicada: aparece, pero a la espera.
    assert tareas[t_sin.id]["tiene_instruccion"] is False and tareas[t_sin.id]["siguiente"]["accion"] == "esperar"
    # Con instrucción y sin micro-lecciones ni cuestionario: lo siguiente es practicar.
    item = tareas[t_prod.id]
    assert item["nivel"] == 0 and item["avance"] == 0 and item["instruccion"]["pasos"] == 3
    assert item["siguiente"]["accion"] == "practicar" and item["ejecuciones"]["objetivo"] == 3
    # La formación en otro departamento se destaca aparte.
    formaciones = datos["formaciones"]
    assert len(formaciones) == 1 and formaciones[0]["otro_departamento"] is True
    assert formaciones[0]["departamento"] == "Oficina técnica" and formaciones[0]["tareas"] >= 1
    assert datos["resumen"]["tareas"] == len(datos["tareas"])

    # Luis (Oficina técnica) no ve tareas de Producción.
    luis = {t["tarea_id"] for t in cliente.get("/api/formacion/itinerario", headers=cab(cliente, "luis")).json()["tareas"]}
    assert t_ot.id in luis and t_prod.id not in luis
    assert cliente.get("/api/formacion/itinerario", headers=cab(cliente, "invitado")).status_code == 401


# --------------------------------------------------------------------------- micro-lecciones


def test_microlecciones_con_json_del_modelo(cliente, bd, planta, ia):
    ia.json = LECCIONES_OK
    tarea, ins = crear_tarea_con_instruccion(bd, planta, "prod")
    r = cliente.post(f"/api/formacion/tareas/{tarea.id}/generar", headers=cab(cliente, "carmen"))
    assert r.status_code == 200, r.text
    lecciones = _lecciones(bd, ins.id)
    assert [l.titulo for l in lecciones] == ["Lección 1", "Lección 2", "Lección 3"]
    assert lecciones[0].pregunta["correcta"] == 0 and len(lecciones[0].pregunta["opciones"]) == 3
    # El prompt lleva los pasos y marca los críticos.
    prompt = ia.llamadas[-1]["mensajes"][-1]["content"]
    assert "Apretar los 4 tornillos en cruz [PASO CRÍTICO]" in prompt
    # Auditoría del cambio y trabajo terminado.
    t = cliente.get(f"/api/trabajos/{r.json()['trabajo_id']}", headers=cab(cliente, "carmen")).json()
    assert t["estado"] == "completado" and t["resultado"] == {"microlecciones": 3}

    # Detalle para quien aprende: sin la respuesta correcta.
    h = cab(cliente, "pedro")
    d = cliente.get(f"/api/formacion/tareas/{tarea.id}", headers=h).json()
    assert len(d["lecciones"]) == 3 and "correcta" not in d["lecciones"][0]["pregunta"]
    assert d["instruccion"]["codigo"] == ins.codigo and len(d["instruccion"]["pasos"]) == 3
    assert d["puede_generar"] is False and d["siguiente"]["accion"] == "microleccion"
    assert d["generacion"]["estado"] == "completado"


def test_microlecciones_con_json_roto(bd, planta, ia):
    def roto(mensajes):
        raise llm.ErrorModelo("El modelo no devolvió un JSON válido.")

    ia.json = roto
    _, ins = crear_tarea_con_instruccion(bd, planta, "prod")
    assert formacion.generar_microlecciones(bd, ins.id) == 3
    bd.commit()
    lecciones = _lecciones(bd, ins.id)
    assert [l.titulo for l in lecciones] == [
        "Paso 1: Preparar la brida y los tornillos", "Paso 2: Apretar los 4 tornillos en cruz",
        "Paso 3: Comprobar el montaje",
    ]
    assert "Coloca la brida B" in lecciones[0].contenido
    critica = lecciones[1]
    assert "Paso crítico" in critica.contenido and "25 N·m" in (critica.punto_clave or "")
    p = critica.pregunta
    assert p["enunciado"] == "¿Cuál de estos pasos es crítico?"
    assert p["opciones"][p["correcta"]] == "Apretar los 4 tornillos en cruz" and len(p["opciones"]) == 3
    p0 = lecciones[0].pregunta
    assert p0["opciones"][p0["correcta"]] == "Apretar los 4 tornillos en cruz"  # lo que va después del paso 1


def test_microlecciones_con_json_incompleto_agrupa_pasos(bd, planta, ia):
    # Una sola lección y además mal formada: no llega al mínimo, se generan desde los pasos.
    ia.json = {"microlecciones": [{"titulo": "Corta", "contenido": "Muy corta."}, "texto suelto"]}
    _, ins = crear_tarea_con_instruccion(bd, planta, "prod", pasos=SIETE_PASOS)
    assert formacion.generar_microlecciones(bd, ins.id) == 3
    bd.commit()
    lecciones = _lecciones(bd, ins.id)
    assert [l.titulo for l in lecciones] == [
        "Pasos 1 a 3: Paso número 1", "Pasos 4 a 5: Paso número 4", "Pasos 6 a 7: Paso número 6",
    ]
    assert all(l.pregunta and len(l.pregunta["opciones"]) == 3 for l in lecciones)
    # Regenerar sustituye las anteriores.
    ia.json = LECCIONES_OK
    # El modelo no habla del paso crítico 4: se añade una lección con ese paso.
    assert formacion.generar_microlecciones(bd, ins.id) == 4
    bd.commit()
    assert [l.titulo for l in _lecciones(bd, ins.id)] == ["Lección 1", "Lección 2", "Lección 3", "Paso 4: Paso número 4"]


def test_lecciones_del_modelo_cubren_los_pasos_criticos(bd, planta, ia):
    # El modelo numera los títulos y se olvida del paso crítico: se limpia el título y se añade su lección.
    ia.json = {"microlecciones": [
        {"titulo": f"Micro-lección {i}: Preparación {i}",
         "contenido": "Revisa la brida y coloca los tornillos en su sitio antes de seguir con el montaje.",
         "punto_clave": None, "pregunta": None}
        for i in range(1, 4)
    ]}
    _, ins = crear_tarea_con_instruccion(bd, planta, "prod")
    assert formacion.generar_microlecciones(bd, ins.id) == 4
    bd.commit()
    lecciones = _lecciones(bd, ins.id)
    assert [l.titulo for l in lecciones[:3]] == ["Preparación 1", "Preparación 2", "Preparación 3"]
    assert lecciones[3].titulo == "Paso 2: Apretar los 4 tornillos en cruz"
    assert "25 N·m" in lecciones[3].contenido and lecciones[3].pregunta is not None


def test_nunca_mas_de_seis_lecciones(bd, planta, ia):
    # Seis lecciones del modelo que no hablan de ninguno de los dos pasos críticos: añadir las suyas
    # daría ocho. Mejor el plan B, que reparte todos los pasos (críticos incluidos) en 3-6 lecciones.
    ia.json = {"microlecciones": [
        {"titulo": f"Tema {i}", "contenido": "Prepara el puesto, revisa el material y sigue el orden de la instrucción.",
         "punto_clave": None, "pregunta": None}
        for i in range(1, 7)
    ]}
    pasos = [{"titulo": f"Operación {i}", "texto": f"Haz la operación {i}.", "es_critico": i in (4, 6)} for i in range(1, 8)]
    _, ins = crear_tarea_con_instruccion(bd, planta, "prod", pasos=pasos)
    n = formacion.generar_microlecciones(bd, ins.id)
    bd.commit()
    lecciones = _lecciones(bd, ins.id)
    assert 3 <= n <= 6 and len(lecciones) == n
    assert [l.titulo for l in lecciones] == ["Pasos 1 a 3: Operación 1", "Pasos 4 a 5: Operación 4", "Pasos 6 a 7: Operación 6"]
    texto = " ".join(l.contenido for l in lecciones)
    assert "Operación 4" in texto and "Operación 6" in texto


def test_normalizar_pregunta_tolerante():
    # Opciones como objetos con la correcta marcada.
    p = formacion._normalizar_pregunta({"enunciado": "¿Qué EPI?", "opciones": [
        {"texto": "Gafas"}, {"texto": "Guantes", "correcta": True}, {"texto": "Ninguno"}]})
    assert p and p["opciones"][p["correcta"]] == "Guantes"
    # Letra y más de tres opciones: se conserva la correcta.
    p = formacion._normalizar_pregunta({"enunciado": "¿Cuál?", "opciones": ["a", "b", "c", "d"], "correcta": "D"})
    assert p and len(p["opciones"]) == 3 and p["opciones"][p["correcta"]] == "d"
    # Caso real con qwen3:0.6b: marca una opción y explica otra. Manda la explicación.
    p = formacion._normalizar_pregunta({
        "enunciado": "¿Qué herramienta se usa para apretar los tornillos?",
        "opciones": ["llave dinamométrica", "pulsera", "pulso"], "correcta": 1,
        "explicacion": "La llave dinamometrica se usa para apretar los tornillos en cruz."})
    assert p and p["opciones"][p["correcta"]] == "llave dinamométrica"
    # Si la explicación nombra varias opciones (o ninguna), se respeta la posición marcada.
    p = formacion._normalizar_pregunta({"enunciado": "¿Orden?", "opciones": ["Limpiar", "Montar", "Probar"],
                                        "correcta": 2, "explicacion": "Primero limpiar, luego montar y al final probar."})
    assert p and p["correcta"] == 2
    # Una opción nombrada solo para negarla no cambia la correcta («no en círculo»).
    p = formacion._normalizar_pregunta({
        "enunciado": "¿Cómo se aprietan los tornillos?", "opciones": ["En cruz", "En círculo", "Da igual"],
        "correcta": 0, "explicacion": "No se aprietan en círculo porque la brida se deforma."})
    assert p and p["correcta"] == 0
    # Coincidencias dentro de otra palabra tampoco cuentan («depende» en «independiente»).
    p = formacion._normalizar_pregunta({
        "enunciado": "¿Cuándo se marca?", "opciones": ["Siempre", "Depende", "Nunca"], "correcta": 0,
        "explicacion": "Es independiente del turno: se marca cada vez."})
    assert p and p["correcta"] == 0
    # Las opciones cortas («Sí», «No») no se pueden comprobar con la explicación: manda la posición.
    p = formacion._normalizar_pregunta({
        "enunciado": "¿Hay que confirmar el paso crítico?", "opciones": ["Sí", "No", "Depende del turno"],
        "correcta": 0, "explicacion": "Depende del turno no es correcto: siempre hay que confirmarlo."})
    assert p and p["correcta"] == 0
    # Opciones numeradas por el modelo («A) ...»): la interfaz ya pone la letra. La correcta puede
    # llegar como «B) texto», «b)» o 1.0.
    p = formacion._normalizar_pregunta({"enunciado": "¿Cómo?", "opciones": ["A) En cruz", "B) En círculo", "C) Da igual"],
                                        "correcta": "B) En círculo"})
    assert p and p["opciones"] == ["En cruz", "En círculo", "Da igual"] and p["correcta"] == 1
    p = formacion._normalizar_pregunta({"enunciado": "¿Cómo?", "opciones": ["a. Uno", "b. Dos", "c. Tres"], "correcta": "c)"})
    assert p and p["opciones"] == ["Uno", "Dos", "Tres"] and p["correcta"] == 2
    p = formacion._normalizar_pregunta({"enunciado": "¿Cuál?", "opciones": ["1) Aflojar", "2) Apretar", "3) Marcar"],
                                        "correcta": 1.0})
    assert p and p["opciones"] == ["Aflojar", "Apretar", "Marcar"] and p["correcta"] == 1
    # Lo que parece numeración pero es un dato, o no va en orden, no se toca.
    p = formacion._normalizar_pregunta({"enunciado": "¿Rango?", "opciones": ["1 - 2 bar", "2 - 3 bar", "3 - 4 bar"],
                                        "correcta": 0})
    assert p and p["opciones"] == ["1 - 2 bar", "2 - 3 bar", "3 - 4 bar"]
    p = formacion._normalizar_pregunta({"enunciado": "¿Cómo?", "opciones": ["A mano", "Con llave", "Con martillo"],
                                        "correcta": "A mano"})
    assert p and p["opciones"][0] == "A mano" and p["correcta"] == 0
    p = formacion._normalizar_pregunta({"enunciado": "¿Cómo?", "opciones": ["B) Uno", "A) Dos", "C) Tres"], "correcta": 0})
    assert p and p["opciones"] == ["B) Uno", "A) Dos", "C) Tres"]
    # Sin correcta válida o con opciones repetidas: se descarta.
    assert formacion._normalizar_pregunta({"enunciado": "x", "opciones": ["a", "b", "c"], "correcta": 1.5}) is None
    assert formacion._normalizar_pregunta({"enunciado": "x", "opciones": ["a", "b", "c"], "correcta": 7}) is None
    assert formacion._normalizar_pregunta({"enunciado": "x", "opciones": ["a", "a", "b"], "correcta": 0}) is None
    assert formacion._normalizar_pregunta({"enunciado": "x", "opciones": "a, b, c", "correcta": 0}) is None


def test_lecciones_con_formatos_raros_y_sin_pregunta_valida(bd, planta, ia):
    """Una lección suelta (sin la lista), el contenido como lista de frases y preguntas que no
    valen: se aprovecha lo que hay y cada lección recibe una pregunta de control hecha con los pasos."""
    sueltas = formacion._normalizar_lecciones({"titulo": "Única", "contenido": ["Coloca la brida en el banco.",
                                                                                   "Revisa que estén los cuatro tornillos."]})
    assert len(sueltas) == 1 and sueltas[0]["contenido"].startswith("- Coloca la brida")

    ia.json = {"lecciones": [
        {"titulo": f"Bloque {i}", "contenido": ["Prepara la brida y revisa los tornillos.", "Sigue el orden de la instrucción."],
         "pregunta": {"enunciado": "¿Qué haces?", "opciones": ["Solo una opción"], "correcta": 0}}
        for i in range(1, 4)
    ] + [{"titulo": "Apretar en cruz", "contenido": "Aprieta los 4 tornillos en cruz con la llave dinamométrica "
                                                    "hasta el par que marca la instrucción, sin saltarte ninguno."}]}
    _, ins = crear_tarea_con_instruccion(bd, planta, "prod")
    assert formacion.generar_microlecciones(bd, ins.id) == 4
    bd.commit()
    lecciones = _lecciones(bd, ins.id)
    assert [l.titulo for l in lecciones] == ["Bloque 1", "Bloque 2", "Bloque 3", "Apretar en cruz"]
    titulos = {"Preparar la brida y los tornillos", "Apretar los 4 tornillos en cruz", "Comprobar el montaje"}
    for l in lecciones:
        p = l.pregunta
        assert p and len(p["opciones"]) == 3 and set(p["opciones"]) <= titulos and 0 <= p["correcta"] < 3
    assert len({l.pregunta["enunciado"] for l in lecciones}) >= 2  # no es siempre la misma pregunta


def test_lecciones_repetitivas_de_un_modelo_pequeno(bd, planta, ia):
    """Caso real: se quita el relleno repetido, cada lección tiene su propia pregunta, lo que falta
    lo completa la instrucción (criterio del paso crítico 6) y el paso crítico 4 recibe su lección."""
    ia.json = LECCIONES_QWEN
    _, ins = crear_tarea_con_instruccion(bd, planta, "prod", pasos=PASOS_REALES)
    assert formacion.generar_microlecciones(bd, ins.id) == 6
    bd.commit()
    lecciones = _lecciones(bd, ins.id)
    assert [l.titulo for l in lecciones[:5]] == [m["titulo"] for m in LECCIONES_QWEN["microlecciones"]]
    assert lecciones[5].titulo == "Paso 4: Apretar los 4 tornillos en cruz"
    assert sum("Aprende a usar la llave" in l.contenido for l in lecciones) == 1
    assert sum(1 for l in lecciones[:5] if l.punto_clave) == 1
    assert "Centra la junta tórica" in lecciones[1].contenido  # lo propio de cada lección se queda
    assert "La presión no baja en 30 segundos." in lecciones[4].contenido  # criterio del paso crítico 6
    enunciados = [l.pregunta["enunciado"] for l in lecciones]
    assert len(set(enunciados)) == 6 and all(len(l.pregunta["opciones"]) == 3 for l in lecciones)
    assert lecciones[0].pregunta["enunciado"] == _PREGUNTA_REPETIDA["enunciado"]  # la primera vale


def test_vista_y_pregunta_de_control(cliente, bd, planta, ia, sin_iluo):
    ia.json = LECCIONES_OK
    tarea, ins = crear_tarea_con_instruccion(bd, planta, "prod")
    formacion.generar_microlecciones(bd, ins.id)
    bd.commit()
    lecciones = _lecciones(bd, ins.id)
    h = cab(cliente, "pedro")
    pedro = planta.personas["pedro"]

    r = cliente.post(f"/api/formacion/microlecciones/{lecciones[0].id}/vista", headers=h)
    assert r.status_code == 200 and r.json()["vistas"] == 1 and r.json()["total"] == 3
    assert (pedro.id, tarea.id) in sin_iluo
    # Marcarla otra vez no duplica nada.
    assert cliente.post(f"/api/formacion/microlecciones/{lecciones[0].id}/vista", headers=h).json()["vistas"] == 1
    bd.expire_all()
    assert len(bd.scalars(select(MicroleccionVista).where(MicroleccionVista.usuario_id == pedro.id,
                                                          MicroleccionVista.microleccion_id == lecciones[0].id)).all()) == 1
    vio = bd.scalars(select(SentenciaXapi).where(SentenciaXapi.verbo == "vio", SentenciaXapi.actor_id == pedro.id,
                                                 SentenciaXapi.objeto_id == str(lecciones[0].id))).all()
    assert len(vio) == 1

    # Primer fallo: no se revela la respuesta (ni la explicación, que la delata); segundo: sí.
    url = f"/api/formacion/microlecciones/{lecciones[0].id}/responder"
    mal = cliente.post(url, json={"opcion": 2}, headers=h).json()
    assert mal == {"correcta": False, "opcion_correcta": None, "explicacion": "", "revelada": False}
    mal2 = cliente.post(url, json={"opcion": 1}, headers=h).json()
    assert mal2 == {"correcta": False, "opcion_correcta": 0, "explicacion": "En cruz para repartir la presión.",
                    "revelada": True}
    bien = cliente.post(url, json={"opcion": 0}, headers=h).json()
    assert bien["correcta"] is True and bien["opcion_correcta"] == 0 and bien["explicacion"]
    assert cliente.post(url, json={"opcion": 5}, headers=h).status_code == 400
    # Los fallos de otra persona no cuentan para Marta: a la primera tampoco se le revela.
    otra = cliente.post(url, json={"opcion": 2}, headers=cab(cliente, "marta")).json()
    assert otra["opcion_correcta"] is None
    # Acertar a la primera sí la confirma.
    l2 = f"/api/formacion/microlecciones/{lecciones[1].id}/responder"
    assert cliente.post(l2, json={"opcion": 0}, headers=h).json()["revelada"] is True

    # Avance y siguiente acción tras ver todas las lecciones.
    for l in lecciones[1:]:
        cliente.post(f"/api/formacion/microlecciones/{l.id}/vista", headers=h)
    d = cliente.get(f"/api/formacion/tareas/{tarea.id}", headers=h).json()
    assert all(l["vista"] for l in d["lecciones"])
    assert d["microlecciones"] == {"total": 3, "vistas": 3} and d["avance"] == 25
    assert d["siguiente"]["accion"] == "practicar"


# --------------------------------------------------------------------------- permisos


def test_permisos_de_formacion(cliente, bd, planta, ia):
    ia.json = LECCIONES_OK
    tarea, ins = crear_tarea_con_instruccion(bd, planta, "prod")
    formacion.generar_microlecciones(bd, ins.id)
    bd.commit()
    leccion = _lecciones(bd, ins.id)[0]

    # Luis (Oficina técnica) no ve la tarea ni sus micro-lecciones.
    hl = cab(cliente, "luis")
    assert cliente.get(f"/api/formacion/tareas/{tarea.id}", headers=hl).status_code == 403
    assert cliente.post(f"/api/formacion/microlecciones/{leccion.id}/vista", headers=hl).status_code == 404
    assert cliente.post(f"/api/formacion/microlecciones/{leccion.id}/responder", json={"opcion": 0},
                        headers=hl).status_code == 404
    assert cliente.get("/api/formacion/tareas/999999", headers=hl).status_code == 404
    # Identificadores fuera del rango de la BD: 404, no un error del servidor.
    assert cliente.get(f"/api/formacion/tareas/{2**40}", headers=hl).status_code == 404
    assert cliente.post(f"/api/formacion/microlecciones/{2**40}/vista", headers=hl).status_code == 404

    # Regenerar: solo expertos y jefes del departamento de la tarea.
    url = f"/api/formacion/tareas/{tarea.id}/generar"
    assert cliente.post(url, headers=cab(cliente, "pedro")).status_code == 403  # empleado sin ser experto
    assert cliente.post(url, headers=cab(cliente, "ana")).status_code == 403  # jefa de otro departamento
    assert cliente.post(url, headers=cab(cliente, "javier")).status_code == 200  # jefe de Producción
    assert cliente.get(f"/api/formacion/tareas/{tarea.id}", headers=cab(cliente, "carmen")).json()["puede_generar"] is True
    sin, _ = crear_tarea_con_instruccion(bd, planta, "prod", publicada=False)
    assert cliente.post(f"/api/formacion/tareas/{sin.id}/generar", headers=cab(cliente, "carmen")).status_code == 409
    assert cliente.post(f"/api/formacion/tareas/{tarea.id}/generar", headers=cab(cliente, "invitado")).status_code == 401
    # Lo decide el departamento de la tarea, no el nivel: el jefe (nivel 3) regenera una tarea de nivel 4.
    alta, _ = crear_tarea_con_instruccion(bd, planta, "prod", nivel_minimo=4)
    assert cliente.post(f"/api/formacion/tareas/{alta.id}/generar", headers=cab(cliente, "javier")).status_code == 200
    assert cliente.post(f"/api/formacion/tareas/{alta.id}/generar", headers=cab(cliente, "ana")).status_code == 403
    assert cliente.post(f"/api/formacion/tareas/{2**40}/generar", headers=cab(cliente, "javier")).status_code == 404


def test_itinerario_con_configuracion_iluo_mal_guardada(cliente, bd, planta):
    """Un valor raro en empresa.config_iluo no rompe el itinerario: se usa el de por defecto."""
    from cidia.modelos import Empresa

    empresa = bd.scalar(select(Empresa).order_by(Empresa.id).limit(1))
    if empresa is None:
        empresa = Empresa(nombre="Empresa de pruebas", config_iluo={}, config={})
        bd.add(empresa)
    antes = dict(empresa.config_iluo or {})
    try:
        empresa.config_iluo = {**antes, "ejecuciones_para_L": "muchas"}
        bd.commit()
        r = cliente.get("/api/formacion/itinerario", headers=cab(cliente, "pedro"))
        assert r.status_code == 200, r.text
        assert all(t["ejecuciones"]["objetivo"] == 3 for t in r.json()["tareas"])
        empresa.config_iluo = {**antes, "ejecuciones_para_L": 5}
        bd.commit()
        assert formacion.objetivo_ejecuciones(bd) == 5
    finally:
        empresa.config_iluo = antes
        bd.commit()


def test_itinerario_con_formacion_de_todo_su_departamento(cliente, bd, planta):
    """Una formación sin puesto en su propio departamento (rotación por la sección) mete en el
    itinerario las tareas de los otros puestos del departamento."""
    from fabrica import _hash

    from cidia.modelos import Formacion, Puesto, Tarea, Usuario

    sufijo = uuid.uuid4().hex[:6]
    prod = planta.deps["prod"].id
    puesto = Puesto(departamento_id=prod, nombre=f"Pintura {sufijo}")
    bd.add(puesto)
    bd.flush()
    otra = Tarea(puesto_id=puesto.id, codigo=f"P-{sufijo}", nombre="Pintar la brida", criticidad=2, nivel_minimo=1)
    u = Usuario(usuario=f"rotacion_{sufijo}", nombre="Persona en rotación", hash_contrasena=_hash(), rol="empleado",
                departamento_id=prod, nivel_id=planta.niveles[1].id, puesto_id=planta.puestos["prod"].id)
    bd.add_all([otra, u])
    bd.commit()
    h = cab(cliente, u.usuario)

    def itinerario() -> dict[int, dict]:
        return {t["tarea_id"]: t for t in cliente.get("/api/formacion/itinerario", headers=h).json()["tareas"]}

    assert otra.id not in itinerario()  # otro puesto de su departamento y sin nivel: no es de su itinerario
    bd.add(Formacion(usuario_id=u.id, departamento_id=prod, estado="activa"))
    bd.commit()
    item = itinerario()[otra.id]
    assert item["origen"] == "formacion" and item["formacion"]["departamento"] == "Producción"


def test_pregunta_guardada_con_otra_forma_no_rompe_la_tarea(cliente, bd, planta):
    """Una micro-lección escrita a mano o por otra versión con una pregunta rara no da un error 500:
    la página de la tarea se carga (la lección queda sin pregunta) y responderla da un 400 claro."""
    tarea, ins = crear_tarea_con_instruccion(bd, planta, "prod")
    raras = [
        {"enunciado": "¿Qué?", "opciones": "a, b, c", "correcta": 0},  # opciones como texto
        ["no es un objeto"],
        {"enunciado": "¿Qué?", "opciones": ["Uno", "Dos"], "correcta": "zeta"},  # correcta ilegible
        {"enunciado": "¿Qué?", "opciones": ["Uno", "Dos"], "correcta": 5},  # fuera de rango
        {"opciones": ["Uno", "Dos"], "correcta": 0},  # sin enunciado
    ]
    buena = {"enunciado": "¿Hay que confirmar el paso crítico?", "opciones": ["Sí", "No"], "correcta": "0",
             "explicacion": "Siempre."}
    for i, p in enumerate([*raras, buena], start=1):
        bd.add(Microleccion(instruccion_id=ins.id, orden=i, titulo=f"Lección {i}", contenido="Contenido de la lección.",
                            pregunta=p))
    bd.commit()
    h = cab(cliente, "pedro")
    r = cliente.get(f"/api/formacion/tareas/{tarea.id}", headers=h)
    assert r.status_code == 200, r.text
    lecciones = r.json()["lecciones"]
    assert [l["pregunta"] for l in lecciones[:-1]] == [None] * len(raras)
    assert lecciones[-1]["pregunta"] == {"enunciado": buena["enunciado"], "opciones": ["Sí", "No"]}
    for l in lecciones[:-1]:
        r = cliente.post(f"/api/formacion/microlecciones/{l['id']}/responder", json={"opcion": 0}, headers=h)
        assert r.status_code == 400 and "pregunta de control" in r.json()["detail"]
    r = cliente.post(f"/api/formacion/microlecciones/{lecciones[-1]['id']}/responder", json={"opcion": 0}, headers=h)
    assert r.status_code == 200 and r.json()["correcta"] is True and r.json()["explicacion"] == "Siempre."


def test_microlecciones_de_un_borrador_no_existen(cliente, bd, planta, ia):
    ia.json = LECCIONES_OK
    _, borrador = crear_tarea_con_instruccion(bd, planta, "prod", publicada=False)
    formacion.generar_microlecciones(bd, borrador.id)
    bd.commit()
    leccion = _lecciones(bd, borrador.id)[0]
    h = cab(cliente, "pedro")  # de Producción: la tarea es suya, pero la instrucción aún no se ha publicado
    assert cliente.post(f"/api/formacion/microlecciones/{leccion.id}/vista", headers=h).status_code == 404
    assert cliente.post(f"/api/formacion/microlecciones/{leccion.id}/responder", json={"opcion": 0},
                        headers=h).status_code == 404


def test_error_de_generacion_solo_para_quien_regenera(cliente, bd, planta, monkeypatch):
    def falla(bd_, instruccion_id):
        raise RuntimeError("No se puede contactar con el modelo: http://10.0.0.7:11434")

    monkeypatch.setattr(formacion, "generar_microlecciones", falla)
    tarea, ins = crear_tarea_con_instruccion(bd, planta, "prod")
    assert cliente.post(f"/api/formacion/tareas/{tarea.id}/generar", headers=cab(cliente, "carmen")).status_code == 200
    empleado = cliente.get(f"/api/formacion/tareas/{tarea.id}", headers=cab(cliente, "pedro")).json()
    assert empleado["generacion"]["estado"] == "error" and empleado["generacion"]["mensaje"] is None
    experta = cliente.get(f"/api/formacion/tareas/{tarea.id}", headers=cab(cliente, "carmen")).json()
    assert "10.0.0.7" in experta["generacion"]["mensaje"]


# --------------------------------------------------------------------------- con el modelo real (CIDIA_TEST_IA_REAL=1)

PASOS_REALES = [
    {"titulo": "Comprobar EPI y zona de trabajo", "texto": "Ponte guantes y gafas. Retira de la mesa piezas de otras órdenes."},
    {"titulo": "Colocar la junta en la brida", "texto": "Centra la junta tórica en la ranura de la brida B sin retorcerla."},
    {"titulo": "Presentar la brida sobre el cuerpo", "texto": "Alinea los cuatro taladros de la brida con los del cuerpo."},
    {"titulo": "Apretar los 4 tornillos en cruz", "texto": "Con la llave dinamométrica, aprieta en cruz en dos pasadas.",
     "es_critico": True, "criterio_aceptacion": "Par final de 25 N·m en los cuatro tornillos."},
    {"titulo": "Marcar los tornillos", "texto": "Marca cada tornillo con rotulador amarillo tras el apriete final."},
    {"titulo": "Verificar estanqueidad", "texto": "Prueba de aire a 2 bar durante 30 segundos sin pérdida.",
     "es_critico": True, "criterio_aceptacion": "La presión no baja en 30 segundos."},
]


@pytest.mark.ia_real
def test_microlecciones_con_modelo_real(bd, planta):
    _, ins = crear_tarea_con_instruccion(bd, planta, "prod", pasos=PASOS_REALES)
    n = formacion.generar_microlecciones(bd, ins.id)
    bd.commit()
    lecciones = _lecciones(bd, ins.id)
    for l in lecciones:
        print(f"\n## {l.orden}. {l.titulo}\n{l.contenido}\n> {l.punto_clave}\n? {l.pregunta}")
    assert 3 <= n <= 6 and len(lecciones) == n
    assert all(l.titulo and len(l.contenido.split()) >= 8 for l in lecciones)
    # Los dos pasos críticos aparecen en alguna lección (del modelo o añadida).
    texto = " ".join(f"{l.titulo} {l.contenido} {l.punto_clave or ''}" for l in lecciones)
    assert formacion._menciona(texto, "Apretar los 4 tornillos en cruz")
    assert formacion._menciona(texto, "Verificar estanqueidad")
