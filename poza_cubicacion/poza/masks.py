from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional


class MaskError(Exception):
    pass


def load_mask_shapes(path: Optional[str]) -> Optional[List[dict]]:
    """
    Devuelve una lista de geometrías GeoJSON (dict) para rasterio.mask.mask.

    Soporta:
    - .geojson / .json (recomendado)
    - .shp (opcional, requiere fiona)
    """
    if not path:
        return None

    p = Path(path)
    if not p.exists():
        raise MaskError(f"No existe el archivo de contorno: {path}")

    ext = p.suffix.lower()

    if ext in [".geojson", ".json"]:
        return _load_geojson(path)

    if ext == ".shp":
        return _load_shp(path)

    raise MaskError("Formato de contorno no soportado. Usa .geojson/.json (recomendado) o .shp.")


def _load_geojson(path: str) -> List[dict]:
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)

    shapes: List[dict] = []
    t = gj.get("type")

    if t == "FeatureCollection":
        for feat in gj.get("features", []) or []:
            geom = feat.get("geometry")
            if geom:
                shapes.append(geom)

    elif t == "Feature":
        geom = gj.get("geometry")
        if geom:
            shapes.append(geom)

    elif t in ("Polygon", "MultiPolygon"):
        shapes.append(gj)

    else:
        raise MaskError("GeoJSON inválido o tipo no soportado.")

    if not shapes:
        raise MaskError("El GeoJSON no contiene geometrías válidas.")
    return shapes


def _load_shp(path: str) -> List[dict]:
    try:
        import fiona
    except Exception as e:
        raise MaskError("Para leer .shp necesitas instalar fiona: pip install fiona") from e

    shapes: List[dict] = []
    with fiona.open(path, "r") as src:
        for feat in src:
            geom = feat.get("geometry") if feat else None
            if geom:
                shapes.append(geom)

    if not shapes:
        raise MaskError("El shapefile no contiene geometrías válidas.")
    return shapes
