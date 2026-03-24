from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
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
from .masks import load_mask_shapes, MaskError
from .export import export_rows_to_csv, open_file_default_app, default_output_name
from .viz import DemRenderer
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
# Visor DEM
# ─────────────────────────────────────────────────────────────────────────────

class DemViewerWidget(QWidget):
    """Visor DEM interactivo con render dual: cache rápido + HQ al detenerse."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

        self.renderer: DemRenderer | None = None

        self.zoom      = 1.0
        self.zoom_min  = 0.35
        self.zoom_max  = 12.0
        self.center_x  = 0.0
        self.center_y  = 0.0

        self._pixmap: QPixmap | None = None
        self._render_info = {"x0": 0.0, "y0": 0.0, "scale": 1.0, "base_scale": 1.0}

        self._fast_timer = QTimer(self)
        self._fast_timer.setSingleShot(True)
        self._fast_timer.timeout.connect(self._do_render_fast)

        self._hq_timer = QTimer(self)
        self._hq_timer.setSingleShot(True)
        self._hq_timer.timeout.connect(self._render_hq)

        self._pan_anchor: tuple[float, float, float, float] | None = None

    # ── API pública ───────────────────────────────────────────────────────────

    def set_renderer(self, renderer: DemRenderer) -> None:
        if self.renderer:
            self.renderer.close()
        self.renderer = renderer
        self.renderer.build_cache(max_tex=2048, levels=4)
        self.zoom     = 1.0
        self.center_x = renderer.width  / 2
        self.center_y = renderer.height / 2
        self._render_fast()
        self._schedule_hq(delay_ms=60)

    def clear(self) -> None:
        if self.renderer:
            self.renderer.close()
        self.renderer  = None
        self._pixmap   = None
        self.update()

    # ── Eventos Qt ────────────────────────────────────────────────────────────

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
            self.center_x = max(0.0, min(cx0 - dx / scale, self.renderer.width))
            self.center_y = max(0.0, min(cy0 - dy / scale, self.renderer.height))
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
        factor = 1.10 if event.angleDelta().y() > 0 else 1 / 1.10
        pos = event.position()
        self._zoom_at(factor, int(pos.x()), int(pos.y()))

    # ── Render ────────────────────────────────────────────────────────────────

    def _render_fast(self) -> None:
        self._fast_timer.start(8)

    def _do_render_fast(self) -> None:
        if not self.renderer:
            return
        rgb, info = self.renderer.render_view_cached(
            center_x=self.center_x, center_y=self.center_y,
            zoom=self.zoom, canvas_w=max(2, self.width()), canvas_h=max(2, self.height()),
        )
        self._render_info = info
        self._pixmap = self._rgb_to_pixmap(rgb)
        self.update()

    def _schedule_hq(self, delay_ms: int = 220) -> None:
        self._hq_timer.start(delay_ms)

    def _render_hq(self) -> None:
        if not self.renderer:
            return
        rgb, info = self.renderer.render_view_hq(
            center_x=self.center_x, center_y=self.center_y,
            zoom=self.zoom, canvas_w=max(2, self.width()), canvas_h=max(2, self.height()),
            hillshade=True,
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

        x0 = float(self._render_info["x0"])
        y0 = float(self._render_info["y0"])
        scale_old = float(self._render_info["scale"])
        rx = x0 + mx / scale_old
        ry = y0 + my / scale_old

        cw, ch = max(2, self.width()), max(2, self.height())
        base_scale = max(min(cw / self.renderer.width, ch / self.renderer.height), 1e-9)
        scale_new  = base_scale * new_zoom
        win_w, win_h = cw / scale_new, ch / scale_new

        new_x0 = max(0.0, min(rx - mx / scale_new, self.renderer.width  - win_w))
        new_y0 = max(0.0, min(ry - my / scale_new, self.renderer.height - win_h))

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
        self._current_dem_id: int | None = None   # id del DEM activo en la DB

        # Reservorios en el combobox
        self.cmb_reservorio.addItem("Reservorio")
        self.cmb_reservorio.addItems([f"Reservorio {i}" for i in range(1, 11)])

        # ── Visor DEM ─────────────────────────────────────────────────────
        self.viewer = DemViewerWidget(self.ui.viewerContainer)
        self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container_layout = self.ui.viewerContainer.layout() or QVBoxLayout(self.ui.viewerContainer)
        container_layout.addWidget(self.viewer)

        # ── Panel de historial ────────────────────────────────────────────
        # Se agrega al layout del groupDem, debajo del viewerContainer
        self.history_panel = HistoryPanel(self.ui.groupDem)
        dem_layout = self.ui.groupDem.layout()
        dem_layout.addWidget(self.history_panel)
        self.history_panel.hide()   # visible solo cuando hay reservorio seleccionado

        # Anchos iniciales de columnas de resultados
        self.tree.setColumnWidth(0, 280)
        self.tree.setColumnWidth(1, 140)
        self.tree.setColumnWidth(2, 70)

        self._connect_signals()
        # Forzar estado inicial limpio
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
        """
        Al seleccionar un reservorio:
          1. Carga su DEM por defecto (MDE_R{n}.tif)
          2. Autocarga las últimas cotas usadas (si hay cubicación previa)
          3. Refresca el panel histórico con sus mediciones y DEMs
        """
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
                self.viewer.set_renderer(renderer)
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
        """
        Rellena automáticamente los campos de cota con los valores de la
        última cubicación guardada para este reservorio.
        No sobreescribe si ya hay un valor ingresado manualmente.
        """
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

                # Solo autocargar si el campo está vacío
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
            self.viewer.set_renderer(renderer)
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
                        # Refrescar pestaña DEMs del panel
                        self.history_panel.load_reservorio(self.current_reservorio_codigo)
            except Exception:
                pass

        self._set_paths_label()

    def pick_mask(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona contorno (GeoJSON recomendado)", "",
            "GeoJSON (*.geojson *.json);;Shapefile (*.shp);;Todos (*.*)",
        )
        if not path:
            return
        self.mask_path = path
        self._set_paths_label()

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

            # ── Persistir en DB + anomalías + audit ─────────────────────────
            self._save_cubicacion(res)

        except (MaskError, DemError) as e:
            QMessageBox.critical(self, "Error", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error inesperado", str(e))

    def _save_cubicacion(self, res: PondVolumes) -> None:
        """
        Guarda la cubicación en la DB, verifica anomalías y actualiza el historial.
        No interrumpe el flujo si la DB no está disponible.
        """
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

                # ── Detección de anomalías ────────────────────────────────
                alert_vol  = repo.check_volume_anomaly(r.id, res.brine_total_m3)
                alert_salt = repo.check_salt_static(r.id, res.salt_level)
                anomalias = [a for a in [alert_vol, alert_salt] if a]

                # ── Guardar cubicación ────────────────────────────────────
                cub = repo.save_cubicacion(
                    reservorio_id=r.id,
                    usuario_id=self._user_id,
                    volumes=res,
                    dem_id=self._current_dem_id,
                )

                # ── Registrar en audit log ────────────────────────────────
                repo.log(
                    "cubicacion_calculada",
                    usuario=repo.get_user_by_id(self._user_id),
                    detalle={
                        "reservorio":       self.current_reservorio_codigo,
                        "cubicacion_id":    cub.id,
                        "cota_sal":         res.salt_level,
                        "cota_agua":        res.water_level,
                        "vol_total_m3":     res.brine_total_m3,
                        "anomalias":        len(anomalias),
                    },
                )

            # ── Mostrar alertas de anomalía ────────────────────────────────
            if anomalias:
                QMessageBox.warning(
                    self, "Anomalía detectada",
                    "\n\n".join(anomalias),
                )

            # ── Refrescar panel histórico ──────────────────────────────────
            self.history_panel.load_reservorio(self.current_reservorio_codigo)

        except Exception:
            # La DB puede no estar lista; el cálculo ya se mostró igual
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
        # Sin DB: abre directamente sin login (modo demo/sin dependencias)
        win = MainWindow()

    win.show()
    sys.exit(app.exec())
