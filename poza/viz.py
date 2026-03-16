from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Optional, List
import numpy as np


@dataclass(frozen=True)
class DemStats:
    min_z: float
    max_z: float


def _agisoft_ramp(t: np.ndarray) -> np.ndarray:
    # azul -> cian -> verde -> amarillo -> naranja -> rojo
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
    az = np.deg2rad(azimuth_deg)
    alt = np.deg2rad(altitude_deg)

    dzdy, dzdx = np.gradient(z)
    slope = np.arctan(np.sqrt(dzdx * dzdx + dzdy * dzdy))
    aspect = np.arctan2(-dzdy, dzdx)

    hs = (np.sin(alt) * np.cos(slope) +
          np.cos(alt) * np.sin(slope) * np.cos(az - aspect))
    return np.clip(hs, 0, 1)


def _format_elev(v_m: float, total_range_m: float) -> str:
    """
    Evita que min/max se vean iguales por redondeo.
    - Si estamos en km, usa más decimales cuando el rango es chico.
    """
    if abs(v_m) >= 1000:
        # si el rango es menor a 200m, sube decimales en km para no “colapsar”
        decimals = 3 if total_range_m < 200 else 2
        return f"{v_m/1000:.{decimals}f} km"
    # en metros
    decimals = 2 if total_range_m < 50 else 1
    return f"{v_m:.{decimals}f} m"


def make_legend(min_z: float, max_z: float, height: int = 220, width: int = 18) -> tuple[np.ndarray, Dict[str, str]]:
    t = np.linspace(1.0, 0.0, height, dtype=np.float64)
    t2 = np.repeat(t[:, None], width, axis=1)
    rgb = _agisoft_ramp(t2)

    rng = float(max_z - min_z)
    labels = {
        "max": _format_elev(max_z, rng),
        "min": _format_elev(min_z, rng),
    }
    return rgb, labels


def _next_pow2(n: int) -> int:
    n = max(1, int(n))
    p = 1
    while p < n:
        p <<= 1
    return p


class DemRenderer:
    """
    Renderer dual:
    - FAST: usa pirámide precargada (cache) para pan/zoom fluido
    - HQ: lee desde el TIFF para recuperar detalle al detenerse

    zoom: relativo al "fit to window"
    coords center_x/center_y: píxeles del raster original
    """

    def __init__(self, dem_path: str, scale_mode: str = "minmax", stats_sample: int = 1024):
        import rasterio
        self.dem_path = dem_path
        self.src = rasterio.open(dem_path)

        self.width = self.src.width
        self.height = self.src.height
        self.nodata = self.src.nodata
        self.transform = self.src.transform
        self.crs = self.src.crs

        self.stats = self._compute_stats(scale_mode=scale_mode, stats_sample=stats_sample)

        # cache pyramid: list of dicts {"ds": int, "rgb": np.uint8[H,W,3]}
        self._cache: List[Dict] = []

    def close(self):
        try:
            self.src.close()
        except Exception:
            pass

    def _compute_stats(self, scale_mode: str, stats_sample: int) -> DemStats:
        import rasterio
        from rasterio.enums import Resampling

        out_w = min(stats_sample, self.width)
        out_h = min(stats_sample, self.height)

        arr = self.src.read(
            1,
            out_shape=(out_h, out_w),
            resampling=Resampling.bilinear,
        ).astype("float64")

        valid = np.isfinite(arr)
        if self.nodata is not None:
            valid &= (arr != self.nodata)

        if not np.any(valid):
            raise ValueError("El DEM no tiene valores válidos para calcular estadísticas.")

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

    def build_cache(self, max_tex: int = 2048, levels: int = 4) -> None:
        """
        Precarga una pirámide de texturas (coloreadas + hillshade).
        max_tex: tamaño máximo del lado mayor del nivel "más detallado" cacheado.
        """
        import rasterio
        from rasterio.enums import Resampling

        self._cache.clear()

        # ds0 = factor de reducción para que el lado mayor quede <= max_tex
        ds0 = int(np.ceil(max(self.width, self.height) / max_tex))
        ds0 = _next_pow2(ds0)  # potencia de 2 para pyramid limpia

        for i in range(levels):
            ds = ds0 * (2 ** i)
            out_w = max(2, int(np.ceil(self.width / ds)))
            out_h = max(2, int(np.ceil(self.height / ds)))

            arr = self.src.read(
                1,
                out_shape=(out_h, out_w),
                resampling=Resampling.bilinear,
            ).astype("float64")

            valid = np.isfinite(arr)
            if self.nodata is not None:
                valid &= (arr != self.nodata)

            lo = self.stats.min_z
            hi = self.stats.max_z
            t = np.zeros_like(arr, dtype=np.float64)
            t[valid] = (arr[valid] - lo) / (hi - lo)
            t = np.clip(t, 0, 1)

            rgb = _agisoft_ramp(t)

            # hillshade suave (en cache siempre ON para look bonito)
            z_fill = arr.copy()
            if np.any(valid):
                z_fill[~valid] = np.median(arr[valid])
            else:
                z_fill[~valid] = 0.0
            hs = _hillshade(z_fill)
            shade = (0.62 + 0.38 * hs)[:, :, None]
            rgb = np.clip(rgb.astype(np.float64) * shade, 0, 255).astype(np.uint8)

            rgb[~valid] = np.array([255, 255, 255], dtype=np.uint8)

            self._cache.append({"ds": ds, "rgb": rgb})

    def _pick_cache_ds(self, scale_raster_to_screen: float) -> Dict:
        """
        Queremos ds grande (más rápido) pero sin que se pixelee:
        1 cached px representa ds raster px => eso se ve como ds*scale pixels en pantalla.
        Para evitar bloques, ideal ds*scale <= ~1.2
        => ds <= 1.2/scale
        """
        if not self._cache:
            raise RuntimeError("Cache no construido. Llama build_cache()")

        desired_ds = max(1, int((1.2 / max(scale_raster_to_screen, 1e-9))))
        # Elegir el ds más grande disponible que no exceda desired_ds (o el más pequeño si ninguno)
        candidates = [c for c in self._cache if c["ds"] <= desired_ds]
        if candidates:
            # el de mayor ds dentro del límite
            return max(candidates, key=lambda d: d["ds"])
        return min(self._cache, key=lambda d: d["ds"])

    def render_view_cached(
        self,
        center_x: float,
        center_y: float,
        zoom: float,
        canvas_w: int,
        canvas_h: int,
    ) -> tuple[np.ndarray, Dict[str, float]]:
        """
        Render FAST desde cache (sin leer TIFF).
        """
        canvas_w = max(2, int(canvas_w))
        canvas_h = max(2, int(canvas_h))

        base_scale = min(canvas_w / self.width, canvas_h / self.height)
        base_scale = max(base_scale, 1e-9)
        scale = base_scale * max(zoom, 1e-6)  # screen_px por raster_px

        cache = self._pick_cache_ds(scale)
        ds = cache["ds"]
        rgb0 = cache["rgb"]  # (Hc, Wc, 3)

        # ventana en raster
        win_w = canvas_w / scale
        win_h = canvas_h / scale

        x0 = center_x - win_w / 2
        y0 = center_y - win_h / 2
        x0 = max(0.0, min(x0, self.width - win_w))
        y0 = max(0.0, min(y0, self.height - win_h))

        # map a coords cache
        cx0 = x0 / ds
        cy0 = y0 / ds
        cwin_w = win_w / ds
        cwin_h = win_h / ds

        # crop
        x1 = int(np.floor(cx0))
        y1 = int(np.floor(cy0))
        x2 = int(np.ceil(cx0 + cwin_w))
        y2 = int(np.ceil(cy0 + cwin_h))

        x1 = max(0, min(x1, rgb0.shape[1] - 1))
        y1 = max(0, min(y1, rgb0.shape[0] - 1))
        x2 = max(x1 + 1, min(x2, rgb0.shape[1]))
        y2 = max(y1 + 1, min(y2, rgb0.shape[0]))

        crop = rgb0[y1:y2, x1:x2, :]

        # redimensionar al canvas (muy rápido)
        from PIL import Image
        img = Image.fromarray(crop, mode="RGB")
        img = img.resize((canvas_w, canvas_h), Image.BILINEAR)
        out = np.array(img, dtype=np.uint8)

        info = {"x0": float(x0), "y0": float(y0), "scale": float(scale), "base_scale": float(base_scale), "ds": float(ds)}
        return out, info

    def render_view_hq(
        self,
        center_x: float,
        center_y: float,
        zoom: float,
        canvas_w: int,
        canvas_h: int,
        hillshade: bool = True,
    ) -> tuple[np.ndarray, Dict[str, float]]:
        """
        Render HQ leyendo del TIFF (más lento), ideal para cuando el usuario se detiene.
        """
        import rasterio
        from rasterio.windows import Window
        from rasterio.enums import Resampling

        canvas_w = max(2, int(canvas_w))
        canvas_h = max(2, int(canvas_h))

        base_scale = min(canvas_w / self.width, canvas_h / self.height)
        base_scale = max(base_scale, 1e-9)
        scale = base_scale * max(zoom, 1e-6)

        win_w = canvas_w / scale
        win_h = canvas_h / scale

        x0 = center_x - win_w / 2
        y0 = center_y - win_h / 2
        x0 = max(0.0, min(x0, self.width - win_w))
        y0 = max(0.0, min(y0, self.height - win_h))

        resampling = Resampling.nearest if zoom >= 1.25 else Resampling.bilinear

        window = Window(x0, y0, win_w, win_h)
        arr = self.src.read(
            1,
            window=window,
            out_shape=(canvas_h, canvas_w),
            resampling=resampling,
        ).astype("float64")

        valid = np.isfinite(arr)
        if self.nodata is not None:
            valid &= (arr != self.nodata)

        lo = self.stats.min_z
        hi = self.stats.max_z
        t = np.zeros_like(arr, dtype=np.float64)
        t[valid] = (arr[valid] - lo) / (hi - lo)
        t = np.clip(t, 0, 1)

        rgb = _agisoft_ramp(t)

        if hillshade:
            z_fill = arr.copy()
            if np.any(valid):
                z_fill[~valid] = np.median(arr[valid])
            else:
                z_fill[~valid] = 0.0
            hs = _hillshade(z_fill)
            shade = (0.62 + 0.38 * hs)[:, :, None]
            rgb = np.clip(rgb.astype(np.float64) * shade, 0, 255).astype(np.uint8)

        rgb[~valid] = np.array([255, 255, 255], dtype=np.uint8)

        info = {"x0": float(x0), "y0": float(y0), "scale": float(scale), "base_scale": float(base_scale)}
        return rgb, info
