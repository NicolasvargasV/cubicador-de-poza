from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List

import numpy as np


class DemError(Exception):
    """Errores relacionados a lectura/uso del DEM."""


@dataclass(frozen=True)
class PondVolumes:
    dem_path: str
    salt_level: float
    water_level: float
    occluded_fraction: float

    salt_total_m3: float
    brine_free_m3: float
    brine_occluded_m3: float
    brine_total_m3: float

    cell_area_m2: float
    area_wet_m2: float
    area_brine_m2: float

    dem_min: float
    dem_max: float

    def to_rows(self) -> list[tuple[str, float, str]]:
        """Filas (Item, Valor, Unidad) para tabla/CSV."""
        return [
            ("Cota sal", self.salt_level, "m"),
            ("Cota pelo de agua", self.water_level, "m"),
            ("Elevación mín. DEM", self.dem_min, "m"),
            ("Elevación máx. DEM", self.dem_max, "m"),
            ("Área Espejo", self.area_wet_m2, "m²"),
            ("Volumen sal (piso -> cota sal)", self.salt_total_m3, "m³"),
            ("Volumen salmuera libre (cota sal -> pelo agua)", self.brine_free_m3, "m³"),
            ("Volumen salmuera ocluida", self.brine_occluded_m3, "m³"),
            ("Volumen total salmuera", self.brine_total_m3, "m³"),
        ]


class DemRaster:
    """
    Lector DEM + recorte por máscara shapes (GeoJSON geometry dicts)
    usando rasterio.mask.mask.
    """

    def __init__(self, dem_path: str, mask_shapes: Optional[List[dict]] = None) -> None:
        self.dem_path = str(dem_path)
        self.mask_shapes = mask_shapes

        self._dem: Optional[np.ndarray] = None
        self._valid: Optional[np.ndarray] = None
        self._transform = None
        self._profile: Optional[Dict[str, Any]] = None
        self._cell_area_m2: Optional[float] = None
        self._nodata: Optional[float] = None

    @property
    def cell_area_m2(self) -> float:
        if self._cell_area_m2 is None:
            raise DemError("DEM no cargado. Llama a load() primero.")
        return self._cell_area_m2

    def load(self) -> "DemRaster":
        import rasterio
        from rasterio.mask import mask

        if not Path(self.dem_path).exists():
            raise DemError(f"No existe el archivo DEM: {self.dem_path}")

        with rasterio.open(self.dem_path) as src:
            if src.crs is not None and getattr(src.crs, "is_geographic", False):
                raise DemError(
                    "Tu DEM está en coordenadas geográficas (grados). "
                    "Reprojéctalo a un CRS proyectado en metros (ej. UTM) para que el volumen salga en m³."
                )

            self._nodata = src.nodata
            self._profile = src.profile.copy()

            if self.mask_shapes:
                data, out_transform = mask(src, self.mask_shapes, crop=True, filled=True)
                dem = data[0].astype("float64")
                transform = out_transform
            else:
                dem = src.read(1).astype("float64")
                transform = src.transform

            self._transform = transform
            self._cell_area_m2 = abs(transform.a * transform.e - transform.b * transform.d)

            valid = np.isfinite(dem)
            if self._nodata is not None:
                valid &= (dem != self._nodata)

            if not np.any(valid):
                raise DemError("No hay celdas válidas (todo es NoData/NaN). Revisa DEM/contorno.")

            self._dem = dem
            self._valid = valid
            return self

    def depth_to_level(self, level: float) -> np.ndarray:
        if self._dem is None or self._valid is None:
            raise DemError("DEM no cargado. Llama a load() primero.")
        depth = np.zeros_like(self._dem, dtype="float64")
        depth[self._valid] = np.maximum(0.0, level - self._dem[self._valid])
        return depth


class PondVolumeCalculator:
    def __init__(self, dem: DemRaster) -> None:
        self.dem = dem

    def compute(self, salt_level: float, water_level: float, occluded_fraction: float = 0.20) -> PondVolumes:
        if self.dem._dem is None or self.dem._valid is None:
            raise DemError("DEM no cargado. Llama a dem.load() antes de compute().")
        if not (0.0 <= occluded_fraction <= 1.0):
            raise ValueError("Fracción ocluida debe estar entre 0 y 1.")

        valid = self.dem._valid
        cell_area = self.dem.cell_area_m2

        dem_values = self.dem._dem[valid]
        dem_min = float(dem_values.min())
        dem_max = float(dem_values.max())

        if salt_level > dem_max:
            raise DemError(
                f"Cota de sal ({salt_level:.2f} m) está por encima del máximo del DEM ({dem_max:.2f} m).\n"
                f"Rango DEM válido: {dem_min:.2f} m – {dem_max:.2f} m"
            )
        if water_level <= dem_min:
            raise DemError(
                f"Cota pelo de agua ({water_level:.2f} m) está por debajo del mínimo del DEM ({dem_min:.2f} m).\n"
                f"Rango DEM válido: {dem_min:.2f} m – {dem_max:.2f} m"
            )

        depth_salt = self.dem.depth_to_level(salt_level)
        depth_water = self.dem.depth_to_level(water_level)

        # salmuera libre = (agua total - sal) truncado a 0
        depth_brine_free = np.zeros_like(depth_water, dtype="float64")
        depth_brine_free[valid] = np.maximum(0.0, depth_water[valid] - depth_salt[valid])

        salt_total_m3 = float(np.sum(depth_salt[valid]) * cell_area)
        brine_free_m3 = float(np.sum(depth_brine_free[valid]) * cell_area)

        brine_occluded_m3 = float(salt_total_m3 * occluded_fraction)
        brine_total_m3 = float(brine_free_m3 + brine_occluded_m3)

        area_wet_m2 = float(np.sum(depth_water[valid] > 0) * cell_area)
        area_brine_m2 = float(np.sum(depth_brine_free[valid] > 0) * cell_area)

        return PondVolumes(
            dem_path=self.dem.dem_path,
            salt_level=salt_level,
            water_level=water_level,
            occluded_fraction=occluded_fraction,
            salt_total_m3=salt_total_m3,
            brine_free_m3=brine_free_m3,
            brine_occluded_m3=brine_occluded_m3,
            brine_total_m3=brine_total_m3,
            cell_area_m2=cell_area,
            area_wet_m2=area_wet_m2,
            area_brine_m2=area_brine_m2,
            dem_min=dem_min,
            dem_max=dem_max,
        )
