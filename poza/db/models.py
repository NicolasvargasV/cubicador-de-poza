"""
poza/db/models.py
─────────────────
Modelos ORM (SQLAlchemy 2.0) para el Cubicador de Pozas.

Tablas:
  usuarios      → operadores y administradores del sistema
  reservorios   → catálogo de pozas con sus rutas DEM/contorno por defecto
  dems          → registro de cada archivo DEM cargado por reservorio
  cubicaciones  → historial completo de cada cálculo realizado
  audit_log     → registro de acciones para trazabilidad y firmas legales
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Usuarios
# ─────────────────────────────────────────────────────────────────────────────

class Usuario(Base):
    """
    Operadores y administradores del sistema.

    rol:
      'admin'    → puede crear usuarios, ver todos los logs, configurar reservorios
      'operador' → puede cargar DEMs, calcular, exportar y firmar informes propios
    """
    __tablename__ = "usuarios"

    id:               Mapped[int]  = mapped_column(Integer, primary_key=True)
    username:         Mapped[str]  = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash:    Mapped[str]  = mapped_column(String(128), nullable=False)
    nombre_completo:  Mapped[str]  = mapped_column(String(128), nullable=False)
    rol:              Mapped[str]  = mapped_column(String(16), default="operador")
    activo:           Mapped[bool] = mapped_column(Boolean, default=True)
    created_at:       Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    cubicaciones:  Mapped[list["Cubicacion"]] = relationship(back_populates="usuario")
    audit_logs:    Mapped[list["AuditLog"]]   = relationship(
        back_populates="usuario",
        foreign_keys="AuditLog.usuario_id",
    )

    def __repr__(self) -> str:
        return f"<Usuario {self.username!r} [{self.rol}]>"


# ─────────────────────────────────────────────────────────────────────────────
# Reservorios
# ─────────────────────────────────────────────────────────────────────────────

class Reservorio(Base):
    """
    Catálogo de pozas/reservorios del salar.

    dem_default  → ruta al último DEM usado (se actualiza automáticamente).
    mask_default → ruta al contorno GeoJSON activo para este reservorio.
    """
    __tablename__ = "reservorios"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    codigo:       Mapped[str]           = mapped_column(String(16), unique=True, nullable=False)
    nombre:       Mapped[str]           = mapped_column(String(128), nullable=False)
    dem_default:  Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mask_default: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activo:       Mapped[bool]          = mapped_column(Boolean, default=True)
    created_at:   Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)

    cubicaciones: Mapped[list["Cubicacion"]] = relationship(back_populates="reservorio")
    dems:         Mapped[list["Dem"]]        = relationship(back_populates="reservorio")

    def __repr__(self) -> str:
        return f"<Reservorio {self.codigo!r}: {self.nombre!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# DEMs
# ─────────────────────────────────────────────────────────────────────────────

class Dem(Base):
    """
    Registro de cada archivo DEM cargado para un reservorio.

    Permite mantener historial de vuelos fotogramétricos y saber qué DEM
    se usó en cada cubicación.
    """
    __tablename__ = "dems"

    id:            Mapped[int]           = mapped_column(Integer, primary_key=True)
    reservorio_id: Mapped[int]           = mapped_column(ForeignKey("reservorios.id"), nullable=False)
    archivo:       Mapped[str]           = mapped_column(String(256), nullable=False)
    ruta:          Mapped[str]           = mapped_column(Text, nullable=False)
    fecha_vuelo:   Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    cargado_por:   Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    created_at:    Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)

    reservorio:           Mapped["Reservorio"]        = relationship(back_populates="dems")
    cargado_por_usuario:  Mapped[Optional["Usuario"]] = relationship(foreign_keys=[cargado_por])
    cubicaciones:         Mapped[list["Cubicacion"]]  = relationship(back_populates="dem")

    def __repr__(self) -> str:
        return f"<Dem {self.archivo!r} → R{self.reservorio_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# Cubicaciones
# ─────────────────────────────────────────────────────────────────────────────

class Cubicacion(Base):
    """
    Resultado completo de cada cálculo de volumen.

    Almacena todos los parámetros de entrada y resultados para:
      - Historial por reservorio (tabla en la GUI)
      - Detección de anomalías (cota sal estática, volumen repetido)
      - Generación de informes firmados
    """
    __tablename__ = "cubicaciones"

    id:                     Mapped[int]           = mapped_column(Integer, primary_key=True)
    reservorio_id:          Mapped[int]           = mapped_column(ForeignKey("reservorios.id"), nullable=False)
    dem_id:                 Mapped[Optional[int]] = mapped_column(ForeignKey("dems.id"), nullable=True)
    usuario_id:             Mapped[int]           = mapped_column(ForeignKey("usuarios.id"), nullable=False)

    # Parámetros de entrada
    cota_sal:               Mapped[float] = mapped_column(Float, nullable=False)
    cota_agua:              Mapped[float] = mapped_column(Float, nullable=False)
    fraccion_ocluida:       Mapped[float] = mapped_column(Float, nullable=False)

    # Resultados
    vol_sal_m3:             Mapped[Optional[float]] = mapped_column(Float)
    vol_salmuera_libre_m3:  Mapped[Optional[float]] = mapped_column(Float)
    vol_salmuera_ocluida_m3: Mapped[Optional[float]] = mapped_column(Float)
    vol_salmuera_total_m3:  Mapped[Optional[float]] = mapped_column(Float)
    area_espejo_m2:         Mapped[Optional[float]] = mapped_column(Float)

    notas:      Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)

    reservorio: Mapped["Reservorio"]        = relationship(back_populates="cubicaciones")
    dem:        Mapped[Optional["Dem"]]     = relationship(back_populates="cubicaciones")
    usuario:    Mapped["Usuario"]           = relationship(back_populates="cubicaciones")

    def __repr__(self) -> str:
        return (
            f"<Cubicacion R{self.reservorio_id} "
            f"sal={self.cota_sal} agua={self.cota_agua} "
            f"@ {self.created_at:%Y-%m-%d %H:%M}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Audit Log
# ─────────────────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """
    Registro inmutable de todas las acciones del sistema.

    El campo 'username' se guarda desnormalizado (además del FK) para que
    el log sea legible incluso si el usuario es eliminado en el futuro.

    Acciones esperadas:
      login, logout, login_fallido,
      cubicacion_calculada, dem_cargado, csv_exportado,
      informe_generado, usuario_creado, usuario_modificado
    """
    __tablename__ = "audit_log"

    id:         Mapped[int]           = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    username:   Mapped[Optional[str]] = mapped_column(String(64))  # desnormalizado
    accion:     Mapped[str]           = mapped_column(String(64), nullable=False, index=True)
    detalle:    Mapped[Optional[str]] = mapped_column(Text)        # JSON serializado
    created_at: Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow, index=True)

    usuario: Mapped[Optional["Usuario"]] = relationship(
        back_populates="audit_logs",
        foreign_keys=[usuario_id],
    )

    def detalle_dict(self) -> dict:
        """Deserializa el campo JSON de detalle."""
        if not self.detalle:
            return {}
        try:
            return json.loads(self.detalle)
        except Exception:
            return {"raw": self.detalle}

    def __repr__(self) -> str:
        return f"<AuditLog [{self.accion!r}] by {self.username!r} @ {self.created_at:%Y-%m-%d %H:%M}>"
