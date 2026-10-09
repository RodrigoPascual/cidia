"""Motor de conocimiento propio: PostgreSQL con pgvector y búsqueda de texto en castellano.

Búsqueda híbrida: una lista por similitud de vectores y otra por palabras (índice GIN con
la configuración 'spanish'), fusionadas con RRF. Los permisos se aplican en el propio SQL.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cidia.config import ajustes
from cidia.conocimiento.base import Encontrado, MotorConocimiento, fusion_rrf
from cidia.conocimiento.extraccion import extraer, trocear
from cidia.ia import llm
from cidia.modelos import Documento, Fragmento, Usuario
from cidia.permisos import Alcance, filtro_documentos

CANDIDATOS = 30
MAX_POR_DOCUMENTO = 3


class MotorPgvector(MotorConocimiento):
    nombre = "pgvector"

    # ------------------------------------------------------------------ indexado

    def indexar(
        self,
        bd: Session,
        doc: Documento,
        texto: str | None = None,
        partes: list[tuple[str, dict[str, Any]]] | None = None,
    ) -> int:
        if partes is None:
            if texto is not None:
                partes = [(texto, {})]
            elif doc.ruta_fichero:
                partes = extraer(ajustes().dir_datos / doc.ruta_fichero)
            else:
                partes = [(doc.contenido_texto or "", {})]
        trozos: list[tuple[str, dict[str, Any]]] = []
        for contenido, meta in partes:
            for t in trocear(contenido):
                trozos.append((t, meta))
        bd.execute(delete(Fragmento).where(Fragmento.documento_id == doc.id))
        if not trozos:
            return 0
        vectores = llm.embeddings([f"{doc.titulo}\n{t}" for t, _ in trozos])
        for i, ((t, meta), v) in enumerate(zip(trozos, vectores, strict=True)):
            bd.add(Fragmento(documento_id=doc.id, orden=i, texto=t, embedding=v, metadatos=meta))
        bd.flush()
        return len(trozos)

    def borrar(self, bd: Session, doc: Documento) -> None:
        bd.execute(delete(Fragmento).where(Fragmento.documento_id == doc.id))

    # ------------------------------------------------------------------ búsqueda

    def buscar(self, bd: Session, consulta: str, alcance: Alcance, k: int = 6) -> list[Encontrado]:
        consulta = (consulta or "").strip()
        if not consulta:
            return []
        filtro = filtro_documentos(alcance)
        # 1) por significado
        q = llm.embedding_consulta(consulta)
        dist = Fragmento.embedding.cosine_distance(q)
        por_vector = bd.execute(
            select(Fragmento.id, (1 - dist).label("sim"))
            .join(Documento, Documento.id == Fragmento.documento_id)
            .where(filtro, Fragmento.embedding.is_not(None), func.vector_dims(Fragmento.embedding) == len(q))
            .order_by(dist)
            .limit(CANDIDATOS)
        ).all()
        # 2) por palabras exactas (cualquiera de los términos)
        palabras = re.findall(r"[\wáéíóúüñÁÉÍÓÚÜÑ][\wáéíóúüñÁÉÍÓÚÜÑ\-./]*", consulta)
        por_texto = []
        if palabras:
            tsq = func.websearch_to_tsquery("spanish", " or ".join(palabras[:30]))
            rango = func.ts_rank_cd(Fragmento.tsv, tsq)
            por_texto = bd.execute(
                select(Fragmento.id, rango.label("rango"))
                .join(Documento, Documento.id == Fragmento.documento_id)
                .where(filtro, Fragmento.tsv.op("@@")(tsq))
                .order_by(rango.desc())
                .limit(CANDIDATOS)
            ).all()
        # 3) fusión
        puntos = fusion_rrf([por_vector, por_texto], clave=lambda fila: fila[0])
        sims = {fid: float(sim) for fid, sim in por_vector}
        rangos = {fid: float(r) for fid, r in por_texto}
        orden = sorted(puntos, key=puntos.get, reverse=True)
        if not orden:
            return []
        frags = {f.id: f for f in bd.scalars(select(Fragmento).where(Fragmento.id.in_(orden[: k * 4]))).all()}
        docs = {d.id: d for d in bd.scalars(select(Documento).where(Documento.id.in_({f.documento_id for f in frags.values()}))).all()}
        salida: list[Encontrado] = []
        por_doc: dict[int, int] = {}
        for fid in orden:
            f = frags.get(fid)
            if f is None:
                continue
            d = docs[f.documento_id]
            if por_doc.get(d.id, 0) >= MAX_POR_DOCUMENTO:
                continue
            por_doc[d.id] = por_doc.get(d.id, 0) + 1
            meta = dict(f.metadatos or {})
            meta.update(metadatos_documento(bd, d))
            meta["coincidencia_texto"] = fid in rangos
            salida.append(
                Encontrado(
                    documento_id=d.id,
                    titulo=d.titulo,
                    texto=f.texto,
                    puntuacion=puntos[fid],
                    similitud=sims.get(fid),
                    metadatos=meta,
                    fragmento_id=fid,
                )
            )
            if len(salida) >= k:
                break
        return salida

    def salud(self) -> dict[str, Any]:
        return {"ok": True, "motor": self.nombre}


def metadatos_documento(bd: Session, d: Documento) -> dict[str, Any]:
    """Datos de un documento que se muestran en las citas."""
    autor = bd.get(Usuario, d.autor_id) if d.autor_id else None
    validador = bd.get(Usuario, d.validador_id) if d.validador_id else None
    return {
        "tipo": d.tipo,
        "version": d.version,
        "departamento_id": d.departamento_id,
        "origen": d.origen,
        "origen_id": d.origen_id,
        "autor": autor.nombre if autor else None,
        "validador": validador.nombre if validador else None,
        "es_formacion": d.es_formacion,
    }
