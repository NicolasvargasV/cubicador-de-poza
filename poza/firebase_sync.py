"""
firebase_sync.py
~~~~~~~~~~~~~~~~
Módulo de sincronización con Firebase (Firestore + Storage).

Uso:
    from .firebase_sync import firebase_sync

    firebase_sync.upload_dem_async(reservorio_codigo, local_path)
    firebase_sync.upload_cubicacion_async(reservorio_codigo, {
        "volumen_m3": 12345.67,
        "cota_llenado": 3420.5,
        "nombre": "Mi Reservorio",
        ...
    })

Degradación graceful: si `firebase_admin` no está instalado o la clave
no existe, todos los métodos son no-ops silenciosos.

Instalación:
    pip install firebase-admin
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Busca la clave en varias ubicaciones posibles
# ──────────────────────────────────────────────────────────────────────────────
_KEY_CANDIDATES: list[Path] = [
    Path(__file__).parent.parent / "firebase-key.json",     # raíz del proyecto
    Path(__file__).parent / "firebase-key.json",            # dentro de poza/
    Path.home() / ".config" / "cubicador" / "firebase-key.json",
]


def _find_key() -> Optional[Path]:
    for p in _KEY_CANDIDATES:
        if p.is_file():
            return p
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Intento de importar firebase_admin
# ──────────────────────────────────────────────────────────────────────────────
try:
    import firebase_admin
    from firebase_admin import credentials, firestore, storage

    _FIREBASE_SDK_AVAILABLE = True
except ImportError:
    _FIREBASE_SDK_AVAILABLE = False
    logger.info("firebase_admin no instalado — sincronización en nube desactivada.")


# ──────────────────────────────────────────────────────────────────────────────
# FirebaseSync
# ──────────────────────────────────────────────────────────────────────────────

class FirebaseSync:
    """
    Interfaz de alto nivel para sincronizar datos con Firebase.

    Todos los uploads se ejecutan en hilos daemon para no bloquear la UI.
    Si Firebase no está disponible, los métodos son silenciosos.
    """

    _PROJECT_ID = "v-metric-76cdb"
    _STORAGE_BUCKET = "v-metric-76cdb.firebasestorage.app"

    def __init__(self) -> None:
        self._app: Any = None           # firebase_admin.App
        self._db: Any = None            # firestore.Client
        self._bucket: Any = None        # storage.Bucket
        self._ready = False
        self._lock = threading.Lock()
        self._init_callbacks: list[Callable[[], None]] = []

        if _FIREBASE_SDK_AVAILABLE:
            self._initialize()

    # ── Inicialización ────────────────────────────────────────────────────────

    def _initialize(self) -> None:
        """Inicializa el SDK de Firebase de forma no bloqueante."""
        key_path = _find_key()
        if key_path is None:
            logger.warning(
                "Firebase: no se encontró firebase-key.json. "
                "Coloca el archivo en la raíz del proyecto para activar la nube."
            )
            return

        def _init_thread() -> None:
            try:
                with self._lock:
                    # Evitar inicializar dos veces si ya existe una app
                    try:
                        self._app = firebase_admin.get_app()
                    except ValueError:
                        cred = credentials.Certificate(str(key_path))
                        self._app = firebase_admin.initialize_app(
                            cred,
                            {
                                "storageBucket": self._STORAGE_BUCKET,
                                "projectId": self._PROJECT_ID,
                            },
                        )

                    self._db = firestore.client(app=self._app)
                    self._bucket = storage.bucket(app=self._app)
                    self._ready = True
                    logger.info("Firebase inicializado correctamente (proyecto: %s).", self._PROJECT_ID)

                # Ejecutar callbacks pendientes
                for cb in self._init_callbacks:
                    try:
                        cb()
                    except Exception:
                        pass
                self._init_callbacks.clear()

            except Exception as exc:
                logger.error("Firebase: error al inicializar — %s", exc)

        t = threading.Thread(target=_init_thread, name="firebase-init", daemon=True)
        t.start()

    # ── API pública ───────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """True si el SDK está listo y conectado."""
        return self._ready

    def upload_dem_async(
        self,
        reservorio_codigo: str,
        local_path: str | Path,
        on_success: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        Sube un archivo DEM (GeoTIFF) a Firebase Storage en un hilo background.

        Ruta en Storage:  dems/{reservorio_codigo}/{nombre_archivo}

        Parámetros
        ----------
        reservorio_codigo : str
            Código único del reservorio (usado como carpeta en Storage).
        local_path : str | Path
            Ruta local del archivo .tif a subir.
        on_success : callable(url), opcional
            Llamado con la URL pública cuando el upload termina.
        on_error : callable(exc), opcional
            Llamado si ocurre un error.
        """
        if not self._ready:
            logger.debug("Firebase no disponible, omitiendo upload_dem.")
            return

        local_path = Path(local_path)
        if not local_path.is_file():
            logger.warning("upload_dem_async: archivo no encontrado — %s", local_path)
            return

        def _upload() -> None:
            try:
                blob_path = f"dems/{reservorio_codigo}/{local_path.name}"
                blob = self._bucket.blob(blob_path)
                blob.upload_from_filename(
                    str(local_path),
                    content_type="image/tiff",
                )
                blob.make_public()
                url = blob.public_url
                logger.info("DEM subido a Storage: %s", blob_path)

                # Registrar metadatos en Firestore
                self._db.collection("reservorios").document(reservorio_codigo).set(
                    {
                        "dem_url": url,
                        "dem_blob_path": blob_path,
                        "dem_filename": local_path.name,
                        "dem_updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    merge=True,
                )

                if on_success:
                    on_success(url)

            except Exception as exc:
                logger.error("Error al subir DEM '%s': %s", local_path.name, exc)
                if on_error:
                    on_error(exc)

        t = threading.Thread(target=_upload, name=f"fb-dem-{reservorio_codigo}", daemon=True)
        t.start()

    def upload_cubicacion_async(
        self,
        reservorio_codigo: str,
        datos: Dict[str, Any],
        on_success: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        Guarda una cubicación en Firestore en un hilo background.

        Estructura en Firestore:
            reservorios/{reservorio_codigo}/cubicaciones/{timestamp_iso}

        Parámetros
        ----------
        reservorio_codigo : str
            Código único del reservorio.
        datos : dict
            Datos de la cubicación. Campos comunes:
                - volumen_m3: float
                - cota_llenado: float
                - area_m2: float
                - nombre: str
                - poligono_geojson: dict  (GeoJSON Feature, opcional)
                - curva_hv: list          (lista de {cota, volumen}, opcional)
        on_success : callable(doc_id), opcional
        on_error : callable(exc), opcional
        """
        if not self._ready:
            logger.debug("Firebase no disponible, omitiendo upload_cubicacion.")
            return

        def _upload() -> None:
            try:
                now_iso = datetime.now(timezone.utc).isoformat()
                doc_data = {
                    **datos,
                    "reservorio_codigo": reservorio_codigo,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }

                # Sub-colección de cubicaciones históricas
                col_ref = (
                    self._db
                    .collection("reservorios")
                    .document(reservorio_codigo)
                    .collection("cubicaciones")
                )
                _, doc_ref = col_ref.add(doc_data)
                doc_id = doc_ref.id
                logger.info(
                    "Cubicación guardada en Firestore: reservorios/%s/cubicaciones/%s",
                    reservorio_codigo, doc_id,
                )

                # También actualizar el documento raíz con el último resultado
                self._db.collection("reservorios").document(reservorio_codigo).set(
                    {
                        "ultima_cubicacion": {
                            "volumen_m3": datos.get("volumen_m3"),
                            "cota_llenado": datos.get("cota_llenado"),
                            "doc_id": doc_id,
                            "updated_at": now_iso,
                        }
                    },
                    merge=True,
                )

                if on_success:
                    on_success(doc_id)

            except Exception as exc:
                logger.error("Error al guardar cubicación para '%s': %s", reservorio_codigo, exc)
                if on_error:
                    on_error(exc)

        t = threading.Thread(target=_upload, name=f"fb-cub-{reservorio_codigo}", daemon=True)
        t.start()

    def fetch_cubicaciones_async(
        self,
        reservorio_codigo: str,
        on_result: Callable[[list], None],
        on_error: Optional[Callable[[Exception], None]] = None,
        limit: int = 50,
    ) -> None:
        """
        Descarga el historial de cubicaciones de un reservorio.

        Parámetros
        ----------
        reservorio_codigo : str
        on_result : callable(list[dict])
            Recibe lista de cubicaciones ordenadas de más reciente a más antigua.
        on_error : callable(exc), opcional
        limit : int
            Máximo número de registros a traer.
        """
        if not self._ready:
            logger.debug("Firebase no disponible, omitiendo fetch_cubicaciones.")
            on_result([])
            return

        def _fetch() -> None:
            try:
                col_ref = (
                    self._db
                    .collection("reservorios")
                    .document(reservorio_codigo)
                    .collection("cubicaciones")
                    .order_by("created_at", direction=firestore.Query.DESCENDING)
                    .limit(limit)
                )
                docs = col_ref.stream()
                results = []
                for doc in docs:
                    d = doc.to_dict()
                    d["_doc_id"] = doc.id
                    results.append(d)

                logger.info(
                    "Cubicaciones descargadas para '%s': %d registros.",
                    reservorio_codigo, len(results),
                )
                on_result(results)

            except Exception as exc:
                logger.error("Error al descargar cubicaciones para '%s': %s", reservorio_codigo, exc)
                if on_error:
                    on_error(exc)
                else:
                    on_result([])

        t = threading.Thread(target=_fetch, name=f"fb-fetch-{reservorio_codigo}", daemon=True)
        t.start()

    def save_reservorio_metadata_async(
        self,
        reservorio_codigo: str,
        nombre: str,
        extra: Optional[Dict[str, Any]] = None,
        on_success: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        Crea o actualiza el documento raíz de un reservorio en Firestore.

        Parámetros
        ----------
        reservorio_codigo : str
        nombre : str
        extra : dict, opcional   (campos adicionales a guardar)
        """
        if not self._ready:
            return

        def _save() -> None:
            try:
                data: Dict[str, Any] = {
                    "codigo": reservorio_codigo,
                    "nombre": nombre,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                if extra:
                    data.update(extra)

                self._db.collection("reservorios").document(reservorio_codigo).set(
                    data, merge=True
                )
                logger.info("Metadatos de reservorio '%s' guardados.", reservorio_codigo)
                if on_success:
                    on_success()

            except Exception as exc:
                logger.error("Error al guardar metadatos de '%s': %s", reservorio_codigo, exc)
                if on_error:
                    on_error(exc)

        t = threading.Thread(target=_save, name=f"fb-meta-{reservorio_codigo}", daemon=True)
        t.start()


# ──────────────────────────────────────────────────────────────────────────────
# Singleton global (importado directamente en gui_qt.py)
# ──────────────────────────────────────────────────────────────────────────────
firebase_sync = FirebaseSync()
