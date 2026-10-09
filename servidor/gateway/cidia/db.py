"""Conexión a PostgreSQL y sesión por petición."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from cidia.config import ajustes


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_fabrica: sessionmaker[Session] | None = None


def motor_bd() -> Engine:
    global _engine, _fabrica
    if _engine is None:
        _engine = create_engine(ajustes().base_datos_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
        _fabrica = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def nueva_sesion() -> Session:
    motor_bd()
    assert _fabrica is not None
    return _fabrica()


def obtener_bd() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición."""
    with nueva_sesion() as s:
        yield s


@contextmanager
def sesion_bd() -> Iterator[Session]:
    """Sesión para trabajos en segundo plano y scripts."""
    s = nueva_sesion()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def inicializar_bd() -> None:
    """Crea la extensión vector y todas las tablas que falten."""
    from cidia import modelos  # noqa: F401  (registra las tablas)

    eng = motor_bd()
    with eng.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(eng)
