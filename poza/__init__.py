# poza/__init__.py
"""
Paquete Poza Cubicación.

Contiene:
- core: cálculo de volúmenes desde DEM + contorno
- viz: previsualización del DEM
- masks: carga de contornos (geojson/shp)
- export: exportación CSV
- gui: interfaz gráfica
"""

__version__ = "1.0.0"

from .core import DemRaster, PondVolumeCalculator, PondVolumes, DemError

__all__ = [
    "DemRaster",
    "PondVolumeCalculator",
    "PondVolumes",
    "DemError",
]
