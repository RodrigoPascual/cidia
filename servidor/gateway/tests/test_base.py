"""Pruebas de la base: sesión, invitado, permisos y búsqueda híbrida del motor propio."""

from fabrica import CONTRASENA, cab

from cidia.conocimiento import motor
from cidia.permisos import alcance_de
from cidia.seguridad import Actor
from cidia.servicios import documentos


def test_salud(cliente):
    assert cliente.get("/salud").json() == {"estado": "ok"}
    assert cliente.get("/api/sistema/info").json()["producto"] == "CidIA"


def test_login_y_perfil(cliente, planta):
    r = cliente.post("/api/auth/login", json={"usuario": "luis", "contrasena": CONTRASENA})
    assert r.status_code == 200
    perfil = r.json()["perfil"]
    assert perfil["nombre"] == "Luis García"
    assert "departamento" not in perfil  # las etiquetas no se muestran al empleado
    assert "admin" not in perfil["servicios"]
    yo = cliente.get("/api/auth/yo", headers={"Authorization": f"Bearer {r.json()['token']}"}).json()
    assert yo["usuario"] == "luis"


def test_login_incorrecto(cliente, planta):
    r = cliente.post("/api/auth/login", json={"usuario": "luis", "contrasena": "mala"})
    assert r.status_code == 401


def test_invitado_solo_chat(cliente):
    h = cab(cliente, "invitado")
    yo = cliente.get("/api/auth/yo", headers=h).json()
    assert yo["invitado"] is True and yo["servicios"] == ["chat"]


def test_salir_revoca(cliente, planta):
    h = cab(cliente, "pedro")
    assert cliente.post("/api/auth/salir", headers=h).status_code == 200
    assert cliente.get("/api/auth/yo", headers=h).status_code == 401


def _doc(bd, titulo, texto, dep, nivel, formacion=False, publico=False):
    return documentos.crear_desde_texto(
        bd, titulo, texto, departamento_id=dep.id if dep else None, nivel_minimo=nivel,
        es_formacion=formacion, es_publico=publico, en_segundo_plano=False,
    )


def test_matriz_de_permisos(bd, planta):
    """El ejemplo del plan: quién encuentra qué."""
    ot, prod = planta.deps["ot"], planta.deps["prod"]
    docs = {
        "manual": _doc(bd, "Manual de iniciación a Oficina técnica", "utillaje iniciación planos", ot, 1, formacion=True),
        "diseno": _doc(bd, "Procedimiento de diseño de utillajes", "diseño utillajes soldadura", ot, 2),
        "costes": _doc(bd, "Costes y proveedores de utillaje", "costes proveedores utillaje", ot, 3),
        "linea2": _doc(bd, "Instrucción de montaje de la línea 2", "montaje línea brida", prod, 1),
        "prensa": _doc(bd, "Solución validada: atasco en la prensa 3", "prensa atasco sensor S4", prod, 1),
        "prl": _doc(bd, "Bienvenida y PRL", "bienvenida prevención riesgos", None, 1, publico=True),
    }
    bd.commit()
    esperado = {
        "ana": {"manual", "diseno", "costes", "prl"},
        "luis": {"manual", "prl"},
        "marta": {"manual", "linea2", "prensa", "prl"},
        "pedro": {"linea2", "prensa", "prl"},
    }
    from cidia.modelos import Documento
    from cidia.permisos import filtro_documentos, puede_ver
    from sqlalchemy import select

    for persona, visibles in esperado.items():
        u = planta.personas[persona]
        actor = Actor(sesion=None, usuario=u)  # type: ignore[arg-type]
        alc = alcance_de(bd, actor)
        ids = set(bd.scalars(select(Documento.id).where(filtro_documentos(alc))).all())
        nombres = {k for k, d in docs.items() if d.id in ids}
        assert nombres == visibles, (persona, nombres)
        assert {k for k, d in docs.items() if puede_ver(alc, d)} == visibles


def test_busqueda_hibrida_respeta_permisos(bd, planta):
    prod = planta.deps["prod"]
    ot = planta.deps["ot"]
    _doc(bd, "Atasco en la prensa 3", "Si la prensa 3 se atasca al cambiar de molde, limpiar el sensor S4 con aire.", prod, 1)
    _doc(bd, "Costes de utillaje", "Los costes del utillaje IT-101 dependen del proveedor.", ot, 3)
    bd.commit()
    pedro = Actor(sesion=None, usuario=planta.personas["pedro"])  # type: ignore[arg-type]
    res = motor().buscar(bd, "¿Qué hago si se atasca la prensa 3?", alcance_de(bd, pedro), k=5)
    assert res and res[0].titulo == "Atasco en la prensa 3"
    assert all(r.titulo != "Costes de utillaje" for r in res)
    # búsqueda por código exacto
    luis = Actor(sesion=None, usuario=planta.personas["luis"])  # type: ignore[arg-type]
    assert not [r for r in motor().buscar(bd, "IT-101", alcance_de(bd, luis)) if r.titulo == "Costes de utillaje"]
    ana = Actor(sesion=None, usuario=planta.personas["ana"])  # type: ignore[arg-type]
    assert [r for r in motor().buscar(bd, "IT-101", alcance_de(bd, ana)) if r.titulo == "Costes de utillaje"]
