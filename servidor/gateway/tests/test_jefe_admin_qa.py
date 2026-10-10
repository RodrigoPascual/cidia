"""Pruebas de los fallos encontrados en la revisión de calidad de la bandeja del jefe y la
administración: niveles con motor externo, búsquedas sin tildes, estado real del sistema y
consultas por fila en las listas (bandeja de aportaciones y empleados)."""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from fabrica import cab
from sqlalchemy import delete, event, select

from cidia.db import motor_bd
from cidia.modelos import Aportacion, Documento, Nivel, Puesto, Usuario
from cidia.rutas import admin as rutas_admin
from cidia.rutas.admin import sin_tildes


@contextmanager
def contar_consultas():
    """Cuenta las sentencias SQL que se ejecutan dentro del bloque."""
    n = {"q": 0}

    def contar(*_a, **_k):
        n["q"] += 1

    motor = motor_bd()
    event.listen(motor, "before_cursor_execute", contar)
    try:
        yield n
    finally:
        event.remove(motor, "before_cursor_execute", contar)


# --------------------------------------------------------------------------- niveles y motor externo


class MotorExternoFalso:
    """Motor externo (como WeKnora) que apunta qué documentos se reetiquetan."""

    externo = True
    nombre = "falso"

    def __init__(self, falla: set[int]):
        self.reetiquetados: list[int] = []
        self.falla = falla

    def reetiquetar(self, bd, doc) -> bool:
        self.reetiquetados.append(doc.id)
        return doc.id not in self.falla


def test_reordenar_niveles_reetiqueta_el_motor_externo(cliente, bd, planta, monkeypatch):
    """Con WeKnora, cada documento lleva la etiqueta de su nivel (n1, n2…): al reordenar, los que
    cambian de número se reetiquetan; si el motor no puede, se reindexan. Antes no se hacía nada y
    las etiquetas quedaban con el número viejo (permisos desfasados en el motor externo)."""
    h = cab(cliente, "admin")
    s = uuid.uuid4().hex[:6]
    dep = planta.deps["prod"].id
    d1 = Documento(titulo=f"N1 {s}", tipo="texto", departamento_id=dep, nivel_minimo=1, estado="listo", motor_id="m1")
    d2 = Documento(titulo=f"N2 {s}", tipo="texto", departamento_id=dep, nivel_minimo=2, estado="listo", motor_id="m2")
    d3 = Documento(titulo=f"N3 {s}", tipo="texto", departamento_id=dep, nivel_minimo=3, estado="listo", motor_id="m3")
    bd.add_all([d1, d2, d3])
    bd.commit()
    falso = MotorExternoFalso(falla={d2.id})
    reindexados: list[int] = []
    monkeypatch.setattr(rutas_admin, "motor", lambda: falso)
    monkeypatch.setattr(rutas_admin.documentos, "reindexar", lambda bd_, doc: reindexados.append(doc.id))

    ids = [n["id"] for n in cliente.get("/api/admin/niveles", headers=h).json()]
    invertido = [ids[1], ids[0]] + ids[2:]
    r = cliente.put("/api/admin/niveles/orden", headers=h, json={"ids": invertido})
    assert r.status_code == 200, r.text
    # Se tocan los documentos de los niveles 1 y 2 (no el del 3, que no cambia de número).
    assert sorted(falso.reetiquetados) == sorted([d1.id, d2.id])
    assert reindexados == [d2.id]
    bd.expire_all()
    assert bd.get(Documento, d1.id).nivel_minimo == 2 and bd.get(Documento, d2.id).nivel_minimo == 1

    # Se deja como estaba (y vuelve a reetiquetar).
    falso.reetiquetados.clear()
    assert cliente.put("/api/admin/niveles/orden", headers=h, json={"ids": ids}).status_code == 200
    assert sorted(falso.reetiquetados) == sorted([d1.id, d2.id])
    bd.execute(delete(Documento).where(Documento.id.in_([d1.id, d2.id, d3.id])))
    bd.commit()


def test_reordenar_niveles_con_motor_propio_no_reindexa(cliente, bd, planta, monkeypatch):
    """El motor propio filtra por SQL: reordenar no lanza ningún reindexado."""
    h = cab(cliente, "admin")
    reindexados: list[int] = []
    monkeypatch.setattr(rutas_admin.documentos, "reindexar", lambda bd_, doc: reindexados.append(doc.id))
    ids = [n["id"] for n in cliente.get("/api/admin/niveles", headers=h).json()]
    assert cliente.put("/api/admin/niveles/orden", headers=h, json={"ids": [ids[1], ids[0]] + ids[2:]}).status_code == 200
    assert cliente.put("/api/admin/niveles/orden", headers=h, json={"ids": ids}).status_code == 200
    assert reindexados == []
    assert [n.id for n in bd.scalars(select(Nivel).order_by(Nivel.orden))] == ids


# --------------------------------------------------------------------------- búsquedas sin tildes


def test_sin_tildes():
    assert sin_tildes("  Logística ÚNICA Peña ") == "logistica unica pena"


def test_buscar_sin_tildes_en_empleados_auditoria_y_registro(cliente, planta):
    """«garcia» encuentra a «Luis García», «logistica» el alta de «Logística…» y «martin» las
    sentencias de Javier Martín. Antes había que escribir las tildes exactas."""
    h = cab(cliente, "admin")
    cab(cliente, "javier")  # deja su sentencia xAPI de inicio de sesión
    r = cliente.get("/api/admin/empleados", headers=h, params={"texto": "GARCIA"})
    assert [e["usuario"] for e in r.json()["empleados"]] == ["luis"]

    nombre = f"Logística {uuid.uuid4().hex[:5]}"
    assert cliente.post("/api/admin/departamentos", headers=h, json={"nombre": nombre}).status_code == 200
    r = cliente.get("/api/admin/auditoria", headers=h, params={"texto": sin_tildes(nombre)})
    assert r.status_code == 200 and any(nombre in f["texto"] for f in r.json()["filas"])
    r = cliente.get("/api/admin/auditoria", headers=h, params={"usuario": "administracion"})
    assert r.json()["total"] >= 1

    r = cliente.get("/api/admin/xapi", headers=h, params={"actor": "martin"})
    assert r.status_code == 200 and r.json()["total"] >= 1
    assert all(s["actor_nombre"] == "Javier Martín" for s in r.json()["sentencias"])
    r = cliente.get("/api/admin/xapi", headers=h, params={"objeto": "sesion"})
    assert r.json()["total"] >= 1


# --------------------------------------------------------------------------- estado real del sistema


def test_estado_del_sistema_comprueba_los_modelos_en_uso(cliente, planta, monkeypatch):
    """El estado cruza los modelos que CidIA usa con los descargados: si falta el de chat, el
    servicio de modelos tiene problemas aunque el servidor de modelos responda. Incluye el motor
    (pgvector y fragmentos), el espacio de trabajo (opcional) y la cola de trabajos."""
    from cidia.ia import asr, llm

    h = cab(cliente, "admin")
    monkeypatch.setattr(asr, "salud", lambda: {"ok": True})
    chat = llm.modelo_permitido(None, "chat")
    embeddings = llm.modelo_permitido(None, "embeddings")
    monkeypatch.setattr(llm, "salud", lambda: {"ok": True, "modelos": [chat, embeddings]})
    r = cliente.get("/api/sistema/estado", headers=h)
    assert r.status_code == 200, r.text
    e = r.json()
    s = e["servicios"]
    assert s["modelos"]["ok"] and s["modelos"]["en_uso"]["chat"] == chat and "chat" not in s["modelos"]["faltan"]
    assert all(isinstance(s[k].get("ms"), int) for k in ("base_datos", "modelos", "voz", "conocimiento"))
    assert s["conocimiento"]["ok"] and s["conocimiento"]["pgvector"] and "fragmentos" in s["conocimiento"]
    assert "configurado" in s["espacio"] and (s["espacio"]["configurado"] or s["espacio"]["ok"])
    assert set(e["cola"]) == {"pendientes", "en_curso", "errores_24h"}

    # Sin el modelo de chat descargado, CidIA no puede responder: el servicio sale con problemas.
    monkeypatch.setattr(llm, "salud", lambda: {"ok": True, "modelos": [embeddings]})
    s = cliente.get("/api/sistema/estado", headers=h).json()["servicios"]
    assert not s["modelos"]["ok"] and s["modelos"]["faltan"]["chat"] == chat and "chat" in s["modelos"]["error"]

    # Si el servidor de modelos no responde, se dice con su error.
    monkeypatch.setattr(llm, "salud", lambda: {"ok": False, "error": "conexión rechazada"})
    s = cliente.get("/api/sistema/estado", headers=h).json()["servicios"]
    assert not s["modelos"]["ok"] and s["modelos"]["error"] == "conexión rechazada"

    # Solo la administración ve el estado.
    assert cliente.get("/api/sistema/estado", headers=cab(cliente, "javier")).status_code == 403


# --------------------------------------------------------------------------- consultas por fila


def test_listado_de_empleados_sin_consultas_por_persona(cliente, bd, planta):
    """Departamento, nivel y puesto se cargan de una vez: añadir personas no añade consultas."""
    h = cab(cliente, "admin")
    with contar_consultas() as antes:
        assert cliente.get("/api/admin/empleados", headers=h).status_code == 200
    s = uuid.uuid4().hex[:6]
    # Cada persona nueva en un puesto distinto: sin la carga conjunta, serían 6 consultas más.
    puestos = [Puesto(departamento_id=planta.deps["ot"].id, nombre=f"Puesto {i} {s}") for i in range(6)]
    bd.add_all(puestos)
    bd.flush()
    nuevos = [Usuario(usuario=f"extra{i}.{s}", nombre=f"Extra {i} {s}", rol="empleado",
                      departamento_id=planta.deps["ot"].id, nivel_id=planta.niveles[2].id,
                      puesto_id=p.id) for i, p in enumerate(puestos)]
    bd.add_all(nuevos)
    bd.commit()
    try:
        with contar_consultas() as despues:
            r = cliente.get("/api/admin/empleados", headers=h)
        assert r.status_code == 200 and r.json()["total"] >= 13
        de_los_nuevos = {e["puesto"]["nombre"] for e in r.json()["empleados"] if e["usuario"].startswith("extra")}
        assert de_los_nuevos == {p.nombre for p in puestos}
        assert despues["q"] <= antes["q"], (antes, despues)
    finally:
        bd.execute(delete(Usuario).where(Usuario.id.in_([u.id for u in nuevos])))
        bd.execute(delete(Puesto).where(Puesto.id.in_([p.id for p in puestos])))
        bd.commit()


@pytest.fixture
def sin_aportaciones(app, bd):
    bd.execute(delete(Aportacion))
    bd.commit()
    yield
    bd.execute(delete(Aportacion))
    bd.commit()


def _pendiente(planta, autor: str, n: int) -> Aportacion:
    return Aportacion(autor_id=planta.personas[autor].id, departamento_id=planta.deps["prod"].id, estado="pendiente",
                      titulo=f"Aportación {n}", problema="Algo pasaba", solucion="Hacer esto", etiquetas=["x"],
                      nivel_minimo=1, texto_original="Algo pasaba y lo resolví haciendo esto.")


def test_bandeja_del_jefe_sin_consultas_por_tarjeta(cliente, bd, planta, sin_aportaciones):
    """La bandeja carga autores, puestos y niveles de una vez (antes, tres consultas por tarjeta)."""
    h = cab(cliente, "javier")
    bd.add_all([_pendiente(planta, "pedro", 1), _pendiente(planta, "marta", 2)])
    bd.commit()
    with contar_consultas() as dos:
        r = cliente.get("/api/aportaciones/pendientes", headers=h)
    assert r.status_code == 200 and len(r.json()["aportaciones"]) == 2
    bd.add_all([_pendiente(planta, quien, i) for i, quien in enumerate(["pedro", "marta", "carmen", "pedro"], 3)])
    bd.commit()
    with contar_consultas() as seis:
        r = cliente.get("/api/aportaciones/pendientes", headers=h)
    aps = r.json()["aportaciones"]
    assert len(aps) == 6 and {a["autor"]["nombre"] for a in aps} == {"Pedro Ruiz", "Marta Sanz", "Carmen Díaz"}
    assert all(a["autor"]["nivel"] and a["autor"]["puesto"] for a in aps)
    assert seis["q"] <= dos["q"], (dos, seis)


# --------------------------------------------------------------------------- auditoría legible


def test_auditoria_legible_sin_resumen():
    """Los cambios que se auditan sin «resumen» se leen como frases, no como la clave en bruto
    (antes: «publicar instruccion instruccion #12»)."""
    from cidia.modelos import Auditoria
    from cidia.rutas.admin_registro import texto_auditoria

    def fila(accion, entidad, ident, detalle):
        return Auditoria(accion=accion, entidad=entidad, entidad_id=ident, detalle=detalle)

    assert texto_auditoria(fila("publicar_instruccion", "instruccion", 12, {"tarea_id": 3, "version": 2})) == \
        "Publicó la instrucción #12 (versión 2)"
    assert texto_auditoria(fila("documento.borrar", "documento", 7, {"titulo": "Manual de la prensa"})) == \
        "Borró el documento «Manual de la prensa»"
    assert texto_auditoria(fila("rechazar_aportacion", "aportacion", 4, {"motivo": "Falta la causa"})) == \
        "Rechazó la aportación #4. Motivo: Falta la causa"
    assert texto_auditoria(fila("ajustar_nivel_iluo", "iluo", "5-9",
                                {"usuario": "Pedro Ruiz", "tarea": "Brida B", "de": "I", "a": "L"})) == \
        "Ajustó el nivel ILUO de Pedro Ruiz en «Brida B»: I → L"
    # Con resumen, manda el resumen; sin frase conocida, la acción se lee con espacios.
    assert texto_auditoria(fila("crear_tarea", "tarea", 1, {"resumen": "Creó la tarea «X»"})) == "Creó la tarea «X»"
    assert texto_auditoria(fila("cambiar_algo", "cosa", None, None)) == "Cambiar algo"


def test_frases_xapi_de_sesion_y_nivel():
    """xAPI legible: «inició sesión» (no «inició Inicio de sesión») y «alcanzó el nivel U en …»
    (antes decía «alcanzó el nivel Montaje de la brida B» sin decir qué nivel)."""
    from cidia.modelos import SentenciaXapi
    from cidia.rutas.admin_registro import frase_sentencia

    sesion = SentenciaXapi(actor_nombre="Marta Sanz", verbo="inicio", objeto_tipo="sesion",
                           objeto_nombre="Inicio de sesión")
    assert frase_sentencia(sesion, "inició") == "Marta Sanz inició sesión"
    nivel = SentenciaXapi(actor_nombre="Pedro Ruiz", verbo="certifico", objeto_tipo="tarea",
                          objeto_nombre="Montaje de la brida B", resultado={"nivel": "U", "success": True})
    assert frase_sentencia(nivel, "alcanzó el nivel") == "Pedro Ruiz alcanzó el nivel U en Montaje de la brida B"
    otra = SentenciaXapi(actor_nombre=None, verbo="completo", objeto_tipo="tarea", objeto_nombre="Brida B")
    assert frase_sentencia(otra, "completó") == "Alguien completó Brida B"
