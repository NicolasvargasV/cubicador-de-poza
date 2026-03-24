# poza/__init__.py
"""
Paquete Poza Cubicación.

Contiene:
- core:   cálculo de volúmenes desde DEM + contorno
- viz:    previsualización del DEM (renderer dual cache/HQ)
- masks:  carga de contornos (geojson/shp)
- export: exportación CSV
- gui_qt: interfaz gráfica (PySide6)
- db:     capa de persistencia (SQLAlchemy + SQLite)
"""

__version__ = "1.0.0"

from .core import DemRaster, PondVolumeCalculator, PondVolumes, DemError

__all__ = [
    "DemRaster",
    "PondVolumeCalculator",
    "PondVolumes",
    "DemError",
]
