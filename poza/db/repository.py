"""
poza/db/repository.py
─────────────────────
Capa de acceso a datos. La GUI y la lógica de negocio solo hablan con
esta clase, nunca con SQLAlchemy ni SQL directamente.

Ventaja: cuando se migre a PostgreSQL, solo cambia la cadena de conexión
en engine.py. Este archivo no necesita tocar.

Uso:
    from poza.db import get_session, Repository

    with get_session() as session:
        repo = Repository(session)
        user = repo.authenticate("juan", "mi_clave")
        repo.log("login", usuario=user)
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from .models import Usuario, Reservorio, Dem, Cubicacion, AuditLog
from ..core import PondVolumes


# ─────────────────────────────────────────────────────────────────────────────
# Errores de dominio
# ─────────────────────────────────────────────────────────────────────────────

class AuthError(Exception):
    """Fallo de autenticación (usuario no existe, clave incorrecta, inactivo)."""


class RepoError(Exception):
    """Error genérico del repositorio."""


# ─────────────────────────────────────────────────────────────────────────────
# Repositorio
# ─────────────────────────────────────────────────────────────────────────────

class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ── Utilidad interna ──────────────────────────────────────────────────────

    def _commit_and_refresh(self, obj):
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj

    # ═════════════════════════════════════════════════════════════════════════
    # USUARIOS
    # ═════════════════════════════════════════════════════════════════════════

    def authenticate(self, username: str, password: str) -> Usuario:
        """
        Verifica credenciales y retorna el Usuario si son válidas.
        Lanza AuthError en caso contrario.
        Importación diferida de bcrypt para no bloquear el inicio si falta.
        """
        import bcrypt

        user: Optional[Usuario] = self.session.scalar(
            select(Usuario).where(Usuario.username == username)
        )
        if user is None:
            raise AuthError("Usuario no encontrado.")
        if not user.activo:
            raise AuthError("El usuario está desactivado.")
        if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
            raise AuthError("Contraseña incorrecta.")
        return user

    def create_user(
        self,
        username: str,
        password: str,
        nombre_completo: str,
        rol: str = "operador",
    ) -> Usuario:
        """Crea un usuario nuevo con la contraseña hasheada con bcrypt."""
        import bcrypt

        existing = self.session.scalar(select(Usuario).where(Usuario.username == username))
        if existing:
            raise RepoError(f"El username '{username}' ya existe.")

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        user = Usuario(
            username=username,
            password_hash=hashed,
            nombre_completo=nombre_completo,
            rol=rol,
        )
        return self._commit_and_refresh(user)

    def update_password(self, usuario_id: int, new_password: str) -> None:
        """Actualiza la contraseña de un usuario."""
        import bcrypt

        user = self.session.get(Usuario, usuario_id)
        if not user:
            raise RepoError("Usuario no encontrado.")
        user.password_hash = bcrypt.hashpw(
            new_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        self.session.commit()

    def set_user_active(self, usuario_id: int, activo: bool) -> None:
        user = self.session.get(Usuario, usuario_id)
        if user:
            user.activo = activo
            self.session.commit()

    def list_users(self) -> list[Usuario]:
        return list(self.session.scalars(select(Usuario).order_by(Usuario.username)))

    def get_user_by_id(self, usuario_id: int) -> Optional[Usuario]:
        return self.session.get(Usuario, usuario_id)

    # ═════════════════════════════════════════════════════════════════════════
    # RESERVORIOS
    # ═════════════════════════════════════════════════════════════════════════

    def list_reservorios(self) -> list[Reservorio]:
        return list(self.session.scalars(
            select(Reservorio)
            .where(Reservorio.activo == True)
            .order_by(Reservorio.codigo)
        ))

    def get_reservorio_by_codigo(self, codigo: str) -> Optional[Reservorio]:
        return self.session.scalar(
            select(Reservorio).where(Reservorio.codigo == codigo)
        )

    def get_reservorio_by_id(self, reservorio_id: int) -> Optional[Reservorio]:
        return self.session.get(Reservorio, reservorio_id)

    def update_reservorio_defaults(
        self,
        reservorio_id: int,
        dem_path: Optional[str] = None,
        mask_path: Optional[str] = None,
    ) -> None:
        """Actualiza las rutas por defecto del reservorio (DEM y/o contorno)."""
        r = self.session.get(Reservorio, reservorio_id)
        if not r:
            raise RepoError(f"Reservorio id={reservorio_id} no encontrado.")
        if dem_path is not None:
            r.dem_default = dem_path
        if mask_path is not None:
            r.mask_default = mask_path
        self.session.commit()

    # ═════════════════════════════════════════════════════════════════════════
    # DEMs
    # ═════════════════════════════════════════════════════════════════════════

    def register_dem(
        self,
        reservorio_id: int,
        archivo: str,
        ruta: str,
        usuario_id: Optional[int] = None,
        fecha_vuelo: Optional[str] = None,
    ) -> Dem:
        """Registra un nuevo DEM en el historial del reservorio."""
        dem = Dem(
            reservorio_id=reservorio_id,
            archivo=archivo,
            ruta=ruta,
            cargado_por=usuario_id,
            fecha_vuelo=fecha_vuelo,
        )
        return self._commit_and_refresh(dem)

    def list_dems(self, reservorio_id: int) -> list[Dem]:
        """Retorna todos los DEMs de un reservorio, del más reciente al más antiguo."""
        return list(self.session.scalars(
            select(Dem)
            .where(Dem.reservorio_id == reservorio_id)
            .order_by(desc(Dem.created_at))
        ))

    def get_last_dem(self, reservorio_id: int) -> Optional[Dem]:
        """Retorna el DEM más reciente cargado para un reservorio."""
        return self.session.scalar(
            select(Dem)
            .where(Dem.reservorio_id == reservorio_id)
            .order_by(desc(Dem.created_at))
            .limit(1)
        )

    def get_dem_by_id(self, dem_id: int) -> Optional[Dem]:
        return self.session.get(Dem, dem_id)

    # ═════════════════════════════════════════════════════════════════════════
    # CUBICACIONES
    # ═════════════════════════════════════════════════════════════════════════

    def save_cubicacion(
        self,
        reservorio_id: int,
        usuario_id: int,
        volumes: PondVolumes,
        dem_id: Optional[int] = None,
        notas: Optional[str] = None,
    ) -> Cubicacion:
        """Persiste el resultado de un cálculo de volumen."""
        c = Cubicacion(
            reservorio_id=reservorio_id,
            dem_id=dem_id,
            usuario_id=usuario_id,
            cota_sal=volumes.salt_level,
            cota_agua=volumes.water_level,
            fraccion_ocluida=volumes.occluded_fraction,
            vol_sal_m3=volumes.salt_total_m3,
            vol_salmuera_libre_m3=volumes.brine_free_m3,
            vol_salmuera_ocluida_m3=volumes.brine_occluded_m3,
            vol_salmuera_total_m3=volumes.brine_total_m3,
            area_espejo_m2=volumes.area_wet_m2,
            notas=notas,
        )
        return self._commit_and_refresh(c)

    def get_last_cubicacion(self, reservorio_id: int) -> Optional[Cubicacion]:
        """Retorna la cubicación más reciente del reservorio."""
        return self.session.scalar(
            select(Cubicacion)
            .where(Cubicacion.reservorio_id == reservorio_id)
            .order_by(desc(Cubicacion.created_at))
            .limit(1)
        )

    def list_cubicaciones(self, reservorio_id: int, limit: int = 100) -> list[Cubicacion]:
        """Retorna el historial de cubicaciones de un reservorio."""
        return list(self.session.scalars(
            select(Cubicacion)
            .where(Cubicacion.reservorio_id == reservorio_id)
            .order_by(desc(Cubicacion.created_at))
            .limit(limit)
        ))

    # ═════════════════════════════════════════════════════════════════════════
    # DETECCIÓN DE ANOMALÍAS
    # ═════════════════════════════════════════════════════════════════════════

    def check_volume_anomaly(
        self,
        reservorio_id: int,
        new_vol_total: float,
        tolerance_pct: float = 2.0,
    ) -> Optional[str]:
        """
        Compara el nuevo volumen total con la última cubicación.
        Retorna un mensaje de alerta si la variación es menor al umbral,
        None si todo está bien.

        tolerance_pct: variación mínima esperada (%). Default 2%.
        """
        last = self.get_last_cubicacion(reservorio_id)
        if last is None or last.vol_salmuera_total_m3 is None:
            return None

        prev = last.vol_salmuera_total_m3
        if prev == 0:
            return None

        variation = abs(new_vol_total - prev) / abs(prev) * 100
        if variation < tolerance_pct:
            return (
                f"⚠️  Cubicación casi idéntica a la anterior:\n"
                f"   Anterior: {prev:,.1f} m³  →  Nueva: {new_vol_total:,.1f} m³\n"
                f"   Variación: {variation:.2f}% (umbral: {tolerance_pct}%)\n\n"
                f"   Verificar si el cálculo fue intencional."
            )
        return None

    def check_salt_static(
        self,
        reservorio_id: int,
        new_cota_sal: float,
        n_consecutive: int = 3,
        tolerance_m: float = 0.01,
    ) -> Optional[str]:
        """
        Verifica si la cota de sal lleva N cubicaciones sin cambiar.
        Esto suele indicar error humano (la sal siempre debería seguir decantando).

        n_consecutive: cuántas cubicaciones iguales consecutivas disparan la alerta.
        tolerance_m: diferencia mínima esperada en metros.
        """
        recent = list(self.session.scalars(
            select(Cubicacion.cota_sal)
            .where(Cubicacion.reservorio_id == reservorio_id)
            .order_by(desc(Cubicacion.created_at))
            .limit(n_consecutive)
        ))

        if len(recent) < n_consecutive:
            return None

        # Verificar si todas las cotas recientes + la nueva son iguales dentro de la tolerancia
        all_levels = [new_cota_sal] + recent
        diffs = [abs(all_levels[i] - all_levels[i + 1]) for i in range(len(all_levels) - 1)]
        if all(d < tolerance_m for d in diffs):
            return (
                f"⚠️  Cota de sal estática detectada:\n"
                f"   Las últimas {n_consecutive + 1} cubicaciones tienen cota sal ≈ {new_cota_sal:.3f} m\n"
                f"   La sal debería estar decantando. Verificar medición."
            )
        return None

    # ═════════════════════════════════════════════════════════════════════════
    # AUDIT LOG
    # ═════════════════════════════════════════════════════════════════════════

    def log(
        self,
        accion: str,
        usuario: Optional[Usuario] = None,
        detalle: Optional[dict] = None,
    ) -> AuditLog:
        """
        Registra una acción en el audit log.

        Ejemplos de accion: 'login', 'logout', 'login_fallido',
        'cubicacion_calculada', 'dem_cargado', 'csv_exportado',
        'informe_generado', 'usuario_creado'.
        """
        entry = AuditLog(
            usuario_id=usuario.id if usuario else None,
            username=usuario.username if usuario else None,
            accion=accion,
            detalle=json.dumps(detalle, ensure_ascii=False, default=str) if detalle else None,
        )
        self.session.add(entry)
        self.session.commit()
        self.session.refresh(entry)
        return entry

    def list_audit_log(
        self,
        limit: int = 200,
        usuario_id: Optional[int] = None,
        accion: Optional[str] = None,
    ) -> list[AuditLog]:
        """Retorna entradas del audit log con filtros opcionales."""
        q = select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit)
        if usuario_id is not None:
            q = q.where(AuditLog.usuario_id == usuario_id)
        if accion is not None:
            q = q.where(AuditLog.accion == accion)
        return list(self.session.scalars(q))
