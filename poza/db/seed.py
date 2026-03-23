"""
poza/db/seed.py
───────────────
Datos iniciales del sistema. Se ejecuta solo si las tablas están vacías.

Incluye:
  - Reservorios R1–R10 (alineados con los DEMs existentes en DEMs/)
  - Usuario administrador por defecto (cambiar clave en primer uso)

IMPORTANTE: Cambiar la clave del admin en el primer login.
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import select

from .models import Usuario, Reservorio


# ─── Catálogo de reservorios del salar ───────────────────────────────────────
# Ajustar nombres si los reservorios tienen nombres operacionales específicos
RESERVORIOS = [
    {"codigo": f"R{i}", "nombre": f"Reservorio {i}"}
    for i in range(1, 11)
]

# ─── Credenciales del admin por defecto ──────────────────────────────────────
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Admin123!"   # ← CAMBIAR EN EL PRIMER INICIO
ADMIN_NOMBRE   = "Administrador"


def seed_database(session: Session) -> None:
    """
    Inicializa la base de datos con datos mínimos si está vacía.
    Es idempotente: puede llamarse múltiples veces sin duplicar datos.
    """
    import bcrypt

    # Reservorios
    for r_data in RESERVORIOS:
        exists = session.scalar(
            select(Reservorio).where(Reservorio.codigo == r_data["codigo"])
        )
        if not exists:
            session.add(Reservorio(codigo=r_data["codigo"], nombre=r_data["nombre"]))

    # Admin por defecto
    admin = session.scalar(select(Usuario).where(Usuario.username == ADMIN_USERNAME))
    if not admin:
        hashed = bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        session.add(Usuario(
            username=ADMIN_USERNAME,
            password_hash=hashed,
            nombre_completo=ADMIN_NOMBRE,
            rol="admin",
        ))

    session.commit()
