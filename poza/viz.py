from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np


@dataclass(frozen=True)
class DemStats:
    min_z: float
    max_z: float


# ─────────────────────────────────────────────────────────────────────────────
# Paleta de colores (estilo Agisoft)
# ─────────────────────────────────────────────────────────────────────────────

def _agisoft_ramp(t: np.ndarray) -> np.ndarray:
    stops = np.array([
        [0.00,  18,  48, 120],
        [0.20,   0, 150, 200],
        [0.40,  30, 190, 120],
        [0.60, 240, 230,  70],
        [0.80, 245, 140,  30],
        [1.00, 220,  40,  30],
    ], dtype=np.float64)

    out = np.zeros(t.shape + (3,), dtype=np.float64)
    for i in range(len(stops) - 1):
        t0, r0, g0, b0 = stops[i]
        t1, r1, g1, b1 = stops[i + 1]
        w = np.clip((t - t0) / (t1 - t0 + 1e-12), 0, 1)
        mask = (t >= t0) & (t <= t1)
        if not np.any(mask):
            continue
        out[mask, 0] = r0 + (r1 - r0) * w[mask]
        out[mask, 1] = g0 + (g1 - g0) * w[mask]
        out[mask, 2] = b0 + (b1 - b0) * w[mask]
    return out.clip(0, 255).astype(np.uint8)


def _hillshade(z: np.ndarray, azimuth_deg: float = 315.0, altitude_deg: float = 45.0) -> np.ndarray:
    az  = np.deg2rad(azimuth_deg)
    alt = np.deg2rad(altitude_deg)
    dzdy, dzdx = np.gradient(z)
    slope  = np.arctan(np.sqrt(dzdx**2 + dzdy**2))
    aspect = np.arctan2(-dzdy, dzdx)
    hs = (np.sin(alt) * np.cos(slope) +
          np.cos(alt) * np.sin(slope) * np.cos(az - aspect))
    return np.clip(hs, 0, 1)


def _format_elev(v_m: float, total_range_m: float) -> str:
    if abs(v_m) >= 1000:
        decimals = 3 if total_range_m < 200 else 2
        return f"{v_m/1000:.{decimals}f} km"
    decimals = 2 if total_range_m < 50 else 1
    return f"{v_m:.{decimals}f} m"


def make_legend(min_z: float, max_z: float, height: int = 220, width: int = 18) -> tuple[np.ndarray, Dict[str, str]]:
    t   = np.linspace(1.0, 0.0, height, dtype=np.float64)
    t2  = np.repeat(t[:, None], width, axis=1)
    rgb = _agisoft_ramp(t2)
    rng = float(max_z - min_z)
    labels = {"max": _format_elev(max_z, rng), "min": _format_elev(min_z, rng)}
    return rgb, labels


def _next_pow2(n: int) -> int:
    n = max(1, int(n))
    p = 1
    while p < n:
        p <<= 1
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Viewport helper  (compartido por DemRenderer y OrthoRenderer)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_viewport(
    canvas_w: int,
    canvas_h: int,
    raster_w: int,
    raster_h: int,
    zoom: float,
    center_x: float,
    center_y: float,
) -> Dict:
    """
    Calcula la geometría de renderizado preservando la relación de aspecto
    del ráster. Si el ráster es más angosto que el canvas se añade letterboxing
    (relleno oscuro) en el canvas; nunca se estira el contenido.

    Retorna un dict con:
      scale         – px pantalla / px ráster
      base_scale    – scale a zoom=1
      x0, y0        – coords ráster de la esquina sup-izq del viewport
      win_w, win_h  – ventana del ráster visible (px ráster)
      render_w, render_h – tamaño de la imagen de salida (px pantalla)
      off_x, off_y  – offset en el canvas donde se dibuja la imagen (letterbox)
    """
    base_scale = min(canvas_w / raster_w, canvas_h / raster_h)
    base_scale = max(base_scale, 1e-9)
    scale = base_scale * max(zoom, 1e-6)

    view_raster_w = canvas_w / scale
    view_raster_h = canvas_h / scale

    # eje X
    if view_raster_w >= raster_w:
        win_w    = float(raster_w)
        x0       = 0.0
        render_w = max(1, int(round(raster_w * scale)))
        off_x    = (canvas_w - render_w) / 2.0
    else:
        win_w    = view_raster_w
        x0       = max(0.0, min(center_x - win_w / 2, raster_w - win_w))
        render_w = canvas_w
        off_x    = 0.0

    # eje Y
    if view_raster_h >= raster_h:
        win_h    = float(raster_h)
        y0       = 0.0
        render_h = max(1, int(round(raster_h * scale)))
        off_y    = (canvas_h - render_h) / 2.0
    else:
        win_h    = view_raster_h
        y0       = max(0.0, min(center_y - win_h / 2, raster_h - win_h))
        render_h = canvas_h
        off_y    = 0.0

    return dict(
        scale=scale, base_scale=base_scale,
        x0=x0, y0=y0,
        win_w=win_w, win_h=win_h,
        render_w=render_w, render_h=render_h,
        off_x=off_x, off_y=off_y,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Renderer DEM  (banda de elevación → paleta de colores + hillshade)
# ─────────────────────────────────────────────────────────────────────────────

class DemRenderer:
    """
    Renderer dual cache/HQ para DEMs (un solo canal de elevación).

    center_x/center_y: coordenada ráster del centro de la vista.
    zoom: relativo al encuadre que cabe justo en el canvas (zoom=1 → fit).
    """

    def __init__(self, dem_path: str, scale_mode: str = "minmax", stats_sample: int = 1024):
        import rasterio
        self.dem_path  = dem_path
        self.src       = rasterio.open(dem_path)
        self.width     = self.src.width
        self.height    = self.src.height
        self.nodata    = self.src.nodata
        self.transform = self.src.transform
        self.crs       = self.src.crs
        self.stats     = self._compute_stats(scale_mode, stats_sample)
        self._cache: List[Dict] = []

    def close(self) -> None:
        try:
            self.src.close()
        except Exception:
            pass

    # ── Estadísticas ──────────────────────────────────────────────────────────

    def _compute_stats(self, scale_mode: str, stats_sample: int) -> DemStats:
        from rasterio.enums import Resampling
        out_w = min(stats_sample, self.width)
        out_h = min(stats_sample, self.height)
        arr   = self.src.read(1, out_shape=(out_h, out_w),
                              resampling=Resampling.bilinear).astype("float64")
        valid = np.isfinite(arr)
        if self.nodata is not None:
            valid &= (arr != self.nodata)
        if not np.any(valid):
            raise ValueError("El DEM no tiene valores válidos.")
        if scale_mode == "p2p98":
            lo = float(np.percentile(arr[valid], 2))
            hi = float(np.percentile(arr[valid], 98))
        else:
            lo = float(np.min(arr[valid]))
            hi = float(np.max(arr[valid]))
        if hi - lo < 1e-12:
            hi = lo + 1.0
        return DemStats(min_z=lo, max_z=hi)

    def legend(self, height: int, width: int = 18) -> tuple[np.ndarray, Dict[str, str]]:
        return make_legend(self.stats.min_z, self.stats.max_z, height=height, width=width)

    # ── Cache ────────────────────────────────────────────────────────────────

    def build_cache(self, max_tex: int = 2048, levels: int = 4) -> None:
        from rasterio.enums import Resampling
        self._cache.clear()
        ds0 = _next_pow2(max(1, int(np.ceil(max(self.width, self.height) / max_tex))))
        for i in range(levels):
            ds    = ds0 * (2 ** i)
            out_w = max(2, int(np.ceil(self.width  / ds)))
            out_h = max(2, int(np.ceil(self.height / ds)))
            arr   = self.src.read(1, out_shape=(out_h, out_w),
                                  resampling=Resampling.bilinear).astype("float64")
            valid = np.isfinite(arr)
            if self.nodata is not None:
                valid &= (arr != self.nodata)
            lo, hi = self.stats.min_z, self.stats.max_z
            t = np.zeros_like(arr)
            t[valid] = np.clip((arr[valid] - lo) / (hi - lo), 0, 1)
            rgb = _agisoft_ramp(t)
            z_fill = arr.copy()
            z_fill[~valid] = float(np.median(arr[valid])) if np.any(valid) else 0.0
            hs    = _hillshade(z_fill)
            shade = (0.62 + 0.38 * hs)[:, :, None]
            rgb   = np.clip(rgb.astype(np.float64) * shade, 0, 255).astype(np.uint8)
            rgb[~valid] = [255, 255, 255]
            self._cache.append({"ds": ds, "rgb": rgb})

    def _pick_cache_ds(self, scale: float) -> Dict:
        if not self._cache:
            raise RuntimeError("Cache no construido. Llama build_cache().")
        desired = max(1, int(1.2 / max(scale, 1e-9)))
        candidates = [c for c in self._cache if c["ds"] <= desired]
        if candidates:
            return max(candidates, key=lambda d: d["ds"])
        return min(self._cache, key=lambda d: d["ds"])

    # ── Render ───────────────────────────────────────────────────────────────

    def render_view_cached(
        self,
        center_x: float, center_y: float,
        zoom: float, canvas_w: int, canvas_h: int,
    ) -> tuple[np.ndarray, Dict]:
        canvas_w, canvas_h = max(2, int(canvas_w)), max(2, int(canvas_h))
        vp    = _compute_viewport(canvas_w, canvas_h, self.width, self.height, zoom, center_x, center_y)
        cache = self._pick_cache_ds(vp["scale"])
        ds    = cache["ds"]
        rgb0  = cache["rgb"]

        cx0    = vp["x0"] / ds;  cy0    = vp["y0"] / ds
        cwin_w = vp["win_w"] / ds; cwin_h = vp["win_h"] / ds
        x1 = max(0, int(np.floor(cx0)));  y1 = max(0, int(np.floor(cy0)))
        x2 = min(rgb0.shape[1], int(np.ceil(cx0 + cwin_w)))
        y2 = min(rgb0.shape[0], int(np.ceil(cy0 + cwin_h)))
        x2, y2 = max(x1 + 1, x2), max(y1 + 1, y2)

        crop = rgb0[y1:y2, x1:x2, :]
        from PIL import Image
        out = np.array(
            Image.fromarray(crop, "RGB").resize((vp["render_w"], vp["render_h"]), Image.BILINEAR),
            dtype=np.uint8,
        )
        return out, vp

    def render_view_hq(
        self,
        center_x: float, center_y: float,
        zoom: float, canvas_w: int, canvas_h: int,
        hillshade: bool = True,
    ) -> tuple[np.ndarray, Dict]:
        from rasterio.windows import Window
        from rasterio.enums import Resampling

        canvas_w, canvas_h = max(2, int(canvas_w)), max(2, int(canvas_h))
        vp = _compute_viewport(canvas_w, canvas_h, self.width, self.height, zoom, center_x, center_y)

        resampling = Resampling.nearest if zoom >= 1.25 else Resampling.bilinear
        window     = Window(vp["x0"], vp["y0"], vp["win_w"], vp["win_h"])
        arr        = self.src.read(
            1, window=window,
            out_shape=(vp["render_h"], vp["render_w"]),
            resampling=resampling,
        ).astype("float64")

        valid = np.isfinite(arr)
        if self.nodata is not None:
            valid &= (arr != self.nodata)

        lo, hi = self.stats.min_z, self.stats.max_z
        t = np.zeros_like(arr)
        t[valid] = np.clip((arr[valid] - lo) / (hi - lo), 0, 1)
        rgb = _agisoft_ramp(t)

        if hillshade:
            z_fill = arr.copy()
            z_fill[~valid] = float(np.median(arr[valid])) if np.any(valid) else 0.0
            hs    = _hillshade(z_fill)
            shade = (0.62 + 0.38 * hs)[:, :, None]
            rgb   = np.clip(rgb.astype(np.float64) * shade, 0, 255).astype(np.uint8)

        rgb[~valid] = [255, 255, 255]
        return rgb, vp


# ─────────────────────────────────────────────────────────────────────────────
# Renderer Ortofoto  (bandas RGB de un GeoTIFF coregistrado con el DEM)
# ─────────────────────────────────────────────────────────────────────────────

class OrthoRenderer:
    """
    Renderiza una ortofoto (GeoTIFF RGB/RGBA/monocanal) con la misma API
    que DemRenderer. Debe tener la misma extensión y resolución que el DEM.

    No produce hillshade; el parámetro hillshade se acepta pero se ignora
    para mantener compatibilidad de interfaz.
    """

    def __init__(self, ortho_path: str):
        import rasterio
        self.ortho_path = ortho_path
        self.src        = rasterio.open(ortho_path)
        self.width      = self.src.width
        self.height     = self.src.height
        self.nodata     = self.src.nodata
        self.transform  = self.src.transform
        self.crs        = self.src.crs
        self._n_bands   = self.src.count
        self._cache: List[Dict] = []

        # Índices de bandas RGB (1-indexed)
        self._band_idx = self._detect_rgb_bands()

    def close(self) -> None:
        try:
            self.src.close()
        except Exception:
            pass

    def _detect_rgb_bands(self) -> List[int]:
        """Detecta los índices R, G, B. Soporta 1, 3 y 4 bandas."""
        ci = self.src.colorinterp  # list de ColorInterp
        try:
            from rasterio.enums import ColorInterp
            r = next((i + 1 for i, c in enumerate(ci) if c == ColorInterp.red),   None)
            g = next((i + 1 for i, c in enumerate(ci) if c == ColorInterp.green), None)
            b = next((i + 1 for i, c in enumerate(ci) if c == ColorInterp.blue),  None)
            if r and g and b:
                return [r, g, b]
        except Exception:
            pass
        if self._n_bands >= 3:
            return [1, 2, 3]
        return [1, 1, 1]  # monocanal → escala de grises

    def _normalize_band(self, arr: np.ndarray) -> np.ndarray:
        """Normaliza una banda al rango 0-255."""
        dtype = self.src.dtypes[0]
        if dtype == "uint8":
            return arr.clip(0, 255).astype(np.uint8)
        valid = np.isfinite(arr)
        if self.nodata is not None:
            valid &= (arr != self.nodata)
        if np.any(valid):
            lo, hi = float(np.percentile(arr[valid], 2)), float(np.percentile(arr[valid], 98))
            if hi > lo:
                arr = np.clip((arr - lo) / (hi - lo) * 255, 0, 255)
            else:
                arr = np.clip(arr, 0, 255)
        return arr.astype(np.uint8)

    def build_cache(self, max_tex: int = 2048, levels: int = 4) -> None:
        from rasterio.enums import Resampling
        self._cache.clear()
        ds0 = _next_pow2(max(1, int(np.ceil(max(self.width, self.height) / max_tex))))
        for i in range(levels):
            ds    = ds0 * (2 ** i)
            out_w = max(2, int(np.ceil(self.width  / ds)))
            out_h = max(2, int(np.ceil(self.height / ds)))
            rgb   = np.zeros((out_h, out_w, 3), dtype=np.uint8)
            for ch, band in enumerate(self._band_idx):
                arr = self.src.read(band, out_shape=(out_h, out_w),
                                    resampling=Resampling.bilinear).astype(np.float32)
                rgb[:, :, ch] = self._normalize_band(arr)
            self._cache.append({"ds": ds, "rgb": rgb})

    def _pick_cache_ds(self, scale: float) -> Dict:
        if not self._cache:
            raise RuntimeError("Cache no construido. Llama build_cache().")
        desired = max(1, int(1.2 / max(scale, 1e-9)))
        candidates = [c for c in self._cache if c["ds"] <= desired]
        if candidates:
            return max(candidates, key=lambda d: d["ds"])
        return min(self._cache, key=lambda d: d["ds"])

    def render_view_cached(
        self,
        center_x: float, center_y: float,
        zoom: float, canvas_w: int, canvas_h: int,
    ) -> tuple[np.ndarray, Dict]:
        canvas_w, canvas_h = max(2, int(canvas_w)), max(2, int(canvas_h))
        vp    = _compute_viewport(canvas_w, canvas_h, self.width, self.height, zoom, center_x, center_y)
        cache = self._pick_cache_ds(vp["scale"])
        ds    = cache["ds"];  rgb0 = cache["rgb"]

        cx0    = vp["x0"] / ds;  cy0    = vp["y0"] / ds
        cwin_w = vp["win_w"] / ds; cwin_h = vp["win_h"] / ds
        x1 = max(0, int(np.floor(cx0)));  y1 = max(0, int(np.floor(cy0)))
        x2 = min(rgb0.shape[1], int(np.ceil(cx0 + cwin_w)))
        y2 = min(rgb0.shape[0], int(np.ceil(cy0 + cwin_h)))
        x2, y2 = max(x1 + 1, x2), max(y1 + 1, y2)

        crop = rgb0[y1:y2, x1:x2, :]
        from PIL import Image
        out = np.array(
            Image.fromarray(crop, "RGB").resize((vp["render_w"], vp["render_h"]), Image.BILINEAR),
            dtype=np.uint8,
        )
        return out, vp

    def render_view_hq(
        self,
        center_x: float, center_y: float,
        zoom: float, canvas_w: int, canvas_h: int,
        hillshade: bool = False,   # ignorado
    ) -> tuple[np.ndarray, Dict]:
        from rasterio.windows import Window
        from rasterio.enums import Resampling

        canvas_w, canvas_h = max(2, int(canvas_w)), max(2, int(canvas_h))
        vp = _compute_viewport(canvas_w, canvas_h, self.width, self.height, zoom, center_x, center_y)

        window     = Window(vp["x0"], vp["y0"], vp["win_w"], vp["win_h"])
        resampling = Resampling.nearest if zoom >= 1.25 else Resampling.bilinear
        rgb        = np.zeros((vp["render_h"], vp["render_w"], 3), dtype=np.uint8)
        for ch, band in enumerate(self._band_idx):
            arr = self.src.read(
                band, window=window,
                out_shape=(vp["render_h"], vp["render_w"]),
                resampling=resampling,
            ).astype(np.float32)
            rgb[:, :, ch] = self._normalize_band(arr)
        return rgb, vp
