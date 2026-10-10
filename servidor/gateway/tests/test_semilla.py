"""Pruebas de la semilla de demostración (Metalúrgica Arlanza, empresa ficticia).

Se siembra una sola vez en la base vacía de esta clave de pruebas (con la IA falsa) y las demás
pruebas reutilizan el resultado. La de `forzar=True` va al final porque vuelve a sembrar.
No usa la fixture `planta`: crearía las mismas personas que la semilla.
"""

from __future__ import annotations

import shutil
from datetime import timedelta

import pytest
from PIL import Image
from sqlalchemy import func, select

from cidia import semilla
from cidia.config import ajustes
from cidia.conocimiento import motor
from cidia.modelos import (
    Aportacion,
    Consulta,
    Departamento,
    Documento,
    Ejecucion,
    EjecucionPaso,
    Empresa,
    Formacion,
    Instruccion,
    IntentoEval,
    Laguna,
    Microleccion,
    MicroleccionVista,
    NivelIluo,
    Observacion,
    Paso,
    PreguntaEval,
    SentenciaXapi,
    Tarea,
    Trabajo,
    Usuario,
    ahora,
)
from cidia.permisos import alcance_de, filtro_documentos, puede_ver
from cidia.semilla_datos import actividad as ACT
from cidia.semilla_datos import documentos as DOCS
from cidia.semilla_datos import instrucciones as INS
from cidia.semilla_datos import organizacion as ORG
from cidia.seguridad import Actor

CONTRASENA = "demo-arlanza-pruebas"
_RESUMEN: dict = {}


@pytest.fixture
def sembrada(app, bd, ia, monkeypatch):
    """Base sembrada una vez por sesión de pruebas (con los modelos falsos de conftest)."""
    monkeypatch.setenv("CIDIA_DEMO_CONTRASENA", CONTRASENA)
    if not _RESUMEN:
        _RESUMEN.update(semilla.sembrar(bd))
    return _RESUMEN


@pytest.fixture
def carpeta(app, request):
    """Carpeta temporal dentro de los datos de esta clave de pruebas."""
    d = ajustes().dir_datos.parent / f"{ajustes().dir_datos.name}_tmp" / request.node.name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _actor(bd, usuario: str) -> Actor:
    u = bd.scalar(select(Usuario).where(Usuario.usuario == usuario))
    return Actor(sesion=None, usuario=u)  # type: ignore[arg-type]


def _contar(bd, modelo, *condiciones) -> int:
    return bd.scalar(select(func.count()).select_from(modelo).where(*condiciones)) or 0


def _recuentos(bd) -> dict[str, int]:
    return {m.__name__: _contar(bd, m) for m in (
        Departamento, Usuario, Tarea, Documento, Instruccion, Paso, Microleccion, PreguntaEval, Laguna, Aportacion,
        Ejecucion, Consulta, IntentoEval, Observacion, NivelIluo, MicroleccionVista, SentenciaXapi)}


# --------------------------------------------------------------------------- recuentos y ficheros


def test_siembra_recuentos(sembrada, bd):
    assert sembrada["sembrado"] is True
    assert CONTRASENA not in str(sembrada)  # el resumen dice dónde está la contraseña, nunca cuál es
    assert sembrada["avisos"] == []
    assert _contar(bd, Departamento) == len(ORG.DEPARTAMENTOS)
    assert _contar(bd, Usuario) == len(ORG.PERSONAS) + 1
    assert _contar(bd, Tarea) == sum(len(p["tareas"]) for p in ORG.PUESTOS)
    # documentos: los de semilla_datos, una instrucción publicada por código y la pregunta frecuente
    assert _contar(bd, Documento, Documento.estado == "listo") == len(DOCS.DOCUMENTOS) + len(INS.INSTRUCCIONES) + 1
    assert _contar(bd, Documento, Documento.estado != "listo") == 0
    assert _contar(bd, Instruccion, Instruccion.estado == "publicada") == len(INS.INSTRUCCIONES)
    assert _contar(bd, Instruccion, Instruccion.estado == "obsoleta") == 1
    assert _contar(bd, Microleccion) == sum(len(d["microlecciones"]) for d in INS.INSTRUCCIONES)
    assert _contar(bd, PreguntaEval, PreguntaEval.estado == "propuesta") == 4
    assert _contar(bd, Ejecucion) == sum(len(e["filas"]) for e in ACT.EJECUCIONES)
    assert _contar(bd, IntentoEval) == len(ACT.INTENTOS)
    assert _contar(bd, Observacion) == len(ACT.OBSERVACIONES)
    assert _contar(bd, NivelIluo) == len(ACT.ILUO)
    assert {n for n in bd.scalars(select(NivelIluo.nivel)).all()} == {1, 2, 3, 4}  # I, L, U y O
    assert _contar(bd, SentenciaXapi) > 400
    # la base queda marcada como sembrada, con la lista de cuentas que creó la semilla
    marca = bd.scalar(select(Empresa)).config["semilla"]
    assert set(marca["usuarios"]) == {p[0] for p in ORG.PERSONAS} | {"admin"}


def test_personas_del_plan(sembrada, bd):
    def u(nombre):
        return bd.scalar(select(Usuario).where(Usuario.usuario == nombre))

    ana, luis, marta, pedro, javier, carmen = (u(x) for x in ("ana", "luis", "marta", "pedro", "javier", "carmen"))
    assert (ana.nombre, ana.departamento.nombre, ana.nivel.orden, ana.rol, ana.es_experto) == \
        ("Ana López", "Oficina técnica", 3, "jefe", True)
    assert (luis.departamento.nombre, luis.nivel.orden, luis.rol) == ("Oficina técnica", 1, "empleado")
    assert (marta.departamento.nombre, marta.nivel.orden) == ("Producción", 2)
    assert (pedro.departamento.nombre, pedro.nivel.orden) == ("Producción", 1)
    assert (javier.rol, javier.departamento.nombre) == ("jefe", "Producción")
    assert carmen.es_experto and carmen.departamento.nombre == "Producción"
    assert u("admin").rol == "admin"
    assert all(x.email.endswith("@arlanza.example") for x in bd.scalars(select(Usuario)).all())
    # Marta se forma en Oficina técnica. En CidIA solo la administración asigna formaciones
    # (Administración › Empleados): la semilla las deja igual, con su auditoría.
    formacion = bd.scalar(select(Formacion).where(Formacion.usuario_id == marta.id))
    assert (formacion.estado, formacion.departamento.nombre) == ("activa", "Oficina técnica")
    assert {f.asignada_por_id for f in bd.scalars(select(Formacion)).all()} == {u("admin").id}


def test_imagenes_de_los_pasos(sembrada, bd):
    pasos = bd.scalars(select(Paso)).all()
    assert pasos and all(p.imagen_ruta for p in pasos)
    for p in pasos[:3]:
        with Image.open(ajustes().dir_datos / p.imagen_ruta) as im:
            assert im.size == (1280, 720)
    brida = bd.scalar(select(Instruccion).where(Instruccion.codigo == "IT-023", Instruccion.estado == "publicada"))
    assert len(brida.pasos) == 7
    p3 = brida.pasos[2]
    assert p3.es_critico and "25 N·m" in p3.titulo and "media pulgada" in p3.texto
    assert [p.orden for p in brida.pasos if p.es_critico] == [3]


def test_lagunas_y_aportaciones(sembrada, bd):
    prensa2 = bd.scalar(select(Laguna).where(Laguna.pregunta == "¿Qué presión lleva el cilindro de la prensa 2?"))
    refrigeracion = bd.scalar(select(Laguna).where(Laguna.pregunta == "¿Cómo se purga el circuito de refrigeración?"))
    assert (prensa2.frecuencia, prensa2.estado) == (3, "abierta")
    assert (refrigeracion.frecuencia, refrigeracion.estado) == (2, "abierta")
    assert _contar(bd, Consulta, Consulta.laguna_id == prensa2.id, Consulta.con_respaldo.is_(False)) == 3
    validada = bd.scalar(select(Aportacion).where(Aportacion.estado == "validada"))
    assert validada.titulo == "Atasco en la prensa 3 al cambiar de molde: limpiar el sensor S4"
    assert validada.autor.usuario == "pedro" and validada.validador.usuario == "javier"
    faq = bd.get(Documento, validada.documento_id)
    assert (faq.tipo, faq.estado, faq.origen) == ("faq", "listo", "aportacion")
    resuelta = bd.scalar(select(Laguna).where(Laguna.aportacion_id == validada.id))
    assert resuelta is not None and resuelta.estado == "resuelta"
    assert _contar(bd, Aportacion, Aportacion.estado == "pendiente") == 2


def test_fechas_en_las_ultimas_seis_semanas(sembrada, bd):
    momento = ahora()
    desde = momento - timedelta(days=ACT.DIAS_IMPLANTACION + 3)
    fechas = bd.scalars(select(SentenciaXapi.momento)).all()
    assert min(fechas) >= desde and max(fechas) <= momento
    assert (max(fechas) - min(fechas)).days >= 35  # repartidas, no amontonadas
    for s in bd.scalars(select(SentenciaXapi).limit(50)).all():
        assert s.sentencia["timestamp"] == s.momento.isoformat()
    consultas = bd.scalars(select(Consulta.creada)).all()
    assert min(consultas) >= desde and max(consultas) <= momento


# --------------------------------------------------------------------------- coherencia


def _curva(bd, usuario: str, codigo: str) -> list[int]:
    u = bd.scalar(select(Usuario).where(Usuario.usuario == usuario))
    t = bd.scalar(select(Tarea).where(Tarea.codigo == codigo))
    return list(bd.scalars(select(Ejecucion.consultas).where(
        Ejecucion.usuario_id == u.id, Ejecucion.tarea_id == t.id, Ejecucion.estado == "completada")
        .order_by(Ejecucion.inicio)).all())


def test_curva_de_autonomia(sembrada, bd):
    for usuario, codigo in (("marta", "IT-023"), ("luis", "IT-051")):
        curva = _curva(bd, usuario, codigo)
        assert len(curva) >= 6 and curva[0] >= 6 and curva[-1] <= 1
        assert all(a >= b for a, b in zip(curva, curva[1:])), curva
    # cada ejecución cuadra con sus pasos y con sus consultas registradas
    por_paso = dict(bd.execute(select(EjecucionPaso.ejecucion_id, func.sum(EjecucionPaso.consultas))
                               .group_by(EjecucionPaso.ejecucion_id)).all())
    registradas = dict(bd.execute(select(Consulta.ejecucion_id, func.count()).where(Consulta.ejecucion_id.is_not(None))
                                  .group_by(Consulta.ejecucion_id)).all())
    criticas = dict(bd.execute(select(Consulta.ejecucion_id, func.count()).join(Paso, Paso.id == Consulta.paso_id)
                               .where(Paso.es_critico.is_(True)).group_by(Consulta.ejecucion_id)).all())
    for ej in bd.scalars(select(Ejecucion)).all():
        assert por_paso.get(ej.id, 0) == ej.consultas
        assert registradas.get(ej.id, 0) == ej.consultas
        assert criticas.get(ej.id, 0) == ej.consultas_criticos


def test_niveles_iluo_respaldados_por_evidencias(sembrada, bd):
    """Los niveles ganados con CidIA coinciden con lo que calcula servicios/iluo con sus evidencias."""
    from cidia.servicios import iluo

    for usuario, codigo, nivel, dias, _, reevaluar in ACT.ILUO:
        historico = dias > ACT.DIAS_IMPLANTACION and (usuario, codigo) != ("carmen", "IT-023")
        if reevaluar or historico:
            continue  # reevaluación pendiente o nivel importado de la matriz en papel (sin evidencias en CidIA)
        u = bd.scalar(select(Usuario).where(Usuario.usuario == usuario))
        t = bd.scalar(select(Tarea).where(Tarea.codigo == codigo))
        fila = bd.scalar(select(NivelIluo).where(NivelIluo.usuario_id == u.id, NivelIluo.tarea_id == t.id))
        assert fila.caduca > fila.desde
        assert iluo.evaluar(bd, u.id, t, fila).nivel == nivel, (usuario, codigo)
    david = bd.scalar(select(NivelIluo).join(Usuario, Usuario.id == NivelIluo.usuario_id)
                      .where(Usuario.usuario == "david"))
    assert david.requiere_reevaluacion and david.nivel == 3
    javier = bd.scalar(select(NivelIluo).join(Usuario, Usuario.id == NivelIluo.usuario_id)
                       .where(Usuario.usuario == "javier"))
    assert javier.nivel == 4 and javier.caduca - ahora() < timedelta(days=31)  # caduca pronto


# --------------------------------------------------------------------------- permisos


def test_matriz_de_permisos_del_plan(sembrada, bd):
    titulos = {
        "manual": "Manual de iniciación a Oficina técnica",
        "diseno": "Procedimiento de diseño de utillajes",
        "costes": "Costes y proveedores de utillaje",
        "linea2": "Instrucción de montaje de la línea 2",
        "prensa": "Atasco en la prensa 3 al cambiar de molde: limpiar el sensor S4",
        "prl": "Bienvenida y PRL",
    }
    docs = {k: bd.scalar(select(Documento).where(Documento.titulo == t)) for k, t in titulos.items()}
    esperado = {
        "ana": {"manual", "diseno", "costes", "prl"},
        "luis": {"manual", "prl"},
        "marta": {"manual", "linea2", "prensa", "prl"},
        "pedro": {"linea2", "prensa", "prl"},
    }
    for persona, visibles in esperado.items():
        alcance = alcance_de(bd, _actor(bd, persona))
        ids = set(bd.scalars(select(Documento.id).where(filtro_documentos(alcance))).all())
        assert {k for k, d in docs.items() if d.id in ids} == visibles, persona
        assert {k for k, d in docs.items() if puede_ver(alcance, d)} == visibles, persona
    invitado = alcance_de(bd, Actor(sesion=None, usuario=None))  # type: ignore[arg-type]
    publicos = bd.scalars(select(Documento.titulo).where(filtro_documentos(invitado))).all()
    assert publicos == ["Bienvenida y PRL"]


def test_busqueda_y_citas_respetan_permisos(sembrada, bd):
    pedro = alcance_de(bd, _actor(bd, "pedro"))
    res = motor().buscar(bd, "La prensa 3 se atasca al cambiar de molde, ¿qué hago con el sensor S4?", pedro, k=6)
    assert any(r.metadatos.get("tipo") == "faq" for r in res)
    luis, ana = alcance_de(bd, _actor(bd, "luis")), alcance_de(bd, _actor(bd, "ana"))
    consulta = "¿Quién aprueba la compra de un utillaje de más de 3.000 €? proveedores homologados"
    assert all(r.titulo != "Costes y proveedores de utillaje" for r in motor().buscar(bd, consulta, luis, k=8))
    assert any(r.titulo == "Costes y proveedores de utillaje" for r in motor().buscar(bd, consulta, ana, k=8))
    # ninguna consulta sembrada cita algo que su autor no pueda ver
    docs = {d.id: d for d in bd.scalars(select(Documento)).all()}
    alcances = {u.id: alcance_de(bd, Actor(sesion=None, usuario=u))  # type: ignore[arg-type]
                for u in bd.scalars(select(Usuario)).all()}
    for c in bd.scalars(select(Consulta).where(Consulta.con_respaldo.is_(True))).all():
        assert c.fuentes, c.pregunta
        for f in c.fuentes:
            assert puede_ver(alcances[c.usuario_id], docs[f["documento_id"]]), (c.pregunta, f["titulo"])


# --------------------------------------------------------------------------- integración con la API


def _token(cliente, usuario: str) -> dict[str, str]:
    r = cliente.post("/api/auth/login", json={"usuario": usuario, "contrasena": CONTRASENA})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_cuentas_y_pantallas_con_los_datos_sembrados(sembrada, cliente):
    assert cliente.post("/api/auth/login", json={"usuario": "ana", "contrasena": "otra"}).status_code == 401
    assert cliente.get("/api/sistema/info").json()["empresa"] == "Metalúrgica Arlanza, S. L."
    luis = _token(cliente, "luis")
    progreso = cliente.get("/api/progreso/yo", headers=luis)
    assert progreso.status_code == 200, progreso.text
    fila = next(t for t in progreso.json()["tareas"] if t["tarea"]["codigo"] == "IT-051")
    assert fila["letra"] == "L" and len(fila["curva"]) == 7
    javier = _token(cliente, "javier")
    lagunas = cliente.get("/api/lagunas", headers=javier).json()["lagunas"]
    assert lagunas[0]["pregunta"] == "¿Qué presión lleva el cilindro de la prensa 2?" and lagunas[0]["frecuencia"] == 3
    pendientes = cliente.get("/api/aportaciones/pendientes", headers=javier).json()
    assert pendientes["resumen"]["pendientes"] == 2
    # Luis (empleado) no puede ver la bandeja de lagunas de un jefe
    assert cliente.get("/api/lagunas", headers=luis).status_code == 403


# --------------------------------------------------------------------------- utilidades


def test_contrasena_generada_y_guardada(monkeypatch, carpeta, caplog):
    monkeypatch.delenv("CIDIA_DEMO_CONTRASENA", raising=False)
    monkeypatch.setattr(ajustes(), "demo_contrasena", "", raising=False)
    monkeypatch.setattr(ajustes(), "dir_datos", carpeta)
    clave, origen = semilla.contrasena_demo()
    fichero = carpeta / semilla.FICHERO_CONTRASENA
    assert origen == str(fichero) and len(clave) >= 12
    assert f"contrasena={clave}" in fichero.read_text(encoding="utf-8")
    assert semilla.contrasena_demo()[0] == clave  # estable entre arranques
    assert clave not in caplog.text  # nunca en los registros
    monkeypatch.setenv("CIDIA_DEMO_CONTRASENA", "de-la-variable")
    assert semilla.contrasena_demo() == ("de-la-variable", "la variable CIDIA_DEMO_CONTRASENA")
    assert not fichero.exists()  # la generada ya no vale


def test_contrasena_desde_los_ajustes(monkeypatch, carpeta):
    """CIDIA_DEMO_CONTRASENA también vale desde el fichero .env (ajustes), no solo del entorno."""
    monkeypatch.delenv("CIDIA_DEMO_CONTRASENA", raising=False)
    monkeypatch.setattr(ajustes(), "dir_datos", carpeta)
    monkeypatch.setattr(ajustes(), "demo_contrasena", "de-los-ajustes", raising=False)
    assert semilla.contrasena_demo() == ("de-los-ajustes", "la variable CIDIA_DEMO_CONTRASENA")
    assert not (carpeta / semilla.FICHERO_CONTRASENA).exists()  # no se genera ninguna


def test_exportar_documentos(carpeta):
    from pypdf import PdfReader

    assert semilla.exportar_documentos(carpeta) == len(DOCS.DOCUMENTOS)
    pdf = PdfReader(str(carpeta / "IT-L2-01-montaje-linea-2.pdf"))
    texto = " ".join(p.extract_text() or "" for p in pdf.pages)
    assert "25 N·m" in texto and "brida B" in texto
    # las lagunas de la demostración no tienen respuesta en ningún documento
    todo = " ".join(d["texto"] for d in DOCS.DOCUMENTOS).lower()
    assert "refrigeración" not in todo and "cilindro de la prensa 2" not in todo


def test_sembrar_si_vacio(sembrada, monkeypatch):
    assert semilla.sembrar_si_vacio() is None  # ya sembrada: no encola nada
    llamadas: list[bool] = []
    monkeypatch.setattr(semilla, "sembrar",
                        lambda bd, forzar=False, progreso=None: llamadas.append(forzar) or {"sembrado": True})
    from cidia.db import nueva_sesion

    # base vacía: encola la siembra y el trabajo la completa
    monkeypatch.setattr(semilla, "estado_base", lambda bd: "vacia")
    tid = semilla.sembrar_si_vacio()
    assert isinstance(tid, int) and llamadas == [False]
    with nueva_sesion() as s:
        t = s.get(Trabajo, tid)
        assert (t.tipo, t.estado, t.resultado) == ("semilla_demo", "completado", {"sembrado": True})
    # siembra que quedó a medias (reinicio del servidor): se repite desde cero con forzar
    monkeypatch.setattr(semilla, "estado_base", lambda bd: "incompleta")
    assert isinstance(semilla.sembrar_si_vacio(), int) and llamadas == [False, True]
    # base con datos propios: no se encola nada
    monkeypatch.setattr(semilla, "estado_base", lambda bd: "con_datos")
    assert semilla.sembrar_si_vacio() is None and llamadas == [False, True]


def test_base_con_datos_propios_no_se_toca(sembrada, bd, monkeypatch):
    """Una base que no sembró la semilla (aunque tenga una «ana») no se siembra ni se vacía nunca."""
    monkeypatch.setenv("CIDIA_DEMO_CONTRASENA", CONTRASENA)
    antes = _recuentos(bd)
    emp = bd.scalar(select(Empresa).order_by(Empresa.id))
    ana = bd.scalar(select(Usuario).where(Usuario.usuario == "ana"))
    try:
        emp.config = {k: v for k, v in (emp.config or {}).items() if k != "semilla"}  # sin marca
        bd.flush()
        assert semilla.estado_base(bd) == "sembrada"  # siembra antigua: «ana» con el correo ficticio
        ana.email = "ana.lopez@empresa-real.es"  # una «ana» de verdad
        bd.flush()
        assert semilla.estado_base(bd) == "con_datos" and not semilla.ya_sembrado(bd)
        for forzar in (False, True):
            r = semilla.sembrar(bd, forzar=forzar)
            assert (r["sembrado"], r["estado"]) == (False, "con_datos") and "datos propios" in r["motivo"]
        with pytest.raises(RuntimeError):
            semilla.vaciar(bd)
    finally:
        bd.rollback()
    assert _recuentos(bd) == antes


def test_siembra_a_medias(sembrada, bd):
    """Con la marca «en_curso» la base está incompleta: sin forzar no se siembra encima."""
    emp = bd.scalar(select(Empresa).order_by(Empresa.id))
    try:
        emp.config = {**emp.config, "semilla": {**emp.config["semilla"], "estado": "en_curso"}}
        bd.flush()
        assert semilla.estado_base(bd) == "incompleta"
        assert semilla.sembrar(bd) == {"sembrado": False, "estado": "incompleta",
                                       "motivo": "La siembra anterior quedó a medias."}
    finally:
        bd.rollback()
    assert semilla.estado_base(bd) == "sembrada"


def test_una_siembra_a_la_vez(sembrada, bd, capsys):
    """Con otra siembra en marcha (su cerrojo cogido) no empieza otra, ni con --forzar: la del
    arranque puede tardar minutos y una lanzada a mano vaciaría lo que está creando."""
    from cidia.db import motor_bd

    antes = _recuentos(bd)
    bd.rollback()  # sin transacción abierta: no retiene tablas mientras prueba la orden manual
    with motor_bd().connect() as otra:
        assert otra.execute(select(func.pg_try_advisory_lock(semilla.CERROJO))).scalar() is True
        otra.commit()
        try:
            r = semilla.sembrar(bd, forzar=True)
            # La orden manual avisa y termina con error antes de tocar el esquema (inicializar_bd
            # esperaría a que la otra siembra soltase la tabla de usuarios).
            assert semilla.main(["--forzar"]) == 1
        finally:
            otra.execute(select(func.pg_advisory_unlock(semilla.CERROJO)))
            otra.commit()
    assert (r["sembrado"], r["estado"]) == (False, "ocupada") and "en marcha" in r["motivo"]
    salida = capsys.readouterr().out
    assert "otra siembra" in salida and "--forzar" not in salida  # aquí forzar no arregla nada
    assert _recuentos(bd) == antes
    with semilla._cerrojo(motor_bd()) as libre:  # al terminar la otra, el cerrojo queda libre
        assert libre


def test_lagunas_sin_vectores_del_modelo(sembrada, bd, monkeypatch):
    """Si el modelo de embeddings falla o devuelve un número de vectores que no cuadra, las lagunas
    se crean igual (sin vector) y la siembra sigue."""
    from cidia.ia import llm

    def caido(textos, modelo=None):
        raise RuntimeError("modelo caído")

    s = semilla._Semilla(bd)
    s.deps = {d["clave"]: bd.scalar(select(Departamento).where(Departamento.nombre == d["nombre"]))
              for d in ORG.DEPARTAMENTOS}
    s.tareas = {t.codigo: t for t in bd.scalars(select(Tarea)).all()}
    s.personas = {u.usuario: u for u in bd.scalars(select(Usuario)).all()}
    antes = _contar(bd, Laguna)
    try:
        for falso in (lambda textos, modelo=None: [[0.1] * 8], caido):  # un vector para cuatro preguntas
            monkeypatch.setattr(llm, "embeddings", falso)
            s.lagunas()
            bd.flush()
        nuevas = bd.scalars(select(Laguna).order_by(Laguna.id.desc()).limit(2 * len(ACT.LAGUNAS))).all()
        assert len(nuevas) == 2 * len(ACT.LAGUNAS) and all(lg.embedding is None for lg in nuevas)
        assert _contar(bd, Laguna) == antes + 2 * len(ACT.LAGUNAS)
    finally:
        bd.rollback()
    assert _contar(bd, Laguna) == antes


def test_idempotente_y_forzar(sembrada, bd, monkeypatch):
    antes = _recuentos(bd)
    assert semilla.sembrar(bd) == {"sembrado": False, "estado": "sembrada", "motivo": "Ya existe el usuario «ana»."}
    assert _recuentos(bd) == antes
    # Con un motor externo (WeKnora), vaciar retira antes sus documentos para no dejarlos huérfanos.
    retirados: list[int] = []

    class MotorExterno:
        def borrar(self, _bd, doc):
            retirados.append(doc.id)
            doc.motor_id = None

    costes = bd.scalar(select(Documento).where(Documento.titulo == "Costes y proveedores de utillaje"))
    costes.motor_id, costes_id = "conocimiento-ot-0004", costes.id
    bd.commit()
    monkeypatch.setattr(semilla, "motor", lambda: MotorExterno())
    monkeypatch.setenv("CIDIA_DEMO_CONTRASENA", CONTRASENA)
    resumen = semilla.sembrar(bd, forzar=True)
    assert resumen["sembrado"] is True
    assert retirados == [costes_id]
    despues = _recuentos(bd)
    assert {k: v for k, v in despues.items() if k != "SentenciaXapi"} == \
        {k: v for k, v in antes.items() if k != "SentenciaXapi"}
    # las pruebas anteriores también dejan trazas (inicios de sesión): se compara lo que escribe la semilla
    assert resumen["xapi"] == despues["SentenciaXapi"] == sembrada["xapi"]
    # los ids no se reutilizan: lo que se conserva (trabajos, auditoría) no apunta a filas nuevas
    nuevo = bd.scalar(select(Documento).where(Documento.titulo == "Costes y proveedores de utillaje"))
    assert nuevo.id > costes_id and nuevo.motor_id is None


def test_copiloto_respeta_permisos_con_los_datos_sembrados(sembrada, cliente, bd):
    """Por la API, como la interfaz: el copiloto no cita lo que la persona no puede ver.

    Va después de forzar: añade consultas y lagunas, que cambiarían los recuentos de esa prueba.
    """
    costes = "Costes y proveedores de utillaje"
    pregunta = "¿Quién aprueba la compra de un utillaje de más de 3.000 €? proveedores homologados"

    def citas(cabeceras: dict[str, str], texto: str = pregunta) -> set[str]:
        r = cliente.post("/api/consulta/simple", json={"pregunta": texto}, headers=cabeceras)
        assert r.status_code == 200, r.text
        return {f["titulo"] for f in r.json()["fuentes"]}

    luis, ana = _token(cliente, "luis"), _token(cliente, "ana")
    assert costes not in citas(luis)  # nivel 1: ni lo cita ni sabe que existe
    assert costes in citas(ana)  # nivel 3 de Oficina técnica
    invitado = {"Authorization": f"Bearer {cliente.post('/api/auth/invitado').json()['token']}"}
    assert citas(invitado) <= {"Bienvenida y PRL"}  # sin sesión, solo lo público
    assert citas(invitado, "¿Dónde está el punto de reunión en caso de emergencia?") <= {"Bienvenida y PRL"}
    # El historial de Luis tiene solo sus consultas (sembradas y nuevas), sin citas que él no vea.
    u = bd.scalar(select(Usuario).where(Usuario.usuario == "luis"))
    h = cliente.get("/api/consulta/historial", params={"por_pagina": 100}, headers=luis)
    assert h.status_code == 200, h.text
    assert h.json()["total"] == _contar(bd, Consulta, Consulta.usuario_id == u.id) > 2
    assert all(costes not in {f["titulo"] for f in c["fuentes"]} for c in h.json()["elementos"])


# --------------------------------------------------------------------------- con los modelos reales


@pytest.mark.ia_real
def test_siembra_con_modelos_reales(app, bd, monkeypatch):
    """Con el modelo de embeddings real, la búsqueda híbrida encuentra lo que el guion necesita."""
    monkeypatch.setenv("CIDIA_DEMO_CONTRASENA", CONTRASENA)
    resumen = semilla.sembrar(bd, forzar=True)
    assert resumen["sembrado"] is True and resumen["avisos"] == []
    marta = alcance_de(bd, _actor(bd, "marta"))
    res = motor().buscar(bd, "¿A qué par aprieto los tornillos de la brida B y con qué llave?", marta, k=5)
    assert any(r.metadatos.get("codigo") == "IT-023" and r.metadatos.get("paso") == 3 for r in res)
    pedro = alcance_de(bd, _actor(bd, "pedro"))
    res = motor().buscar(bd, "La prensa 3 se queda parada después de cambiar el molde", pedro, k=5)
    assert any(r.metadatos.get("tipo") == "faq" for r in res)
