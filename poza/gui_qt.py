from __future__ import annotations

import json
import math
import sys
from enum import IntEnum
from pathlib import Path
from typing import Dict, List, Tuple

from PySide6.QtCore import Qt, QPointF, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .core import DemRaster, PondVolumeCalculator, DemError, PondVolumes
from .masks import load_mask_shapes, MaskError, polygon_raster_to_geojson
from .export import export_rows_to_csv, open_file_default_app, default_output_name
from .viz import DemRenderer, OrthoRenderer
from .ui_mainwindow import Ui_MainWindow

try:
    from .db import get_session, Repository
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False

try:
    from .firebase_sync import firebase_sync
    _FB_AVAILABLE = True
except ImportError:
    _FB_AVAILABLE = False


COLOR_PRIMARY   = "#29306A"
COLOR_ACCENT    = "#F75C03"
COLOR_TEXT      = "#333333"
COLOR_BG        = "#F6F6F6"
COLOR_SECONDARY = "#808B96"


def fmt(x: float, decimals: int = 3) -> str:
    return f"{x:,.{decimals}f}"


# ─────────────────────────────────────────────────────────────────────────────
# Estado de la herramienta de polígono
# ─────────────────────────────────────────────────────────────────────────────

class PolyTool(IntEnum):
    IDLE    = 0   # sin herramienta activa
    DRAWING = 1   # clic para agregar vértices
    CURSOR  = 2   # polígono cerrado; arrastrar vértices con ratón (T/R/Enter activos)


# ─────────────────────────────────────────────────────────────────────────────
# Diálogo de inicio de sesión
# ─────────────────────────────────────────────────────────────────────────────

class LoginDialog(QDialog):
    _STYLE = f"""
        QDialog    {{ background: {COLOR_BG}; }}
        QLabel#title  {{ font: bold 16pt "Segoe UI"; color: {COLOR_PRIMARY}; }}
        QLabel#subtitle {{ font: 9pt "Segoe UI"; color: {COLOR_SECONDARY}; }}
        QLabel#error  {{ font: bold 9pt "Segoe UI"; color: #C0392B; }}
        QLineEdit {{
            font: 10pt "Segoe UI"; padding: 6px 8px;
            border: 1px solid #C8CBE0; border-radius: 5px;
            background: white; color: {COLOR_TEXT};
        }}
        QLineEdit:focus {{ border: 2px solid {COLOR_PRIMARY}; }}
        QPushButton#btnLogin {{
            font: bold 10pt "Segoe UI"; color: white;
            background: {COLOR_PRIMARY}; border: none;
            border-radius: 5px; padding: 8px 24px;
        }}
        QPushButton#btnLogin:hover   {{ background: #3D4A9A; }}
        QPushButton#btnLogin:pressed {{ background: {COLOR_ACCENT}; }}
        QLabel {{ font: 9pt "Segoe UI"; color: {COLOR_TEXT}; }}
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cubicador de Pozas — Inicio de sesión")
        self.setFixedSize(400, 300)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setStyleSheet(self._STYLE)
        self._user_id: int | None = None
        self._user_nombre = self._user_username = ""
        self._user_rol = "operador"
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(10)
        lbl = QLabel("Iniciar sesión"); lbl.setObjectName("title"); layout.addWidget(lbl)
        sub = QLabel("Cubicador de Pozas · Operación Atacama"); sub.setObjectName("subtitle"); layout.addWidget(sub)
        layout.addSpacing(12)
        form = QFormLayout(); form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._txt_user = QLineEdit(); self._txt_user.setPlaceholderText("Usuario"); self._txt_user.setMaxLength(64)
        self._txt_pass = QLineEdit(); self._txt_pass.setPlaceholderText("Contraseña")
        self._txt_pass.setEchoMode(QLineEdit.Password); self._txt_pass.setMaxLength(128)
        self._txt_pass.returnPressed.connect(self._try_login)
        form.addRow("Usuario:", self._txt_user); form.addRow("Contraseña:", self._txt_pass)
        layout.addLayout(form)
        self._lbl_error = QLabel(""); self._lbl_error.setObjectName("error")
        self._lbl_error.setAlignment(Qt.AlignCenter); layout.addWidget(self._lbl_error)
        layout.addStretch()
        btn = QPushButton("Acceder"); btn.setObjectName("btnLogin"); btn.setDefault(True)
        btn.clicked.connect(self._try_login); layout.addWidget(btn, alignment=Qt.AlignRight)

    def _try_login(self) -> None:
        username = self._txt_user.text().strip()
        password = self._txt_pass.text()
        if not username or not password:
            self._lbl_error.setText("Ingresa usuario y contraseña."); return
        if not _DB_AVAILABLE:
            self._user_nombre = self._user_username = username; self.accept(); return
        try:
            with get_session() as session:
                repo = Repository(session)
                user = repo.authenticate(username, password)
                self._user_id = user.id; self._user_nombre = user.nombre_completo
                self._user_username = user.username; self._user_rol = user.rol
                repo.log("login", usuario=user, detalle={"ip": "localhost"})
            self._lbl_error.setText(""); self.accept()
        except Exception as e:
            try:
                with get_session() as s:
                    Repository(s).log("login_fallido", detalle={"username": username, "motivo": str(e)})
            except Exception: pass
            self._lbl_error.setText(str(e)); self._txt_pass.clear(); self._txt_pass.setFocus()

    @property
    def user_id(self):       return self._user_id
    @property
    def user_nombre(self):   return self._user_nombre
    @property
    def user_username(self): return self._user_username
    @property
    def user_rol(self):      return self._user_rol


# ─────────────────────────────────────────────────────────────────────────────
# Visor DEM / Ortofoto con preservación de aspect-ratio y herramienta polígono
# ─────────────────────────────────────────────────────────────────────────────

class DemViewerWidget(QWidget):
    """
    • Letterboxing estricto (aspect ratio del ráster nunca se deforma)
    • Renderizadores DEM / ortofoto intercambiables
    • Herramienta polígono:
        DRAWING  → clic añade vértices; clic en inicio cierra → CURSOR
        CURSOR   → arrastrar vértice mueve; T=añadir arista; R=quitar; Enter=confirmar
    """

    polygon_committed  = Signal(list)   # [lista GeoJSON shapes]
    poly_tool_changed  = Signal(int)    # emitido al cambiar PolyTool

    CLOSE_DIST_PX: float = 14.0
    VERTEX_HIT_PX: float = 14.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.StrongFocus)

        self._dem_renderer:   DemRenderer   | None = None
        self._ortho_renderer: OrthoRenderer | None = None
        self._use_ortho = False

        self.zoom = 1.0; self.zoom_min = 0.35; self.zoom_max = 12.0
        self.center_x = self.center_y = 0.0

        self._pixmap: QPixmap | None = None
        self._render_info: Dict = {
            "x0": 0.0, "y0": 0.0, "scale": 1.0, "base_scale": 1.0,
            "off_x": 0.0, "off_y": 0.0, "render_w": 1, "render_h": 1,
        }
        self._fast_timer = QTimer(self); self._fast_timer.setSingleShot(True)
        self._fast_timer.timeout.connect(self._do_render_fast)
        self._hq_timer   = QTimer(self); self._hq_timer.setSingleShot(True)
        self._hq_timer.timeout.connect(self._render_hq)
        self._pan_anchor: tuple | None = None

        # Polígono
        self._poly_tool: PolyTool = PolyTool.IDLE
        self._poly_verts_raster: List[Tuple[float, float]] = []
        self._poly_closed = False
        self._poly_mouse_screen: Tuple[float, float] = (0.0, 0.0)
        self._drag_vertex_idx: int | None = None   # índice del vértice arrastrado

    # ── Renderer activo ───────────────────────────────────────────────────────

    @property
    def renderer(self):
        return self._ortho_renderer if self._use_ortho else self._dem_renderer

    # ── API pública ───────────────────────────────────────────────────────────

    def set_dem_renderer(self, r: DemRenderer) -> None:
        if self._dem_renderer: self._dem_renderer.close()
        self._dem_renderer = r; r.build_cache(max_tex=2048, levels=4)
        if not self._use_ortho: self._reset_view(r)

    def set_ortho_renderer(self, r: OrthoRenderer) -> None:
        if self._ortho_renderer: self._ortho_renderer.close()
        self._ortho_renderer = r; r.build_cache(max_tex=2048, levels=4)
        if self._use_ortho: self._render_fast(); self._schedule_hq(60)

    def set_use_ortho(self, use: bool) -> None:
        if use and not self._ortho_renderer: return
        self._use_ortho = use
        if self.renderer: self._render_fast(); self._schedule_hq(60)

    def set_renderer(self, r: DemRenderer) -> None:   # compatibilidad
        self.set_dem_renderer(r)

    def clear(self) -> None:
        if self._dem_renderer:   self._dem_renderer.close()
        if self._ortho_renderer: self._ortho_renderer.close()
        self._dem_renderer = self._ortho_renderer = self._pixmap = None
        self.clear_polygon(); self.update()

    def set_poly_tool(self, tool: PolyTool) -> None:
        prev = self._poly_tool
        self._poly_tool = tool
        self._drag_vertex_idx = None
        if tool == PolyTool.DRAWING:
            self._poly_verts_raster.clear(); self._poly_closed = False
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        if tool != prev: self.poly_tool_changed.emit(int(tool))
        self.update()

    def clear_polygon(self) -> None:
        prev = self._poly_tool
        self._poly_tool = PolyTool.IDLE
        self._poly_verts_raster.clear(); self._poly_closed = False
        self._drag_vertex_idx = None; self.setCursor(Qt.ArrowCursor)
        if prev != PolyTool.IDLE: self.poly_tool_changed.emit(0)
        self.update()

    # ── Eventos Qt ────────────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event); self._render_fast(); self._schedule_hq()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(20, 20, 30))   # fondo letterbox
        if self._pixmap:
            p.drawPixmap(int(self._render_info.get("off_x", 0)),
                         int(self._render_info.get("off_y", 0)), self._pixmap)
        if self._poly_tool != PolyTool.IDLE and self._poly_verts_raster:
            self._draw_poly_overlay(p)
        elif self._poly_tool == PolyTool.DRAWING:
            self._draw_hint(p, "  Clic=agregar vértice   Clic en inicio=cerrar   Esc=cancelar  ")
        p.end()

    def mousePressEvent(self, event) -> None:
        self.setFocus()
        sx, sy = float(event.position().x()), float(event.position().y())

        # ── DRAWING ──────────────────────────────────────────────────────────
        if self._poly_tool == PolyTool.DRAWING:
            if event.button() == Qt.LeftButton:
                if len(self._poly_verts_raster) >= 3 and self._should_close(sx, sy):
                    self._poly_closed = True
                    self.set_poly_tool(PolyTool.CURSOR)   # auto-switch; emite señal
                else:
                    self._poly_verts_raster.append(self._s2r(sx, sy)); self.update()
            return

        # ── CURSOR ───────────────────────────────────────────────────────────
        if self._poly_tool == PolyTool.CURSOR:
            if event.button() == Qt.LeftButton:
                idx = self._nearest_vertex_idx(sx, sy)
                if idx is not None:
                    self._drag_vertex_idx = idx; self.setCursor(Qt.ClosedHandCursor)
            elif event.button() == Qt.RightButton:
                self._pan_anchor = (sx, sy, self.center_x, self.center_y)
            return

        # ── IDLE: pan con botón izquierdo ─────────────────────────────────────
        if event.button() == Qt.LeftButton:
            self._pan_anchor = (sx, sy, self.center_x, self.center_y)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        sx, sy = float(event.position().x()), float(event.position().y())
        self._poly_mouse_screen = (sx, sy)

        if self._poly_tool == PolyTool.DRAWING:
            self.update(); return

        if self._poly_tool == PolyTool.CURSOR:
            if self._drag_vertex_idx is not None:
                rx, ry = self._s2r(sx, sy)
                r = self.renderer
                if r:
                    rx = max(0.0, min(rx, r.width)); ry = max(0.0, min(ry, r.height))
                self._poly_verts_raster[self._drag_vertex_idx] = (rx, ry)
            elif self._pan_anchor:
                x0, y0, cx0, cy0 = self._pan_anchor
                sc = float(self._render_info.get("scale", 1.0))
                if self.renderer:
                    self.center_x = max(0.0, min(cx0 - (sx - x0) / sc, self.renderer.width))
                    self.center_y = max(0.0, min(cy0 - (sy - y0) / sc, self.renderer.height))
                    self._render_fast(); self._schedule_hq()
            else:
                idx = self._nearest_vertex_idx(sx, sy)
                self.setCursor(Qt.PointingHandCursor if idx is not None else Qt.ArrowCursor)
            self.update(); return

        if self._pan_anchor and self.renderer:
            x0, y0, cx0, cy0 = self._pan_anchor
            sc = float(self._render_info.get("scale", 1.0))
            self.center_x = max(0.0, min(cx0 - (sx - x0) / sc, self.renderer.width))
            self.center_y = max(0.0, min(cy0 - (sy - y0) / sc, self.renderer.height))
            self._render_fast(); self._schedule_hq()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_vertex_idx is not None and event.button() == Qt.LeftButton:
            self._drag_vertex_idx = None
            sx, sy = float(event.position().x()), float(event.position().y())
            idx = self._nearest_vertex_idx(sx, sy)
            self.setCursor(Qt.PointingHandCursor if idx is not None else Qt.ArrowCursor)
            self._schedule_hq(); return
        if event.button() in (Qt.LeftButton, Qt.RightButton) and self._pan_anchor:
            self._schedule_hq(); self._pan_anchor = None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        if not self.renderer: return
        factor = 1.10 if event.angleDelta().y() > 0 else 1 / 1.10
        p = event.position()
        self._zoom_at(factor, int(p.x()), int(p.y()))

    def keyPressEvent(self, event) -> None:
        k = event.key()
        if k == Qt.Key_Escape:
            self.clear_polygon(); return
        if self._poly_tool == PolyTool.CURSOR and self._poly_closed:
            if k == Qt.Key_T:
                self._insert_vertex_at_cursor(self._poly_mouse_screen); return
            if k == Qt.Key_R:
                self._remove_nearest_vertex(self._poly_mouse_screen); return
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self._commit_polygon(); return
        super().keyPressEvent(event)

    # ── Coordenadas ───────────────────────────────────────────────────────────

    def _s2r(self, sx: float, sy: float) -> Tuple[float, float]:
        i = self._render_info
        return (i["x0"] + (sx - i["off_x"]) / i["scale"],
                i["y0"] + (sy - i["off_y"]) / i["scale"])

    def _r2s(self, rx: float, ry: float) -> Tuple[float, float]:
        i = self._render_info
        return (i["off_x"] + (rx - i["x0"]) * i["scale"],
                i["off_y"] + (ry - i["y0"]) * i["scale"])

    # ── Lógica polígono ───────────────────────────────────────────────────────

    def _should_close(self, sx: float, sy: float) -> bool:
        if len(self._poly_verts_raster) < 3: return False
        fsx, fsy = self._r2s(*self._poly_verts_raster[0])
        return math.hypot(sx - fsx, sy - fsy) <= self.CLOSE_DIST_PX

    def _nearest_vertex_idx(self, sx: float, sy: float) -> int | None:
        if not self._poly_verts_raster: return None
        best_i, best_d = 0, float("inf")
        for i, (rx, ry) in enumerate(self._poly_verts_raster):
            vsx, vsy = self._r2s(rx, ry)
            d = math.hypot(sx - vsx, sy - vsy)
            if d < best_d: best_d, best_i = d, i
        return best_i if best_d <= self.VERTEX_HIT_PX else None

    def _insert_vertex_at_cursor(self, ms: Tuple[float, float]) -> None:
        v = self._poly_verts_raster
        if len(v) < 2: return
        mx_r, my_r = self._s2r(*ms)
        best_dist, best_idx, best_pt = float("inf"), 0, (mx_r, my_r)
        for i in range(len(v)):
            a, b = v[i], v[(i + 1) % len(v)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            s2 = dx * dx + dy * dy
            if s2 < 1e-12: continue
            t = max(0.0, min(1.0, ((mx_r - a[0]) * dx + (my_r - a[1]) * dy) / s2))
            px, py = a[0] + t * dx, a[1] + t * dy
            d2 = (mx_r - px) ** 2 + (my_r - py) ** 2
            if d2 < best_dist: best_dist, best_idx, best_pt = d2, i, (px, py)
        v.insert(best_idx + 1, best_pt); self.update()

    def _remove_nearest_vertex(self, ms: Tuple[float, float]) -> None:
        v = self._poly_verts_raster
        if len(v) <= 3: return
        mx_r, my_r = self._s2r(*ms)
        del v[min(range(len(v)), key=lambda i: (v[i][0]-mx_r)**2+(v[i][1]-my_r)**2)]
        self.update()

    def _commit_polygon(self) -> None:
        r = self._dem_renderer or self._ortho_renderer
        if not r or not self._poly_verts_raster: return
        try:
            shape = polygon_raster_to_geojson(self._poly_verts_raster, r.transform)
            self.polygon_committed.emit([shape])
        except Exception: pass
        self.clear_polygon()

    # ── Overlay polígono ──────────────────────────────────────────────────────

    def _draw_hint(self, p: QPainter, text: str) -> None:
        p.setPen(QColor(255, 255, 255, 200))
        p.fillRect(4, self.height() - 22, self.width() - 8, 18, QColor(0, 0, 0, 130))
        p.drawText(8, self.height() - 7, text)

    def _draw_poly_overlay(self, p: QPainter) -> None:
        vs = [self._r2s(rx, ry) for rx, ry in self._poly_verts_raster]
        if not vs: return
        mx, my = self._poly_mouse_screen
        n = len(vs)

        # Relleno traslúcido
        if self._poly_closed and n >= 3:
            p.setBrush(QColor(255, 200, 50, 45)); p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([QPointF(sx, sy) for sx, sy in vs]))

        # Aristas
        edge_pen = QPen(QColor(255, 180, 0), 2); edge_pen.setCosmetic(True)
        p.setPen(edge_pen); p.setBrush(Qt.NoBrush)
        for i in range(n - 1):
            p.drawLine(QPointF(*vs[i]), QPointF(*vs[i + 1]))
        if self._poly_closed and n >= 2:
            p.drawLine(QPointF(*vs[-1]), QPointF(*vs[0]))

        # Línea guía al cursor (DRAWING)
        if self._poly_tool == PolyTool.DRAWING:
            gp = QPen(QColor(255, 255, 100, 180), 1, Qt.DashLine); gp.setCosmetic(True)
            p.setPen(gp); p.drawLine(QPointF(*vs[-1]), QPointF(mx, my))
            if n >= 3:
                fsx, fsy = vs[0]; rd = self.CLOSE_DIST_PX
                d = math.hypot(mx - fsx, my - fsy)
                if d <= rd:
                    p.setPen(QPen(QColor(50, 255, 120), 2)); p.setBrush(QColor(50, 255, 120, 80))
                else:
                    p.setPen(QPen(QColor(255, 180, 0), 1)); p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(fsx, fsy), rd, rd)

        # Vértices
        hover_idx = self._nearest_vertex_idx(mx, my) if self._poly_tool == PolyTool.CURSOR else None
        for idx, (sx, sy) in enumerate(vs):
            if self._drag_vertex_idx == idx:
                p.setPen(QPen(QColor(80, 200, 255), 2)); p.setBrush(QColor(80, 200, 255, 230))
                p.drawEllipse(QPointF(sx, sy), 7.0, 7.0)
            elif hover_idx == idx:
                p.setPen(QPen(QColor(255, 80, 80), 2)); p.setBrush(QColor(255, 80, 80, 200))
                p.drawEllipse(QPointF(sx, sy), 6.0, 6.0)
            else:
                p.setPen(QPen(QColor(255, 220, 50), 2)); p.setBrush(QColor(255, 220, 50, 210))
                p.drawEllipse(QPointF(sx, sy), 4.5, 4.5)

        # Hint teclado
        if self._poly_tool == PolyTool.CURSOR and self._poly_closed:
            self._draw_hint(p, "  Arrastrar=mover   T=insertar   R=quitar   Enter=confirmar   Esc=cancelar  ")

    # ── Render ────────────────────────────────────────────────────────────────

    def _reset_view(self, r) -> None:
        self.zoom = 1.0; self.center_x = r.width / 2.0; self.center_y = r.height / 2.0
        self._render_fast(); self._schedule_hq(60)

    def _render_fast(self) -> None: self._fast_timer.start(8)

    def _do_render_fast(self) -> None:
        r = self.renderer
        if not r: return
        rgb, info = r.render_view_cached(
            center_x=self.center_x, center_y=self.center_y, zoom=self.zoom,
            canvas_w=max(2, self.width()), canvas_h=max(2, self.height()))
        self._render_info = info; self._pixmap = self._rgb_to_pixmap(rgb); self.update()

    def _schedule_hq(self, delay_ms: int = 220) -> None: self._hq_timer.start(delay_ms)

    def _render_hq(self) -> None:
        r = self.renderer
        if not r: return
        rgb, info = r.render_view_hq(
            center_x=self.center_x, center_y=self.center_y, zoom=self.zoom,
            canvas_w=max(2, self.width()), canvas_h=max(2, self.height()),
            hillshade=not self._use_ortho)
        self._render_info = info; self._pixmap = self._rgb_to_pixmap(rgb); self.update()

    def _rgb_to_pixmap(self, rgb) -> QPixmap:
        h, w, _ = rgb.shape
        return QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy())

    def _zoom_at(self, factor: float, mx: int, my: int) -> None:
        if not self.renderer: return
        new_zoom = max(self.zoom_min, min(self.zoom_max, self.zoom * factor))
        if abs(new_zoom - self.zoom) < 1e-12: return
        i = self._render_info
        off_x, off_y = float(i.get("off_x", 0)), float(i.get("off_y", 0))
        scale_old = float(i["scale"])
        rx = float(i["x0"]) + (mx - off_x) / scale_old
        ry = float(i["y0"]) + (my - off_y) / scale_old
        cw, ch = max(2, self.width()), max(2, self.height())
        base    = max(min(cw / self.renderer.width, ch / self.renderer.height), 1e-9)
        sc_new  = base * new_zoom
        win_w, win_h = cw / sc_new, ch / sc_new
        new_x0 = max(0.0, min(rx - (mx - off_x) / sc_new, self.renderer.width  - win_w))
        new_y0 = max(0.0, min(ry - (my - off_y) / sc_new, self.renderer.height - win_h))
        self.zoom = new_zoom
        self.center_x = new_x0 + win_w / 2
        self.center_y = new_y0 + win_h / 2
        self._render_fast(); self._schedule_hq()


# ─────────────────────────────────────────────────────────────────────────────
# Panel de historial
# ─────────────────────────────────────────────────────────────────────────────

class HistoryPanel(QWidget):
    TAB_MEDICIONES, TAB_DEMS, TAB_IMAGENES = 0, 1, 2

    _BTN = """
        QPushButton { font: bold 9pt "Segoe UI"; padding: 5px 14px; border: none;
            border-radius: 4px 4px 0 0; background: #EAECF4; color: #555577; }
        QPushButton:hover   { background: #D8DBF0; color: #29306A; }
        QPushButton:checked { background: #29306A; color: white; border-bottom: 3px solid #F75C03; }
    """
    _TBL = """
        QTableWidget { font: 9pt "Segoe UI"; border: none; background: #FAFBFF;
            alternate-background-color: #F0F2FA; gridline-color: #E8EAF6; color: #222244; }
        QHeaderView::section { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #3D4A9A, stop:1 #29306A); color: white; font: bold 9pt "Segoe UI";
            padding: 5px 6px; border: none; border-right: 1px solid #4A58B8; }
        QTableWidget::item { padding: 3px 6px; }
        QTableWidget::item:selected { background: #29306A; color: white; }
        QScrollBar:vertical { background: #F0F2FA; width: 7px; border-radius: 3px; }
        QScrollBar::handle:vertical { background: #C0C5E0; border-radius: 3px; min-height: 24px; }
        QScrollBar::handle:vertical:hover { background: #29306A; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(60)
        self.setStyleSheet("background: #FFFFFF;")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self); root.setContentsMargins(0, 4, 0, 0); root.setSpacing(0)

        bar = QWidget(); bar.setStyleSheet("background: transparent;")
        bl  = QHBoxLayout(bar); bl.setContentsMargins(2, 0, 0, 0); bl.setSpacing(3)
        self._btn_group = QButtonGroup(self); self._btn_group.setExclusive(True)
        for label, idx in [("📋  Mediciones", 0), ("🗺  DEMs", 1), ("🖼  Imágenes", 2)]:
            btn = QPushButton(label); btn.setCheckable(True); btn.setStyleSheet(self._BTN)
            self._btn_group.addButton(btn, idx); bl.addWidget(btn)
        bl.addStretch(); self._btn_group.button(0).setChecked(True)
        root.addWidget(bar)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #D0D4E8; margin: 0;"); sep.setFixedHeight(1)
        root.addWidget(sep)

        self._stack = QStackedWidget(); root.addWidget(self._stack)
        self.tbl_mediciones = self._make_table([
            "Fecha", "Operador", "Cota Sal (m)", "Cota Agua (m)",
            "Vol. Sal (m³)", "Vol. Salmuera (m³)", "Área Espejo (m²)", "Notas",
        ])
        self.tbl_dems = self._make_table(["Fecha Carga", "Archivo", "Fecha Vuelo", "Cargado por"])
        self._stack.addWidget(self.tbl_mediciones)
        self._stack.addWidget(self.tbl_dems)
        self._stack.addWidget(self._make_placeholder("📷  Módulo de imágenes fotogramétricas — próximamente."))
        self._btn_group.idClicked.connect(self._stack.setCurrentIndex)

    def _make_table(self, headers: list[str]) -> QTableWidget:
        tbl = QTableWidget(0, len(headers)); tbl.setHorizontalHeaderLabels(headers)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setAlternatingRowColors(True); tbl.setStyleSheet(self._TBL); tbl.setShowGrid(True)
        return tbl

    def _make_placeholder(self, msg: str) -> QWidget:
        w = QWidget(); w.setStyleSheet("background: #FAFBFF;")
        lbl = QLabel(msg); lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #9098B5; font: italic 10pt 'Segoe UI';")
        QVBoxLayout(w).addWidget(lbl); return w

    def load_reservorio(self, codigo: str) -> None:
        self.tbl_mediciones.setRowCount(0); self.tbl_dems.setRowCount(0)
        if not _DB_AVAILABLE: return
        try:
            with get_session() as session:
                repo = Repository(session)
                res  = repo.get_reservorio_by_codigo(codigo)
                if not res: return
                for c in repo.list_cubicaciones(res.id):
                    r = self.tbl_mediciones.rowCount(); self.tbl_mediciones.insertRow(r)
                    fecha = c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "—"
                    op    = c.usuario.nombre_completo if c.usuario else "—"
                    for col, val in enumerate([
                        fecha, op, f"{c.cota_sal:.3f}", f"{c.cota_agua:.3f}",
                        fmt(c.vol_sal_m3, 1)            if c.vol_sal_m3            is not None else "—",
                        fmt(c.vol_salmuera_total_m3, 1) if c.vol_salmuera_total_m3 is not None else "—",
                        fmt(c.area_espejo_m2, 1)        if c.area_espejo_m2        is not None else "—",
                        c.notas or "",
                    ]):
                        self._cell(self.tbl_mediciones, r, col, val)
                for d in repo.list_dems(res.id):
                    r = self.tbl_dems.rowCount(); self.tbl_dems.insertRow(r)
                    fecha = d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else "—"
                    cb    = d.cargado_por_usuario.nombre_completo if d.cargado_por_usuario else "—"
                    for col, val in enumerate([fecha, d.archivo, d.fecha_vuelo or "—", cb]):
                        self._cell(self.tbl_dems, r, col, val)
        except Exception: pass

    def clear(self) -> None:
        self.tbl_mediciones.setRowCount(0); self.tbl_dems.setRowCount(0)

    @staticmethod
    def _cell(tbl, row, col, text, align=Qt.AlignVCenter | Qt.AlignLeft) -> None:
        it = QTableWidgetItem(str(text)); it.setTextAlignment(align); tbl.setItem(row, col, it)


# ─────────────────────────────────────────────────────────────────────────────
# Estilos botones toolbar
# ─────────────────────────────────────────────────────────────────────────────

_BTN = """
    QPushButton {
        font: 9pt "Segoe UI"; padding: 4px 11px; min-height: 24px;
        border: 1px solid #C8CBE0; border-radius: 4px;
        background: #F0F2FA; color: #29306A;
    }
    QPushButton:hover    { background: #E0E4F0; }
    QPushButton:checked  { background: #29306A; color: white; border-color: #29306A; }
    QPushButton:pressed  { background: #F75C03; color: white; }
    QPushButton:disabled { color: #AAAAAA; background: #F5F5F5; border-color: #E0E0E0; }
"""
_SEP = "QFrame { color: #C8CBE0; margin: 3px 2px; }"


# ─────────────────────────────────────────────────────────────────────────────
# Ventana principal
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self, user_id=None, user_nombre="", user_username="", user_rol="operador") -> None:
        super().__init__()
        self._user_id = user_id; self._user_nombre = user_nombre
        self._user_username = user_username; self._user_rol = user_rol

        self.ui = Ui_MainWindow(); self.ui.setupUi(self)
        self.setWindowTitle(f"Cubicador de Pozas  ·  {user_nombre or user_username or 'sin sesión'}")

        # Aliases
        self.cmb_reservorio = self.ui.cmbReservorio; self.lbl_paths = self.ui.lblPaths
        self.chk_use_mask   = self.ui.chkUseMask;   self.txt_salt  = self.ui.txtSalt
        self.txt_water      = self.ui.txtWater;      self.txt_occ   = self.ui.txtOcc
        self.tree           = self.ui.treeResults
        self.btn_pick_dem   = self.ui.btnPickDem;    self.btn_pick_mask  = self.ui.btnPickMask
        self.btn_calculate  = self.ui.btnCalculate;  self.btn_export_csv = self.ui.btnExportCsv
        self.btn_clear      = self.ui.btnClear

        # Estado
        self.dem_path = self.mask_path = None
        self.latest_result: PondVolumes | None = None
        self.latest_rows: list = []
        self.current_reservorio_codigo: str | None = None
        self._current_dem_id: int | None = None

        self.cmb_reservorio.addItem("Reservorio")
        self.cmb_reservorio.addItems([f"Reservorio {i}" for i in range(1, 11)])

        # ── Toolbar del visor ─────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet("background: #EAECF4; border-bottom: 1px solid #C8CBE0;")
        tl = QHBoxLayout(toolbar); tl.setContentsMargins(6, 3, 6, 3); tl.setSpacing(4)

        # Grupo ortofoto
        self.btn_pick_ortho = QPushButton("📂  Cargar ortofoto…")
        self.btn_ortho      = QPushButton("🛰  Ortofoto")
        self.btn_ortho.setCheckable(True); self.btn_ortho.setEnabled(False)
        for b in (self.btn_pick_ortho, self.btn_ortho): b.setStyleSheet(_BTN); tl.addWidget(b)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.VLine); sep1.setStyleSheet(_SEP); tl.addWidget(sep1)

        # Grupo polígono
        self.btn_draw_poly   = QPushButton("✏  Dibujar")
        self.btn_cursor_poly = QPushButton("↖  Cursor")
        self.btn_clear_poly  = QPushButton("🗑  Borrar")
        self.btn_draw_poly.setCheckable(True)
        self.btn_cursor_poly.setCheckable(True); self.btn_cursor_poly.setEnabled(False)
        for b in (self.btn_draw_poly, self.btn_cursor_poly, self.btn_clear_poly):
            b.setStyleSheet(_BTN); tl.addWidget(b)

        tl.addStretch()

        # ── Visor ─────────────────────────────────────────────────────────────
        self.viewer = DemViewerWidget()
        self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Container: toolbar encima + viewer abajo
        viewer_box = QWidget()
        vbl = QVBoxLayout(viewer_box); vbl.setContentsMargins(0, 0, 0, 0); vbl.setSpacing(0)
        vbl.addWidget(toolbar)
        vbl.addWidget(self.viewer, stretch=1)

        # ── Panel historial ───────────────────────────────────────────────────
        self.history_panel = HistoryPanel()

        # ── Splitter vertical viewer ↕ historial ─────────────────────────────
        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.setChildrenCollapsible(True)
        self._splitter.addWidget(viewer_box)
        self._splitter.addWidget(self.history_panel)
        self._splitter.setStretchFactor(0, 4); self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([550, 200])
        self._splitter.setStyleSheet(
            "QSplitter::handle { background: #C8CBE0; height: 5px; }"
            "QSplitter::handle:hover { background: #29306A; }"
        )

        # Reemplazar viewerContainer en el layout de groupDem con el splitter
        dem_layout = self.ui.groupDem.layout()
        dem_layout.removeWidget(self.ui.viewerContainer)
        self.ui.viewerContainer.hide()   # ya no lo usamos
        dem_layout.addWidget(self._splitter)
        self.history_panel.hide()

        # Columnas resultados
        self.tree.setColumnWidth(0, 280); self.tree.setColumnWidth(1, 140); self.tree.setColumnWidth(2, 70)

        self._connect_signals()
        self._on_reservorio_changed(self.cmb_reservorio.currentIndex())

    # ── Señales ───────────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self.btn_pick_dem.clicked.connect(self.pick_dem)
        self.btn_pick_mask.clicked.connect(self.pick_mask)
        self.chk_use_mask.toggled.connect(self._set_paths_label)
        self.btn_calculate.clicked.connect(self.calculate)
        self.btn_export_csv.clicked.connect(self.export_csv)
        self.btn_clear.clicked.connect(self.clear_results)
        self.cmb_reservorio.currentIndexChanged.connect(self._on_reservorio_changed)
        # Toolbar visor
        self.btn_pick_ortho.clicked.connect(self.pick_ortho)
        self.btn_ortho.toggled.connect(lambda c: self.viewer.set_use_ortho(c))
        self.btn_draw_poly.toggled.connect(self._on_draw_poly_toggled)
        self.btn_cursor_poly.toggled.connect(self._on_cursor_poly_toggled)
        self.btn_clear_poly.clicked.connect(self._on_clear_poly)
        self.viewer.polygon_committed.connect(self._on_polygon_committed)
        self.viewer.poly_tool_changed.connect(self._on_viewer_poly_tool_changed)

    def closeEvent(self, event) -> None:
        self._audit("logout"); self.viewer.clear(); super().closeEvent(event)

    # ── Handlers polígono ─────────────────────────────────────────────────────

    def _on_draw_poly_toggled(self, checked: bool) -> None:
        if checked:
            self.btn_cursor_poly.blockSignals(True); self.btn_cursor_poly.setChecked(False); self.btn_cursor_poly.blockSignals(False)
            self.viewer.set_poly_tool(PolyTool.DRAWING); self.viewer.setFocus()
        else:
            if self.viewer._poly_tool == PolyTool.DRAWING:
                self.viewer.clear_polygon()

    def _on_cursor_poly_toggled(self, checked: bool) -> None:
        if checked:
            if not self.viewer._poly_closed:
                self.btn_cursor_poly.blockSignals(True); self.btn_cursor_poly.setChecked(False); self.btn_cursor_poly.blockSignals(False)
                return
            self.btn_draw_poly.blockSignals(True); self.btn_draw_poly.setChecked(False); self.btn_draw_poly.blockSignals(False)
            self.viewer.set_poly_tool(PolyTool.CURSOR); self.viewer.setFocus()
        else:
            if self.viewer._poly_tool == PolyTool.CURSOR:
                self.viewer.clear_polygon()

    def _on_viewer_poly_tool_changed(self, tool_int: int) -> None:
        """Sincroniza botones cuando el visor cambia de herramienta internamente."""
        tool = PolyTool(tool_int)
        for btn in (self.btn_draw_poly, self.btn_cursor_poly): btn.blockSignals(True)
        self.btn_draw_poly.setChecked(tool == PolyTool.DRAWING)
        self.btn_cursor_poly.setChecked(tool == PolyTool.CURSOR)
        self.btn_cursor_poly.setEnabled(self.viewer._poly_closed)
        for btn in (self.btn_draw_poly, self.btn_cursor_poly): btn.blockSignals(False)

    def _on_clear_poly(self) -> None:
        self.viewer.clear_polygon()
        for b in (self.btn_draw_poly, self.btn_cursor_poly):
            b.blockSignals(True); b.setChecked(False); b.blockSignals(False)
        self.btn_cursor_poly.setEnabled(False)

    def _on_polygon_committed(self, shapes: list) -> None:
        data_dir = self._dems_dir()
        try: data_dir.mkdir(parents=True, exist_ok=True)
        except Exception: data_dir = Path(__file__).parent.parent
        n = self.current_reservorio_codigo or "X"
        out = data_dir / f"contorno_dibujado_{n}.geojson"
        doc = {"type": "FeatureCollection",
               "features": [{"type": "Feature", "geometry": s, "properties": {}} for s in shapes]}
        try:
            out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "Polígono", f"No se pudo guardar:\n{e}"); return
        self.mask_path = str(out); self.chk_use_mask.setChecked(True); self._set_paths_label()
        self.btn_cursor_poly.setEnabled(False)
        QMessageBox.information(self, "Polígono guardado",
                                f"Guardado como:\n{out.name}\n\nActivo como contorno.")

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _set_paths_label(self) -> None:
        dem  = self.dem_path  or "(sin DEM)"
        mask = self.mask_path or "(sin contorno)"
        use  = "Sí" if self.chk_use_mask.isChecked() and self.mask_path else "No"
        self.lbl_paths.setText(f"DEM: {dem}   |   Contorno: {mask}   |   Usar contorno: {use}")

    def _get_float(self, s: str, name: str) -> float:
        try: return float((s or "").strip().replace(",", "."))
        except ValueError: raise ValueError(f"{name} debe ser numérico.")

    def _dems_dir(self) -> Path:
        return (Path(sys.executable).parent if getattr(sys, "frozen", False)
                else Path(__file__).parent.parent) / "DEMs"

    def _audit(self, accion: str, detalle: dict | None = None) -> None:
        if not _DB_AVAILABLE or self._user_id is None: return
        try:
            with get_session() as s:
                repo = Repository(s)
                repo.log(accion, usuario=repo.get_user_by_id(self._user_id), detalle=detalle)
        except Exception: pass

    # ── Cambio de reservorio ──────────────────────────────────────────────────

    def _on_reservorio_changed(self, index: int) -> None:
        if index <= 0:
            self.current_reservorio_codigo = self._current_dem_id = self.dem_path = None
            self.viewer.clear(); self.history_panel.clear(); self.history_panel.hide()
            self._set_paths_label(); return

        self.current_reservorio_codigo = f"R{index}"; self._current_dem_id = None
        dem_file = self._dems_dir() / f"MDE_R{index}.tif"
        if dem_file.exists():
            self.dem_path = str(dem_file)
            try:
                r = DemRenderer(self.dem_path, scale_mode="minmax", stats_sample=1024)
                self.viewer.set_dem_renderer(r); self.viewer._reset_view(r)
            except Exception as e:
                QMessageBox.critical(self, "DEM", f"No se pudo cargar DEM:\n{e}")
                self.dem_path = None; self.viewer.clear()
        else:
            self.dem_path = None; self.viewer.clear()
        self._autoload_last_cotas(self.current_reservorio_codigo)
        self.history_panel.load_reservorio(self.current_reservorio_codigo)
        self.history_panel.show(); self._set_paths_label()

    def _autoload_last_cotas(self, codigo: str) -> None:
        if not _DB_AVAILABLE: return
        try:
            with get_session() as s:
                repo = Repository(s); rv = repo.get_reservorio_by_codigo(codigo)
                if not rv: return
                last = repo.get_last_cubicacion(rv.id)
                if not last: return
                if not self.txt_salt.text().strip():  self.txt_salt.setText(f"{last.cota_sal:.3f}")
                if not self.txt_water.text().strip(): self.txt_water.setText(f"{last.cota_agua:.3f}")
                if not self.txt_occ.text().strip():   self.txt_occ.setText(f"{last.fraccion_ocluida:.2f}")
        except Exception: pass

    # ── Acciones de archivo ───────────────────────────────────────────────────

    def pick_dem(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Selecciona el DEM", "",
                                              "GeoTIFF (*.tif *.tiff);;Todos (*.*)")
        if not path: return
        self.dem_path = path
        try:
            r = DemRenderer(path, scale_mode="minmax", stats_sample=1024)
            self.viewer.set_dem_renderer(r); self.viewer._reset_view(r)
        except Exception as e:
            QMessageBox.critical(self, "DEM", f"No se pudo cargar DEM:\n{e}")
            self._set_paths_label(); return
        if _DB_AVAILABLE and self.current_reservorio_codigo and self._user_id is not None:
            try:
                with get_session() as s:
                    repo = Repository(s); rv = repo.get_reservorio_by_codigo(self.current_reservorio_codigo)
                    if rv:
                        dem_obj = repo.register_dem(reservorio_id=rv.id, archivo=Path(path).name,
                                                    ruta=path, usuario_id=self._user_id)
                        self._current_dem_id = dem_obj.id
                        repo.update_reservorio_defaults(rv.id, dem_path=path)
                        repo.log("dem_cargado", usuario=repo.get_user_by_id(self._user_id),
                                 detalle={"reservorio": self.current_reservorio_codigo,
                                          "archivo": Path(path).name})
                        self.history_panel.load_reservorio(self.current_reservorio_codigo)
            except Exception: pass
        # Subir DEM a Firebase en segundo plano
        if _FB_AVAILABLE and self.current_reservorio_codigo:
            firebase_sync.upload_dem_async(self.current_reservorio_codigo, path)
        self._set_paths_label()

    def pick_ortho(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Selecciona ortofoto", "",
                                              "GeoTIFF (*.tif *.tiff);;Todos (*.*)")
        if not path: return
        try:
            self.viewer.set_ortho_renderer(OrthoRenderer(path))
            self.btn_ortho.setEnabled(True); self.btn_ortho.setChecked(True)
        except Exception as e:
            QMessageBox.critical(self, "Ortofoto", f"No se pudo cargar:\n{e}")

    def pick_mask(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona contorno", "",
            "Contornos (*.geojson *.json *.kml *.kmz *.shp);;Todos (*.*)")
        if not path: return
        self.mask_path = path; self.chk_use_mask.setChecked(True); self._set_paths_label()

    # ── Cálculo ───────────────────────────────────────────────────────────────

    def calculate(self) -> None:
        if not self.dem_path:
            QMessageBox.critical(self, "Falta DEM", "Selecciona un DEM primero."); return
        try:
            salt  = self._get_float(self.txt_salt.text(),  "Cota de sal")
            water = self._get_float(self.txt_water.text(), "Cota pelo de agua")
            occ   = self._get_float(self.txt_occ.text(),   "Fracción ocluida")
            if not (0.0 <= occ <= 1.0): raise ValueError("Fracción ocluida debe estar entre 0 y 1.")
            shapes = load_mask_shapes(self.mask_path) if self.chk_use_mask.isChecked() and self.mask_path else None
            res    = PondVolumeCalculator(DemRaster(self.dem_path, mask_shapes=shapes).load()).compute(
                salt, water, occluded_fraction=occ)
            self.latest_result = res; self.latest_rows = res.to_rows()
            self._populate_table(self.latest_rows)
            warns = []
            if res.salt_level  < res.dem_min or res.salt_level  > res.dem_max:
                warns.append(f"  • Cota de sal ({res.salt_level:.2f} m) fuera del rango DEM [{res.dem_min:.2f}–{res.dem_max:.2f} m].")
            if res.water_level < res.dem_min or res.water_level > res.dem_max:
                warns.append(f"  • Cota pelo de agua ({res.water_level:.2f} m) fuera del rango DEM [{res.dem_min:.2f}–{res.dem_max:.2f} m].")
            if warns:
                QMessageBox.warning(self, "Advertencia de rango",
                                    f"(mín: {res.dem_min:.2f} m, máx: {res.dem_max:.2f} m):\n\n"
                                    + "\n".join(warns)
                                    + "\n\nEl cálculo se realizó de todas formas.")
            self._save_cubicacion(res)
        except (MaskError, DemError) as e: QMessageBox.critical(self, "Error", str(e))
        except Exception as e: QMessageBox.critical(self, "Error inesperado", str(e))

    def _save_cubicacion(self, res: PondVolumes) -> None:
        if not _DB_AVAILABLE or not self.current_reservorio_codigo or self._user_id is None: return
        try:
            with get_session() as s:
                repo = Repository(s); rv = repo.get_reservorio_by_codigo(self.current_reservorio_codigo)
                if not rv: return
                anomalias = [a for a in [
                    repo.check_volume_anomaly(rv.id, res.brine_total_m3),
                    repo.check_salt_static(rv.id, res.salt_level),
                ] if a]
                cub = repo.save_cubicacion(reservorio_id=rv.id, usuario_id=self._user_id,
                                           volumes=res, dem_id=self._current_dem_id)
                repo.log("cubicacion_calculada", usuario=repo.get_user_by_id(self._user_id),
                         detalle={"reservorio": self.current_reservorio_codigo,
                                  "cubicacion_id": cub.id, "cota_sal": res.salt_level,
                                  "cota_agua": res.water_level, "vol_total_m3": res.brine_total_m3,
                                  "anomalias": len(anomalias)})
            if anomalias: QMessageBox.warning(self, "Anomalía detectada", "\n\n".join(anomalias))
            self.history_panel.load_reservorio(self.current_reservorio_codigo)
            # Subir cubicación a Firebase
            if _FB_AVAILABLE:
                firebase_sync.upload_cubicacion_async(
                    self.current_reservorio_codigo,
                    {"cota_sal": res.salt_level, "cota_agua": res.water_level,
                     "vol_sal_m3": res.vol_sal_m3, "vol_salmuera_m3": res.brine_total_m3,
                     "area_espejo_m2": res.area_espejo_m2, "usuario": self._user_username}
                )
        except Exception: pass

    def _populate_table(self, rows) -> None:
        self.tree.clear()
        for item, value, unit in rows:
            v = fmt(value, 3) if unit in ("m³","m²","kL","ML") else fmt(value, 2) if unit in ("m","-") else str(value)
            self.tree.addTopLevelItem(QTreeWidgetItem([item, v, unit]))
        self.tree.resizeColumnToContents(0)

    def export_csv(self) -> None:
        if not self.latest_rows:
            QMessageBox.information(self, "Exportar", "Primero calcula resultados."); return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar CSV", default_output_name(), "CSV (*.csv)")
        if not path: return
        try:
            open_file_default_app(export_rows_to_csv(path, self.latest_rows))
            self._audit("csv_exportado", detalle={"reservorio": self.current_reservorio_codigo,
                                                  "archivo": Path(path).name})
        except Exception as e: QMessageBox.critical(self, "Exportar CSV", str(e))

    def clear_results(self) -> None:
        self.latest_result = None; self.latest_rows = []; self.tree.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)
    if _DB_AVAILABLE:
        dlg = LoginDialog()
        if dlg.exec() != QDialog.Accepted: sys.exit(0)
        win = MainWindow(user_id=dlg.user_id, user_nombre=dlg.user_nombre,
                         user_username=dlg.user_username, user_rol=dlg.user_rol)
    else:
        win = MainWindow()
    win.showMaximized()   # pantalla completa por defecto
    sys.exit(app.exec())
