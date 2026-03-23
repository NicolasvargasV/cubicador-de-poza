"""
poza/db
───────
Paquete de persistencia del Cubicador de Pozas.

Uso básico:
    from poza.db import init_db, get_session, Repository

    # Al inicio de la aplicación (una sola vez):
    init_db()

    # En cualquier operación de datos:
    with get_session() as session:
        repo = Repository(session)
        usuario = repo.authenticate("juan", "clave")
        repo.log("login", usuario=usuario)
"""

from .engine import engine, SessionLocal, get_session
from .models import Base, Usuario, Reservorio, Dem, Cubicacion, AuditLog
from .repository import Repository, AuthError, RepoError
from .seed import seed_database


def init_db() -> None:
    """
    Crea todas las tablas si no existen y carga datos iniciales.
    Llamar una vez al inicio de la aplicación.
    """
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_database(session)


__all__ = [
    # Inicialización
    "init_db",
    # Sesión
    "engine",
    "SessionLocal",
    "get_session",
    # Modelos
    "Base",
    "Usuario",
    "Reservorio",
    "Dem",
    "Cubicacion",
    "AuditLog",
    # Repositorio
    "Repository",
    "AuthError",
    "RepoError",
]
