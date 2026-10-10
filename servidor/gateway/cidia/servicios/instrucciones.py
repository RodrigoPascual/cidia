"""Instrucciones de trabajo versionadas: listado, borrador, publicación, versiones y diferencias.

Ciclo de vida: borrador → publicada → obsoleta (cuando se publica una versión posterior). Hay
como mucho una versión publicada por tarea. Las imágenes y clips de los pasos se comparten entre
versiones (una versión nueva copia sus rutas), así que editar un borrador solo borra las imágenes
subidas a mano que ya no usa ningún paso de ninguna versión.

Permisos: gestionan instrucciones los expertos, los jefes y la administración; expertos y jefes,
solo las de las tareas de su propio departamento.

Contrato (servicios/contratos.md): `publicar(bd, actor, instruccion_id)` y `a_dict(bd, ins, con_pasos)`.
Las funciones de operación (crear, editar, nueva versión, borrar...) hacen commit al terminar.
"""

from __future__ import annotations

import logging
import shutil
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from cidia.conocimiento import motor
from cidia.ficheros import guardar_subida, ruta_absoluta
from cidia.modelos import Captura, Documento, Instruccion, Paso, Puesto, Tarea, Trabajo, ahora
from cidia.seguridad import Actor, url_fichero
from cidia.servicios import documentos
from cidia.xapi import auditar, registrar

log = logging.getLogger("cidia.instrucciones")

EDITABLES = ("borrador", "en_revision")
MAX_PASOS = 60
EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGEN = 15 * 1024 * 1024
CAMPOS_TEXTO = {"titulo": 300, "codigo": 30, "resumen": 5000, "riesgos": 5000, "epis": 3000, "herramientas": 3000}


def _texto(v: Any, maximo: int) -> str:
    return str(v).strip()[:maximo] if v is not None else ""


def _persona(u: Any) -> dict[str, Any] | None:
    return {"id": u.id, "nombre": u.nombre} if u else None


# --------------------------------------------------------------------------- permisos


def departamento_de(tarea: Tarea | None) -> int | None:
    return tarea.puesto.departamento_id if tarea is not None and tarea.puesto is not None else None


def puede_gestionar(actor: Actor, departamento_id: int | None) -> bool:
    """Expertos, jefes y administración; los dos primeros, solo en su departamento."""
    if actor.es_invitado or not actor.es_experto:
        return False
    if actor.es_admin:
        return True
    return departamento_id is not None and departamento_id == actor.departamento_id


def tarea_gestionable(bd: Session, actor: Actor, tarea_id: int) -> Tarea:
    t = bd.get(Tarea, tarea_id)
    if t is None:
        raise HTTPException(404, "La tarea no existe.")
    if not puede_gestionar(actor, departamento_de(t)):
        raise HTTPException(403, "Solo puedes trabajar con las tareas de tu departamento.")
    return t


def obtener(bd: Session, actor: Actor, instruccion_id: int) -> Instruccion:
    ins = bd.get(Instruccion, instruccion_id)
    if ins is None:
        raise HTTPException(404, "La instrucción no existe.")
    if not puede_gestionar(actor, departamento_de(ins.tarea)):
        raise HTTPException(403, "Esta instrucción es de otro departamento.")
    return ins


def _exigir_borrador(ins: Instruccion) -> None:
    if ins.estado not in EDITABLES:
        raise HTTPException(409, "Solo se puede modificar un borrador. "
                                 "Crea una nueva versión para cambiar una instrucción publicada.")


def _borrador_bloqueado(bd: Session, actor: Actor, instruccion_id: int) -> Instruccion:
    """Borrador listo para modificarlo: con la tarea bloqueada (como al publicar) y el estado
    releído, nadie puede publicarlo a la vez y acabar cambiando una versión ya publicada."""
    ins = obtener(bd, actor, instruccion_id)
    bloquear_tarea(bd, ins.tarea_id)
    bd.refresh(ins)
    _exigir_borrador(ins)
    return ins


# --------------------------------------------------------------------------- representación


def paso_dict(p: Paso) -> dict[str, Any]:
    return {
        "id": p.id,
        "orden": p.orden,
        "titulo": p.titulo,
        "texto": p.texto or "",
        "es_critico": p.es_critico,
        "es_seguridad": p.es_seguridad,
        "criterio_aceptacion": p.criterio_aceptacion or "",
        "imagen_url": url_fichero(p.imagen_ruta),
        "clip_url": url_fichero(p.clip_ruta),
        "t_inicio": p.t_inicio,
        "t_fin": p.t_fin,
    }


def tarea_dict(t: Tarea | None) -> dict[str, Any] | None:
    if t is None:
        return None
    dep = t.puesto.departamento if t.puesto else None
    return {
        "id": t.id,
        "codigo": t.codigo,
        "nombre": t.nombre,
        "puesto": t.puesto.nombre if t.puesto else None,
        "departamento_id": dep.id if dep else None,
        "departamento": dep.nombre if dep else None,
        "nivel_minimo": t.nivel_minimo,
        "criticidad": t.criticidad,
    }


def a_dict(bd: Session, ins: Instruccion, con_pasos: bool = True) -> dict[str, Any]:
    """Instrucción para la API, con URLs firmadas de imágenes, clips y vídeo original."""
    pasos = list(ins.pasos)
    d: dict[str, Any] = {
        "id": ins.id,
        "tarea_id": ins.tarea_id,
        "tarea": tarea_dict(ins.tarea),
        "codigo": ins.codigo,
        "version": ins.version,
        "estado": ins.estado,
        "titulo": ins.titulo,
        "resumen": ins.resumen or "",
        "riesgos": ins.riesgos or "",
        "epis": ins.epis or "",
        "herramientas": ins.herramientas or "",
        "autor": _persona(ins.autor),
        "revisor": _persona(ins.revisor),
        "captura_id": ins.captura_id,
        "video_url": url_fichero(ins.video_ruta),
        "documento_id": ins.documento_id,
        "creada": ins.creada.isoformat() if ins.creada else None,
        "publicada_en": ins.publicada_en.isoformat() if ins.publicada_en else None,
        "n_pasos": len(pasos),
        "pasos_criticos": sum(1 for p in pasos if p.es_critico),
        "pasos_seguridad": sum(1 for p in pasos if p.es_seguridad),
        "miniatura_url": url_fichero(next((p.imagen_ruta for p in pasos if p.imagen_ruta), None)),
    }
    if con_pasos:
        d["pasos"] = [paso_dict(p) for p in pasos]
    return d


def vigente(bd: Session, tarea_id: int) -> Instruccion | None:
    """Versión publicada de una tarea (la que usan el copiloto, el modo planta y la formación)."""
    return bd.scalar(select(Instruccion).where(Instruccion.tarea_id == tarea_id, Instruccion.estado == "publicada")
                     .order_by(Instruccion.version.desc()).limit(1))


def _borrador_de(bd: Session, tarea_id: int) -> Instruccion | None:
    return bd.scalar(select(Instruccion).where(Instruccion.tarea_id == tarea_id, Instruccion.estado.in_(EDITABLES))
                     .order_by(Instruccion.version.desc()).limit(1))


def detalle(bd: Session, actor: Actor, instruccion_id: int) -> dict[str, Any]:
    """a_dict más lo que necesita el editor: versión vigente, borrador existente y nº de versiones."""
    ins = obtener(bd, actor, instruccion_id)
    d = a_dict(bd, ins)
    vig = vigente(bd, ins.tarea_id)
    bor = _borrador_de(bd, ins.tarea_id)
    d["vigente"] = {"id": vig.id, "version": vig.version} if vig else None
    d["borrador_existente"] = {"id": bor.id, "version": bor.version} if bor and bor.id != ins.id else None
    d["n_versiones"] = bd.scalar(select(func.count(Instruccion.id)).where(Instruccion.tarea_id == ins.tarea_id)) or 0
    d["editable"] = ins.estado in EDITABLES
    d["transcripcion"] = _transcripcion_de(bd, ins.captura_id)
    return d


def _transcripcion_de(bd: Session, captura_id: int | None) -> list[dict[str, Any]] | None:
    """Lo que dijo el experto en el vídeo, con sus tiempos, para revisar cada paso contra ello en el
    editor. Solo los segmentos (sin el fichero ni el resto de la captura)."""
    cap = bd.get(Captura, captura_id) if captura_id else None
    trans = cap.transcripcion if cap is not None and cap.tipo == "video" else None
    segmentos = (trans.get("segmentos") or []) if isinstance(trans, dict) else []
    salida = [{"inicio": s.get("inicio"), "fin": s.get("fin"), "texto": str(s.get("texto") or "").strip()}
              for s in segmentos if isinstance(s, dict) and str(s.get("texto") or "").strip()]
    return salida or None



def contar_borradores(bd: Session, actor: Actor) -> int:
    """Borradores que la persona puede revisar y publicar (contador de la barra lateral)."""
    if actor.es_invitado or not actor.es_experto:
        return 0
    q = (select(func.count(Instruccion.id)).join(Tarea, Tarea.id == Instruccion.tarea_id)
         .join(Puesto, Puesto.id == Tarea.puesto_id).where(Instruccion.estado.in_(EDITABLES)))
    if not actor.es_admin:
        if not actor.departamento_id:
            return 0
        q = q.where(Puesto.departamento_id == actor.departamento_id)
    return bd.scalar(q) or 0


# --------------------------------------------------------------------------- listados


def listar(bd: Session, actor: Actor, tarea_id: int | None = None, departamento_id: int | None = None,
           estado: str | None = None, texto: str | None = None) -> list[dict[str, Any]]:
    q = (select(Instruccion).join(Tarea, Tarea.id == Instruccion.tarea_id).join(Puesto, Puesto.id == Tarea.puesto_id)
         .options(selectinload(Instruccion.pasos)))
    if not actor.es_admin:
        if not actor.departamento_id:
            return []
        q = q.where(Puesto.departamento_id == actor.departamento_id)
    if departamento_id:
        q = q.where(Puesto.departamento_id == departamento_id)
    if tarea_id:
        q = q.where(Instruccion.tarea_id == tarea_id)
    if estado:
        q = q.where(Instruccion.estado == estado)
    if texto and texto.strip():
        patron = f"%{texto.strip()}%"
        q = q.where(Instruccion.titulo.ilike(patron) | Instruccion.codigo.ilike(patron) | Tarea.nombre.ilike(patron)
                    | Tarea.codigo.ilike(patron))
    filas = bd.scalars(q.order_by(Tarea.nombre, Instruccion.version.desc())).all()
    return [a_dict(bd, i, con_pasos=False) for i in filas]


def tareas_gestionables(bd: Session, actor: Actor) -> list[dict[str, Any]]:
    """Tareas activas que la persona puede capturar o documentar (para los selectores)."""
    q = (select(Tarea).join(Puesto, Puesto.id == Tarea.puesto_id).where(Tarea.activa.is_(True))
         .options(selectinload(Tarea.puesto).selectinload(Puesto.departamento)))
    if not actor.es_admin:
        if not actor.es_experto or not actor.departamento_id:
            return []
        q = q.where(Puesto.departamento_id == actor.departamento_id)
    tareas = bd.scalars(q.order_by(Tarea.codigo, Tarea.nombre)).all()
    ids = [t.id for t in tareas]
    versiones: dict[int, dict[str, Any]] = {}
    if ids:
        for i in bd.execute(select(Instruccion.tarea_id, Instruccion.id, Instruccion.version, Instruccion.estado)
                            .where(Instruccion.tarea_id.in_(ids)).order_by(Instruccion.version)).all():
            v = versiones.setdefault(i.tarea_id, {"publicada": None, "borrador": None, "versiones": 0})
            v["versiones"] += 1
            if i.estado == "publicada":
                v["publicada"] = {"id": i.id, "version": i.version}
            elif i.estado in EDITABLES:
                v["borrador"] = {"id": i.id, "version": i.version}
    salida = []
    for t in tareas:
        d = tarea_dict(t) or {}
        d.update(versiones.get(t.id, {"publicada": None, "borrador": None, "versiones": 0}))
        salida.append(d)
    return salida


def versiones(bd: Session, actor: Actor, instruccion_id: int) -> list[dict[str, Any]]:
    ins = obtener(bd, actor, instruccion_id)
    todas = bd.scalars(select(Instruccion).where(Instruccion.tarea_id == ins.tarea_id)
                       .options(selectinload(Instruccion.pasos)).order_by(Instruccion.version.desc())).all()
    return [{
        "id": i.id, "version": i.version, "estado": i.estado, "codigo": i.codigo, "titulo": i.titulo,
        "autor": _persona(i.autor), "revisor": _persona(i.revisor), "n_pasos": len(i.pasos),
        "creada": i.creada.isoformat() if i.creada else None,
        "publicada_en": i.publicada_en.isoformat() if i.publicada_en else None,
        "actual": i.id == ins.id,
    } for i in todas]


# --------------------------------------------------------------------------- creación y edición


def bloquear_tarea(bd: Session, tarea_id: int) -> None:
    """Bloquea la fila de la tarea hasta el commit. Serializa lo que reparte versiones o cambia la
    vigente (borrador nuevo, nueva versión, publicar): dos peticiones a la vez no pueden coger el
    mismo número de versión ni dejar dos versiones publicadas."""
    bd.execute(select(Tarea.id).where(Tarea.id == tarea_id).with_for_update())


def siguiente_version(bd: Session, tarea_id: int) -> int:
    return (bd.scalar(select(func.max(Instruccion.version)).where(Instruccion.tarea_id == tarea_id)) or 0) + 1


def codigo_para(bd: Session, tarea: Tarea) -> str:
    """Código de la instrucción: el de versiones anteriores, el de la tarea o IT-<id>."""
    previo = bd.scalar(select(Instruccion.codigo).where(Instruccion.tarea_id == tarea.id, Instruccion.codigo.is_not(None))
                       .order_by(Instruccion.version.desc()).limit(1))
    return previo or tarea.codigo or f"IT-{tarea.id:03d}"


def _nuevo_paso(orden: int, datos: dict[str, Any]) -> Paso:
    return Paso(
        orden=orden,
        titulo=_texto(datos.get("titulo"), 300) or f"Paso {orden}",
        texto=_texto(datos.get("texto"), 5000) or None,
        es_critico=bool(datos.get("es_critico")),
        es_seguridad=bool(datos.get("es_seguridad")),
        criterio_aceptacion=_texto(datos.get("criterio_aceptacion"), 2000) or None,
        imagen_ruta=datos.get("imagen_ruta"),
        clip_ruta=datos.get("clip_ruta"),
        t_inicio=datos.get("t_inicio"),
        t_fin=datos.get("t_fin"),
    )


def crear_borrador(bd: Session, tarea: Tarea, autor_id: int | None, datos: dict[str, Any],
                   captura_id: int | None = None, video_ruta: str | None = None) -> Instruccion:
    """Crea una instrucción en borrador con la versión siguiente de la tarea. Sin permisos ni commit:
    la usan la captura (vídeo, entrevista), la creación manual y la nueva versión."""
    bloquear_tarea(bd, tarea.id)
    ins = Instruccion(
        tarea_id=tarea.id,
        codigo=_texto(datos.get("codigo"), 30) or codigo_para(bd, tarea),
        version=siguiente_version(bd, tarea.id),
        estado="borrador",
        titulo=_texto(datos.get("titulo"), 300) or tarea.nombre,
        resumen=_texto(datos.get("resumen"), 5000) or None,
        riesgos=_texto(datos.get("riesgos"), 5000) or tarea.riesgos_prl or None,
        epis=_texto(datos.get("epis"), 3000) or None,
        herramientas=_texto(datos.get("herramientas"), 3000) or None,
        autor_id=autor_id,
        captura_id=captura_id,
        video_ruta=video_ruta,
    )
    ins.pasos = [_nuevo_paso(i, p) for i, p in enumerate((datos.get("pasos") or [])[:MAX_PASOS], start=1)]
    bd.add(ins)
    bd.flush()
    return ins


def crear_manual(bd: Session, actor: Actor, datos: dict[str, Any]) -> Instruccion:
    """Borrador nuevo escrito a mano. Solo un borrador por tarea a la vez."""
    if not datos.get("tarea_id"):
        raise HTTPException(400, "Elige la tarea de la instrucción.")
    tarea = tarea_gestionable(bd, actor, int(datos["tarea_id"]))
    if not tarea.activa:
        raise HTTPException(400, "Esa tarea está dada de baja. Elige otra o pide a la administración que la reactive.")
    bloquear_tarea(bd, tarea.id)
    existente = _borrador_de(bd, tarea.id)
    if existente:
        raise HTTPException(409, f"Ya hay un borrador (versión {existente.version}) de esta tarea. "
                                 "Ábrelo desde la lista para seguir editándolo.")
    publicada = vigente(bd, tarea.id)
    if publicada:
        raise HTTPException(409, f"Esta tarea ya tiene publicada la versión {publicada.version}. "
                                 "Ábrela y pulsa «Crear nueva versión» para partir de ella.")
    ins = crear_borrador(bd, tarea, actor.id, datos)
    registrar(bd, actor, "capturo", "instruccion", ins.id, f"{ins.codigo} · {ins.titulo}",
              contexto={"origen": "manual", "tarea_id": tarea.id, "version": ins.version})
    bd.commit()
    return ins


def _sincronizar_pasos(ins: Instruccion, entrada: list[dict[str, Any]]) -> None:
    """La lista recibida manda: añade, quita, reordena y edita. Los pasos se identifican por id;
    los que no lo traen son nuevos. Los tiempos y ficheros de los existentes no se tocan."""
    if len(entrada) > MAX_PASOS:
        raise HTTPException(400, f"Una instrucción no puede tener más de {MAX_PASOS} pasos.")
    existentes = {p.id: p for p in ins.pasos}
    usados: set[int] = set()
    nuevos: list[Paso] = []
    for orden, e in enumerate(entrada, start=1):
        pid = e.get("id")
        if pid is not None:
            p = existentes.get(pid)
            if p is None or pid in usados:
                raise HTTPException(400, "Uno de los pasos no pertenece a esta instrucción. Recarga la página.")
            usados.add(pid)
        else:
            p = Paso(orden=orden, titulo="")
        p.orden = orden
        p.titulo = _texto(e.get("titulo"), 300)
        p.texto = _texto(e.get("texto"), 5000) or None
        p.criterio_aceptacion = _texto(e.get("criterio_aceptacion"), 2000) or None
        p.es_critico = bool(e.get("es_critico"))
        p.es_seguridad = bool(e.get("es_seguridad"))
        nuevos.append(p)
    ins.pasos = nuevos  # delete-orphan elimina los que ya no están


def editar(bd: Session, actor: Actor, instruccion_id: int, datos: dict[str, Any]) -> Instruccion:
    ins = _borrador_bloqueado(bd, actor, instruccion_id)
    propias = imagenes_propias(ins)  # por si se quita un paso con una imagen subida a mano
    for campo, maximo in CAMPOS_TEXTO.items():
        if campo in datos and datos[campo] is not None:
            valor = _texto(datos[campo], maximo)
            if campo == "titulo" and not valor:
                raise HTTPException(400, "La instrucción necesita un título.")
            if campo == "codigo" and not valor:
                continue
            setattr(ins, campo, valor or None)
    if datos.get("pasos") is not None:
        _sincronizar_pasos(ins, datos["pasos"])
    bd.commit()
    borrar_imagenes_sin_uso(bd, propias)  # las que ya no usa ningún paso (de ninguna versión)
    bd.refresh(ins)
    return ins


def cambiar_imagen(bd: Session, actor: Actor, instruccion_id: int, paso_id: int, subida: UploadFile) -> Instruccion:
    ins = _borrador_bloqueado(bd, actor, instruccion_id)
    paso = bd.get(Paso, paso_id)
    if paso is None or paso.instruccion_id != ins.id:
        raise HTTPException(404, "El paso no existe en esta instrucción.")
    ext = Path(subida.filename or "").suffix.lower()
    if ext not in EXT_IMAGEN:
        raise HTTPException(400, "Sube una imagen JPG, PNG o WebP.")
    # Si se conoce el tamaño, se rechaza antes de escribir nada en disco (guardar_subida admite 2 GB).
    if (getattr(subida, "size", None) or 0) > MAX_IMAGEN:
        raise HTTPException(413, "La imagen es demasiado grande (máximo 15 MB).")
    ruta, _, tam = guardar_subida(subida, "instrucciones")
    fallo: tuple[int, str] | None = None
    if tam == 0:
        fallo = (400, "La imagen está vacía.")
    elif tam > MAX_IMAGEN:
        fallo = (413, "La imagen es demasiado grande (máximo 15 MB).")
    elif not _es_imagen(ruta_absoluta(ruta)):
        # La extensión decide cómo se sirve: el contenido tiene que ser de verdad una imagen.
        fallo = (400, "El fichero no es una imagen JPG, PNG o WebP válida.")
    if fallo:
        _borrar_subida(ruta)
        raise HTTPException(*fallo)
    anterior = paso.imagen_ruta
    paso.imagen_ruta = ruta
    bd.commit()
    # La imagen sustituida se borra si era una subida a mano que ya no usa ningún paso (las de la
    # captura y las de otras versiones se conservan).
    if anterior and not bd.scalar(select(Paso.id).where(Paso.imagen_ruta == anterior).limit(1)):
        _borrar_subida(anterior)
    bd.refresh(ins)
    return ins


def _borrar_subida(ruta: str) -> None:
    """Borra una imagen subida a mano (instrucciones/<carpeta propia>/<fichero>) con su carpeta.
    Cualquier otra ruta (captura, semilla) no se toca."""
    partes = Path(ruta).parts
    if len(partes) != 3 or partes[0] != "instrucciones":
        return
    try:
        shutil.rmtree(ruta_absoluta(ruta).parent, ignore_errors=True)
    except HTTPException:
        pass


def _es_imagen(p: Path) -> bool:
    """¿Empieza el fichero como un JPG, un PNG o un WebP?"""
    with p.open("rb") as f:
        cabecera = f.read(12)
    return (cabecera.startswith(b"\xff\xd8\xff") or cabecera.startswith(b"\x89PNG\r\n\x1a\n")
            or (cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP"))


def nueva_version(bd: Session, actor: Actor, instruccion_id: int) -> tuple[Instruccion, bool]:
    """Copia una versión publicada (u obsoleta) como borrador v+1. Si la tarea ya tiene un
    borrador, devuelve ese (y True) en vez de crear otro."""
    base = obtener(bd, actor, instruccion_id)
    if base.estado in EDITABLES:
        raise HTTPException(409, "Esta versión aún es un borrador: edítala directamente.")
    bloquear_tarea(bd, base.tarea_id)  # con un doble clic, la segunda petición encuentra el borrador
    existente = _borrador_de(bd, base.tarea_id)
    if existente:
        return existente, True
    datos = {
        "codigo": base.codigo, "titulo": base.titulo, "resumen": base.resumen, "riesgos": base.riesgos,
        "epis": base.epis, "herramientas": base.herramientas,
        "pasos": [{
            "titulo": p.titulo, "texto": p.texto, "es_critico": p.es_critico, "es_seguridad": p.es_seguridad,
            "criterio_aceptacion": p.criterio_aceptacion, "imagen_ruta": p.imagen_ruta, "clip_ruta": p.clip_ruta,
            "t_inicio": p.t_inicio, "t_fin": p.t_fin,
        } for p in base.pasos],
    }
    copia = crear_borrador(bd, base.tarea, actor.id, datos, captura_id=base.captura_id, video_ruta=base.video_ruta)
    registrar(bd, actor, "capturo", "instruccion", copia.id, f"{copia.codigo} · {copia.titulo}",
              contexto={"origen": "nueva_version", "desde": base.id, "version": copia.version, "tarea_id": base.tarea_id})
    bd.commit()
    return copia, False


def imagenes_propias(ins: Instruccion) -> set[str]:
    """Imágenes subidas a mano para los pasos de esta instrucción (no las de la captura)."""
    return {p.imagen_ruta for p in ins.pasos if p.imagen_ruta and p.imagen_ruta.startswith("instrucciones/")}


def borrar_imagenes_sin_uso(bd: Session, rutas: set[str]) -> None:
    """Después de borrar pasos (y del commit): borra las imágenes subidas a mano que ya no use ningún paso."""
    if not rutas:
        return
    en_uso = set(bd.scalars(select(Paso.imagen_ruta).where(Paso.imagen_ruta.in_(rutas))).all())
    for ruta in rutas - en_uso:
        _borrar_subida(ruta)


def borrar_borrador(bd: Session, actor: Actor, instruccion_id: int) -> None:
    ins = _borrador_bloqueado(bd, actor, instruccion_id)
    propias = imagenes_propias(ins)
    bd.execute(update(Captura).where(Captura.instruccion_id == ins.id).values(instruccion_id=None))
    auditar(bd, actor, "borrar_borrador", "instruccion", ins.id,
            {"tarea_id": ins.tarea_id, "version": ins.version, "titulo": ins.titulo})
    registrar(bd, actor, "borro", "instruccion", ins.id, f"{ins.codigo} v{ins.version} · {ins.titulo}",
              contexto={"tarea_id": ins.tarea_id, "version": ins.version})
    bd.delete(ins)
    bd.commit()
    borrar_imagenes_sin_uso(bd, propias)


# --------------------------------------------------------------------------- publicación


def texto_indexable(ins: Instruccion) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
    """Texto completo y partes para el motor: una parte general y una por paso (con su paso_id)."""
    base = {"instruccion_id": ins.id, "codigo": ins.codigo}
    general = [f"{ins.codigo} · {ins.titulo} (versión {ins.version})"]
    if ins.tarea:
        general.append(f"Tarea: {ins.tarea.nombre}")
    for etiqueta, valor in (("Resumen", ins.resumen), ("Riesgos", ins.riesgos), ("EPIs", ins.epis),
                            ("Herramientas", ins.herramientas)):
        if valor:
            general.append(f"{etiqueta}: {valor}")
    partes: list[tuple[str, dict[str, Any]]] = [("\n".join(general), {**base, "paso": 0, "paso_id": None, "seccion": "general"})]
    for p in ins.pasos:
        marcas = [m for m, si in (("PASO CRÍTICO", p.es_critico), ("SEGURIDAD", p.es_seguridad)) if si]
        lineas = [f"Paso {p.orden}. {p.titulo}" + (f" [{' · '.join(marcas)}]" if marcas else "")]
        if p.texto:
            lineas.append(p.texto)
        if p.criterio_aceptacion:
            lineas.append(f"Criterio de aceptación: {p.criterio_aceptacion}")
        partes.append(("\n".join(lineas), {**base, "paso": p.orden, "paso_id": p.id}))
    return "\n\n".join(t for t, _ in partes), partes


def _indexando(bd: Session, documento_id: int) -> bool:
    """¿Tiene el documento un indexado pendiente o en curso en la cola de trabajos?"""
    return bd.scalar(select(Trabajo.id).where(Trabajo.entidad == "documento", Trabajo.entidad_id == documento_id,
                                              Trabajo.estado.in_(("pendiente", "en_curso"))).limit(1)) is not None


def _retirar_documento(bd: Session, documento_id: int) -> None:
    """El documento de una versión que pasa a obsoleta deja de encontrarse (se conserva la fila)."""
    doc = bd.get(Documento, documento_id)
    if doc is None:
        return
    try:
        motor().borrar(bd, doc)
    except Exception:  # noqa: BLE001
        log.exception("No se pudo retirar del motor el documento %s", doc.id)
    doc.estado = "obsoleto"
    doc.fragmentos_n = 0
    doc.mensaje_estado = "Sustituido por una versión posterior de la instrucción."


def publicar_con_detalle(bd: Session, actor: Actor, instruccion_id: int) -> tuple[Instruccion, int]:
    """Como `publicar`, pero devuelve también cuántas personas quedan marcadas para reevaluación."""
    from cidia.servicios import evaluacion, formacion, iluo  # aquí para evitar importaciones circulares

    ins = obtener(bd, actor, instruccion_id)
    # Una publicación por tarea a la vez: con la tarea bloqueada se vuelve a leer el estado, así un
    # doble clic no publica dos veces ni dos borradores a la vez quedan los dos como vigentes.
    bd.flush()  # (refresh descarta lo no guardado: quien llama puede haber tocado la instrucción)
    bloquear_tarea(bd, ins.tarea_id)
    bd.refresh(ins)
    if ins.estado == "publicada":
        raise HTTPException(409, "Esta versión ya está publicada.")
    if ins.estado == "obsoleta":
        raise HTTPException(409, "Esta versión está obsoleta. Crea una nueva versión desde la vigente.")
    if not (ins.titulo or "").strip():
        raise HTTPException(400, "La instrucción necesita un título.")
    if not ins.pasos:
        raise HTTPException(400, "Añade al menos un paso antes de publicar.")
    for p in ins.pasos:
        if not (p.titulo or "").strip():
            raise HTTPException(400, f"El paso {p.orden} no tiene título.")
    tarea = ins.tarea
    dep = departamento_de(tarea)
    otras = bd.scalars(select(Instruccion).where(Instruccion.tarea_id == tarea.id, Instruccion.id != ins.id)
                       .execution_options(populate_existing=True)).all()
    # Si entretanto se publicó una versión posterior, esta pasa a ser la siguiente.
    if any(o.version > ins.version and o.estado not in EDITABLES for o in otras):
        ins.version = max(o.version for o in otras) + 1
    anteriores = [o for o in otras if o.estado == "publicada"]
    # Si la vigente aún se está indexando, su trabajo terminaría después de retirarla y la dejaría otra
    # vez al alcance del copiloto junto a la nueva: hay que esperar a que acabe.
    indexando = [o for o in anteriores if o.documento_id and _indexando(bd, o.documento_id)]
    if indexando:
        raise HTTPException(409, f"La versión {indexando[0].version} todavía se está preparando para el copiloto. "
                                 "Espera a que termine (suele tardar uno o dos minutos) y vuelve a publicar.")
    for o in anteriores:
        o.estado = "obsoleta"
        if o.documento_id:
            _retirar_documento(bd, o.documento_id)
    ins.estado = "publicada"
    ins.revisor_id = actor.id
    ins.publicada_en = ahora()
    bd.flush()
    try:
        # En un punto de guardado: si falla (p. ej., un error de SQL), se deshace solo lo suyo y la
        # sesión sigue utilizable para terminar la publicación.
        with bd.begin_nested():
            reevaluaciones = iluo.marcar_reevaluacion(bd, tarea.id) or 0
    except Exception:  # noqa: BLE001
        log.exception("No se pudo marcar la reevaluación de la tarea %s", tarea.id)
        reevaluaciones = 0
    nombre = f"{ins.codigo} v{ins.version} · {ins.titulo}"
    registrar(bd, actor, "publico", "instruccion", ins.id, nombre,
              resultado={"version": ins.version, "pasos": len(ins.pasos), "reevaluaciones": reevaluaciones},
              contexto={"tarea_id": tarea.id, "departamento_id": dep, "obsoletas": [o.id for o in anteriores]})
    auditar(bd, actor, "publicar_instruccion", "instruccion", ins.id,
            {"tarea_id": tarea.id, "version": ins.version, "obsoletas": [o.id for o in anteriores]})
    texto, partes = texto_indexable(ins)
    # Hace commit de todo lo anterior y encola el indexado en la base del departamento.
    doc = documentos.crear_desde_texto(
        bd, titulo=f"{ins.codigo} · {ins.titulo} (v{ins.version})", texto=texto, tipo="instruccion",
        departamento_id=dep, nivel_minimo=tarea.nivel_minimo or 1, es_formacion=True, es_publico=False,
        autor_id=ins.autor_id, validador_id=actor.id, subido_por_id=actor.id, origen="instruccion",
        origen_id=ins.id, version=ins.version, partes=partes, en_segundo_plano=True, descripcion=ins.resumen,
    )
    ins.documento_id = doc.id
    bd.commit()
    # Micro-lecciones y preguntas: trabajos de sus módulos, que leen la versión ya publicada.
    for encolar in (formacion.encolar_generacion, evaluacion.encolar_generacion):
        try:
            encolar(ins.id)
        except Exception:  # noqa: BLE001
            log.exception("No se pudo encolar %s para la instrucción %s", encolar.__module__, ins.id)
    bd.refresh(ins)
    return ins, reevaluaciones


def publicar(bd: Session, actor: Actor, instruccion_id: int) -> Instruccion:
    """Publica un borrador (contrato). Solo expertos, jefes o administración del departamento de la
    tarea; quien publica queda como revisor. La versión publicada anterior pasa a obsoleta y deja de
    encontrarse; la nueva se indexa (tipo «instruccion», una parte por paso con {paso, paso_id,
    instruccion_id, codigo}), se marca la reevaluación ILUO y se encolan micro-lecciones y preguntas.
    Hace commit: los trabajos encolados deben ver ya la versión publicada."""
    return publicar_con_detalle(bd, actor, instruccion_id)[0]


# --------------------------------------------------------------------------- diferencias

CAMPOS_GENERALES = (("titulo", "Título"), ("resumen", "Resumen"), ("riesgos", "Riesgos"), ("epis", "EPIs"),
                    ("herramientas", "Herramientas"))
CAMPOS_PASO = (("titulo", "Título"), ("texto", "Texto"), ("criterio_aceptacion", "Criterio de aceptación"),
               ("es_critico", "Paso crítico"), ("es_seguridad", "Seguridad"), ("imagen_ruta", "Imagen"),
               ("clip_ruta", "Clip"))


def _valor(campo: str, v: Any) -> Any:
    if campo in ("imagen_ruta", "clip_ruta"):
        return url_fichero(v)
    if isinstance(v, bool):
        return "Sí" if v else "No"
    return (v or "").strip() if isinstance(v, str) or v is None else v


def _campos_cambiados(a: Paso, b: Paso) -> list[dict[str, Any]]:
    salida = []
    for campo, nombre in CAMPOS_PASO:
        va, vb = getattr(a, campo), getattr(b, campo)
        if (va or None) != (vb or None) and not (isinstance(va, str) and isinstance(vb, str) and va.strip() == vb.strip()):
            salida.append({"campo": campo, "nombre": nombre, "antes": _valor(campo, va), "despues": _valor(campo, vb)})
    return salida


def _clave(titulo: str | None) -> str:
    return " ".join((titulo or "").lower().split())


def _parecidos(a: Paso, b: Paso) -> bool:
    """¿Es el mismo paso con otro título? (contenido parecido en al menos un 50 %)."""
    ta, tb = _clave(f"{a.titulo} {a.texto or ''}"), _clave(f"{b.titulo} {b.texto or ''}")
    return SequenceMatcher(a=ta, b=tb, autojunk=False).ratio() >= 0.5


def comparar(antes: Instruccion, despues: Instruccion) -> dict[str, Any]:
    """Cambios de `antes` a `despues`: campos generales y lista de cambios por paso
    (nuevo, eliminado, modificado o movido). Los pasos se emparejan por título."""
    generales = []
    for campo, nombre in CAMPOS_GENERALES:
        va, vb = (getattr(antes, campo) or "").strip(), (getattr(despues, campo) or "").strip()
        if va != vb:
            generales.append({"campo": campo, "nombre": nombre, "antes": va, "despues": vb})
    a, b = list(antes.pasos), list(despues.pasos)
    cambios: list[dict[str, Any]] = []
    sm = SequenceMatcher(a=[_clave(p.titulo) for p in a], b=[_clave(p.titulo) for p in b], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for pa, pb in zip(a[i1:i2], b[j1:j2], strict=True):
                campos = _campos_cambiados(pa, pb)
                if campos:
                    cambios.append({"tipo": "modificado", "orden_antes": pa.orden, "orden_despues": pb.orden,
                                    "titulo": pb.titulo, "campos": campos})
            continue
        # Bloques distintos: un paso con el título cambiado pero contenido parecido es el mismo paso
        # modificado; si no se parecen, es una baja y un alta.
        pares = min(i2 - i1, j2 - j1) if op == "replace" else 0
        bajas, altas = list(a[i1 + pares:i2]), list(b[j1 + pares:j2])
        for pa, pb in zip(a[i1:i1 + pares], b[j1:j1 + pares], strict=True):
            if _parecidos(pa, pb):
                cambios.append({"tipo": "modificado", "orden_antes": pa.orden, "orden_despues": pb.orden,
                                "titulo": pb.titulo, "campos": _campos_cambiados(pa, pb)})
            else:
                bajas.append(pa)
                altas.append(pb)
        for pa in bajas:
            cambios.append({"tipo": "eliminado", "orden_antes": pa.orden, "orden_despues": None,
                            "titulo": pa.titulo, "campos": []})
        for pb in altas:
            cambios.append({"tipo": "nuevo", "orden_antes": None, "orden_despues": pb.orden,
                            "titulo": pb.titulo, "campos": []})
    # Un paso eliminado y otro nuevo con el mismo título es un paso que se ha movido.
    eliminados = {_clave(c["titulo"]): c for c in cambios if c["tipo"] == "eliminado"}
    for c in [c for c in cambios if c["tipo"] == "nuevo"]:
        previo = eliminados.pop(_clave(c["titulo"]), None)
        if previo is None:
            continue
        pa = next(p for p in a if p.orden == previo["orden_antes"])
        pb = next(p for p in b if p.orden == c["orden_despues"])
        cambios.remove(previo)
        c.update(tipo="movido", orden_antes=pa.orden, campos=_campos_cambiados(pa, pb))
    cambios.sort(key=lambda c: (c["orden_despues"] or c["orden_antes"] or 0, c["orden_despues"] is None))
    return {
        "de": {"id": antes.id, "version": antes.version, "estado": antes.estado},
        "a": {"id": despues.id, "version": despues.version, "estado": despues.estado},
        "generales": generales,
        "pasos": cambios,
        "sin_cambios": not generales and not cambios,
    }


def diferencias(bd: Session, actor: Actor, instruccion_id: int, con_id: int | None = None) -> dict[str, Any]:
    """Compara una versión con otra de la misma tarea (por defecto, con la anterior)."""
    ins = obtener(bd, actor, instruccion_id)
    if con_id is not None:
        otra = obtener(bd, actor, con_id)
        if otra.tarea_id != ins.tarea_id:
            raise HTTPException(400, "Solo se pueden comparar versiones de la misma tarea.")
    else:
        otra = bd.scalar(select(Instruccion).where(Instruccion.tarea_id == ins.tarea_id, Instruccion.version < ins.version)
                         .order_by(Instruccion.version.desc()).limit(1))
        if otra is None:
            return {"de": None, "a": {"id": ins.id, "version": ins.version, "estado": ins.estado},
                    "generales": [], "pasos": [], "sin_cambios": True, "sin_anterior": True}
    antes, despues = (otra, ins) if otra.version <= ins.version else (ins, otra)
    return comparar(antes, despues)
