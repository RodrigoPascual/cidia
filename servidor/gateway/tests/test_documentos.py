"""Consola de documentos: alta (texto y PDF), listados con permisos, edición de etiquetas,
reindexado, borrado, descarga y la consola de depuración de la búsqueda (motor propio)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fabrica import cab
from sqlalchemy import select

from cidia.config import ajustes
from cidia.conocimiento import motor
from cidia.modelos import Auditoria, Documento, Fragmento, SentenciaXapi, Trabajo
from cidia.permisos import alcance_de
from cidia.seguridad import Actor
from cidia.servicios import documentos


def _unico(prefijo: str) -> str:
    return f"{prefijo} {uuid.uuid4().hex[:8]}"


def _subir(cliente: Any, h: dict[str, str], nombre: str, contenido: bytes | str, **campos: Any):
    if isinstance(contenido, str):
        contenido = contenido.encode("utf-8")
    datos = {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in campos.items()}
    return cliente.post("/api/documentos", headers=h, files={"fichero": (nombre, contenido)}, data=datos)


def pdf_minimo(texto: str) -> bytes:
    """PDF de una página con `texto` (ASCII) en Helvetica, con su tabla xref correcta."""
    flujo = f"BT /F1 14 Tf 72 720 Td ({texto}) Tj ET".encode("latin-1")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida = b"%PDF-1.4\n"
    posiciones = []
    for i, obj in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for p in posiciones:
        salida += b"%010d 00000 n \n" % p
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref)
    return salida


def _titulos(r) -> set[str]:
    return {d["titulo"] for d in r.json()["documentos"]}


# --------------------------------------------------------------------------- alta


def test_subir_texto_se_indexa(cliente, planta):
    h = cab(cliente, "javier")
    titulo = _unico("Atasco en la prensa 3")
    texto = ("Si la prensa 3 se atasca al cambiar de molde, para la máquina.\n\n"
             "Limpia el sensor S4 con aire comprimido y rearma desde el panel.")
    r = _subir(cliente, h, "atasco.txt", texto, titulo=titulo, nivel_minimo=1, descripcion="Solución validada")
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["titulo"] == titulo and d["tipo"] == "texto" and d["estado"] == "listo"
    assert d["departamento"] == "Producción" and d["nivel_minimo"] == 1 and d["nivel_nombre"] == "Operario"
    assert d["fragmentos"] >= 1 and d["puede_editar"] is True
    assert d["subido_por"] == "Javier Martín" and d["descripcion"] == "Solución validada"
    assert d["url_descarga"].endswith("&descargar=1")
    det = cliente.get(f"/api/documentos/{d['id']}", headers=h).json()
    assert det["fragmentos_total"] == d["fragmentos"]
    assert det["fragmentos_muestra"][0]["con_vector"] is True
    assert "sensor S4" in " ".join(f["texto"] for f in det["fragmentos_muestra"])
    assert det["trabajos"][0]["estado"] == "completado"


def test_subir_pdf_conserva_la_pagina(cliente, planta, bd):
    h = cab(cliente, "javier")
    titulo = _unico("Engrase del husillo")
    r = _subir(cliente, h, "engrase.pdf", pdf_minimo("Engrasar el husillo cada 40 horas de uso"),
               titulo=titulo, nivel_minimo=2, es_formacion=True)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["tipo"] == "pdf" and d["estado"] == "listo" and d["es_formacion"] is True
    frags = bd.scalars(select(Fragmento).where(Fragmento.documento_id == d["id"])).all()
    assert frags and frags[0].metadatos.get("pagina") == 1 and "husillo" in frags[0].texto
    assert bd.scalar(select(SentenciaXapi).where(SentenciaXapi.verbo == "subio",
                                                 SentenciaXapi.objeto_id == str(d["id"]))) is not None


def test_error_de_indexado_queda_a_la_vista(cliente, planta):
    h = cab(cliente, "javier")
    r = _subir(cliente, h, "roto.pdf", b"esto no es un PDF", titulo=_unico("PDF roto"))
    assert r.status_code == 201
    assert r.json()["estado"] == "error" and r.json()["mensaje_estado"]


def test_validaciones_de_subida(cliente, planta):
    h = cab(cliente, "javier")
    r = _subir(cliente, h, "programa.exe", b"MZ...")
    assert r.status_code == 400 and "formato" in r.json()["detail"]
    assert _subir(cliente, h, "vacio.txt", b"").status_code == 400
    assert _subir(cliente, h, "nivel.txt", "texto", nivel_minimo=9).status_code == 400
    ha = cab(cliente, "admin")
    r = _subir(cliente, ha, "huerfano.txt", "texto sin departamento")
    assert r.status_code == 400 and "departamento" in r.json()["detail"]
    assert _subir(cliente, ha, "x.txt", "texto", departamento_id=999999).status_code == 400
    # la administración sí puede subir un documento público sin departamento
    r = _subir(cliente, ha, "prl.txt", "Bienvenida y prevención de riesgos", es_publico=True, departamento_id="")
    assert r.status_code == 201 and r.json()["departamento_id"] is None


# --------------------------------------------------------------------------- permisos


def test_empleado_e_invitado_no_pueden(cliente, planta):
    hp = cab(cliente, "pedro")
    assert _subir(cliente, hp, "a.txt", "hola").status_code == 403
    assert cliente.get("/api/documentos", headers=hp).status_code == 403
    assert cliente.get("/api/documentos/opciones", headers=hp).status_code == 403
    assert cliente.post("/api/documentos/probar-busqueda", headers=hp, json={"consulta": "hola"}).status_code == 403
    assert cliente.get("/api/documentos", headers=cab(cliente, "invitado")).status_code == 401
    assert cliente.get("/api/documentos").status_code == 401


def test_permisos_por_departamento(cliente, planta):
    marca = uuid.uuid4().hex[:8]
    ha, hj, hadm = cab(cliente, "ana"), cab(cliente, "javier"), cab(cliente, "admin")
    privado = _subir(cliente, ha, "costes.txt", "Costes del utillaje", titulo=f"Costes {marca}", nivel_minimo=2).json()
    publico = _subir(cliente, ha, "normas.txt", "Normas de la oficina", titulo=f"Normas {marca}", es_publico=True).json()
    prod = _subir(cliente, hj, "linea.txt", "Montaje de la línea 2", titulo=f"Línea {marca}").json()

    # el jefe de producción ve lo suyo y lo público, pero no lo privado de oficina técnica
    assert _titulos(cliente.get("/api/documentos", headers=hj, params={"texto": marca})) == \
        {f"Normas {marca}", f"Línea {marca}"}
    assert _titulos(cliente.get("/api/documentos", headers=hadm, params={"texto": marca})) == \
        {f"Costes {marca}", f"Normas {marca}", f"Línea {marca}"}
    filtro_ot = cliente.get("/api/documentos", headers=hj, params={"texto": marca, "departamento_id": planta.deps["ot"].id})
    assert _titulos(filtro_ot) == {f"Normas {marca}"}

    assert cliente.get(f"/api/documentos/{privado['id']}", headers=hj).status_code == 404
    assert cliente.get(f"/api/documentos/{privado['id']}/descarga", headers=hj).status_code == 404
    det = cliente.get(f"/api/documentos/{publico['id']}", headers=hj)
    assert det.status_code == 200 and det.json()["puede_editar"] is False
    assert cliente.patch(f"/api/documentos/{publico['id']}", headers=hj, json={"titulo": "Mío"}).status_code == 403
    assert cliente.post(f"/api/documentos/{publico['id']}/reindexar", headers=hj).status_code == 403
    assert cliente.delete(f"/api/documentos/{publico['id']}", headers=hj).status_code == 403
    assert cliente.delete(f"/api/documentos/{privado['id']}", headers=hj).status_code == 404
    # ana no puede subir a producción; javier sí puede tocar lo suyo
    r = _subir(cliente, ha, "x.txt", "texto", departamento_id=planta.deps["prod"].id)
    assert r.status_code == 403
    assert cliente.get(f"/api/documentos/{prod['id']}", headers=hj).json()["puede_editar"] is True


def test_filtros_y_paginacion(cliente, planta):
    marca = uuid.uuid4().hex[:8]
    h = cab(cliente, "admin")
    dep = planta.deps["prod"].id
    _subir(cliente, h, "a.txt", "uno", titulo=f"A {marca}", departamento_id=dep, es_formacion=True)
    _subir(cliente, h, "b.txt", "dos", titulo=f"B {marca}", departamento_id=dep, es_publico=True)
    _subir(cliente, h, "c.pdf", pdf_minimo("Tres"), titulo=f"C {marca}", departamento_id=dep)

    def buscar(**params: Any) -> set[str]:
        return _titulos(cliente.get("/api/documentos", headers=h, params={"texto": marca, **params}))

    assert buscar(tipo="pdf") == {f"C {marca}"}
    assert buscar(es_publico="true") == {f"B {marca}"}
    assert buscar(es_formacion="true") == {f"A {marca}"}
    assert buscar(estado="listo") == {f"A {marca}", f"B {marca}", f"C {marca}"}
    pag = cliente.get("/api/documentos", headers=h, params={"texto": marca, "por_pagina": 2}).json()
    assert pag["total"] == 3 and pag["paginas"] == 2 and len(pag["documentos"]) == 2
    assert pag["documentos"][0]["titulo"] == f"C {marca}"  # los más recientes primero
    assert pag["resumen"]["total"] >= 3 and pag["motor"] == "pgvector"
    pag2 = cliente.get("/api/documentos", headers=h, params={"texto": marca, "por_pagina": 2, "pagina": 2}).json()
    assert [d["titulo"] for d in pag2["documentos"]] == [f"A {marca}"]


def test_opciones(cliente, planta):
    o = cliente.get("/api/documentos/opciones", headers=cab(cliente, "javier")).json()
    gestionables = {d["nombre"] for d in o["departamentos"] if d["gestionable"]}
    assert gestionables == {"Producción"} and "personas" not in o
    assert [n["orden"] for n in o["niveles"]][:4] == [1, 2, 3, 4]
    assert o["departamento_propio"] == planta.deps["prod"].id and o["es_admin"] is False
    oa = cliente.get("/api/documentos/opciones", headers=cab(cliente, "admin")).json()
    assert all(d["gestionable"] for d in oa["departamentos"])
    assert "Pedro Ruiz" in {p["nombre"] for p in oa["personas"]}


# --------------------------------------------------------------------------- edición, reindexado y borrado


def test_editar_etiquetas(cliente, planta, bd):
    hj = cab(cliente, "javier")
    texto = "La válvula V7 del circuito hidráulico se purga con la máquina parada."
    d = _subir(cliente, hj, "valvula.txt", texto, titulo=_unico("Purga de la válvula V7")).json()
    r = cliente.patch(f"/api/documentos/{d['id']}", headers=hj,
                      json={"titulo": "Purga de la válvula V7 (revisada)", "nivel_minimo": 3, "es_formacion": True})
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["titulo"] == "Purga de la válvula V7 (revisada)" and e["nivel_minimo"] == 3 and e["es_formacion"]
    audit = bd.scalar(select(Auditoria).where(Auditoria.accion == "documento.editar",
                                              Auditoria.entidad_id == str(d["id"])))
    assert audit is not None and audit.detalle["cambios"]["nivel_minimo"] == [1, 3]
    # el motor propio aplica el nuevo nivel en el SQL: pedro (operario) ya no lo encuentra
    pedro = Actor(sesion=None, usuario=planta.personas["pedro"])  # type: ignore[arg-type]
    assert all(x.documento_id != d["id"] for x in motor().buscar(bd, "purga válvula V7", alcance_de(bd, pedro), 10))
    javier = Actor(sesion=None, usuario=planta.personas["javier"])  # type: ignore[arg-type]
    assert any(x.documento_id == d["id"] for x in motor().buscar(bd, "purga válvula V7", alcance_de(bd, javier), 10))

    assert cliente.patch(f"/api/documentos/{d['id']}", headers=hj, json={"titulo": "  "}).status_code == 400
    assert cliente.patch(f"/api/documentos/{d['id']}", headers=hj, json={"nivel_minimo": 7}).status_code == 400
    r = cliente.patch(f"/api/documentos/{d['id']}", headers=hj, json={"departamento_id": planta.deps["ot"].id})
    assert r.status_code == 403
    ha = cab(cliente, "admin")
    r = cliente.patch(f"/api/documentos/{d['id']}", headers=ha, json={"departamento_id": planta.deps["ot"].id})
    assert r.status_code == 200 and r.json()["departamento"] == "Oficina técnica"
    assert cliente.get(f"/api/documentos/{d['id']}", headers=hj).status_code == 404
    r = cliente.patch(f"/api/documentos/{d['id']}", headers=ha, json={"departamento_id": None})
    assert r.status_code == 400  # sin departamento tiene que ser público
    r = cliente.patch(f"/api/documentos/{d['id']}", headers=ha, json={"departamento_id": None, "es_publico": True})
    assert r.status_code == 200 and r.json()["es_publico"] is True


def test_reindexar(cliente, planta, bd):
    hj = cab(cliente, "javier")
    d = _subir(cliente, hj, "r.txt", "Ajuste del tope mecánico de la prensa 5.", titulo=_unico("Tope")).json()
    r = cliente.post(f"/api/documentos/{d['id']}/reindexar", headers=hj)
    assert r.status_code == 200 and r.json()["estado"] == "listo"
    assert bd.scalar(select(Auditoria).where(Auditoria.accion == "documento.reindexar",
                                             Auditoria.entidad_id == str(d["id"]))) is not None


def test_reindexar_conserva_los_pasos(cliente, planta, bd):
    """Un documento sin fichero (p. ej. una instrucción) mantiene los metadatos de cada paso."""
    doc = documentos.crear_desde_texto(
        bd, _unico("IT-023 Montaje de la brida B"), "Paso 1 y paso 2", tipo="instruccion",
        departamento_id=planta.deps["prod"].id, origen="instruccion", en_segundo_plano=False,
        partes=[("Limpiar el asiento de la brida con un trapo sin pelusa.", {"paso": 1, "paso_id": 101}),
                ("Apretar los tornillos en cruz a 25 Nm.", {"paso": 2, "paso_id": 102})],
    )
    bd.commit()
    r = cliente.post(f"/api/documentos/{doc.id}/reindexar", headers=cab(cliente, "javier"))
    assert r.status_code == 200 and r.json()["estado"] == "listo"
    bd.expire_all()
    metas = [f.metadatos for f in bd.scalars(select(Fragmento).where(Fragmento.documento_id == doc.id)
                                             .order_by(Fragmento.orden)).all()]
    assert [m.get("paso") for m in metas] == [1, 2] and metas[1]["paso_id"] == 102
    assert cliente.get(f"/api/documentos/{doc.id}/descarga", headers=cab(cliente, "javier")).status_code == 404


def test_indexado_interrumpido_se_puede_reindexar(cliente, planta, bd):
    """Un documento que se quedó «procesando» sin trabajo vivo (reinicio del servidor) no bloquea
    la recarga automática ni el reindexado; con un trabajo vivo, reindexar responde 409."""
    hj = cab(cliente, "javier")
    d = _subir(cliente, hj, "corte.txt", "Cambio de la cuchilla de la cortadora C-1.", titulo=_unico("Corte")).json()
    assert d["indexando"] is False and d["interrumpido"] is False
    fila = bd.get(Documento, d["id"])
    fila.estado = "procesando"  # como si se hubiera reiniciado a mitad de indexado
    bd.commit()
    lista = cliente.get("/api/documentos", headers=hj, params={"texto": d["titulo"]}).json()
    assert lista["documentos"][0]["interrumpido"] is True and lista["documentos"][0]["indexando"] is False
    assert lista["resumen"]["procesando"] >= 1 and lista["resumen"]["indexando"] == 0
    r = cliente.post(f"/api/documentos/{d['id']}/reindexar", headers=hj)
    assert r.status_code == 200 and r.json()["estado"] == "listo" and r.json()["interrumpido"] is False

    # con un indexado vivo en la cola: se marca como «indexando» y no se puede reindexar otra vez
    t = Trabajo(tipo="indexar_documento", entidad="documento", entidad_id=d["id"], estado="en_curso")
    bd.add(t)
    fila.estado = "procesando"
    bd.commit()
    try:
        lista = cliente.get("/api/documentos", headers=hj, params={"texto": d["titulo"]}).json()
        assert lista["documentos"][0]["indexando"] is True and lista["resumen"]["indexando"] >= 1
        assert cliente.post(f"/api/documentos/{d['id']}/reindexar", headers=hj).status_code == 409
        # con el motor propio, cambiar etiquetas o borrar sigue permitido (el filtro es SQL)
        assert cliente.patch(f"/api/documentos/{d['id']}", headers=hj, json={"nivel_minimo": 2}).status_code == 200
    finally:
        t.estado = "completado"
        fila.estado = "listo"
        bd.commit()


def test_ficha_en_borrador_no_se_indexa_desde_documentos(cliente, planta, bd):
    """Una ficha de captura sin publicar se ve en la biblioteca, pero reindexarla la pondría al
    alcance del copiloto sin validar: solo se indexa al publicarla desde Captura."""
    doc = Documento(titulo=_unico("Ficha sin validar"), tipo="ficha", departamento_id=planta.deps["prod"].id,
                    nivel_minimo=1, estado="borrador", contenido_texto="Truco del sensor S4 sin revisar.",
                    origen="captura")
    bd.add(doc)
    bd.commit()
    r = cliente.post(f"/api/documentos/{doc.id}/reindexar", headers=cab(cliente, "javier"))
    assert r.status_code == 409 and "borrador" in r.json()["detail"]
    bd.expire_all()
    assert bd.get(Documento, doc.id).estado == "borrador"
    assert bd.scalar(select(Fragmento).where(Fragmento.documento_id == doc.id)) is None


def test_las_instrucciones_no_se_borran_desde_documentos(cliente, planta, bd):
    """El documento de una instrucción publicada (o sustituida) se gestiona desde Instrucciones:
    borrarlo dejaría la instrucción vigente fuera del copiloto sin forma de volver a indexarla."""
    doc = documentos.crear_desde_texto(
        bd, _unico("IT-099 Engrase"), "Paso 1. Engrasa la guía.", tipo="instruccion",
        departamento_id=planta.deps["prod"].id, origen="instruccion", en_segundo_plano=False,
    )
    bd.commit()
    r = cliente.delete(f"/api/documentos/{doc.id}", headers=cab(cliente, "javier"))
    assert r.status_code == 409 and "Instrucciones" in r.json()["detail"]
    bd.expire_all()
    assert bd.get(Documento, doc.id) is not None


def test_nivel_no_numerico_en_la_subida(cliente, planta):
    r = _subir(cliente, cab(cliente, "javier"), "n.txt", "texto", nivel_minimo="alto")
    assert r.status_code == 400 and "nivel mínimo" in r.json()["detail"]


def test_borrar(cliente, planta, bd):
    hj = cab(cliente, "javier")
    d = _subir(cliente, hj, "borrar.txt", "Documento que se va a borrar.", titulo=_unico("Borrable")).json()
    fila = bd.get(Documento, d["id"])
    ruta = ajustes().dir_datos / fila.ruta_fichero
    assert ruta.is_file()
    assert cliente.delete(f"/api/documentos/{d['id']}", headers=hj).json() == {"ok": True}
    assert cliente.get(f"/api/documentos/{d['id']}", headers=hj).status_code == 404
    assert not ruta.exists()
    bd.expire_all()
    assert bd.get(Documento, d["id"]) is None
    assert bd.scalar(select(Fragmento).where(Fragmento.documento_id == d["id"])) is None
    assert bd.scalar(select(Auditoria).where(Auditoria.accion == "documento.borrar",
                                             Auditoria.entidad_id == str(d["id"]))) is not None


def test_descarga_del_original(cliente, planta):
    hj = cab(cliente, "javier")
    d = _subir(cliente, hj, "original.txt", "Contenido original", titulo=_unico("Original")).json()
    r = cliente.get(f"/api/documentos/{d['id']}/descarga", headers=hj)
    assert r.status_code == 200 and r.json()["nombre_fichero"] == "original.txt"
    f = cliente.get(r.json()["url"])
    assert f.status_code == 200 and f.content == b"Contenido original"
    assert "attachment" in f.headers.get("content-disposition", "")


# --------------------------------------------------------------------------- consola de búsqueda


def test_probar_busqueda(cliente, planta, bd):
    marca = uuid.uuid4().hex[:6]
    hj, ha, hadm = cab(cliente, "javier"), cab(cliente, "ana"), cab(cliente, "admin")
    t_prod = f"Atasco del alimentador {marca}"
    t_jefes = f"Costes del alimentador {marca}"
    t_ot = f"Utillaje del alimentador {marca}"
    _subir(cliente, hj, "a.txt", "Si el alimentador AL-9 se atasca, retira la chapa y limpia el sensor óptico.",
           titulo=t_prod)
    _subir(cliente, hj, "b.txt", "El alimentador AL-9 cuesta 1200 euros de mantenimiento al año.",
           titulo=t_jefes, nivel_minimo=3)
    _subir(cliente, ha, "c.txt", "Utillaje del alimentador AL-9 para la soldadura.", titulo=t_ot, nivel_minimo=1)

    r = cliente.post("/api/documentos/probar-busqueda", headers=hj,
                     json={"consulta": "¿Qué hago si se atasca el alimentador AL-9?", "k": 10})
    assert r.status_code == 200, r.text
    res = r.json()
    titulos = [x["titulo"] for x in res["resultados"]]
    assert t_prod in titulos and t_jefes in titulos and t_ot not in titulos
    primero = res["resultados"][0]
    assert primero["posicion"] == 1 and primero["puntuacion"] > 0 and primero["similitud"] is not None
    assert primero["metadatos"]["tipo"] and res["motor"] == "pgvector" and res["duracion_ms"] >= 0
    assert res["como"]["nombre"] == "Javier Martín"
    assert {"Documentos públicos", "Producción · hasta nivel 3 (Responsable)"} <= {a["texto"] for a in res["alcance"]}

    # la administración puede probar como otra persona: pedro (operario) no ve lo de nivel 3
    r = cliente.post("/api/documentos/probar-busqueda", headers=hadm,
                     json={"consulta": "atasco alimentador AL-9", "como_usuario_id": planta.personas["pedro"].id, "k": 10})
    titulos = [x["titulo"] for x in r.json()["resultados"]]
    assert t_prod in titulos and t_jefes not in titulos and t_ot not in titulos
    assert r.json()["como"]["nombre"] == "Pedro Ruiz"
    assert bd.scalar(select(Auditoria).where(Auditoria.accion == "documentos.probar_busqueda_como",
                                             Auditoria.entidad_id == str(planta.personas["pedro"].id))) is not None
    r = cliente.post("/api/documentos/probar-busqueda", headers=hadm,
                     json={"consulta": "atasco alimentador AL-9", "como_invitado": True})
    assert all(x["es_publico"] for x in r.json()["resultados"])
    assert r.json()["alcance"] == [{"tipo": "publico", "texto": "Documentos públicos"}]

    # un jefe puede buscar como las personas de su departamento (pedro no ve lo de nivel 3)...
    r = cliente.post("/api/documentos/probar-busqueda", headers=hj,
                     json={"consulta": "atasco alimentador AL-9", "como_usuario_id": planta.personas["pedro"].id, "k": 10})
    assert r.status_code == 200, r.text
    titulos = [x["titulo"] for x in r.json()["resultados"]]
    assert t_prod in titulos and t_jefes not in titulos and r.json()["como"]["nombre"] == "Pedro Ruiz"
    # ... pero solo ve lo que él mismo puede ver: marta se forma en Oficina técnica y allí encuentra
    # material que javier, de Producción, no tiene por qué ver
    t_form = f"Formación del alimentador {marca}"
    _subir(cliente, ha, "f.txt", "Guía de formación del alimentador AL-9 para quien empieza.", titulo=t_form,
           es_formacion=True)
    como_marta = {"consulta": "formación alimentador AL-9", "como_usuario_id": planta.personas["marta"].id, "k": 10}
    assert t_form in [x["titulo"] for x in cliente.post("/api/documentos/probar-busqueda", headers=hadm,
                                                         json=como_marta).json()["resultados"]]
    r = cliente.post("/api/documentos/probar-busqueda", headers=hj, json=como_marta)
    assert r.status_code == 200 and t_form not in [x["titulo"] for x in r.json()["resultados"]]
    # no como personas de otro departamento ni como invitado; una pregunta vacía no vale
    opciones = cliente.get("/api/documentos/opciones", headers=hj).json()
    assert {p["usuario"] for p in opciones["personas"]} >= {"pedro", "marta"}
    assert not {p["usuario"] for p in opciones["personas"]} & {"ana", "luis", "javier"}
    for cuerpo in ({"como_usuario_id": planta.personas["luis"].id}, {"como_usuario_id": 999999}, {"como_invitado": True}):
        r = cliente.post("/api/documentos/probar-busqueda", headers=hj, json={"consulta": "atasco", **cuerpo})
        assert r.status_code == 403, cuerpo
    assert cliente.post("/api/documentos/probar-busqueda", headers=hj, json={"consulta": "  "}).status_code == 400
    r = cliente.post("/api/documentos/probar-busqueda", headers=hadm,
                     json={"consulta": "atasco", "como_usuario_id": 999999})
    assert r.status_code == 404


def test_probar_busqueda_errores_del_motor(cliente, planta, monkeypatch):
    """Un modelo caído se explica; un error interno no enseña sus detalles."""
    from cidia.ia.llm import ErrorModelo
    from cidia.rutas import documentos as rutas_documentos

    class Roto:
        nombre = "roto"

        def __init__(self, error: Exception) -> None:
            self.error = error

        def buscar(self, *a: Any, **k: Any):
            raise self.error

    h = cab(cliente, "javier")
    monkeypatch.setattr(rutas_documentos, "motor", lambda: Roto(ErrorModelo("No se puede contactar con el modelo de embeddings")))
    r = cliente.post("/api/documentos/probar-busqueda", headers=h, json={"consulta": "atasco"})
    assert r.status_code == 502 and "modelo de embeddings" in r.json()["detail"]
    monkeypatch.setattr(rutas_documentos, "motor", lambda: Roto(KeyError("columna_secreta")))
    r = cliente.post("/api/documentos/probar-busqueda", headers=h, json={"consulta": "atasco"})
    assert r.status_code == 500 and "columna_secreta" not in r.json()["detail"]


@pytest.mark.ia_real
def test_probar_busqueda_con_modelo_real(cliente, planta):
    """Subida y consola de búsqueda con el modelo de embeddings real (CIDIA_TEST_IA_REAL=1)."""
    h = cab(cliente, "javier")
    titulo = _unico("Cambio de cuchillas de la cizalla")
    texto = ("Para cambiar las cuchillas de la cizalla C-2, bloquea la máquina con candado, "
             "afloja los seis tornillos del portacuchillas y monta las cuchillas nuevas con la marca hacia arriba.")
    d = _subir(cliente, h, "cizalla.txt", texto, titulo=titulo).json()
    assert d["estado"] == "listo", d.get("mensaje_estado")
    r = cliente.post("/api/documentos/probar-busqueda", headers=h,
                     json={"consulta": "¿Cómo se cambian las cuchillas de la cizalla?", "k": 3}).json()
    assert r["resultados"][0]["titulo"] == titulo
    assert r["resultados"][0]["similitud"] >= r["umbral_respaldo"] and r["con_respaldo"] is True
    cliente.delete(f"/api/documentos/{d['id']}", headers=h)
