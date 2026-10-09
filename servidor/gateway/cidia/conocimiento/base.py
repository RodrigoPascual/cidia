"""Interfaz común de los motores de conocimiento."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from cidia.modelos import Documento
from cidia.permisos import Alcance


@dataclass
class Encontrado:
    """Fragmento devuelto por una búsqueda, ya filtrado por permisos."""

    documento_id: int
    titulo: str
    texto: str
    puntuacion: float  # puntuación fusionada (RRF), para ordenar
    similitud: float | None = None  # similitud semántica (0..1) del fragmento, para decidir si hay respaldo
    metadatos: dict[str, Any] = field(default_factory=dict)
    fragmento_id: int | str | None = None


class MotorConocimiento(ABC):
    nombre = "base"
    externo = False  # True si los datos viven fuera de PostgreSQL (WeKnora): hay que reetiquetar

    @abstractmethod
    def indexar(
        self,
        bd: Session,
        doc: Documento,
        texto: str | None = None,
        partes: list[tuple[str, dict[str, Any]]] | None = None,
    ) -> int:
        """Indexa un documento. Fuente, por prioridad: `partes` [(texto, metadatos)], `texto`
        o el fichero doc.ruta_fichero. Devuelve el número de fragmentos."""

    @abstractmethod
    def borrar(self, bd: Session, doc: Documento) -> None:
        """Elimina el documento del índice."""

    @abstractmethod
    def buscar(self, bd: Session, consulta: str, alcance: Alcance, k: int = 6) -> list[Encontrado]:
        """Búsqueda híbrida limitada al alcance."""

    def salud(self) -> dict[str, Any]:
        return {"ok": True}

    def reetiquetar(self, bd: Session, doc: Documento) -> bool:
        """Actualiza las etiquetas de permisos de un documento ya indexado. El motor propio
        filtra por SQL y no necesita nada; un motor externo debe reetiquetar o reindexar."""
        return True

    def ambitos(self, bd: Session, alcance: Alcance) -> list[dict[str, Any]] | None:
        """Bases y etiquetas del motor externo que corresponden a un alcance (depuración)."""
        return None


def fusion_rrf(listas: list[list[Any]], clave: Any, k: int = 60) -> dict[Any, float]:
    """Reciprocal Rank Fusion: suma 1/(k + posición) de cada elemento en cada lista."""
    puntos: dict[Any, float] = {}
    for lista in listas:
        for pos, elem in enumerate(lista, start=1):
            c = clave(elem)
            puntos[c] = puntos.get(c, 0.0) + 1.0 / (k + pos)
    return puntos
