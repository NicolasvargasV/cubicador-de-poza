from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .core import DemRaster, PondVolumeCalculator, DemError, PondVolumes
from .masks import load_mask_shapes, MaskError
from .export import export_rows_to_csv, open_file_default_app, default_output_name
from .viz import DemRenderer
from .ui_mainwindow import Ui_MainWindow


COLOR_PRIMARY = "#29306A"
COLOR_SECONDARY = "#808B96"
COLOR_ACCENT = "#F75C03"
COLOR_TEXT = "#333333"
COLOR_BG = "#F6F6F6"
COLOR_WHITE = "#FFFFFF"


def fmt(x: float, decimals=3) -> str:
    return f"{x:,.{decimals}f}"


class DemViewerWidget(QWidget):
    """Visor DEM basado en Qt, equivalente al DemViewer de Tkinter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

        self.renderer: DemRenderer | None = None

        self.zoom = 1.0
        self.zoom_min = 0.35
        self.zoom_max = 12.0
        self.center_x = 0.0
        self.center_y = 0.0

        self._pixmap: QPixmap | None = None
        self._render_info = {"x0": 0.0, "y0": 0.0, "scale": 1.0, "base_scale": 1.0}

        self._fast_timer = QTimer(self)
        self._fast_timer.setSingleShot(True)
        self._fast_timer.timeout.connect(self._do_render_fast)

        self._hq_timer = QTimer(self)
        self._hq_timer.setSingleShot(True)
        self._hq_timer.timeout.connect(self._render_hq)

        self._pan_anchor: tuple[float, float, float, float] | None = None

    # API pública ---------------------------------------------------------

    def set_renderer(self, renderer: DemRenderer) -> None:
        if self.renderer:
            self.renderer.close()
        self.renderer = renderer

        self.renderer.build_cache(max_tex=2048, levels=4)

        self.zoom = 1.0
        self.center_x = renderer.width / 2
        self.center_y = renderer.height / 2

        self._render_fast()
        self._schedule_hq(delay_ms=60)

    def clear(self) -> None:
        if self.renderer:
            self.renderer.close()
        self.renderer = None
        self._pixmap = None
        self.update()

    # Eventos Qt ----------------------------------------------------------

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._render_fast()
        self._schedule_hq()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.white)
        if self._pixmap is not None:
            painter.drawPixmap(0, 0, self.width(), self.height(), self._pixmap)
        painter.end()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._pan_anchor = (
                float(event.position().x()),
                float(event.position().y()),
                self.center_x,
                self.center_y,
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._pan_anchor and self.renderer:
            x0, y0, cx0, cy0 = self._pan_anchor
            dx = float(event.position().x()) - x0
            dy = float(event.position().y()) - y0

            scale = float(self._render_info.get("scale", 1.0))
            self.center_x = cx0 - dx / scale
            self.center_y = cy0 - dy / scale

            self.center_x = max(0.0, min(self.center_x, self.renderer.width))
            self.center_y = max(0.0, min(self.center_y, self.renderer.height))

            self._render_fast()
            self._schedule_hq()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._schedule_hq()
            self._pan_anchor = None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if not self.renderer:
            return
        delta = event.angleDelta().y()
        factor = 1.10 if delta > 0 else 1 / 1.10
        pos = event.position()
        self._zoom_at(factor, int(pos.x()), int(pos.y()))

    # Render --------------------------------------------------------------

    def _render_fast(self) -> None:
        if self._fast_timer.isActive():
            self._fast_timer.stop()
        self._fast_timer.start(8)

    def _do_render_fast(self) -> None:
        if not self.renderer:
            return
        cw = max(2, self.width())
        ch = max(2, self.height())

        rgb, info = self.renderer.render_view_cached(
            center_x=self.center_x,
            center_y=self.center_y,
            zoom=self.zoom,
            canvas_w=cw,
            canvas_h=ch,
        )
        self._render_info = info
        self._pixmap = self._rgb_to_pixmap(rgb)
        self.update()

    def _schedule_hq(self, delay_ms: int = 220) -> None:
        if self._hq_timer.isActive():
            self._hq_timer.stop()
        self._hq_timer.start(delay_ms)

    def _render_hq(self) -> None:
        if not self.renderer:
            return
        cw = max(2, self.width())
        ch = max(2, self.height())

        rgb, info = self.renderer.render_view_hq(
            center_x=self.center_x,
            center_y=self.center_y,
            zoom=self.zoom,
            canvas_w=cw,
            canvas_h=ch,
            hillshade=True,
        )
        self._render_info = info
        self._pixmap = self._rgb_to_pixmap(rgb)
        self.update()

    def _rgb_to_pixmap(self, rgb) -> QPixmap:
        # rgb: numpy array HxWx3, uint8
        import numpy as np

        if not isinstance(rgb, np.ndarray):  # seguridad extra
            raise TypeError("Se esperaba un array numpy para la imagen DEM")

        h, w, ch = rgb.shape
        assert ch == 3
        bytes_per_line = 3 * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
        return QPixmap.fromImage(qimg)

    def _zoom_at(self, factor: float, mx: int, my: int) -> None:
        if not self.renderer:
            return

        old_zoom = self.zoom
        new_zoom = max(self.zoom_min, min(self.zoom_max, old_zoom * factor))
        if abs(new_zoom - old_zoom) < 1e-12:
            return

        x0 = float(self._render_info["x0"])
        y0 = float(self._render_info["y0"])
        scale_old = float(self._render_info["scale"])

        rx = x0 + mx / scale_old
        ry = y0 + my / scale_old

        cw = max(2, self.width())
        ch = max(2, self.height())

        base_scale = min(cw / self.renderer.width, ch / self.renderer.height)
        base_scale = max(base_scale, 1e-9)
        scale_new = base_scale * new_zoom

        win_w = cw / scale_new
        win_h = ch / scale_new

        new_x0 = rx - mx / scale_new
        new_y0 = ry - my / scale_new

        new_x0 = max(0.0, min(new_x0, self.renderer.width - win_w))
        new_y0 = max(0.0, min(new_y0, self.renderer.height - win_h))

        self.zoom = new_zoom
        self.center_x = new_x0 + win_w / 2
        self.center_y = new_y0 + win_h / 2

        self._render_fast()
        self._schedule_hq()


class MainWindow(QMainWindow):
    """Ventana principal Qt. La UI procede de mainwindow.ui (generado con pyside6-uic)."""

    def __init__(self) -> None:
        super().__init__()

        # Carga la UI generada por Qt Designer / pyside6-uic
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # Aliases para que el resto del código no cambie
        self.cmb_reservorio = self.ui.cmbReservorio
        self.lbl_paths      = self.ui.lblPaths
        self.chk_use_mask   = self.ui.chkUseMask
        self.txt_salt       = self.ui.txtSalt
        self.txt_water      = self.ui.txtWater
        self.txt_occ        = self.ui.txtOcc
        self.tree           = self.ui.treeResults
        self.btn_pick_dem   = self.ui.btnPickDem
        self.btn_pick_mask  = self.ui.btnPickMask
        self.btn_calculate  = self.ui.btnCalculate
        self.btn_export_csv = self.ui.btnExportCsv
        self.btn_clear      = self.ui.btnClear

        # Rellenar combobox de reservorios
        self.cmb_reservorio.addItem("Reservorio")
        self.cmb_reservorio.addItems([f"Reservorio {i}" for i in range(1, 11)])

        # Insertar el visor DEM en el contenedor del .ui
        self.viewer = DemViewerWidget(self.ui.viewerContainer)
        self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container_layout = self.ui.viewerContainer.layout()
        if container_layout is None:
            container_layout = QVBoxLayout(self.ui.viewerContainer)
        container_layout.addWidget(self.viewer)

        # Estado
        self.dem_path: str | None = None
        self.mask_path: str | None = None
        self.latest_result: PondVolumes | None = None
        self.latest_rows: list[tuple[str, float, str]] = []

        # Anchos de columnas en resultados
        self.tree.setColumnWidth(0, 280)
        self.tree.setColumnWidth(1, 140)
        self.tree.setColumnWidth(2, 70)

        self._connect_signals()
        self._on_reservorio_changed(self.cmb_reservorio.currentIndex())

    # ------------------------------------------------------------------ #
    # Señales                                                             #
    # ------------------------------------------------------------------ #

    def _connect_signals(self) -> None:
        self.btn_pick_dem.clicked.connect(self.pick_dem)
        self.btn_pick_mask.clicked.connect(self.pick_mask)
        self.chk_use_mask.toggled.connect(self._set_paths_label)
        self.btn_calculate.clicked.connect(self.calculate)
        self.btn_export_csv.clicked.connect(self.export_csv)
        self.btn_clear.clicked.connect(self.clear_results)
        self.cmb_reservorio.currentIndexChanged.connect(self._on_reservorio_changed)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.viewer.clear()
        super().closeEvent(event)

    # Utilidades internas -------------------------------------------------

    def _set_paths_label(self) -> None:
        dem = self.dem_path if self.dem_path else "(sin DEM)"
        mask = self.mask_path if self.mask_path else "(sin contorno)"
        use = "Sí" if self.chk_use_mask.isChecked() and self.mask_path else "No"
        self.lbl_paths.setText(f"DEM: {dem}   |   Contorno: {mask}   |   Usar contorno: {use}")

    def _get_float(self, s: str, name: str) -> float:
        s = (s or "").strip().replace(",", ".")
        try:
            return float(s)
        except ValueError:
            raise ValueError(f"{name} debe ser numérico (ej. 2301.02).")

    # Utilidades de rutas --------------------------------------------------

    def _dems_dir(self) -> Path:
        """Resuelve la carpeta DEMs en desarrollo y en ejecutable PyInstaller."""
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent / "DEMs"
        return Path(__file__).parent.parent / "DEMs"

    def _on_reservorio_changed(self, index: int) -> None:
        """Carga automáticamente el DEM del reservorio seleccionado."""
        if index <= 0:  # placeholder "Reservorio"
            self.dem_path = None
            self.viewer.clear()
            self._set_paths_label()
            return
        number = index  # índice 1 → Reservorio 1, índice 2 → Reservorio 2 …
        dem_file = self._dems_dir() / f"MDE_R{number}.tif"
        if not dem_file.exists():
            self.dem_path = None
            self.viewer.clear()
            self._set_paths_label()
            return
        self.dem_path = str(dem_file)
        try:
            renderer = DemRenderer(self.dem_path, scale_mode="minmax", stats_sample=1024)
            self.viewer.set_renderer(renderer)
        except Exception as e:  # pragma: no cover - GUI
            QMessageBox.critical(self, "DEM", f"No se pudo cargar DEM:\n{e}")
            self.dem_path = None
        self._set_paths_label()

    def pick_dem(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecciona el DEM",
            "",
            "GeoTIFF (*.tif *.tiff);;Todos (*.*)",
        )
        if not path:
            return
        self.dem_path = path
        try:
            renderer = DemRenderer(self.dem_path, scale_mode="minmax", stats_sample=1024)
            self.viewer.set_renderer(renderer)
        except Exception as e:  # pragma: no cover - GUI
            QMessageBox.critical(self, "DEM", f"No se pudo cargar DEM:\n{e}")
        self._set_paths_label()

    def pick_mask(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecciona contorno (GeoJSON recomendado)",
            "",
            "GeoJSON (*.geojson *.json);;Shapefile (*.shp);;Todos (*.*)",
        )
        if not path:
            return
        self.mask_path = path
        self._set_paths_label()

    def calculate(self) -> None:
        if not self.dem_path:
            QMessageBox.critical(self, "Falta DEM", "Selecciona un DEM primero.")
            return

        try:
            salt = self._get_float(self.txt_salt.text(), "Cota de sal")
            water = self._get_float(self.txt_water.text(), "Cota pelo de agua")
            occ = self._get_float(self.txt_occ.text(), "Fracción ocluida")
            if not (0.0 <= occ <= 1.0):
                raise ValueError("Fracción ocluida debe estar entre 0 y 1 (ej. 0.20).")

            shapes = None
            if self.chk_use_mask.isChecked() and self.mask_path:
                shapes = load_mask_shapes(self.mask_path)

            dem = DemRaster(self.dem_path, mask_shapes=shapes).load()
            calc = PondVolumeCalculator(dem)
            res = calc.compute(salt, water, occluded_fraction=occ)

            self.latest_result = res
            self.latest_rows = res.to_rows()
            self._populate_table(self.latest_rows)

            # Advertencias de rango
            warnings_list = []
            if res.salt_level < res.dem_min or res.salt_level > res.dem_max:
                warnings_list.append(
                    f"  • Cota de sal ({res.salt_level:.2f} m) fuera del rango DEM "
                    f"[{res.dem_min:.2f} – {res.dem_max:.2f} m]."
                )
            if res.water_level < res.dem_min or res.water_level > res.dem_max:
                warnings_list.append(
                    f"  • Cota pelo de agua ({res.water_level:.2f} m) fuera del rango DEM "
                    f"[{res.dem_min:.2f} – {res.dem_max:.2f} m]."
                )
            if warnings_list:
                QMessageBox.warning(
                    self,
                    "Advertencia de rango",
                    "Las siguientes cotas están fuera del rango de elevación del DEM\n"
                    f"(mín: {res.dem_min:.2f} m, máx: {res.dem_max:.2f} m):\n\n"
                    + "\n".join(warnings_list)
                    + "\n\nEl cálculo se realizó de todas formas, pero los resultados "
                    "pueden ser cero o incorrectos.",
                )

        except MaskError as e:
            QMessageBox.critical(self, "Contorno", str(e))
        except DemError as e:
            QMessageBox.critical(self, "DEM", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _populate_table(self, rows: list[tuple[str, float, str]]) -> None:
        self.tree.clear()
        for item, value, unit in rows:
            if unit in ("m³", "m²", "kL", "ML"):
                v = fmt(value, 3)
            elif unit == "m":
                v = fmt(value, 2)
            elif unit == "-":
                v = fmt(value, 2)
            else:
                v = str(value)
            qitem = QTreeWidgetItem([item, v, unit])
            self.tree.addTopLevelItem(qitem)
        self.tree.resizeColumnToContents(0)

    def export_csv(self) -> None:
        if not self.latest_rows:
            QMessageBox.information(self, "Exportar", "Primero calcula resultados.")
            return
        initial = default_output_name()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar CSV",
            initial,
            "CSV (*.csv)",
        )
        if not path:
            return
        try:
            out = export_rows_to_csv(path, self.latest_rows)
            open_file_default_app(out)
        except Exception as e:
            QMessageBox.critical(self, "Exportar CSV", str(e))

    def clear_results(self) -> None:
        self.latest_result = None
        self.latest_rows = []
        self.tree.clear()


def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
