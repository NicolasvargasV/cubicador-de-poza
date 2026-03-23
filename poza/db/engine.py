"""
poza/db/engine.py
─────────────────
Configura el motor SQLAlchemy y la fábrica de sesiones.

Lógica de ruta del archivo .sqlite:
  - Corriendo desde fuente (.py): <raíz del proyecto>/data/cubicador.db
  - Corriendo como .exe (PyInstaller): <carpeta del .exe>/data/cubicador.db

Así el archivo de datos viaja junto al ejecutable en producción,
y queda fuera del repositorio git (cubierto por .gitignore).

Para migrar a PostgreSQL en el futuro, basta cambiar DATABASE_URL:
    "postgresql://usuario:clave@servidor/cubicador"
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session


def get_db_path() -> Path:
    """Resuelve la ruta al archivo .sqlite según el entorno de ejecución."""
    if getattr(sys, "_MEIPASS", None):
        # Empaquetado como .exe → carpeta junto al ejecutable
        base = Path(sys.executable).parent
    else:
        # Desde fuente → raíz del proyecto (dos niveles arriba de este archivo)
        base = Path(__file__).resolve().parent.parent.parent

    db_dir = base / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "cubicador.db"


def _build_engine():
    db_path = get_db_path()
    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        echo=False,          # Cambiar a True para ver SQL en consola (debug)
    )

    # Activa foreign keys en SQLite (por defecto están desactivadas)
    @event.listens_for(_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return _engine


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_session() -> Session:
    """Devuelve una nueva sesión. Usar con 'with' o cerrar manualmente."""
    return SessionLocal()
