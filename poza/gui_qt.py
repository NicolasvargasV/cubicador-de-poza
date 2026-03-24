from __future__ import annotations

import json
import math
import sys
from enum import IntEnum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QPointF, QTimer, Signal
from PySide6.QtGui import (
    QColor, QImage, QPainter, QPen, QPixmap, QPolygonF,
)
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

# Capa de DB con degradación graceful: si aún no están instaladas las
# dependencias (sqlalchemy/bcrypt), el resto de la app sigue funcionando.
try:
    from .db import get_session, Repository
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False


COLOR_PRIMARY   = "#29306A"
COLOR_ACCENT    = "#F75C03"
COLOR_TEXT      = "#333333"
COLOR_BG        = "#F6F6F6"
COLOR_WHITE     = "#FFFFFF"
COLOR_SECONDARY = "#808B96"


def fmt(x: float, decimals: int = 3) -> str:
    return f"{x:,.{decimals}f}"


# ─────────────────────────────────────────────────────────────────────────────
# Estado de la herramienta de polígono
# ─────────────────────────────────────────────────────────────────────────────

class PolyTool(IntEnum):
    IDLE     = 0   # sin herramienta activa
    DRAWING  = 1   # dibujando vértices
    EDITING  = 2   # polígono cerrado, editando vértices


# ─────────────────────────────────────────────────────────────────────────────
# Diálogo de inicio de sesión
# ─────────────────────────────────────────────────────────────────────────────

class LoginDialog(QDialog):
    """
    Ventana de autenticación mostrada antes de abrir la ventana principal.
    Valida las credenciales contra la DB y registra el evento en el audit log.
    """

    _STYLE = f"""
        QDialog {{
            background: {COLOR_BG};
        }}
        QLabel#title {{
            font: bold 16pt "Segoe UI";
            color: {COLOR_PRIMARY};
        }}
        QLabel#subtitle {{
            font: 9pt "Segoe UI";
            color: {COLOR_SECONDARY};
        }}
        QLabel#error {{
            font: bold 9pt "Segoe UI";
            color: #C0392B;
        }}
        QLineEdit {{
            font: 10pt "Segoe UI";
            padding: 6px 8px;
            border: 1px solid #C8CBE0;
            border-radius: 5px;
            background: white;
            color: {COLOR_TEXT};
        }}
        QLineEdit:focus {{
            border: 2px solid {COLOR_PRIMARY};
        }}
        QPushButton#btnLogin {{
            font: bold 10pt "Segoe UI";
            color: white;
            background: {COLOR_PRIMARY};
            border: none;
            border-radius: 5px;
            padding: 8px 24px;
        }}
        QPushButton#btnLogin:hover  {{ background: #3D4A9A; }}
        QPushButton#btnLogin:pressed{{ background: {COLOR_ACCENT}; }}
        QLabel {{
            font: 9pt "Segoe UI";
            color: {COLOR_TEXT};
        }}
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cubicador de Pozas — Inicio de sesión")
        self.setFixedSize(400, 300)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setStyleSheet(self._STYLE)

        # Datos del usuario autenticado (se rellenan en _try_login)
        self._user_id:       int | None = None
        self._user_nombre:   str = ""
        self._user_username: str = ""
        self._user_rol:      str = "operador"

        self._build_ui()

    # ── Construcción de UI ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(10)

        # Encabezado
        lbl_title = QLabel("Iniciar sesión")
        lbl_title.setObjectName("title")
        layout.addWidget(lbl_title)

        lbl_sub = QLabel("Cubicador de Pozas · Operación Atacama")
        lbl_sub.setObjectName("subtitle")
        layout.addWidget(lbl_sub)

        layout.addSpacing(12)

        # Formulario
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._txt_user = QLineEdit()
        self._txt_user.setPlaceholderText("Usuario")
        self._txt_user.setMaxLength(64)

        self._txt_pass = QLineEdit()
        self._txt_pass.setPlaceholderText("Contraseña")
        self._txt_pass.setEchoMode(QLineEdit.Password)
        self._txt_pass.setMaxLength(128)
        self._txt_pass.returnPressed.connect(self._try_login)

        form.addRow("Usuario:", self._txt_user)
        form.addRow("Contraseña:", self._txt_pass)
        layout.addLayout(form)

        # Etiqueta de error
        self._lbl_error = QLabel("")
        self._lbl_error.setObjectName("error")
        self._lbl_error.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._lbl_error)

        layout.addStretch()

        # Botón de acceso
        self._btn_login = QPushButton("Acceder")
        self._btn_login.setObjectName("btnLogin")
        self._btn_login.setDefault(True)
        self._btn_login.clicked.connect(self._try_login)
        layout.addWidget(self._btn_login, alignment=Qt.AlignRight)

    # ── Lógica de autenticación ───────────────────────────────────────────────

    def _try_login(self) -> None:
        username = self._txt_user.text().strip()
        password = self._txt_pass.text()

        if not username or not password:
            self._lbl_error.setText("Ingresa usuario y contraseña.")
            return

        if not _DB_AVAILABLE:
            # Sin DB: acceso sin autenticación (modo demo)
            self._user_id       = None
            self._user_nombre   = username
            self._user_username = username
            self._user_rol      = "operador"
            self.accept()
            return

        try:
            with get_session() as session:
                repo = Repository(session)
                user = repo.authenticate(username, password)

                # Extraer datos antes de cerrar la sesión
                self._user_id       = user.id
                self._user_nombre   = user.nombre_completo
                self._user_username = user.username
                self._user_rol      = user.rol

                repo.log(
                    "login",
                    usuario=user,
                    detalle={"ip": "localhost"},
                )

            self._lbl_error.setText("")
            self.accept()

        except Exception as e:
            # Intentar registrar fallo si tenemos sesión (puede fallar)
            try:
                with get_session() as session:
                    repo = Repository(session)
                    repo.log("login_fallido", detalle={"username": username, "motivo": str(e)})
            except Exception:
                pass

            self._lbl_error.setText(str(e))
            self._txt_pass.clear()
            self._txt_pass.setFocus()

    # ── Propiedades de acceso post-login ─────────────────────────────────────

    @property
    def user_id(self) -> int | None:
        return self._user_id

    @property
    def user_nombre(self) -> str:
        return self._user_nombre

    @property
    def user_username(self) -> str:
        return self._user_username

    @property
    def user_rol(self) -> str:
        return self._user_rol


# ─────────────────────────────────────────────────────────────────────────────
# Visor DEM / Ortofoto  (con preservación de relación de aspecto + polígono)
# ─────────────────────────────────────────────────────────────────────────────

class DemViewerWidget(QWidget):
    """
    Visor interactivo con:
      • Preservación estricta del aspect ratio (letterboxing con fondo oscuro)
      • Render dual: cache rápido + HQ al detenerse
      • Dos renderizadores intercambiables: DEM y ortofoto
      • Herramienta de dibujo de polígono manual
    """

    polygon_committed = Signal(list)   # [lista de GeoJSON shape dicts]

    # Distancia en px de pantalla para cerrar el polígono al clickear
    CLOSE_DIST_PX: float = 14.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.StrongFocus)

        # ── Renderizadores ────────────────────────────────────────────────────
        self._dem_renderer:   DemRenderer   | None = None
        self._ortho_renderer: OrthoRenderer | None = None
        self._use_ortho: bool = False

        # ── Vista ─────────────────────────────────────────────────────────────
        self.zoom      = 1.0
        self.zoom_min  = 0.35
        self.zoom_max  = 12.0
        self.center_x  = 0.0
        self.center_y  = 0.0

        self._pixmap: QPixmap | None = None
        self._render_info: Dict = {
            "x0": 0.0, "y0": 0.0,
            "scale": 1.0, "base_scale": 1.0,
            "off_x": 0.0, "off_y": 0.0,
            "render_w": 1, "render_h": 1,
        }

        self._fast_timer = QTimer(self)
        self._fast_timer.setSingleShot(True)
        self._fast_timer.timeout.connect(self._do_render_fast)

        self._hq_timer = QTimer(self)
        self._hq_timer.setSingleShot(True)
        self._hq_timer.timeout.connect(self._render_hq)

        self._pan_anchor: tuple[float, float, float, float] | None = None

        # ── Herramienta de polígono ───────────────────────────────────────────
        self._poly_tool:         PolyTool              = PolyTool.IDLE
        self._poly_verts_raster: List[Tuple[float, float]] = []  # vértices en px ráster
        self._poly_closed:       bool                  = False
        self._poly_mouse_screen: Tuple[float, float]   = (0.0, 0.0)  # última posición del cursor

    # ── Propiedad renderer activo ─────────────────────────────────────────────

    @property
    def renderer(self) -> DemRenderer | OrthoRenderer | None:
        if self._use_ortho:
            return self._ortho_renderer
        return self._dem_renderer

    # ── API pública ───────────────────────────────────────────────────────────

    def set_dem_renderer(self, renderer: DemRenderer) -> None:
        """Carga un nuevo DEM y reinicia la vista."""
        if self._dem_renderer:
            self._dem_renderer.close()
        self._dem_renderer = renderer
        self._dem_renderer.build_cache(max_tex=2048, levels=4)
        # Resetear vista solo si este renderer va a ser el activo
        if not self._use_ortho:
            self._reset_view(renderer)

    def set_ortho_renderer(self, renderer: OrthoRenderer) -> None:
        """Carga una nueva ortofoto (no reinicia zoom/pan)."""
        if self._ortho_renderer:
            self._ortho_renderer.close()
        self._ortho_renderer = renderer
        self._ortho_renderer.build_cache(max_tex=2048, levels=4)
        if self._use_ortho:
            self._render_fast()
            self._schedule_hq(delay_ms=60)

    def set_use_ortho(self, use: bool) -> None:
        """Alterna entre vista DEM y ortofoto."""
        if use and self._ortho_renderer is None:
            return  # sin ortofoto cargada, ignorar
        self._use_ortho = use
        if self.renderer:
            self._render_fast()
            self._schedule_hq(delay_ms=60)

    # Alias de compatibilidad con el código anterior
    def set_renderer(self, renderer: DemRenderer) -> None:
        self.set_dem_renderer(renderer)

    def clear(self) -> None:
        if self._dem_renderer:
            self._dem_renderer.close()
        if self._ortho_renderer:
            self._ortho_renderer.close()
        self._dem_renderer   = None
        self._ortho_renderer = None
        self._pixmap         = None
        self.clear_polygon()
        self.update()

    def set_poly_tool(self, tool: PolyTool) -> None:
        self._poly_tool = tool
        if tool == PolyTool.DRAWING:
            self._poly_verts_raster.clear()
            self._poly_closed = False
            self.setCursor(Qt.CrossCursor)
        elif tool == PolyTool.IDLE:
            self.setCursor(Qt.ArrowCursor)
        self.update()

    def clear_polygon(self) -> None:
        self._poly_tool = PolyTool.IDLE
        self._poly_verts_raster.clear()
        self._poly_closed = False
        self.setCursor(Qt.ArrowCursor)
        self.update()

    # ── Eventos Qt ────────────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._render_fast()
        self._schedule_hq()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)

        # Fondo oscuro (letterbox)
        painter.fillRect(self.rect(), QColor(20, 20, 30))

        if self._pixmap is not None:
            ox = int(self._render_info.get("off_x", 0.0))
            oy = int(self._render_info.get("off_y", 0.0))
            # Dibujar pixmap a su tamaño natural, en la posición letterbox
            painter.drawPixmap(ox, oy, self._pixmap)

        # Overlay de polígono
        if self._poly_tool != PolyTool.IDLE and self._poly_verts_raster:
            self._draw_poly_overlay(painter)
        elif self._poly_tool == PolyTool.DRAWING and not self._poly_verts_raster:
            # Sin vértices aún: mostrar guía de uso
            pass

        painter.end()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.setFocus()

        if self._poly_tool == PolyTool.DRAWING:
            if event.button() == Qt.LeftButton:
                sx = float(event.position().x())
                sy = float(event.position().y())

                # ¿Cerrar polígono?
                if len(self._poly_verts_raster) >= 3 and self._should_close(sx, sy):
                    self._poly_closed = True
                    self._poly_tool   = PolyTool.EDITING
                    self.setCursor(Qt.ArrowCursor)
                    self.update()
                else:
                    rx, ry = self._s2r(sx, sy)
                    self._poly_verts_raster.append((rx, ry))
                    self.update()
                return

        elif self._poly_tool == PolyTool.EDITING:
            # En modo edición, el ratón solo actúa con T/R/Enter (teclado)
            # Click izquierdo: iniciar pan si quiere mover la vista
            if event.button() == Qt.RightButton:
                self._pan_anchor = (
                    float(event.position().x()),
                    float(event.position().y()),
                    self.center_x,
                    self.center_y,
                )
            return

        # Modo IDLE: pan con botón izquierdo
        if event.button() == Qt.LeftButton:
            self._pan_anchor = (
                float(event.position().x()),
                float(event.position().y()),
                self.center_x,
                self.center_y,
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        sx = float(event.position().x())
        sy = float(event.position().y())
        self._poly_mouse_screen = (sx, sy)

        # Repintar overlay si herramienta activa (línea guía al cursor)
        if self._poly_tool in (PolyTool.DRAWING, PolyTool.EDITING):
            self.update()
            # En modo edición no hacemos pan con botón derecho aquí (lo hacemos
            # solo cuando el anchor está activo)
            if self._poly_tool == PolyTool.EDITING and self._pan_anchor:
                x0, y0, cx0, cy0 = self._pan_anchor
                dx = sx - x0; dy = sy - y0
                scale = float(self._render_info.get("scale", 1.0))
                if self.renderer:
                    self.center_x = max(0.0, min(cx0 - dx / scale, self.renderer.width))
                    self.center_y = max(0.0, min(cy0 - dy / scale, self.renderer.height))
                    self._render_fast()
                    self._schedule_hq()
            return

        if self._pan_anchor and self.renderer:
            x0, y0, cx0, cy0 = self._pan_anchor
            dx = sx - x0
            dy = sy - y0
            scale = float(self._render_info.get("scale", 1.0))
            self.center_x = max(0.0, min(cx0 - dx / scale, self.renderer.width))
            self.center_y = max(0.0, min(cy0 - dy / scale, self.renderer.height))
            self._render_fast()
            self._schedule_hq()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() in (Qt.LeftButton, Qt.RightButton):
            if self._pan_anchor:
                self._schedule_hq()
                self._pan_anchor = None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if not self.renderer:
            return
        factor = 1.10 if event.angleDelta().y() > 0 else 1 / 1.10
        pos = event.position()
        self._zoom_at(factor, int(pos.x()), int(pos.y()))

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        key = event.key()

        # ESC: cancelar herramienta
        if key == Qt.Key_Escape:
            self.clear_polygon()
            return

        if self._poly_tool == PolyTool.EDITING:
            # T: insertar vértice en el borde más cercano al cursor
            if key == Qt.Key_T:
                self._insert_vertex_at_cursor(self._poly_mouse_screen)
                return

            # R: eliminar vértice más cercano al cursor (mínimo 3)
            if key == Qt.Key_R:
                self._remove_nearest_vertex(self._poly_mouse_screen)
                return

            # Enter / Return: confirmar polígono
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._commit_polygon()
                return

        super().keyPressEvent(event)

    # ── Coordenadas ───────────────────────────────────────────────────────────

    def _s2r(self, sx: float, sy: float) -> Tuple[float, float]:
        """Convierte coordenadas de pantalla → píxeles del ráster."""
        info = self._render_info
        rx = info["x0"] + (sx - info["off_x"]) / info["scale"]
        ry = info["y0"] + (sy - info["off_y"]) / info["scale"]
        return rx, ry

    def _r2s(self, rx: float, ry: float) -> Tuple[float, float]:
        """Convierte píxeles del ráster → coordenadas de pantalla."""
        info = self._render_info
        sx = info["off_x"] + (rx - info["x0"]) * info["scale"]
        sy = info["off_y"] + (ry - info["y0"]) * info["scale"]
        return sx, sy

    # ── Lógica de polígono ────────────────────────────────────────────────────

    def _should_close(self, sx: float, sy: float) -> bool:
        """True si el cursor está cerca del primer vértice (para cerrar el polígono)."""
        if len(self._poly_verts_raster) < 3:
            return False
        first_s = self._r2s(*self._poly_verts_raster[0])
        return math.hypot(sx - first_s[0], sy - first_s[1]) <= self.CLOSE_DIST_PX

    def _insert_vertex_at_cursor(self, mouse_screen: Tuple[float, float]) -> None:
        """Inserta un vértice en el segmento más cercano al cursor."""
        verts = self._poly_verts_raster
        if len(verts) < 2:
            return
        n = len(verts)
        mx_r, my_r = self._s2r(*mouse_screen)

        best_dist  = float("inf")
        best_idx   = 0
        best_pt_r  = (mx_r, my_r)

        for i in range(n):
            a = verts[i]
            b = verts[(i + 1) % n]
            dx, dy = b[0] - a[0], b[1] - a[1]
            seg_len2 = dx * dx + dy * dy
            if seg_len2 < 1e-12:
                continue
            t = ((mx_r - a[0]) * dx + (my_r - a[1]) * dy) / seg_len2
            t = max(0.0, min(1.0, t))
            proj_x = a[0] + t * dx
            proj_y = a[1] + t * dy
            dist2  = (mx_r - proj_x) ** 2 + (my_r - proj_y) ** 2
            if dist2 < best_dist:
                best_dist = dist2
                best_idx  = i
                best_pt_r = (proj_x, proj_y)

        self._poly_verts_raster.insert(best_idx + 1, best_pt_r)
        self.update()

    def _remove_nearest_vertex(self, mouse_screen: Tuple[float, float]) -> None:
        """Elimina el vértice más cercano al cursor (mínimo 3 vértices)."""
        verts = self._poly_verts_raster
        if len(verts) <= 3:
            return
        mx_r, my_r = self._s2r(*mouse_screen)
        best_i = min(
            range(len(verts)),
            key=lambda i: (verts[i][0] - mx_r) ** 2 + (verts[i][1] - my_r) ** 2,
        )
        del self._poly_verts_raster[best_i]
        self.update()

    def _commit_polygon(self) -> None:
        """Convierte el polígono dibujado a GeoJSON y emite la señal."""
        r = self._dem_renderer
        if r is None:
            r = self._ortho_renderer
        if r is None or not self._poly_verts_raster:
            return
        try:
            shape = polygon_raster_to_geojson(self._poly_verts_raster, r.transform)
            self.polygon_committed.emit([shape])
        except Exception as e:
            pass  # ignorar silenciosamente; el error se verá en la consola
        # Limpiar estado
        self._poly_tool = PolyTool.IDLE
        self._poly_closed = False
        self._poly_verts_raster.clear()
        self.setCursor(Qt.ArrowCursor)
        self.update()

    # ── Overlay de polígono ───────────────────────────────────────────────────

    def _draw_poly_overlay(self, painter: QPainter) -> None:
        verts_s = [self._r2s(rx, ry) for rx, ry in self._poly_verts_raster]
        if not verts_s:
            return

        mx, my = self._poly_mouse_screen

        # ── Relleno traslúcido si cerrado ────────────────────────────────
        if self._poly_closed and len(verts_s) >= 3:
            poly = QPolygonF([QPointF(sx, sy) for sx, sy in verts_s])
            fill_color = QColor(255, 200, 50, 45)
            painter.setBrush(fill_color)
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(poly)

        # ── Líneas del borde ─────────────────────────────────────────────
        edge_pen = QPen(QColor(255, 180, 0), 2, Qt.SolidLine)
        edge_pen.setCosmetic(True)
        painter.setPen(edge_pen)
        painter.setBrush(Qt.NoBrush)
        n = len(verts_s)
        for i in range(n - 1):
            sx0, sy0 = verts_s[i]
            sx1, sy1 = verts_s[i + 1]
            painter.drawLine(QPointF(sx0, sy0), QPointF(sx1, sy1))
        if self._poly_closed and n >= 2:
            sx0, sy0 = verts_s[-1]
            sx1, sy1 = verts_s[0]
            painter.drawLine(QPointF(sx0, sy0), QPointF(sx1, sy1))

        # ── Línea guía al cursor (solo en modo DRAWING) ───────────────────
        if self._poly_tool == PolyTool.DRAWING and verts_s:
            guide_pen = QPen(QColor(255, 255, 100, 180), 1, Qt.DashLine)
            guide_pen.setCosmetic(True)
            painter.setPen(guide_pen)
            sx0, sy0 = verts_s[-1]
            painter.drawLine(QPointF(sx0, sy0), QPointF(mx, my))

            # Círculo de cierre en el primer vértice
            if len(verts_s) >= 3:
                fsx, fsy = verts_s[0]
                close_dist = math.hypot(mx - fsx, my - fsy)
                radius = self.CLOSE_DIST_PX
                if close_dist <= radius:
                    painter.setPen(QPen(QColor(50, 255, 120), 2))
                    painter.setBrush(QColor(50, 255, 120, 80))
                else:
                    painter.setPen(QPen(QColor(255, 180, 0), 1))
                    painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(fsx, fsy), radius, radius)

        # ── Vértices ─────────────────────────────────────────────────────
        for idx, (sx, sy) in enumerate(verts_s):
            if self._poly_tool == PolyTool.EDITING:
                # Resaltar vértice más cercano al cursor (candidato para R)
                rx, ry = self._poly_verts_raster[idx]
                mrx, mry = self._s2r(mx, my)
                dist_r = math.hypot(rx - mrx, ry - mry)
                scale  = self._render_info.get("scale", 1.0)
                dist_px = dist_r * scale
                is_nearest = (dist_px == min(
                    math.hypot(
                        (self._poly_verts_raster[k][0] - mrx) * scale,
                        (self._poly_verts_raster[k][1] - mry) * scale,
                    )
                    for k in range(len(verts_s))
                ))
                if is_nearest and dist_px < 40:
                    painter.setPen(QPen(QColor(255, 80, 80), 2))
                    painter.setBrush(QColor(255, 80, 80, 200))
                    painter.drawEllipse(QPointF(sx, sy), 6.0, 6.0)
                    continue

            painter.setPen(QPen(QColor(255, 220, 50), 2))
            painter.setBrush(QColor(255, 220, 50, 220))
            painter.drawEllipse(QPointF(sx, sy), 4.5, 4.5)

        # ── Hint de teclado (modo EDITING) ───────────────────────────────
        if self._poly_tool == PolyTool.EDITING:
            hint = "  T=añadir vértice   R=quitar vértice   Enter=confirmar   Esc=cancelar  "
            painter.setFont(painter.font())
            painter.setPen(QColor(255, 255, 255, 200))
            painter.fillRect(4, self.height() - 22, self.width() - 8, 18, QColor(0, 0, 0, 120))
            painter.drawText(8, self.height() - 7, hint)

    # ── Render ────────────────────────────────────────────────────────────────

    def _reset_view(self, r) -> None:
        """Reinicia zoom y centro de la vista según el renderer dado."""
        self.zoom     = 1.0
        self.center_x = r.width  / 2.0
        self.center_y = r.height / 2.0
        self._render_fast()
        self._schedule_hq(delay_ms=60)

    def _render_fast(self) -> None:
        self._fast_timer.start(8)

    def _do_render_fast(self) -> None:
        r = self.renderer
        if not r:
            return
        rgb, info = r.render_view_cached(
            center_x=self.center_x, center_y=self.center_y,
            zoom=self.zoom,
            canvas_w=max(2, self.width()),
            canvas_h=max(2, self.height()),
        )
        self._render_info = info
        self._pixmap = self._rgb_to_pixmap(rgb)
        self.update()

    def _schedule_hq(self, delay_ms: int = 220) -> None:
        self._hq_timer.start(delay_ms)

    def _render_hq(self) -> None:
        r = self.renderer
        if not r:
            return
        rgb, info = r.render_view_hq(
            center_x=self.center_x, center_y=self.center_y,
            zoom=self.zoom,
            canvas_w=max(2, self.width()),
            canvas_h=max(2, self.height()),
            hillshade=not self._use_ortho,
        )
        self._render_info = info
        self._pixmap = self._rgb_to_pixmap(rgb)
        self.update()

    def _rgb_to_pixmap(self, rgb) -> QPixmap:
        import numpy as np
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        return QPixmap.fromImage(qimg)

    def _zoom_at(self, factor: float, mx: int, my: int) -> None:
        if not self.renderer:
            return
        old_zoom = self.zoom
        new_zoom = max(self.zoom_min, min(self.zoom_max, old_zoom * factor))
        if abs(new_zoom - old_zoom) < 1e-12:
            return

        info    = self._render_info
        off_x   = float(info.get("off_x", 0.0))
        off_y   = float(info.get("off_y", 0.0))
        x0      = float(info["x0"])
        y0      = float(info["y0"])
        scale_old = float(info["scale"])

        # Punto del ráster bajo el cursor (corregido por letterbox)
        rx = x0 + (mx - off_x) / scale_old
        ry = y0 + (my - off_y) / scale_old

        cw, ch = max(2, self.width()), max(2, self.height())
        base_scale = max(min(cw / self.renderer.width, ch / self.renderer.height), 1e-9)
        scale_new  = base_scale * new_zoom
        win_w = cw / scale_new
        win_h = ch / scale_new

        # Nuevo x0, y0 para que el punto (rx, ry) quede bajo (mx, my)
        new_x0 = max(0.0, min(rx - (mx - off_x) / scale_new, self.renderer.width  - win_w))
        new_y0 = max(0.0, min(ry - (my - off_y) / scale_new, self.renderer.height - win_h))

        self.zoom     = new_zoom
        self.center_x = new_x0 + win_w / 2
        self.center_y = new_y0 + win_h / 2
        self._render_fast()
        self._schedule_hq()


# ─────────────────────────────────────────────────────────────────────────────
# Panel de historial (Mediciones / DEMs / Imágenes)
# ─────────────────────────────────────────────────────────────────────────────

class HistoryPanel(QWidget):
    """
    Panel de datos históricos bajo el canvas DEM.

    Tres pestañas:
      • Mediciones  → cubicaciones históricas del reservorio
      • DEMs        → archivos DEM registrados para el reservorio
      • Imágenes    → placeholder para imágenes fotogramétricas
    """

    TAB_MEDICIONES = 0
    TAB_DEMS       = 1
    TAB_IMAGENES   = 2

    _BTN_STYLE = """
        QPushButton {
            font: bold 9pt "Segoe UI";
            padding: 5px 16px;
            border: none;
            border-radius: 4px 4px 0 0;
            background: #EAECF4;
            color: #555577;
        }
        QPushButton:hover   { background: #D8DBF0; color: #29306A; }
        QPushButton:checked {
            background: #29306A;
            color: white;
            border-bottom: 3px solid #F75C03;
        }
    """

    _TABLE_STYLE = """
        QTableWidget {
            font: 9pt "Segoe UI";
            border: none;
            background: #FAFBFF;
            alternate-background-color: #F0F2FA;
            gridline-color: #E8EAF6;
            color: #222244;
        }
        QHeaderView::section {
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #3D4A9A, stop:1 #29306A);
            color: white;
            font: bold 9pt "Segoe UI";
            padding: 5px 6px;
            border: none;
            border-right: 1px solid #4A58B8;
        }
        QTableWidget::item { padding: 3px 6px; }
        QTableWidget::item:selected {
            background: #29306A;
            color: white;
        }
        QScrollBar:vertical {
            background: #F0F2FA; width: 7px; border-radius: 3px;
        }
        QScrollBar::handle:vertical {
            background: #C0C5E0; border-radius: 3px; min-height: 24px;
        }
        QScrollBar::handle:vertical:hover { background: #29306A; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(210)
        self.setMaximumHeight(270)
        self.setStyleSheet("background: #FFFFFF;")
        self._build_ui()

    # ── Construcción de UI ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 0)
        root.setSpacing(0)

        # ── Barra de pestañas ──────────────────────────────────────────────
        tab_bar = QWidget()
        tab_bar.setStyleSheet("background: transparent;")
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(2, 0, 0, 0)
        tab_layout.setSpacing(3)

        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        for label, idx in [("📋  Mediciones", self.TAB_MEDICIONES),
                            ("🗺  DEMs",       self.TAB_DEMS),
                            ("🖼  Imágenes",   self.TAB_IMAGENES)]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(self._BTN_STYLE)
            self._btn_group.addButton(btn, idx)
            tab_layout.addWidget(btn)

        tab_layout.addStretch()
        self._btn_group.button(self.TAB_MEDICIONES).setChecked(True)
        root.addWidget(tab_bar)

        # ── Separador ──────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #D0D4E8; margin: 0;")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # ── Stack de tablas ────────────────────────────────────────────────
        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        # Tabla Mediciones
        self.tbl_mediciones = self._make_table([
            "Fecha", "Operador",
            "Cota Sal (m)", "Cota Agua (m)",
            "Vol. Sal (m³)", "Vol. Salmuera (m³)", "Área Espejo (m²)",
            "Notas",
        ])
        self._stack.addWidget(self.tbl_mediciones)  # idx 0

        # Tabla DEMs
        self.tbl_dems = self._make_table([
            "Fecha Carga", "Archivo",
            "Fecha Vuelo", "Cargado por",
        ])
        self._stack.addWidget(self.tbl_dems)  # idx 1

        # Placeholder Imágenes
        self._stack.addWidget(self._make_placeholder(
            "📷  Módulo de imágenes fotogramétricas — próximamente."
        ))  # idx 2

        # ── Conectar botones → stack ────────────────────────────────────────
        self._btn_group.idClicked.connect(self._stack.setCurrentIndex)

    def _make_table(self, headers: list[str]) -> QTableWidget:
        tbl = QTableWidget(0, len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.setStyleSheet(self._TABLE_STYLE)
        tbl.setShowGrid(True)
        return tbl

    def _make_placeholder(self, message: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: #FAFBFF;")
        lbl = QLabel(message)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #9098B5; font: italic 10pt 'Segoe UI';")
        lay = QVBoxLayout(w)
        lay.addWidget(lbl)
        return w

    # ── API pública ───────────────────────────────────────────────────────────

    def load_reservorio(self, reservorio_codigo: str) -> None:
        """
        Carga datos históricos del reservorio desde la DB.
        Si la DB no está disponible todavía, deja las tablas vacías.
        """
        self.tbl_mediciones.setRowCount(0)
        self.tbl_dems.setRowCount(0)

        if not _DB_AVAILABLE:
            return

        try:
            with get_session() as session:
                repo = Repository(session)
                reservorio = repo.get_reservorio_by_codigo(reservorio_codigo)
                if not reservorio:
                    return

                self._load_mediciones(repo, reservorio.id)
                self._load_dems(repo, reservorio.id)

        except Exception:
            # DB aún no inicializada o error de conexión: simplemente no mostramos datos
            pass

    def clear(self) -> None:
        self.tbl_mediciones.setRowCount(0)
        self.tbl_dems.setRowCount(0)

    # ── Carga de datos ────────────────────────────────────────────────────────

    def _load_mediciones(self, repo: "Repository", reservorio_id: int) -> None:
        cubicaciones = repo.list_cubicaciones(reservorio_id)

        for c in cubicaciones:
            row = self.tbl_mediciones.rowCount()
            self.tbl_mediciones.insertRow(row)

            fecha    = c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "—"
            operador = c.usuario.nombre_completo if c.usuario else "—"

            values = [
                fecha,
                operador,
                f"{c.cota_sal:.3f}",
                f"{c.cota_agua:.3f}",
                fmt(c.vol_sal_m3, 1)            if c.vol_sal_m3            is not None else "—",
                fmt(c.vol_salmuera_total_m3, 1) if c.vol_salmuera_total_m3 is not None else "—",
                fmt(c.area_espejo_m2, 1)        if c.area_espejo_m2        is not None else "—",
                c.notas or "",
            ]
            for col, val in enumerate(values):
                self._set_cell(self.tbl_mediciones, row, col, val)

    def _load_dems(self, repo: "Repository", reservorio_id: int) -> None:
        dems = repo.list_dems(reservorio_id)

        for d in dems:
            row = self.tbl_dems.rowCount()
            self.tbl_dems.insertRow(row)

            fecha      = d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else "—"
            cargado_by = d.cargado_por_usuario.nombre_completo if d.cargado_por_usuario else "—"

            values = [
                fecha,
                d.archivo,
                d.fecha_vuelo or "—",
                cargado_by,
            ]
            for col, val in enumerate(values):
                self._set_cell(self.tbl_dems, row, col, val)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _set_cell(tbl: QTableWidget, row: int, col: int, text: str,
                  align: Qt.AlignmentFlag = Qt.AlignVCenter | Qt.AlignLeft) -> None:
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(align)
        tbl.setItem(row, col, item)


# ─────────────────────────────────────────────────────────────────────────────
# Ventana principal
# ─────────────────────────────────────────────────────────────────────────────

_VIEWER_BTN_STYLE = """
    QPushButton {
        font: 9pt "Segoe UI";
        padding: 4px 10px;
        border: 1px solid #C8CBE0;
        border-radius: 4px;
        background: #F0F2FA;
        color: #29306A;
    }
    QPushButton:hover    { background: #E0E4F0; }
    QPushButton:checked  { background: #29306A; color: white; border: none; }
    QPushButton:pressed  { background: #F75C03; color: white; }
    QPushButton:disabled { color: #AAAAAA; background: #F6F6F6; border-color: #E0E0E0; }
"""


class MainWindow(QMainWindow):
    """Ventana principal Qt. La UI procede de mainwindow.ui (generado con pyside6-uic)."""

    def __init__(
        self,
        user_id:       int | None = None,
        user_nombre:   str = "",
        user_username: str = "",
        user_rol:      str = "operador",
    ) -> None:
        super().__init__()

        # Usuario autenticado (datos planos, sin ORM para evitar sesiones colgantes)
        self._user_id       = user_id
        self._user_nombre   = user_nombre
        self._user_username = user_username
        self._user_rol      = user_rol

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # Mostrar usuario activo en el título
        nombre_display = user_nombre or user_username or "sin sesión"
        self.setWindowTitle(f"Cubicador de Pozas  ·  {nombre_display}")

        # Aliases de widgets para que el código no cambie
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

        # Estado
        self.dem_path:  str | None = None
        self.mask_path: str | None = None
        self.latest_result: PondVolumes | None = None
        self.latest_rows:   list[tuple[str, float, str]] = []
        self.current_reservorio_codigo: str | None = None
        self._current_dem_id: int | None = None

        # Reservorios en el combobox
        self.cmb_reservorio.addItem("Reservorio")
        self.cmb_reservorio.addItems([f"Reservorio {i}" for i in range(1, 11)])

        # ── Toolbar del visor ─────────────────────────────────────────────
        viewer_toolbar = QWidget()
        toolbar_layout = QHBoxLayout(viewer_toolbar)
        toolbar_layout.setContentsMargins(2, 2, 2, 4)
        toolbar_layout.setSpacing(5)

        self.btn_ortho      = QPushButton("🛰  Ortofoto")
        self.btn_pick_ortho = QPushButton("📂  Cargar ortofoto…")
        self.btn_draw_poly  = QPushButton("✏  Dibujar polígono")
        self.btn_clear_poly = QPushButton("🗑  Borrar polígono")

        self.btn_ortho.setCheckable(True)
        self.btn_draw_poly.setCheckable(True)
        self.btn_ortho.setEnabled(False)  # activo solo cuando hay ortofoto

        for btn in (self.btn_ortho, self.btn_pick_ortho,
                    self.btn_draw_poly, self.btn_clear_poly):
            btn.setStyleSheet(_VIEWER_BTN_STYLE)
            toolbar_layout.addWidget(btn)

        toolbar_layout.addStretch()

        # ── Visor DEM ─────────────────────────────────────────────────────
        self.viewer = DemViewerWidget(self.ui.viewerContainer)
        self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        container_layout = self.ui.viewerContainer.layout()
        if container_layout is None:
            container_layout = QVBoxLayout(self.ui.viewerContainer)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(viewer_toolbar)
        container_layout.addWidget(self.viewer)

        # ── Panel de historial ────────────────────────────────────────────
        self.history_panel = HistoryPanel(self.ui.groupDem)
        dem_layout = self.ui.groupDem.layout()
        dem_layout.addWidget(self.history_panel)
        self.history_panel.hide()

        # Anchos iniciales de columnas de resultados
        self.tree.setColumnWidth(0, 280)
        self.tree.setColumnWidth(1, 140)
        self.tree.setColumnWidth(2, 70)

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

        # Toolbar del visor
        self.btn_ortho.toggled.connect(self._on_ortho_toggled)
        self.btn_pick_ortho.clicked.connect(self.pick_ortho)
        self.btn_draw_poly.toggled.connect(self._on_draw_poly_toggled)
        self.btn_clear_poly.clicked.connect(self._on_clear_poly)
        self.viewer.polygon_committed.connect(self._on_polygon_committed)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._audit("logout")
        self.viewer.clear()
        super().closeEvent(event)

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _set_paths_label(self) -> None:
        dem  = self.dem_path  if self.dem_path  else "(sin DEM)"
        mask = self.mask_path if self.mask_path else "(sin contorno)"
        use  = "Sí" if self.chk_use_mask.isChecked() and self.mask_path else "No"
        self.lbl_paths.setText(f"DEM: {dem}   |   Contorno: {mask}   |   Usar contorno: {use}")

    def _get_float(self, s: str, name: str) -> float:
        s = (s or "").strip().replace(",", ".")
        try:
            return float(s)
        except ValueError:
            raise ValueError(f"{name} debe ser numérico (ej. 2301.02).")

    def _dems_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent / "DEMs"
        return Path(__file__).parent.parent / "DEMs"

    def _audit(self, accion: str, detalle: dict | None = None) -> None:
        """Registra una acción en el audit log. Falla silenciosamente."""
        if not _DB_AVAILABLE or self._user_id is None:
            return
        try:
            with get_session() as session:
                repo = Repository(session)
                user = repo.get_user_by_id(self._user_id)
                repo.log(accion, usuario=user, detalle=detalle)
        except Exception:
            pass

    # ── Cambio de reservorio ──────────────────────────────────────────────────

    def _on_reservorio_changed(self, index: int) -> None:
        if index <= 0:
            self.current_reservorio_codigo = None
            self._current_dem_id = None
            self.dem_path = None
            self.viewer.clear()
            self.history_panel.clear()
            self.history_panel.hide()
            self._set_paths_label()
            return

        self.current_reservorio_codigo = f"R{index}"
        self._current_dem_id = None

        # ── Cargar DEM por defecto ──────────────────────────────────────────
        dem_file = self._dems_dir() / f"MDE_R{index}.tif"
        if dem_file.exists():
            self.dem_path = str(dem_file)
            try:
                renderer = DemRenderer(self.dem_path, scale_mode="minmax", stats_sample=1024)
                self.viewer.set_dem_renderer(renderer)
                # Resetear vista al cargar nuevo reservorio
                self.viewer._reset_view(renderer)
            except Exception as e:
                QMessageBox.critical(self, "DEM", f"No se pudo cargar DEM:\n{e}")
                self.dem_path = None
                self.viewer.clear()
        else:
            self.dem_path = None
            self.viewer.clear()

        # ── Autocargar últimas cotas ────────────────────────────────────────
        self._autoload_last_cotas(self.current_reservorio_codigo)

        # ── Cargar historial ────────────────────────────────────────────────
        self.history_panel.load_reservorio(self.current_reservorio_codigo)
        self.history_panel.show()

        self._set_paths_label()

    def _autoload_last_cotas(self, reservorio_codigo: str) -> None:
        if not _DB_AVAILABLE:
            return
        try:
            with get_session() as session:
                repo = Repository(session)
                r = repo.get_reservorio_by_codigo(reservorio_codigo)
                if not r:
                    return
                last = repo.get_last_cubicacion(r.id)
                if not last:
                    return

                if not self.txt_salt.text().strip():
                    self.txt_salt.setText(f"{last.cota_sal:.3f}")
                if not self.txt_water.text().strip():
                    self.txt_water.setText(f"{last.cota_agua:.3f}")
                if not self.txt_occ.text().strip():
                    self.txt_occ.setText(f"{last.fraccion_ocluida:.2f}")

        except Exception:
            pass

    # ── Acciones de archivo ───────────────────────────────────────────────────

    def pick_dem(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona el DEM", "",
            "GeoTIFF (*.tif *.tiff);;Todos (*.*)",
        )
        if not path:
            return
        self.dem_path = path
        try:
            renderer = DemRenderer(self.dem_path, scale_mode="minmax", stats_sample=1024)
            self.viewer.set_dem_renderer(renderer)
            self.viewer._reset_view(renderer)
        except Exception as e:
            QMessageBox.critical(self, "DEM", f"No se pudo cargar DEM:\n{e}")
            self._set_paths_label()
            return

        # ── Registrar DEM en la DB ──────────────────────────────────────────
        if _DB_AVAILABLE and self.current_reservorio_codigo and self._user_id is not None:
            try:
                with get_session() as session:
                    repo = Repository(session)
                    r = repo.get_reservorio_by_codigo(self.current_reservorio_codigo)
                    if r:
                        dem_obj = repo.register_dem(
                            reservorio_id=r.id,
                            archivo=Path(path).name,
                            ruta=path,
                            usuario_id=self._user_id,
                        )
                        self._current_dem_id = dem_obj.id
                        repo.update_reservorio_defaults(r.id, dem_path=path)
                        repo.log(
                            "dem_cargado",
                            usuario=repo.get_user_by_id(self._user_id),
                            detalle={"reservorio": self.current_reservorio_codigo,
                                     "archivo": Path(path).name},
                        )
                        self.history_panel.load_reservorio(self.current_reservorio_codigo)
            except Exception:
                pass

        self._set_paths_label()

    def pick_ortho(self) -> None:
        """Carga una ortofoto GeoTIFF para superponer sobre el DEM."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona ortofoto", "",
            "GeoTIFF (*.tif *.tiff);;Todos (*.*)",
        )
        if not path:
            return
        try:
            renderer = OrthoRenderer(path)
            self.viewer.set_ortho_renderer(renderer)
            self.btn_ortho.setEnabled(True)
            self.btn_ortho.setChecked(True)   # activar automáticamente
        except Exception as e:
            QMessageBox.critical(self, "Ortofoto", f"No se pudo cargar la ortofoto:\n{e}")

    def pick_mask(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona contorno", "",
            "Contornos (*.geojson *.json *.kml *.kmz *.shp);;Todos (*.*)",
        )
        if not path:
            return
        self.mask_path = path
        self.chk_use_mask.setChecked(True)
        self._set_paths_label()

    # ── Handlers toolbar visor ────────────────────────────────────────────────

    def _on_ortho_toggled(self, checked: bool) -> None:
        self.viewer.set_use_ortho(checked)

    def _on_draw_poly_toggled(self, checked: bool) -> None:
        if checked:
            self.viewer.set_poly_tool(PolyTool.DRAWING)
            self.viewer.setFocus()
        else:
            # Solo cancela si no hay un polígono cerrado en edición
            if self.viewer._poly_tool == PolyTool.DRAWING:
                self.viewer.clear_polygon()

    def _on_clear_poly(self) -> None:
        self.viewer.clear_polygon()
        self.btn_draw_poly.setChecked(False)

    def _on_polygon_committed(self, shapes: list) -> None:
        """
        Callback cuando el usuario confirma el polígono dibujado.
        Guarda el polígono como GeoJSON y lo activa como contorno.
        """
        # Crear directorio de datos si no existe
        data_dir = self._dems_dir()
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            data_dir = Path(__file__).parent.parent

        n = self.current_reservorio_codigo or "X"
        out_path = data_dir / f"contorno_dibujado_{n}.geojson"

        geojson_doc = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": s, "properties": {}}
                for s in shapes
            ],
        }
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(geojson_doc, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Polígono", f"No se pudo guardar el polígono:\n{e}")
            return

        self.mask_path = str(out_path)
        self.chk_use_mask.setChecked(True)
        self._set_paths_label()
        self.btn_draw_poly.setChecked(False)

        QMessageBox.information(
            self, "Polígono guardado",
            f"Polígono guardado como:\n{out_path.name}\n\n"
            "Ya está activo como contorno para el cálculo.",
        )

    # ── Cálculo ───────────────────────────────────────────────────────────────

    def calculate(self) -> None:
        if not self.dem_path:
            QMessageBox.critical(self, "Falta DEM", "Selecciona un DEM primero.")
            return

        try:
            salt  = self._get_float(self.txt_salt.text(),  "Cota de sal")
            water = self._get_float(self.txt_water.text(), "Cota pelo de agua")
            occ   = self._get_float(self.txt_occ.text(),   "Fracción ocluida")
            if not (0.0 <= occ <= 1.0):
                raise ValueError("Fracción ocluida debe estar entre 0 y 1 (ej. 0.20).")

            shapes = None
            if self.chk_use_mask.isChecked() and self.mask_path:
                shapes = load_mask_shapes(self.mask_path)

            dem  = DemRaster(self.dem_path, mask_shapes=shapes).load()
            calc = PondVolumeCalculator(dem)
            res  = calc.compute(salt, water, occluded_fraction=occ)

            self.latest_result = res
            self.latest_rows   = res.to_rows()
            self._populate_table(self.latest_rows)

            # ── Advertencias de rango DEM ───────────────────────────────────
            warns = []
            if res.salt_level  < res.dem_min or res.salt_level  > res.dem_max:
                warns.append(f"  • Cota de sal ({res.salt_level:.2f} m) fuera del rango DEM "
                             f"[{res.dem_min:.2f} – {res.dem_max:.2f} m].")
            if res.water_level < res.dem_min or res.water_level > res.dem_max:
                warns.append(f"  • Cota pelo de agua ({res.water_level:.2f} m) fuera del rango DEM "
                             f"[{res.dem_min:.2f} – {res.dem_max:.2f} m].")
            if warns:
                QMessageBox.warning(
                    self, "Advertencia de rango",
                    f"(mín: {res.dem_min:.2f} m, máx: {res.dem_max:.2f} m):\n\n"
                    + "\n".join(warns)
                    + "\n\nEl cálculo se realizó de todas formas, pero los resultados "
                      "pueden ser cero o incorrectos.",
                )

            self._save_cubicacion(res)

        except (MaskError, DemError) as e:
            QMessageBox.critical(self, "Error", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error inesperado", str(e))

    def _save_cubicacion(self, res: PondVolumes) -> None:
        if not _DB_AVAILABLE or not self.current_reservorio_codigo:
            return
        if self._user_id is None:
            return

        try:
            with get_session() as session:
                repo = Repository(session)
                r = repo.get_reservorio_by_codigo(self.current_reservorio_codigo)
                if not r:
                    return

                alert_vol  = repo.check_volume_anomaly(r.id, res.brine_total_m3)
                alert_salt = repo.check_salt_static(r.id, res.salt_level)
                anomalias  = [a for a in [alert_vol, alert_salt] if a]

                cub = repo.save_cubicacion(
                    reservorio_id=r.id,
                    usuario_id=self._user_id,
                    volumes=res,
                    dem_id=self._current_dem_id,
                )

                repo.log(
                    "cubicacion_calculada",
                    usuario=repo.get_user_by_id(self._user_id),
                    detalle={
                        "reservorio":    self.current_reservorio_codigo,
                        "cubicacion_id": cub.id,
                        "cota_sal":      res.salt_level,
                        "cota_agua":     res.water_level,
                        "vol_total_m3":  res.brine_total_m3,
                        "anomalias":     len(anomalias),
                    },
                )

            if anomalias:
                QMessageBox.warning(self, "Anomalía detectada", "\n\n".join(anomalias))

            self.history_panel.load_reservorio(self.current_reservorio_codigo)

        except Exception:
            pass

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
            self.tree.addTopLevelItem(QTreeWidgetItem([item, v, unit]))
        self.tree.resizeColumnToContents(0)

    # ── Exportar CSV ──────────────────────────────────────────────────────────

    def export_csv(self) -> None:
        if not self.latest_rows:
            QMessageBox.information(self, "Exportar", "Primero calcula resultados.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar CSV", default_output_name(), "CSV (*.csv)",
        )
        if not path:
            return
        try:
            out = export_rows_to_csv(path, self.latest_rows)
            self._audit(
                "csv_exportado",
                detalle={"reservorio": self.current_reservorio_codigo, "archivo": Path(path).name},
            )
            open_file_default_app(out)
        except Exception as e:
            QMessageBox.critical(self, "Exportar CSV", str(e))

    def clear_results(self) -> None:
        self.latest_result = None
        self.latest_rows   = []
        self.tree.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)

    if _DB_AVAILABLE:
        dlg = LoginDialog()
        if dlg.exec() != QDialog.Accepted:
            sys.exit(0)
        win = MainWindow(
            user_id       = dlg.user_id,
            user_nombre   = dlg.user_nombre,
            user_username = dlg.user_username,
            user_rol      = dlg.user_rol,
        )
    else:
        win = MainWindow()

    win.show()
    sys.exit(app.exec())
