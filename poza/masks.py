from __future__ import annotations

import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional


class MaskError(Exception):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher principal
# ─────────────────────────────────────────────────────────────────────────────

def load_mask_shapes(path: Optional[str]) -> Optional[List[dict]]:
    """
    Retorna una lista de geometrías GeoJSON para rasterio.mask.mask.

    Formatos soportados:
      .geojson / .json  – GeoJSON estándar (recomendado)
      .shp              – Shapefile (requiere fiona)
      .kml              – KML (coordenadas lon/lat/alt)
      .kmz              – KML comprimido
    """
    if not path:
        return None

    p   = Path(path)
    ext = p.suffix.lower()

    if not p.exists():
        raise MaskError(f"No existe el archivo de contorno: {path}")

    if ext in (".geojson", ".json"):
        return _load_geojson(path)
    if ext == ".shp":
        return _load_shp(path)
    if ext == ".kml":
        return _load_kml(p.read_text(encoding="utf-8"))
    if ext == ".kmz":
        return _load_kmz(path)

    raise MaskError(
        "Formato de contorno no soportado. "
        "Usa .geojson/.json (recomendado), .kml, .kmz o .shp."
    )


# ─────────────────────────────────────────────────────────────────────────────
# GeoJSON
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Shapefile (requiere fiona)
# ─────────────────────────────────────────────────────────────────────────────

def _load_shp(path: str) -> List[dict]:
    try:
        import fiona
    except ImportError as e:
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


# ─────────────────────────────────────────────────────────────────────────────
# KML / KMZ  (sin dependencias externas – usa xml.etree stdlib)
# ─────────────────────────────────────────────────────────────────────────────

_KML_NS = "http://www.opengis.net/kml/2.2"
_KML_NS_ALT = ""   # algunos archivos KML no usan namespace


def _parse_kml_coords(text: str) -> List[tuple]:
    """
    Parsea un bloque de texto de <coordinates> KML.
    Formato: 'lon,lat[,alt] lon,lat[,alt] ...'
    Retorna lista de (lon, lat).
    """
    coords: List[tuple] = []
    for token in text.strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                lon, lat = float(parts[0]), float(parts[1])
                coords.append((lon, lat))
            except ValueError:
                pass
    return coords


def _kml_coords_to_geojson_polygon(rings: List[List[tuple]]) -> dict:
    """Convierte anillos KML (exterior + interior) a GeoJSON Polygon."""
    closed_rings = []
    for ring in rings:
        if len(ring) < 4:
            continue
        r = list(ring)
        if r[0] != r[-1]:
            r.append(r[0])  # cerrar anillo
        closed_rings.append([[lon, lat] for lon, lat in r])
    if not closed_rings:
        return {}
    return {"type": "Polygon", "coordinates": closed_rings}


def _extract_kml_shapes(root: ET.Element, ns: str) -> List[dict]:
    """
    Recorre el árbol XML KML buscando Polygon, MultiGeometry y LinearRing.
    """
    shapes: List[dict] = []

    def tag(name: str) -> str:
        return f"{{{ns}}}{name}" if ns else name

    # Buscar todos los Polygon
    for poly_el in root.iter(tag("Polygon")):
        rings: List[List[tuple]] = []

        # Anillo exterior
        outer = poly_el.find(f".//{tag('outerBoundaryIs')}/{tag('LinearRing')}/{tag('coordinates')}")
        if outer is not None and outer.text:
            c = _parse_kml_coords(outer.text)
            if c:
                rings.append(c)

        # Anillos interiores (hoyos)
        for inner in poly_el.findall(f".//{tag('innerBoundaryIs')}/{tag('LinearRing')}/{tag('coordinates')}"):
            if inner.text:
                c = _parse_kml_coords(inner.text)
                if c:
                    rings.append(c)

        shape = _kml_coords_to_geojson_polygon(rings)
        if shape:
            shapes.append(shape)

    # Si hay LineString cerrados como LinearRing sueltos (algunos exportadores)
    if not shapes:
        for lr_el in root.iter(tag("LinearRing")):
            coord_el = lr_el.find(tag("coordinates"))
            if coord_el is not None and coord_el.text:
                c = _parse_kml_coords(coord_el.text)
                shape = _kml_coords_to_geojson_polygon([c])
                if shape:
                    shapes.append(shape)

    return shapes


def _load_kml(kml_text: str) -> List[dict]:
    """Parsea texto KML y retorna lista de geometrías GeoJSON."""
    try:
        root = ET.fromstring(kml_text)
    except ET.ParseError as e:
        raise MaskError(f"KML inválido: {e}") from e

    # Intentar con namespace primero, luego sin él
    ns = _KML_NS if root.tag.startswith(f"{{{_KML_NS}}}") else ""
    shapes = _extract_kml_shapes(root, ns)

    if not shapes:
        raise MaskError(
            "No se encontraron polígonos en el KML. "
            "Verifica que el archivo contiene geometrías de tipo Polygon."
        )
    return shapes


def _load_kmz(path: str) -> List[dict]:
    """Descomprime un KMZ y parsea el KML principal."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            # El KML principal suele llamarse doc.kml o ser el primer .kml
            kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
            if not kml_names:
                raise MaskError("El KMZ no contiene archivos KML.")
            # Preferir doc.kml, luego el primero
            main = next((n for n in kml_names if Path(n).name.lower() == "doc.kml"), kml_names[0])
            kml_text = zf.read(main).decode("utf-8")
    except zipfile.BadZipFile as e:
        raise MaskError(f"Archivo KMZ inválido: {e}") from e

    return _load_kml(kml_text)


# ─────────────────────────────────────────────────────────────────────────────
# Conversión de polígono dibujado en el visor → GeoJSON
# ─────────────────────────────────────────────────────────────────────────────

def polygon_raster_to_geojson(
    verts_raster: List[tuple],
    affine_transform,
) -> dict:
    """
    Convierte una lista de coordenadas (col, row) en px del ráster a un
    dict GeoJSON Polygon usando el affine transform del ráster.

    affine_transform: rasterio.transform.Affine (o cualquier objeto compatible
    con el operador *).  transform * (col, row) → (x, y) en el CRS del ráster.

    Retorna un dict de GeoJSON Polygon que puede usarse directamente con
    rasterio.mask.mask.
    """
    if len(verts_raster) < 3:
        raise MaskError("El polígono debe tener al menos 3 vértices.")

    geo_coords = []
    for col, row in verts_raster:
        x, y = affine_transform * (col, row)
        geo_coords.append([x, y])

    # Cerrar el anillo
    if geo_coords[0] != geo_coords[-1]:
        geo_coords.append(geo_coords[0])

    return {"type": "Polygon", "coordinates": [geo_coords]}
