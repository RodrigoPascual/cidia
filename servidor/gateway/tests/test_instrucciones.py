"""Pruebas de las instrucciones versionadas: borrador, publicación, versiones, diferencias y permisos."""

from __future__ import annotations

import itertools

import pytest
from fabrica import cab
from sqlalchemy import select

from cidia.config import ajustes
from cidia.modelos import Documento, Fragmento, Instruccion, Paso, SentenciaXapi, Tarea
from cidia.seguridad import Actor
from cidia.servicios import instrucciones

_contador = itertools.count(1)

PASOS = [
    {"titulo": "Preparar la brida", "texto": "Limpia la superficie de apoyo con un trapo seco."},
    {"titulo": "Apretar los tornillos", "texto": "Aprieta en cruz a 25 N·m.", "es_critico": True,
     "criterio_aceptacion": "Par comprobado con la llave dinamométrica."},
    {"titulo": "Comprobar fugas", "texto": "Prueba de presión a 6 bar durante un minuto.", "es_seguridad": True},
]

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"
)


def nueva_tarea(bd, planta, dep: str = "prod", nivel: int = 1) -> Tarea:
    """Cada prueba usa su propia tarea (la base de datos se comparte en toda la sesión)."""
    n = next(_contador)
    t = Tarea(puesto_id=planta.puestos[dep].id, codigo=f"IT-T{n:03d}", nombre=f"Tarea de prueba {n}",
              nivel_minimo=nivel)
    bd.add(t)
    bd.commit()
    return t


@pytest.fixture
def ganchos(monkeypatch):
    """Sustituye las llamadas a ILUO, formación y evaluación (otros módulos) y las anota."""
    from cidia.servicios import evaluacion, formacion, iluo

    llamadas: list[tuple[str, int]] = []
    monkeypatch.setattr(iluo, "marcar_reevaluacion", lambda bd, tarea_id: llamadas.append(("iluo", tarea_id)) or 2)
    monkeypatch.setattr(formacion, "encolar_generacion", lambda iid: llamadas.append(("formacion", iid)))
    monkeypatch.setattr(evaluacion, "encolar_generacion", lambda iid: llamadas.append(("evaluacion", iid)))
    return llamadas


def crear(cliente, h, tarea, pasos=PASOS, titulo="Montaje de la brida") -> dict:
    r = cliente.post("/api/instrucciones", headers=h, json={"tarea_id": tarea.id, "titulo": titulo, "pasos": pasos})
    assert r.status_code == 200, r.text
    return r.json()


def test_crear_editar_y_publicar(cliente, bd, planta, ganchos):
    h = cab(cliente, "carmen")
    t = nueva_tarea(bd, planta, "prod", nivel=2)
    d = crear(cliente, h, t)
    assert d["estado"] == "borrador" and d["version"] == 1 and d["codigo"] == t.codigo
    assert d["n_pasos"] == 3 and d["pasos_criticos"] == 1 and d["autor"]["nombre"] == "Carmen Díaz"
    assert d["editable"] is True and d["tarea"]["departamento"] == "Producción"
    ids = [p["id"] for p in d["pasos"]]

    # Reordenar (2 → 1), quitar el tercero, añadir uno nuevo y cambiar marcas.
    pasos = [
        {**d["pasos"][1], "es_seguridad": True},
        {**d["pasos"][0], "texto": "Limpia y seca la superficie."},
        {"titulo": "Etiquetar el conjunto", "texto": "Pon la etiqueta verde."},
    ]
    r = cliente.put(f"/api/instrucciones/{d['id']}", headers=h,
                    json={"resumen": "Montaje de la brida B en la línea 2.", "epis": "Guantes\nGafas", "pasos": pasos})
    assert r.status_code == 200, r.text
    e = r.json()
    assert [p["id"] for p in e["pasos"][:2]] == [ids[1], ids[0]]
    assert [p["orden"] for p in e["pasos"]] == [1, 2, 3]
    assert e["pasos"][0]["es_critico"] and e["pasos"][0]["es_seguridad"]
    assert e["pasos"][1]["texto"] == "Limpia y seca la superficie."
    assert e["pasos"][2]["titulo"] == "Etiquetar el conjunto" and e["n_pasos"] == 3
    bd.expire_all()
    assert bd.get(Paso, ids[2]) is None  # el paso quitado ya no existe

    assert cliente.put(f"/api/instrucciones/{d['id']}", headers=h, json={"titulo": "  "}).status_code == 400
    ajeno = {"id": 999999, "titulo": "Intruso"}
    assert cliente.put(f"/api/instrucciones/{d['id']}", headers=h, json={"pasos": [ajeno]}).status_code == 400
    vacio = [{**e["pasos"][0], "titulo": ""}, *e["pasos"][1:]]
    assert cliente.put(f"/api/instrucciones/{d['id']}", headers=h, json={"pasos": vacio}).status_code == 200
    r = cliente.post(f"/api/instrucciones/{d['id']}/publicar", headers=h)
    assert r.status_code == 400 and "paso 1" in r.json()["detail"]
    cliente.put(f"/api/instrucciones/{d['id']}", headers=h, json={"pasos": e["pasos"]})

    r = cliente.post(f"/api/instrucciones/{d['id']}/publicar", headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["estado"] == "publicada" and p["revisor"]["nombre"] == "Carmen Díaz" and p["publicada_en"]
    assert p["reevaluaciones"] == 2 and p["editable"] is False
    assert ("iluo", t.id) in ganchos and ("formacion", d["id"]) in ganchos and ("evaluacion", d["id"]) in ganchos

    # Indexada en la base de Producción, como material de formación y con el nivel de la tarea.
    bd.expire_all()
    doc = bd.get(Documento, p["documento_id"])
    assert doc.tipo == "instruccion" and doc.estado == "listo" and doc.origen_id == d["id"]
    assert doc.departamento_id == planta.deps["prod"].id and doc.nivel_minimo == 2 and doc.es_formacion
    assert doc.validador_id == planta.personas["carmen"].id
    metas = [f.metadatos for f in bd.scalars(select(Fragmento).where(Fragmento.documento_id == doc.id)).all()]
    assert {m.get("paso_id") for m in metas} >= {x["id"] for x in e["pasos"]}
    assert all(m["instruccion_id"] == d["id"] and m["codigo"] == t.codigo for m in metas)
    assert bd.scalar(select(SentenciaXapi).where(SentenciaXapi.verbo == "publico",
                                                 SentenciaXapi.objeto_id == str(d["id"]))) is not None

    # Una publicada ya no se edita ni se vuelve a publicar.
    assert cliente.put(f"/api/instrucciones/{d['id']}", headers=h, json={"titulo": "Otro"}).status_code == 409
    assert cliente.post(f"/api/instrucciones/{d['id']}/publicar", headers=h).status_code == 409


def test_versiones_obsoletas_y_diferencias(cliente, bd, planta, ganchos):
    h = cab(cliente, "carmen")
    t = nueva_tarea(bd, planta, "prod")
    v1 = crear(cliente, h, t)
    assert cliente.post(f"/api/instrucciones/{v1['id']}/publicar", headers=h).status_code == 200
    # No se puede empezar otra a mano: se parte de la publicada.
    r = cliente.post("/api/instrucciones", headers=h, json={"tarea_id": t.id, "titulo": "Otra"})
    assert r.status_code == 409

    r = cliente.post(f"/api/instrucciones/{v1['id']}/nueva-version", headers=h)
    assert r.status_code == 200, r.text
    v2 = r.json()
    assert v2["version"] == 2 and v2["estado"] == "borrador" and v2["ya_existia"] is False
    assert [p["titulo"] for p in v2["pasos"]] == [p["titulo"] for p in PASOS]
    assert v2["vigente"] == {"id": v1["id"], "version": 1}
    # Si ya hay un borrador, se devuelve ese en vez de crear otro.
    otra = cliente.post(f"/api/instrucciones/{v1['id']}/nueva-version", headers=h).json()
    assert otra["id"] == v2["id"] and otra["ya_existia"] is True
    assert cliente.get(f"/api/instrucciones/{v1['id']}", headers=h).json()["borrador_existente"]["id"] == v2["id"]

    pasos = [
        v2["pasos"][0],
        {**v2["pasos"][1], "texto": "Aprieta en cruz a 30 N·m."},
        {"titulo": "Etiquetar el conjunto", "texto": "Etiqueta verde."},
    ]
    assert cliente.put(f"/api/instrucciones/{v2['id']}", headers=h, json={"pasos": pasos}).status_code == 200
    dif = cliente.get(f"/api/instrucciones/{v2['id']}/diferencias", headers=h).json()
    assert dif["de"]["version"] == 1 and dif["a"]["version"] == 2 and not dif["sin_cambios"]
    tipos = {(c["tipo"], c["titulo"]) for c in dif["pasos"]}
    assert ("modificado", "Apretar los tornillos") in tipos
    assert ("eliminado", "Comprobar fugas") in tipos and ("nuevo", "Etiquetar el conjunto") in tipos
    mod = next(c for c in dif["pasos"] if c["tipo"] == "modificado")
    assert mod["campos"][0]["campo"] == "texto" and mod["campos"][0]["despues"] == "Aprieta en cruz a 30 N·m."

    r = cliente.post(f"/api/instrucciones/{v2['id']}/publicar", headers=h)
    assert r.status_code == 200, r.text
    bd.expire_all()
    viejo = bd.get(Instruccion, v1["id"])
    assert viejo.estado == "obsoleta"
    doc_viejo = bd.get(Documento, viejo.documento_id)
    assert doc_viejo.estado == "obsoleto"  # deja de encontrarse
    assert not bd.scalars(select(Fragmento).where(Fragmento.documento_id == doc_viejo.id)).all()
    assert bd.get(Documento, r.json()["documento_id"]).estado == "listo"

    versiones = cliente.get(f"/api/instrucciones/{v2['id']}/versiones", headers=h).json()
    assert [(v["version"], v["estado"]) for v in versiones] == [(2, "publicada"), (1, "obsoleta")]
    assert versiones[0]["actual"] is True
    # Una obsoleta no se publica de nuevo; sí se puede comparar.
    assert cliente.post(f"/api/instrucciones/{v1['id']}/publicar", headers=h).status_code == 409
    inv = cliente.get(f"/api/instrucciones/{v1['id']}/diferencias?con={v2['id']}", headers=h).json()
    assert inv["de"]["version"] == 1 and inv["a"]["version"] == 2


def test_movido_en_diferencias(cliente, bd, planta, ganchos):
    h = cab(cliente, "carmen")
    t = nueva_tarea(bd, planta, "prod")
    v1 = crear(cliente, h, t)
    cliente.post(f"/api/instrucciones/{v1['id']}/publicar", headers=h)
    v2 = cliente.post(f"/api/instrucciones/{v1['id']}/nueva-version", headers=h).json()
    a, b, c = v2["pasos"]
    cliente.put(f"/api/instrucciones/{v2['id']}", headers=h, json={"pasos": [c, a, b]})
    dif = cliente.get(f"/api/instrucciones/{v2['id']}/diferencias", headers=h).json()
    movido = [x for x in dif["pasos"] if x["tipo"] == "movido"]
    assert movido and movido[0]["titulo"] == "Comprobar fugas" and movido[0]["orden_antes"] == 3
    assert movido[0]["orden_despues"] == 1


def test_imagen_de_un_paso(cliente, bd, planta):
    h = cab(cliente, "carmen")
    d = crear(cliente, h, nueva_tarea(bd, planta, "prod"))
    paso = d["pasos"][0]
    r = cliente.post(f"/api/instrucciones/{d['id']}/pasos/{paso['id']}/imagen", headers=h,
                     files={"fichero": ("foto.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    url = r.json()["pasos"][0]["imagen_url"]
    assert url and cliente.get(url).content == PNG
    bd.expire_all()
    assert (ajustes().dir_datos / bd.get(Paso, paso["id"]).imagen_ruta).exists()
    r = cliente.post(f"/api/instrucciones/{d['id']}/pasos/{paso['id']}/imagen", headers=h,
                     files={"fichero": ("notas.txt", b"hola", "text/plain")})
    assert r.status_code == 400
    otro = crear(cliente, h, nueva_tarea(bd, planta, "prod"))
    r = cliente.post(f"/api/instrucciones/{d['id']}/pasos/{otro['pasos'][0]['id']}/imagen", headers=h,
                     files={"fichero": ("foto.png", PNG, "image/png")})
    assert r.status_code == 404
    # Con extensión de imagen pero sin serlo (p. ej., una página web): se rechaza y no queda nada.
    antes = set((ajustes().dir_datos / "instrucciones").iterdir())
    r = cliente.post(f"/api/instrucciones/{d['id']}/pasos/{paso['id']}/imagen", headers=h,
                     files={"fichero": ("foto.png", b"<html><script>alert(1)</script></html>", "image/png")})
    assert r.status_code == 400 and "no es una imagen" in r.json()["detail"]
    assert set((ajustes().dir_datos / "instrucciones").iterdir()) == antes
    # Al cambiar una imagen subida a mano, la anterior (que ya no usa nadie) se borra.
    bd.expire_all()
    primera = ajustes().dir_datos / bd.get(Paso, paso["id"]).imagen_ruta
    r = cliente.post(f"/api/instrucciones/{d['id']}/pasos/{paso['id']}/imagen", headers=h,
                     files={"fichero": ("otra.png", PNG, "image/png")})
    assert r.status_code == 200 and not primera.exists() and not primera.parent.exists()


def test_imagen_demasiado_grande_no_llega_al_disco(cliente, bd, planta):
    h = cab(cliente, "carmen")
    d = crear(cliente, h, nueva_tarea(bd, planta, "prod"))
    carpeta = ajustes().dir_datos / "instrucciones"
    carpeta.mkdir(parents=True, exist_ok=True)
    antes = set(carpeta.iterdir())
    grande = PNG + b"\0" * (instrucciones.MAX_IMAGEN + 1)
    r = cliente.post(f"/api/instrucciones/{d['id']}/pasos/{d['pasos'][0]['id']}/imagen", headers=h,
                     files={"fichero": ("foto.png", grande, "image/png")})
    assert r.status_code == 413 and "15 MB" in r.json()["detail"]
    assert set(carpeta.iterdir()) == antes


def test_publicar_aunque_falle_iluo(cliente, bd, planta, monkeypatch):
    """Si marcar la reevaluación falla dentro de la BD, la publicación sigue (punto de guardado)."""
    from sqlalchemy import text

    from cidia.servicios import evaluacion, formacion, iluo

    monkeypatch.setattr(iluo, "marcar_reevaluacion", lambda bd, tarea_id: bd.execute(text("SELECT * FROM no_existe")))
    monkeypatch.setattr(formacion, "encolar_generacion", lambda iid: None)
    monkeypatch.setattr(evaluacion, "encolar_generacion", lambda iid: None)
    h = cab(cliente, "carmen")
    d = crear(cliente, h, nueva_tarea(bd, planta, "prod"))
    r = cliente.post(f"/api/instrucciones/{d['id']}/publicar", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "publicada" and r.json()["reevaluaciones"] == 0


def test_borrar_borrador(cliente, bd, planta, ganchos):
    h = cab(cliente, "carmen")
    d = crear(cliente, h, nueva_tarea(bd, planta, "prod"))
    assert cliente.post("/api/instrucciones", headers=h, json={"tarea_id": d["tarea_id"]}).status_code == 409
    assert cliente.delete(f"/api/instrucciones/{d['id']}", headers=h).status_code == 200
    assert cliente.get(f"/api/instrucciones/{d['id']}", headers=h).status_code == 404
    p = crear(cliente, h, nueva_tarea(bd, planta, "prod"))
    cliente.post(f"/api/instrucciones/{p['id']}/publicar", headers=h)
    assert cliente.delete(f"/api/instrucciones/{p['id']}", headers=h).status_code == 409


def test_listados_y_tareas(cliente, bd, planta):
    t_prod = nueva_tarea(bd, planta, "prod")
    t_ot = nueva_tarea(bd, planta, "ot")
    d_prod = crear(cliente, cab(cliente, "carmen"), t_prod)
    d_ot = crear(cliente, cab(cliente, "ana"), t_ot)

    lista = cliente.get("/api/instrucciones", headers=cab(cliente, "carmen")).json()
    ids = {i["id"] for i in lista}
    assert d_prod["id"] in ids and d_ot["id"] not in ids
    assert "pasos" not in lista[0] and lista[0]["n_pasos"] >= 1
    filtrada = cliente.get(f"/api/instrucciones?tarea_id={t_prod.id}&estado=borrador",
                           headers=cab(cliente, "carmen")).json()
    assert [i["id"] for i in filtrada] == [d_prod["id"]]
    buscada = cliente.get("/api/instrucciones?q=brida", headers=cab(cliente, "carmen")).json()
    assert d_prod["id"] in {i["id"] for i in buscada}
    todas = {i["id"] for i in cliente.get("/api/instrucciones", headers=cab(cliente, "admin")).json()}
    assert {d_prod["id"], d_ot["id"]} <= todas

    tareas = cliente.get("/api/instrucciones/tareas", headers=cab(cliente, "carmen")).json()
    deps = {t["departamento"] for t in tareas}
    assert deps == {"Producción"}
    mia = next(t for t in tareas if t["id"] == t_prod.id)
    assert mia["borrador"]["id"] == d_prod["id"] and mia["publicada"] is None
    assert {t["departamento"] for t in cliente.get("/api/instrucciones/tareas", headers=cab(cliente, "admin")).json()} \
        >= {"Producción", "Oficina técnica"}

    # Contador de borradores para la barra lateral: solo los de su departamento.
    def actor(u: str) -> Actor:
        return Actor(sesion=None, usuario=planta.personas[u])  # type: ignore[arg-type]

    bd.expire_all()
    pendientes = instrucciones.contar_borradores(bd, actor("carmen"))
    assert pendientes >= 1 and instrucciones.contar_borradores(bd, actor("javier")) == pendientes
    assert instrucciones.contar_borradores(bd, actor("pedro")) == 0
    assert instrucciones.contar_borradores(bd, actor("admin")) >= pendientes + 1


def test_permisos_instrucciones(cliente, bd, planta, ganchos):
    t_prod = nueva_tarea(bd, planta, "prod")
    t_ot = nueva_tarea(bd, planta, "ot")
    d = crear(cliente, cab(cliente, "carmen"), t_prod)

    # Empleados sin la marca de experto: nada.
    for persona in ("luis", "pedro"):
        h = cab(cliente, persona)
        assert cliente.get("/api/instrucciones", headers=h).status_code == 403
        assert cliente.get(f"/api/instrucciones/{d['id']}", headers=h).status_code == 403
        assert cliente.post("/api/instrucciones", headers=h, json={"tarea_id": t_prod.id}).status_code == 403
        assert cliente.post(f"/api/instrucciones/{d['id']}/publicar", headers=h).status_code == 403
    assert cliente.get("/api/instrucciones", headers=cab(cliente, "invitado")).status_code in (401, 403)
    assert cliente.get("/api/instrucciones").status_code == 401

    # Experta de Producción con una tarea de Oficina técnica.
    hc = cab(cliente, "carmen")
    r = cliente.post("/api/instrucciones", headers=hc, json={"tarea_id": t_ot.id, "titulo": "X"})
    assert r.status_code == 403
    # Jefa experta de Oficina técnica con una instrucción de Producción.
    ha = cab(cliente, "ana")
    for metodo, ruta in (("get", ""), ("get", "/versiones"), ("get", "/diferencias"), ("post", "/publicar"),
                         ("post", "/nueva-version"), ("delete", "")):
        assert getattr(cliente, metodo)(f"/api/instrucciones/{d['id']}{ruta}", headers=ha).status_code == 403, ruta
    assert cliente.put(f"/api/instrucciones/{d['id']}", headers=ha, json={"titulo": "Mío"}).status_code == 403
    paso = d["pasos"][0]["id"]
    r = cliente.post(f"/api/instrucciones/{d['id']}/pasos/{paso}/imagen", headers=ha,
                     files={"fichero": ("foto.png", PNG, "image/png")})
    assert r.status_code == 403

    # El jefe de Producción sí puede publicar el borrador de su experta (y queda como revisor).
    r = cliente.post(f"/api/instrucciones/{d['id']}/publicar", headers=cab(cliente, "javier"))
    assert r.status_code == 200 and r.json()["revisor"]["nombre"] == "Javier Martín"
    assert r.json()["autor"]["nombre"] == "Carmen Díaz"
