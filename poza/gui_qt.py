from __future__ import annotations

import json
import math
import sys
from enum import IntEnum
from pathlib import Path
from typing import Dict, List, Tuple

from PySide6.QtCore import Qt, QPointF, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox,
    QDialog, QDockWidget, QFileDialog, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QSizePolicy, QSplitter, QStackedWidget, QStatusBar,
    QTableWidget, QTableWidgetItem, QTextBrowser,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .core import DemRaster, PondVolumeCalculator, DemError, PondVolumes
from .masks import polygon_raster_to_geojson   # sólo para convertir polígono dibujado
from .export import (
    export_rows_to_csv,
    export_rows_to_google_sheets,
    open_file_default_app,
    open_url_default_app,
    default_output_name,
)
from .viz import DemRenderer, OrthoRenderer

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

try:
    from .firebase_auth import (
        sign_in as fb_sign_in,
        FirebaseAuthError,
        create_firebase_user,
        list_firebase_users,
        set_user_active_firebase,
        update_user_role_firebase,
        is_available as fb_auth_available,
    )
    _FB_AUTH_AVAILABLE = True
except ImportError:
    _FB_AUTH_AVAILABLE = False


# ── Constantes de la app ──────────────────────────────────────────────────────
_APP_NAME  = "V-Metric"
_ICON_PATH = Path(__file__).parent.parent / "img" / "app.ico"
GOOGLE_SHEETS_SPREADSHEET_ID = "1P5_JBl2xSwLC7E0HmThbPPXVC93ecKETgRCbZFI-j9M"

# ── Sistema de temas centralizado ─────────────────────────────────────────────
from .themes import (
    ThemeTokens, THEMES, THEME_PREDETERMINADO,
    build_qss, build_login_qss, get_theme_by_name,
    contrast_ok, CUSTOM_FIELDS,
)

# Token del tema activo (global mutable — actualizado por _apply_theme)
_ACTIVE_TOKENS: ThemeTokens = THEME_PREDETERMINADO


def _apply_theme(app: QApplication, theme_name: str,
                 custom_colors: dict | None = None) -> None:
    """
    Aplica el tema seleccionado a toda la aplicación Qt.
    Centralizado — un único punto de verdad para el estilo global.
    """
    global _ACTIVE_TOKENS
    _ACTIVE_TOKENS = get_theme_by_name(theme_name, custom_colors)
    app.setStyleSheet(build_qss(_ACTIVE_TOKENS))


_PREFS_PATH = Path.home() / ".config" / "cubicador" / "prefs.json"

def _load_prefs() -> dict:
    try:
        if _PREFS_PATH.is_file():
            return json.loads(_PREFS_PATH.read_text("utf-8"))
    except Exception:
        pass
    return {"theme": "predeterminado", "decimals": 3, "custom_colors": {}}

def _save_prefs(p: dict) -> None:
    try:
        _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PREFS_PATH.write_text(json.dumps(p, indent=2), "utf-8")
    except Exception:
        pass

def fmt(x: float, decimals: int = 3) -> str:
    return f"{x:,.{decimals}f}"


# ─────────────────────────────────────────────────────────────────────────────
# Spinner animado
# ─────────────────────────────────────────────────────────────────────────────

class SpinnerLabel(QLabel):
    _FRAMES = "⣾⣽⣻⢿⡿⣟⣯⣷"
    def __init__(self, parent=None):
        super().__init__("", parent)
        self._frame = 0
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick)
        self.hide()
    def start(self):
        self._timer.start(80); self.show()
    def stop(self):
        self._timer.stop(); self.setText(""); self.hide()
    def _tick(self):
        self._frame = (self._frame + 1) % len(self._FRAMES)
        self.setText(self._FRAMES[self._frame])


# ─────────────────────────────────────────────────────────────────────────────
# Diálogo de inicio de sesión (con throbber)
# ─────────────────────────────────────────────────────────────────────────────

class LoginDialog(QDialog):
    """
    Pantalla de inicio de sesión.
    SIEMPRE usa el tema Claro corporativo (identidad de marca fija),
    independientemente del tema configurado por el usuario.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{_APP_NAME} — Inicio de sesión")
        self.setFixedSize(420, 360)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        if _ICON_PATH.exists():
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(str(_ICON_PATH)))
        # Siempre tema Claro — no afectado por el tema global de la app
        self.setStyleSheet(build_login_qss())
        self._user_id   = None   # int: SQLite shadow user id (para FKs locales)
        self._user_uid  = None   # str: Firebase UID
        self._user_nombre = self._user_email = ""
        self._user_rol = "operador"
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self); layout.setContentsMargins(36, 30, 36, 26); layout.setSpacing(10)
        # Header decorativo
        hdr = QWidget(); hdr.setFixedHeight(6)
        hdr.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                          f"stop:0 {THEME_PREDETERMINADO.primary},stop:1 {THEME_PREDETERMINADO.accent_pos});")
        layout.addWidget(hdr)
        layout.addSpacing(4)
        lbl = QLabel(f"  {_APP_NAME}")
        lbl.setObjectName("loginTitle")
        lbl.setStyleSheet(f"font: bold 20pt 'Segoe UI'; color: {THEME_PREDETERMINADO.primary}; background: transparent;")
        layout.addWidget(lbl)
        sub = QLabel("  Operación Atacama — Iniciar sesión")
        sub.setStyleSheet(f"font: 9pt 'Segoe UI'; color: {THEME_PREDETERMINADO.secondary}; background: transparent;")
        layout.addWidget(sub)
        layout.addSpacing(14)
        form = QFormLayout(); form.setSpacing(10); form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._txt_user = QLineEdit(); self._txt_user.setPlaceholderText("correo@empresa.cl"); self._txt_user.setMaxLength(128)
        self._txt_pass = QLineEdit(); self._txt_pass.setPlaceholderText("Contraseña")
        self._txt_pass.setEchoMode(QLineEdit.Password); self._txt_pass.setMaxLength(128)
        self._txt_pass.returnPressed.connect(self._try_login)
        form.addRow("Correo electrónico:", self._txt_user)
        form.addRow("Contraseña:", self._txt_pass)
        layout.addLayout(form)
        self._lbl_error = QLabel("")
        self._lbl_error.setAlignment(Qt.AlignCenter)
        self._lbl_error.setStyleSheet("color: #C0392B; font: bold 9pt 'Segoe UI'; background: transparent;")
        layout.addWidget(self._lbl_error)
        # Throbber
        thr = QHBoxLayout()
        self._spinner = SpinnerLabel()
        self._spinner.setStyleSheet(f"font: bold 14pt 'Segoe UI'; color: {THEME_PREDETERMINADO.primary};")
        self._spinner_lbl = QLabel("")
        self._spinner_lbl.setStyleSheet(f"color:{THEME_PREDETERMINADO.secondary}; font: italic 9pt 'Segoe UI'; background:transparent;")
        thr.addWidget(self._spinner); thr.addWidget(self._spinner_lbl); thr.addStretch()
        layout.addLayout(thr)
        layout.addStretch()
        row = QHBoxLayout()
        btn = QPushButton("Acceder")
        # objectName registrado en build_login_qss para estilos de login
        btn.setObjectName("btnLoginAcceder"); btn.setDefault(True)
        btn.clicked.connect(self._try_login)
        row.addStretch(); row.addWidget(btn); layout.addLayout(row)

    def _try_login(self):
        email = self._txt_user.text().strip(); password = self._txt_pass.text()
        if not email or not password:
            self._lbl_error.setText("Ingresa correo y contraseña."); return
        self._spinner.start(); self._spinner_lbl.setText("Validando credenciales…")
        self._lbl_error.setText(""); QApplication.processEvents()

        # ── Firebase Auth ──────────────────────────────────────────────────
        if _FB_AUTH_AVAILABLE and fb_auth_available():
            try:
                session = fb_sign_in(email, password)
                self._user_uid   = session.uid
                self._user_email = session.email
                self._user_nombre = session.nombre_completo or email.split("@")[0]
                self._user_rol   = session.rol

                # Crear/obtener shadow user en SQLite para FKs de cubicaciones
                if _DB_AVAILABLE:
                    try:
                        from sqlalchemy import select as _sel
                        from .db.models import Usuario as _Usr
                        with get_session() as s:
                            u = s.scalar(_sel(_Usr).where(_Usr.username == email))
                            if u is None:
                                import bcrypt as _bc
                                u = _Usr(username=email,
                                         password_hash=_bc.hashpw(b"firebase-shadow", _bc.gensalt()).decode(),
                                         nombre_completo=self._user_nombre, rol=self._user_rol)
                                s.add(u); s.commit(); s.refresh(u)
                            elif u.nombre_completo != self._user_nombre or u.rol != self._user_rol:
                                u.nombre_completo = self._user_nombre; u.rol = self._user_rol
                                s.commit()
                            self._user_id = u.id
                    except Exception:
                        self._user_id = None

                # Registrar actividad en Firestore
                if _FB_AVAILABLE:
                    firebase_sync.log_activity_async(
                        self._user_uid, "login",
                        {"email": email, "rol": self._user_rol},
                    )
                self._spinner.stop(); self._spinner_lbl.setText(""); self.accept()

            except FirebaseAuthError as e:
                self._spinner.stop(); self._spinner_lbl.setText("")
                if _FB_AVAILABLE:
                    firebase_sync.log_activity_async("anon", "login_fallido", {"email": email, "motivo": str(e)})
                self._lbl_error.setText(str(e)); self._txt_pass.clear(); self._txt_pass.setFocus()
            return

        # ── Fallback: SQLite auth (solo si Firebase no está configurado) ───
        if not _DB_AVAILABLE:
            self._user_nombre = self._user_email = email
            self._spinner.stop(); self._spinner_lbl.setText(""); self.accept(); return
        try:
            with get_session() as s:
                repo = Repository(s)
                user = repo.authenticate(email, password)
                self._user_id     = user.id
                self._user_uid    = None
                self._user_email  = user.username
                self._user_nombre = user.nombre_completo
                self._user_rol    = user.rol
                repo.log("login", usuario=user, detalle={"ip": "localhost"})
            self._spinner.stop(); self._spinner_lbl.setText(""); self.accept()
        except Exception as e:
            self._spinner.stop(); self._spinner_lbl.setText("")
            try:
                with get_session() as s2:
                    Repository(s2).log("login_fallido", detalle={"email": email, "motivo": str(e)})
            except Exception: pass
            self._lbl_error.setText(str(e)); self._txt_pass.clear(); self._txt_pass.setFocus()

    @property
    def user_id(self): return self._user_id        # int | None (SQLite shadow id)
    @property
    def user_uid(self): return self._user_uid      # str | None (Firebase UID)
    @property
    def user_nombre(self): return self._user_nombre
    @property
    def user_username(self): return self._user_email   # email usado como username
    @property
    def user_rol(self): return self._user_rol


# ─────────────────────────────────────────────────────────────────────────────
# Diálogos secundarios
# ─────────────────────────────────────────────────────────────────────────────

class AccountDialog(QDialog):
    def __init__(self, user_nombre="", user_username="", user_rol="operador",
                 user_id=None, parent=None):
        super().__init__(parent)
        self._user_nombre   = user_nombre
        self._user_username = user_username
        self._user_rol      = user_rol
        self._user_id       = user_id
        self.setWindowTitle("Gestión de cuenta")
        self.setMinimumSize(480, 380)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        if _ICON_PATH.exists():
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(str(_ICON_PATH)))
        self._build_ui()

    def _build_ui(self):
        vl = QVBoxLayout(self); vl.setContentsMargins(0, 0, 0, 0); vl.setSpacing(0)

        # ── Tab bar ──
        tab_bar = QWidget()
        tab_bar.setObjectName("dialogHeader")
        tbl = QHBoxLayout(tab_bar); tbl.setContentsMargins(12, 8, 12, 0); tbl.setSpacing(4)
        lbl_title = QLabel(f"  {_APP_NAME}  ·  Cuenta")
        lbl_title.setStyleSheet("font: bold 13pt 'Segoe UI';")
        tbl.addWidget(lbl_title); tbl.addStretch()

        self._tab_group = QButtonGroup(self); self._tab_group.setExclusive(True)
        self._tab_stack = QStackedWidget()

        def _add_tab(label: str, widget: QWidget, idx: int):
            btn = QPushButton(label); btn.setCheckable(True)
            btn.setObjectName("dialogTab")
            self._tab_group.addButton(btn, idx); tbl.addWidget(btn)
            self._tab_stack.addWidget(widget)
            return btn

        btn0 = _add_tab("👤  Mi cuenta", self._build_my_account_tab(), 0)
        btn0.setChecked(True)
        if self._user_rol == "admin":
            _add_tab("👥  Gestión de usuarios", self._build_admin_tab(), 1)

        self._tab_group.idClicked.connect(self._tab_stack.setCurrentIndex)

        vl.addWidget(tab_bar)
        vl.addWidget(self._tab_stack, 1)

    def _build_my_account_tab(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w); vl.setContentsMargins(28, 20, 28, 20); vl.setSpacing(10)
        lbl_user = QLabel(f"Usuario: <b>{self._user_username}</b>")
        vl.addWidget(lbl_user)
        form = QFormLayout(); form.setSpacing(8); form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.txt_nombre = QLineEdit(self._user_nombre)
        self.txt_pass1  = QLineEdit(); self.txt_pass1.setPlaceholderText("Nueva contraseña (opcional)")
        self.txt_pass1.setEchoMode(QLineEdit.Password)
        self.txt_pass2  = QLineEdit(); self.txt_pass2.setPlaceholderText("Confirmar contraseña")
        self.txt_pass2.setEchoMode(QLineEdit.Password)
        form.addRow("Nombre completo:", self.txt_nombre)
        form.addRow("Nueva contraseña:", self.txt_pass1)
        form.addRow("Confirmar:", self.txt_pass2)
        vl.addLayout(form)
        self._lbl_msg = QLabel(""); self._lbl_msg.setAlignment(Qt.AlignCenter)
        vl.addWidget(self._lbl_msg); vl.addStretch()
        row = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar"); btn_cancel.setObjectName("btnSecondary"); btn_cancel.clicked.connect(self.reject)
        btn_save   = QPushButton("Guardar cambios"); btn_save.setObjectName("btnPrimary"); btn_save.clicked.connect(self._save_account)
        row.addStretch(); row.addWidget(btn_cancel); row.addWidget(btn_save); vl.addLayout(row)
        return w

    def _save_account(self):
        if self.txt_pass1.text() and self.txt_pass1.text() != self.txt_pass2.text():
            self._lbl_msg.setStyleSheet("color:#C0392B; font:bold 9pt 'Segoe UI';")
            self._lbl_msg.setText("Las contraseñas no coinciden."); return
        self._lbl_msg.setStyleSheet("color:#27AE60; font:bold 9pt 'Segoe UI';")
        self._lbl_msg.setText("Cambios guardados."); QTimer.singleShot(800, self.accept)

    def _build_admin_tab(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w); vl.setContentsMargins(16, 12, 16, 12); vl.setSpacing(8)

        # Tabla de usuarios
        lbl = QLabel("Usuarios registrados"); lbl.setStyleSheet("font: bold 10pt 'Segoe UI';")
        vl.addWidget(lbl)
        self._tbl_users = QTableWidget(0, 4)
        self._tbl_users.setHorizontalHeaderLabels(["Correo", "Nombre", "Rol", "Activo"])
        self._tbl_users.horizontalHeader().setStretchLastSection(True)
        self._tbl_users.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._tbl_users.verticalHeader().setVisible(False)
        self._tbl_users.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_users.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl_users.setAlternatingRowColors(True)
        self._tbl_users.setMaximumHeight(140)
        vl.addWidget(self._tbl_users)
        self._refresh_users_table()

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); vl.addWidget(sep)

        # Formulario crear usuario
        lbl2 = QLabel("Crear nuevo usuario"); lbl2.setStyleSheet("font: bold 10pt 'Segoe UI';")
        vl.addWidget(lbl2)
        form2 = QFormLayout(); form2.setSpacing(6); form2.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.txt_new_user   = QLineEdit(); self.txt_new_user.setPlaceholderText("correo@empresa.cl")
        self.txt_new_nombre = QLineEdit(); self.txt_new_nombre.setPlaceholderText("Nombre Apellido")
        self.txt_new_pass   = QLineEdit(); self.txt_new_pass.setPlaceholderText("Contraseña inicial (mín. 6 car.)"); self.txt_new_pass.setEchoMode(QLineEdit.Password)
        self.cmb_new_rol    = QComboBox(); self.cmb_new_rol.addItems(["operador", "admin"])
        form2.addRow("Correo:", self.txt_new_user)
        form2.addRow("Nombre:", self.txt_new_nombre)
        form2.addRow("Contraseña:", self.txt_new_pass)
        form2.addRow("Rol:", self.cmb_new_rol)
        vl.addLayout(form2)
        self._lbl_admin_msg = QLabel(""); self._lbl_admin_msg.setAlignment(Qt.AlignCenter); vl.addWidget(self._lbl_admin_msg)
        row = QHBoxLayout()
        btn_create = QPushButton("➕  Crear usuario"); btn_create.setObjectName("btnPrimary"); btn_create.clicked.connect(self._create_user)
        row.addStretch(); row.addWidget(btn_create); vl.addLayout(row)
        return w

    def _refresh_users_table(self):
        self._tbl_users.setRowCount(0)
        # Preferir Firebase para listar usuarios
        if _FB_AUTH_AVAILABLE:
            try:
                users = list_firebase_users()
                for u in users:
                    r = self._tbl_users.rowCount(); self._tbl_users.insertRow(r)
                    for col, val in enumerate([
                        u.get("email", ""),
                        u.get("nombre_completo", ""),
                        u.get("rol", "operador"),
                        "✓" if u.get("activo", True) else "✗",
                    ]):
                        it = QTableWidgetItem(str(val)); it.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                        self._tbl_users.setItem(r, col, it)
                return
            except Exception:
                pass
        # Fallback SQLite
        if not _DB_AVAILABLE: return
        try:
            with get_session() as s:
                users = Repository(s).list_users()
            for u in users:
                r = self._tbl_users.rowCount(); self._tbl_users.insertRow(r)
                for col, val in enumerate([u.username, u.nombre_completo, u.rol, "✓" if u.activo else "✗"]):
                    it = QTableWidgetItem(str(val)); it.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                    self._tbl_users.setItem(r, col, it)
        except Exception:
            pass

    def _create_user(self):
        email    = self.txt_new_user.text().strip()
        nombre   = self.txt_new_nombre.text().strip()
        password = self.txt_new_pass.text()
        rol      = self.cmb_new_rol.currentText()
        if not email or not nombre or not password:
            self._lbl_admin_msg.setStyleSheet("color:#C0392B; font:bold 9pt 'Segoe UI';")
            self._lbl_admin_msg.setText("Completa todos los campos."); return
        if len(password) < 6:
            self._lbl_admin_msg.setStyleSheet("color:#C0392B; font:bold 9pt 'Segoe UI';")
            self._lbl_admin_msg.setText("La contraseña debe tener al menos 6 caracteres."); return

        # Crear en Firebase si está disponible
        if _FB_AUTH_AVAILABLE:
            try:
                create_firebase_user(email=email, password=password,
                                     nombre_completo=nombre, rol=rol)
                self._lbl_admin_msg.setStyleSheet("color:#27AE60; font:bold 9pt 'Segoe UI';")
                self._lbl_admin_msg.setText(f"Usuario '{email}' creado en Firebase.")
                self.txt_new_user.clear(); self.txt_new_nombre.clear(); self.txt_new_pass.clear()
                self._refresh_users_table(); return
            except Exception as e:
                self._lbl_admin_msg.setStyleSheet("color:#C0392B; font:bold 9pt 'Segoe UI';")
                self._lbl_admin_msg.setText(str(e)); return

        # Fallback SQLite
        if not _DB_AVAILABLE:
            self._lbl_admin_msg.setStyleSheet("color:#C0392B; font:bold 9pt 'Segoe UI';")
            self._lbl_admin_msg.setText("Firebase Auth no disponible."); return
        try:
            with get_session() as s:
                Repository(s).create_user(username=email, nombre_completo=nombre,
                                           password=password, rol=rol)
            self._lbl_admin_msg.setStyleSheet("color:#27AE60; font:bold 9pt 'Segoe UI';")
            self._lbl_admin_msg.setText(f"Usuario '{email}' creado.")
            self.txt_new_user.clear(); self.txt_new_nombre.clear(); self.txt_new_pass.clear()
            self._refresh_users_table()
        except Exception as e:
            self._lbl_admin_msg.setStyleSheet("color:#C0392B; font:bold 9pt 'Segoe UI';")
            self._lbl_admin_msg.setText(str(e))


class PreferencesDialog(QDialog):
    """
    Diálogo de preferencias con selector de 4 temas y personalización de colores.
    El cambio se aplica en vivo al confirmar.
    """
    # Nombres mostrados en el ComboBox
    _THEME_LABELS = ["🌑  Predeterminado", "🎨  Personalizado"]
    _THEME_KEYS   = ["predeterminado", "personalizado"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferencias — V-Metric")
        self.setMinimumSize(520, 420)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        if _ICON_PATH.exists():
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(str(_ICON_PATH)))
        self._prefs = _load_prefs()
        self._custom_colors: dict = dict(self._prefs.get("custom_colors", {}))
        self._swatch_btns: dict = {}   # field_key → QPushButton
        self._build_ui()

    def _build_ui(self):
        vl = QVBoxLayout(self); vl.setContentsMargins(0, 0, 0, 0); vl.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setObjectName("dialogHeader")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(20, 14, 20, 14)
        lbl_h = QLabel("⚙  Preferencias"); lbl_h.setObjectName("dialogHeader")
        lbl_h.setStyleSheet(f"font: bold 14pt 'Segoe UI'; color: {_ACTIVE_TOKENS.text_header}; background: transparent;")
        hl.addWidget(lbl_h); hl.addStretch()
        vl.addWidget(hdr)

        body = QWidget(); vl.addWidget(body, 1)
        bl = QVBoxLayout(body); bl.setContentsMargins(24, 18, 24, 18); bl.setSpacing(14)

        # ── Tema ──
        grp_tema = QGroupBox("🎨  Tema de interfaz"); grp_tema.setProperty("accent", "false")
        tgl = QVBoxLayout(grp_tema); tgl.setContentsMargins(12, 14, 12, 12); tgl.setSpacing(8)

        row_cmb = QHBoxLayout()
        lbl_tm = QLabel("Seleccionar tema:"); lbl_tm.setFixedWidth(130)
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItems(self._THEME_LABELS)
        current_theme = self._prefs.get("theme", "predeterminado")
        idx = self._THEME_KEYS.index(current_theme) if current_theme in self._THEME_KEYS else 0
        self.cmb_theme.setCurrentIndex(idx)
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_changed)
        row_cmb.addWidget(lbl_tm); row_cmb.addWidget(self.cmb_theme, 1)
        tgl.addLayout(row_cmb)

        # Preview del tema
        self._lbl_preview = QLabel()
        self._lbl_preview.setWordWrap(True)
        self._lbl_preview.setStyleSheet("font: italic 9pt 'Segoe UI'; padding: 4px;")
        tgl.addWidget(self._lbl_preview)
        self._update_preview(idx)
        bl.addWidget(grp_tema)

        # ── Colores personalizados ──
        self._grp_custom = QGroupBox("🎨  Colores personalizados")
        self._grp_custom.setProperty("accent", "true")
        cgl = QVBoxLayout(self._grp_custom); cgl.setContentsMargins(12, 14, 12, 12); cgl.setSpacing(6)
        lbl_info = QLabel("Ajusta los colores base del tema personalizado:")
        lbl_info.setStyleSheet("font: italic 9pt 'Segoe UI';")
        cgl.addWidget(lbl_info)
        warn_lbl = QLabel("⚠  El contraste mínimo WCAG AA es 4.5:1. Los valores inválidos se marcan en rojo.")
        warn_lbl.setWordWrap(True)
        warn_lbl.setStyleSheet("font: 8pt 'Segoe UI'; color: #888;")
        cgl.addWidget(warn_lbl)
        self._contrast_labels: dict = {}
        for field_key, field_label in CUSTOM_FIELDS:
            row_c = QHBoxLayout()
            lbl_c = QLabel(f"{field_label}:"); lbl_c.setFixedWidth(160)
            current_val = self._custom_colors.get(field_key,
                          getattr(THEME_PREDETERMINADO, field_key, "#29306A"))
            swatch = QPushButton()
            swatch.setObjectName("colorSwatch")
            swatch.setFixedSize(48, 26)
            swatch.setStyleSheet(f"background: {current_val}; border: 2px solid #888; border-radius:4px;")
            swatch.setToolTip(current_val)
            swatch.clicked.connect(lambda _, fk=field_key: self._pick_color(fk))
            self._swatch_btns[field_key] = swatch
            lbl_hex = QLabel(current_val)
            lbl_hex.setStyleSheet("font: 8pt 'Courier New'; min-width: 70px;")
            self._contrast_labels[field_key] = lbl_hex
            row_c.addWidget(lbl_c); row_c.addWidget(swatch); row_c.addWidget(lbl_hex); row_c.addStretch()
            cgl.addLayout(row_c)
        bl.addWidget(self._grp_custom)
        self._grp_custom.setVisible(idx == 1)  # solo visible en "Personalizado"

        # ── Decimales ──
        grp_dec = QGroupBox("🔢  Precisión numérica")
        dgl = QHBoxLayout(grp_dec); dgl.setContentsMargins(12, 14, 12, 12); dgl.setSpacing(10)
        lbl_dec = QLabel("Decimales en resultados:"); lbl_dec.setFixedWidth(190)
        self.txt_decimals = QLineEdit(str(self._prefs.get("decimals", 3)))
        self.txt_decimals.setFixedWidth(60)
        dgl.addWidget(lbl_dec); dgl.addWidget(self.txt_decimals); dgl.addStretch()
        bl.addWidget(grp_dec)
        bl.addStretch()

        # Botones
        row_btns = QHBoxLayout()
        btn_reset = QPushButton("↺  Restaurar defaults")
        btn_reset.setObjectName("btnSecondary"); btn_reset.clicked.connect(self._reset_custom)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("btnSecondary"); btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("✓  Guardar y aplicar")
        btn_save.setObjectName("btnPrimary"); btn_save.clicked.connect(self._save)
        row_btns.addWidget(btn_reset); row_btns.addStretch()
        row_btns.addWidget(btn_cancel); row_btns.addWidget(btn_save)
        bl.addLayout(row_btns)

    def _on_theme_changed(self, idx: int):
        self._grp_custom.setVisible(idx == 1)
        self._update_preview(idx)
        self.adjustSize()

    def _update_preview(self, idx: int):
        descs = [
            "Escala de grises sobria con acentos teal — tema oscuro, ideal para trabajo en campo.",
            "Define tus propios colores. Se aplican sobre la estructura del tema Predeterminado.",
        ]
        self._lbl_preview.setText(descs[idx] if idx < len(descs) else "")

    def _pick_color(self, field_key: str):
        from PySide6.QtWidgets import QColorDialog
        from PySide6.QtGui import QColor
        current = self._custom_colors.get(field_key, getattr(THEME_PREDETERMINADO, field_key, "#29306A"))
        color = QColorDialog.getColor(QColor(current), self, f"Selecciona color — {field_key}")
        if not color.isValid(): return
        hex_val = color.name().upper()
        self._custom_colors[field_key] = hex_val
        swatch = self._swatch_btns[field_key]
        swatch.setStyleSheet(f"background: {hex_val}; border: 2px solid #888; border-radius:4px;")
        swatch.setToolTip(hex_val)
        lbl = self._contrast_labels[field_key]
        lbl.setText(hex_val)
        # Validar contraste con fondo base
        bg = self._custom_colors.get("bg_base", THEME_PREDETERMINADO.bg_base)
        if field_key in ("text_base", "primary", "secondary"):
            ok = contrast_ok(hex_val, bg)
            lbl.setStyleSheet(
                f"font: 8pt 'Courier New'; min-width:70px; color: {'#27AE60' if ok else '#C0392B'};"
            )

    def _reset_custom(self):
        """Restaura los colores personalizados a los defaults de Predeterminado."""
        self._custom_colors.clear()
        for field_key, _ in CUSTOM_FIELDS:
            val = getattr(THEME_PREDETERMINADO, field_key, "#29306A")
            self._custom_colors[field_key] = val
            swatch = self._swatch_btns[field_key]
            swatch.setStyleSheet(f"background: {val}; border: 2px solid #888; border-radius:4px;")
            swatch.setToolTip(val)
            lbl = self._contrast_labels[field_key]
            lbl.setText(val)
            lbl.setStyleSheet("font: 8pt 'Courier New'; min-width:70px;")

    def _save(self):
        idx = self.cmb_theme.currentIndex()
        try:
            decimals = max(0, min(6, int(self.txt_decimals.text().strip())))
        except ValueError:
            decimals = 3
        self._prefs["theme"] = self._THEME_KEYS[idx]
        self._prefs["decimals"] = decimals
        self._prefs["custom_colors"] = self._custom_colors
        _save_prefs(self._prefs)
        # Aplicar tema en vivo — afecta toda la aplicación excepto el login
        app = QApplication.instance()
        if app:
            _apply_theme(app, self._prefs["theme"],
                         self._custom_colors if idx == 1 else None)
        self.accept()


_HELP_HTML = """
<html><body style="font-family:'Segoe UI'; font-size:10pt; color:#F6F6F6; margin:16px;">
<h2 style="color:#F75C03;">Manual de uso — Cubicador de Pozas</h2>
<h3 style="color:#FFFFFF;">1. Cargar DEM</h3>
<p>En el panel <b>Parámetros</b>, haz clic en <b>Cargar DEM…</b> y selecciona un archivo GeoTIFF (.tif / .tiff). El visor mostrará el mapa de elevación con escala de colores automática.</p>
<h3 style="color:#F6F6F6;">2. Contorno (máscara)</h3>
<p>Carga un contorno desde archivo (<b>Cargar contorno…</b>) en formato GeoJSON, KML, KMZ o SHP, o dibuja el contorno directamente en el visor:</p>
<ul>
<li>Haz clic en <b>✏ Dibujar</b> en la barra del visor.</li>
<li>Haz clic en el mapa para añadir vértices.</li>
<li>Haz clic cerca del primer vértice para cerrar el polígono.</li>
<li>Activa <b>↖ Cursor</b> para arrastrar vértices.</li>
<li>Con <b>Cursor</b> activo: <b>T</b> = insertar vértice, <b>R</b> = eliminar vértice, <b>Enter</b> = confirmar.</li>
<li><b>Esc</b> cancela en cualquier momento.</li>
</ul>
<h3 style="color:#FFFFFF;">3. Ortofoto</h3>
<p>Haz clic en <b>Cargar ortofoto…</b> y luego activa el botón <b>🛰 Ortofoto</b> para alternar entre el DEM y la imagen RGB georeferenciada.</p>
<h3 style="color:#F75C03;">4. Parámetros de cálculo</h3>
<ul>
<li><b>Cota de sal (m):</b> elevación superior de la capa de sal.</li>
<li><b>Cota pelo de agua (m):</b> elevación de la superficie libre del agua.</li>
<li><b>Fracción ocluida:</b> porcentaje de la superficie oculta (0.00 a 1.00).</li>
</ul>
<h3 style="color:#FFFFFF;">5. Calcular y exportar</h3>
<p>Haz clic en <b>⚡ Calcular volúmenes</b>. Los resultados aparecen en el panel <b>Resultados</b>. Usa <b>Exportar CSV</b> para guardar.</p>
<h3 style="color:#FFFFFF;">6. Navegar el visor</h3>
<ul>
<li><b>Rueda del ratón:</b> zoom centrado en el cursor.</li>
<li><b>Arrastrar:</b> paneo (en modo IDLE o con botón derecho).</li>
</ul>
<h3 style="color:#FFFFFF;">7. Paneles modulares</h3>
<p>Todos los paneles son flotantes y reposicionables. Arrástralos desde su barra de título. Si cierras uno, recupéralo desde el menú <b>Vista</b>.</p>
</body></html>
"""

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ayuda — Manual de uso")
        self.resize(700, 520)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        vl = QVBoxLayout(self); vl.setContentsMargins(0, 0, 0, 12)
        browser = QTextBrowser(); browser.setHtml(_HELP_HTML)
        vl.addWidget(browser)
        btn = QPushButton("Cerrar"); btn.setObjectName("btnPrimary"); btn.setFixedWidth(100)
        btn.clicked.connect(self.accept)
        row = QHBoxLayout(); row.addStretch(); row.addWidget(btn); vl.addLayout(row)


# ─────────────────────────────────────────────────────────────────────────────
# PolyTool enum + DemViewerWidget
# ─────────────────────────────────────────────────────────────────────────────

class PolyTool(IntEnum):
    IDLE       = 0
    DRAWING    = 1
    CURSOR     = 2
    RULER      = 3
    ELEV_POINT = 4


class DemViewerWidget(QWidget):
    polygon_committed = Signal(list)
    poly_tool_changed = Signal(int)

    CLOSE_DIST_PX: float = 14.0
    VERTEX_HIT_PX: float = 14.0

    def __init__(self, parent=None):
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
        self._poly_tool: PolyTool = PolyTool.IDLE
        self._poly_verts_raster: List[Tuple[float, float]] = []
        self._poly_closed = False
        self._poly_mouse_screen: Tuple[float, float] = (0.0, 0.0)
        self._drag_vertex_idx: int | None = None
        # ── Herramienta de cota puntual ───────────────────────────────────
        self._elev_points: List[Tuple[float, float, float]] = []  # (rx, ry, elev_m)
        self._cursor_elev: float | None = None
        # ── Herramienta de regla ──────────────────────────────────────────
        self._ruler_p1: Tuple[float, float] | None = None   # (rx, ry)
        self._ruler_p2: Tuple[float, float] | None = None   # (rx, ry) — extremo fijo
        self._ruler_mouse: Tuple[float, float] = (0.0, 0.0) # posición screen del cursor

    @property
    def renderer(self):
        return self._ortho_renderer if self._use_ortho else self._dem_renderer

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

    def set_renderer(self, r: DemRenderer) -> None:
        self.set_dem_renderer(r)

    def clear(self) -> None:
        if self._dem_renderer:   self._dem_renderer.close()
        if self._ortho_renderer: self._ortho_renderer.close()
        self._dem_renderer = self._ortho_renderer = self._pixmap = None
        self.clear_polygon(); self.update()

    def set_poly_tool(self, tool: PolyTool) -> None:
        prev = self._poly_tool; self._poly_tool = tool; self._drag_vertex_idx = None
        if tool == PolyTool.DRAWING:
            self._poly_verts_raster.clear(); self._poly_closed = False
            self.setCursor(Qt.CrossCursor)
        elif tool == PolyTool.ELEV_POINT:
            self.setCursor(Qt.CrossCursor)
        elif tool == PolyTool.RULER:
            self._ruler_p1 = self._ruler_p2 = None
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        if tool != prev: self.poly_tool_changed.emit(int(tool))
        self.update()

    def clear_polygon(self) -> None:
        prev = self._poly_tool; self._poly_tool = PolyTool.IDLE
        self._poly_verts_raster.clear(); self._poly_closed = False
        self._drag_vertex_idx = None; self.setCursor(Qt.ArrowCursor)
        if prev != PolyTool.IDLE: self.poly_tool_changed.emit(0)
        self.update()

    def clear_canvas(self) -> None:
        """Limpia polígono, regla y puntos de cota — vuelve a IDLE."""
        self._poly_verts_raster.clear(); self._poly_closed = False
        self._drag_vertex_idx = None
        self._elev_points.clear(); self._cursor_elev = None
        self._ruler_p1 = self._ruler_p2 = None
        prev = self._poly_tool; self._poly_tool = PolyTool.IDLE
        self.setCursor(Qt.ArrowCursor)
        if prev != PolyTool.IDLE: self.poly_tool_changed.emit(0)
        self.update()

    # ── Eventos ───────────────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event); self._render_fast(); self._schedule_hq()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        # fondo blanco (letterbox)
        p.fillRect(self.rect(), QColor(255, 255, 255))
        if self._pixmap:
            p.drawPixmap(int(self._render_info.get("off_x", 0)),
                         int(self._render_info.get("off_y", 0)), self._pixmap)
        if self._poly_tool not in (PolyTool.IDLE, PolyTool.ELEV_POINT, PolyTool.RULER):
            if self._poly_verts_raster:
                self._draw_poly_overlay(p)
            elif self._poly_tool == PolyTool.DRAWING:
                self._draw_hint(p, "  Clic = agregar vértice   Clic en inicio = cerrar   Esc = cancelar  ")
        if self._poly_tool == PolyTool.ELEV_POINT or self._elev_points:
            self._draw_elev_overlay(p)
        if self._poly_tool == PolyTool.RULER or self._ruler_p1:
            self._draw_ruler_overlay(p)
        p.end()

    def mousePressEvent(self, event) -> None:
        self.setFocus()
        sx, sy = float(event.position().x()), float(event.position().y())
        # SIEMPRE actualizar posición del mouse para evitar línea a (0,0)
        self._poly_mouse_screen = (sx, sy)

        if self._poly_tool == PolyTool.ELEV_POINT:
            if event.button() == Qt.LeftButton:
                rx, ry = self._s2r(sx, sy)
                r = self._dem_renderer
                if r and hasattr(r, "elevation_at"):
                    elev = r.elevation_at(rx, ry)
                    if elev is not None:
                        self._elev_points.append((rx, ry, elev)); self.update()
            return

        if self._poly_tool == PolyTool.RULER:
            if event.button() == Qt.LeftButton:
                rx, ry = self._s2r(sx, sy)
                if self._ruler_p1 is None:
                    self._ruler_p1 = (rx, ry)
                else:
                    self._ruler_p2 = (rx, ry)
                self.update()
            return

        if self._poly_tool == PolyTool.DRAWING:
            if event.button() == Qt.LeftButton:
                if len(self._poly_verts_raster) >= 3 and self._should_close(sx, sy):
                    self._poly_closed = True; self.set_poly_tool(PolyTool.CURSOR)
                else:
                    self._poly_verts_raster.append(self._s2r(sx, sy)); self.update()
            return

        if self._poly_tool == PolyTool.CURSOR:
            if event.button() == Qt.LeftButton:
                idx = self._nearest_vertex_idx(sx, sy)
                if idx is not None:
                    self._drag_vertex_idx = idx; self.setCursor(Qt.ClosedHandCursor)
            elif event.button() == Qt.RightButton:
                self._pan_anchor = (sx, sy, self.center_x, self.center_y)
            return

        if event.button() == Qt.LeftButton:
            self._pan_anchor = (sx, sy, self.center_x, self.center_y)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        sx, sy = float(event.position().x()), float(event.position().y())
        self._poly_mouse_screen = (sx, sy)
        self._ruler_mouse = (sx, sy)

        if self._poly_tool == PolyTool.ELEV_POINT:
            # Mostrar cota bajo cursor en tiempo real
            rx, ry = self._s2r(sx, sy)
            r = self._dem_renderer
            if r and hasattr(r, "elevation_at"):
                self._cursor_elev = r.elevation_at(rx, ry)
            self.update(); return

        if self._poly_tool == PolyTool.RULER:
            self.update(); return

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
        p = event.position(); self._zoom_at(factor, int(p.x()), int(p.y()))

    def keyPressEvent(self, event) -> None:
        k = event.key()
        if k == Qt.Key_Escape:
            if self._poly_tool in (PolyTool.ELEV_POINT, PolyTool.RULER):
                self._poly_tool = PolyTool.IDLE; self.poly_tool_changed.emit(0)
                self.setCursor(Qt.ArrowCursor); self.update()
            else:
                self.clear_polygon()
            return
        if self._poly_tool == PolyTool.CURSOR and self._poly_closed:
            if k == Qt.Key_T: self._insert_vertex_at_cursor(self._poly_mouse_screen); return
            if k == Qt.Key_R: self._remove_nearest_vertex(self._poly_mouse_screen); return
            if k in (Qt.Key_Return, Qt.Key_Enter): self._commit_polygon(); return
        super().keyPressEvent(event)

    # ── Coordenadas ───────────────────────────────────────────────────────────

    def _s2r(self, sx, sy):
        i = self._render_info
        return (i["x0"] + (sx - i["off_x"]) / i["scale"],
                i["y0"] + (sy - i["off_y"]) / i["scale"])

    def _r2s(self, rx, ry):
        i = self._render_info
        return (i["off_x"] + (rx - i["x0"]) * i["scale"],
                i["off_y"] + (ry - i["y0"]) * i["scale"])

    # ── Lógica polígono ───────────────────────────────────────────────────────

    def _should_close(self, sx, sy) -> bool:
        if len(self._poly_verts_raster) < 3: return False
        fsx, fsy = self._r2s(*self._poly_verts_raster[0])
        return math.hypot(sx - fsx, sy - fsy) <= self.CLOSE_DIST_PX

    def _nearest_vertex_idx(self, sx, sy) -> int | None:
        if not self._poly_verts_raster: return None
        best_i, best_d = 0, float("inf")
        for i, (rx, ry) in enumerate(self._poly_verts_raster):
            vsx, vsy = self._r2s(rx, ry)
            d = math.hypot(sx - vsx, sy - vsy)
            if d < best_d: best_d, best_i = d, i
        return best_i if best_d <= self.VERTEX_HIT_PX else None

    def _insert_vertex_at_cursor(self, ms) -> None:
        v = self._poly_verts_raster
        if len(v) < 2: return
        mx_r, my_r = self._s2r(*ms)
        best_dist, best_idx, best_pt = float("inf"), 0, (mx_r, my_r)
        for i in range(len(v)):
            a, b = v[i], v[(i + 1) % len(v)]
            dx, dy = b[0] - a[0], b[1] - a[1]; s2 = dx * dx + dy * dy
            if s2 < 1e-12: continue
            t = max(0.0, min(1.0, ((mx_r - a[0]) * dx + (my_r - a[1]) * dy) / s2))
            px, py = a[0] + t * dx, a[1] + t * dy
            d2 = (mx_r - px) ** 2 + (my_r - py) ** 2
            if d2 < best_dist: best_dist, best_idx, best_pt = d2, i, (px, py)
        v.insert(best_idx + 1, best_pt); self.update()

    def _remove_nearest_vertex(self, ms) -> None:
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
            self.clear_polygon()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error al convertir polígono", str(e))

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

        if self._poly_closed and n >= 3:
            p.setBrush(QColor(255, 200, 50, 45)); p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([QPointF(sx, sy) for sx, sy in vs]))

        edge_pen = QPen(QColor(255, 180, 0), 2); edge_pen.setCosmetic(True)
        p.setPen(edge_pen); p.setBrush(Qt.NoBrush)
        for i in range(n - 1):
            p.drawLine(QPointF(*vs[i]), QPointF(*vs[i + 1]))
        if self._poly_closed and n >= 2:
            p.drawLine(QPointF(*vs[-1]), QPointF(*vs[0]))

        if self._poly_tool == PolyTool.DRAWING and n >= 1:
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
            self._draw_hint(p, "  Clic = agregar vértice   Clic en inicio = cerrar   Esc = cancelar  ")

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

        if self._poly_tool == PolyTool.CURSOR and self._poly_closed:
            self._draw_hint(p, "  Arrastrar = mover   T = insertar   R = quitar   Enter = confirmar   Esc = cancelar  ")

    # ── Overlay: cotas ────────────────────────────────────────────────────────

    def _draw_elev_overlay(self, p: QPainter) -> None:
        """Dibuja los puntos de cota medidos y la cota bajo el cursor."""
        # Badge de cota en cursor
        if self._poly_tool == PolyTool.ELEV_POINT and self._cursor_elev is not None:
            mx, my = self._poly_mouse_screen
            text = f"  {self._cursor_elev:.3f} m  "
            p.setPen(QColor(255, 255, 255))
            p.fillRect(int(mx) + 10, int(my) - 20, 100, 18, QColor(0, 0, 0, 170))
            p.drawText(int(mx) + 12, int(my) - 6, text)

        # Puntos registrados
        for rx, ry, elev in self._elev_points:
            sx, sy = self._r2s(rx, ry)
            p.setPen(QPen(QColor(0, 220, 180), 2)); p.setBrush(QColor(0, 220, 180, 200))
            p.drawEllipse(QPointF(sx, sy), 5.0, 5.0)
            label = f" {elev:.3f} m"
            p.fillRect(int(sx) + 7, int(sy) - 16, 90, 16, QColor(0, 0, 0, 150))
            p.setPen(QColor(0, 255, 200)); p.drawText(int(sx) + 8, int(sy) - 4, label)

        if self._poly_tool == PolyTool.ELEV_POINT:
            hint = "  Clic = medir cota   Esc = salir  "
            if self._elev_points:
                hint = f"  {len(self._elev_points)} punto(s) medido(s)   Esc = salir  "
            self._draw_hint(p, hint)

    # ── Overlay: regla ────────────────────────────────────────────────────────

    def _draw_ruler_overlay(self, p: QPainter) -> None:
        """Dibuja la regla de distancia (dos clics)."""
        if self._ruler_p1 is None: return
        sx1, sy1 = self._r2s(*self._ruler_p1)

        # Línea hasta el segundo punto o hasta el cursor
        if self._ruler_p2 is not None:
            sx2, sy2 = self._r2s(*self._ruler_p2)
        else:
            sx2, sy2 = self._ruler_mouse

        pen = QPen(QColor(255, 220, 0), 2, Qt.DashLine); pen.setCosmetic(True)
        p.setPen(pen); p.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))
        p.setPen(QPen(QColor(255, 220, 0), 2)); p.setBrush(QColor(255, 220, 0, 220))
        p.drawEllipse(QPointF(sx1, sy1), 5.0, 5.0)

        # Calcular distancia en metros si hay renderer con transform
        r = self._dem_renderer
        if r and hasattr(r, "cell_size_m"):
            cw, ch = r.cell_size_m
            rx2, ry2 = self._s2r(sx2, sy2) if self._ruler_p2 is None else self._ruler_p2
            dx_m = (rx2 - self._ruler_p1[0]) * cw
            dy_m = (ry2 - self._ruler_p1[1]) * ch
            dist = math.hypot(dx_m, dy_m)
            label = f"  {dist:,.1f} m  " if dist < 10_000 else f"  {dist/1000:.3f} km  "
            mx_lbl = int((sx1 + sx2) / 2); my_lbl = int((sy1 + sy2) / 2)
            p.fillRect(mx_lbl - 4, my_lbl - 16, 100, 16, QColor(0, 0, 0, 160))
            p.setPen(QColor(255, 240, 0)); p.drawText(mx_lbl, my_lbl - 4, label)

        if self._ruler_p2 is None:
            self._draw_hint(p, "  Clic = fijar segundo punto   Esc = cancelar  ")
        else:
            p.setPen(QPen(QColor(255, 220, 0), 2)); p.setBrush(QColor(255, 220, 0, 220))
            p.drawEllipse(QPointF(sx2, sy2), 5.0, 5.0)
            self._draw_hint(p, "  Esc = limpiar regla  ")

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
        base   = max(min(cw / self.renderer.width, ch / self.renderer.height), 1e-9)
        sc_new = base * new_zoom; win_w, win_h = cw / sc_new, ch / sc_new
        new_x0 = max(0.0, min(rx - (mx - off_x) / sc_new, self.renderer.width  - win_w))
        new_y0 = max(0.0, min(ry - (my - off_y) / sc_new, self.renderer.height - win_h))
        self.zoom = new_zoom; self.center_x = new_x0 + win_w / 2; self.center_y = new_y0 + win_h / 2
        self._render_fast(); self._schedule_hq()


# ─────────────────────────────────────────────────────────────────────────────
# Panel de historial
# ─────────────────────────────────────────────────────────────────────────────

class HistoryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 4, 0, 0); root.setSpacing(0)
        bar = QWidget(); bar.setStyleSheet("background: transparent;")
        bl  = QHBoxLayout(bar); bl.setContentsMargins(2, 0, 0, 0); bl.setSpacing(3)
        self._btn_group = QButtonGroup(self); self._btn_group.setExclusive(True)
        for label, idx in [("📋  Mediciones", 0), ("🗺  DEMs", 1)]:
            btn = QPushButton(label); btn.setCheckable(True); btn.setObjectName("histTab")
            self._btn_group.addButton(btn, idx); bl.addWidget(btn)
        bl.addStretch(); self._btn_group.button(0).setChecked(True)
        root.addWidget(bar)
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFixedHeight(1)
        root.addWidget(sep)
        self._stack = QStackedWidget(); root.addWidget(self._stack)
        self.tbl_mediciones = self._make_table([
            "Fecha", "Operador", "Cota Sal (m)", "Cota Agua (m)",
            "Vol. Sal (m³)", "Vol. Salmuera (m³)", "Área Espejo (m²)", "Notas",
        ])
        self.tbl_dems = self._make_table(["Fecha Carga", "Archivo", "Fecha Vuelo", "Cargado por"])
        self._stack.addWidget(self.tbl_mediciones)
        self._stack.addWidget(self.tbl_dems)
        self._btn_group.idClicked.connect(self._stack.setCurrentIndex)

    def _make_table(self, headers):
        tbl = QTableWidget(0, len(headers)); tbl.setHorizontalHeaderLabels(headers)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setAlternatingRowColors(True); tbl.setShowGrid(True)
        return tbl

    def _make_placeholder(self, msg):
        w = QWidget()
        lbl = QLabel(msg); lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font: italic 10pt 'Segoe UI';")
        QVBoxLayout(w).addWidget(lbl); return w

    def load_reservorio(self, codigo: str) -> None:
        self.tbl_mediciones.setRowCount(0); self.tbl_dems.setRowCount(0)
        if not _DB_AVAILABLE: return
        try:
            with get_session() as session:
                repo = Repository(session); res = repo.get_reservorio_by_codigo(codigo)
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
# Ventana principal
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self, user_id=None, user_uid=None, user_nombre="", user_username="", user_rol="operador"):
        super().__init__()
        self._user_id  = user_id   # int | None — SQLite shadow id (FKs cubicaciones)
        self._user_uid = user_uid  # str | None — Firebase UID
        self._user_nombre = user_nombre
        self._user_username = user_username; self._user_rol = user_rol
        self.dem_path = None
        self.latest_result: PondVolumes | None = None
        self.latest_rows: list = []
        self.current_reservorio_codigo: str | None = None
        self._current_dem_id: int | None = None
        self._prefs = _load_prefs()

        user_str = user_nombre or user_username or "sin sesión"
        self.setWindowTitle(f"{_APP_NAME}  ·  {user_str}")
        if _ICON_PATH.exists():
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(str(_ICON_PATH)))
        self.setDockOptions(
            QMainWindow.AnimatedDocks |
            QMainWindow.AllowTabbedDocks |
            QMainWindow.AllowNestedDocks
        )
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)
        self.setCorner(Qt.BottomLeftCorner,  Qt.LeftDockWidgetArea)

        self._build_central()
        self._build_params_dock()
        self._build_results_dock()
        self._build_history_dock()
        self._build_status_bar()
        self._build_menu_bar()
        self._connect_signals()
        # Layout predeterminado: params arriba, resultados abajo (en columna derecha)
        self.splitDockWidget(self._dock_params, self._dock_results, Qt.Vertical)
        self._on_reservorio_changed(0)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(150, self._apply_default_sizes)

    def _apply_default_sizes(self):
        """Ajusta proporciones 70% canvas / 30% panel derecho.
        Divide la columna derecha: 65% parámetros / 35% resultados.
        """
        w = self.width()
        h = self.height()
        right_w = max(300, int(w * 0.30))
        self.resizeDocks([self._dock_params], [right_w], Qt.Horizontal)
        # Altura: params 65%, resultados 35%
        params_h = max(420, int(h * 0.65))
        results_h = max(220, int(h * 0.35))
        self.resizeDocks(
            [self._dock_params, self._dock_results],
            [params_h, results_h],
            Qt.Vertical
        )

    # ── Central widget ────────────────────────────────────────────────────────

    def _build_central(self):
        # Header bar
        header = QWidget(); header.setFixedHeight(56)
        header.setObjectName("headerBar")
        hl = QHBoxLayout(header); hl.setContentsMargins(18, 8, 18, 8); hl.setSpacing(12)
        lbl_title = QLabel(_APP_NAME)
        lbl_title.setStyleSheet("font: bold 14pt 'Segoe UI'; letter-spacing: 1px;")
        hl.addWidget(lbl_title)
        lbl_sub = QLabel("— Cálculo de volúmenes de pozas")
        lbl_sub.setStyleSheet("font: 10pt 'Segoe UI';")
        hl.addWidget(lbl_sub); hl.addStretch()

        # Viewer toolbar
        toolbar = QWidget()
        toolbar.setObjectName("viewerToolbar")
        tl = QHBoxLayout(toolbar); tl.setContentsMargins(6, 3, 6, 3); tl.setSpacing(4)
        self.btn_cursor_poly = QPushButton("↖  Cursor")
        self.btn_cursor_poly.setCheckable(True); self.btn_cursor_poly.setEnabled(False)
        self.btn_elev_point = QPushButton("📍  Cota")
        self.btn_elev_point.setCheckable(True)
        sep1 = QFrame(); sep1.setFrameShape(QFrame.VLine)
        self.btn_limpiar = QPushButton("🗑  Limpiar")
        tl.addWidget(self.btn_cursor_poly)
        tl.addWidget(self.btn_elev_point)
        tl.addWidget(sep1)
        tl.addWidget(self.btn_limpiar)
        tl.addStretch()

        # DEM viewer
        self.viewer = DemViewerWidget()
        self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        central = QWidget()
        vl = QVBoxLayout(central); vl.setContentsMargins(0, 0, 0, 0); vl.setSpacing(0)
        vl.addWidget(header)
        vl.addWidget(toolbar)
        vl.addWidget(self.viewer, 1)
        self.setCentralWidget(central)

    # ── Dock: Parámetros ──────────────────────────────────────────────────────

    def _build_params_dock(self):
        panel = QWidget(); panel.setMinimumWidth(270)
        vl = QVBoxLayout(panel); vl.setContentsMargins(10, 10, 10, 10); vl.setSpacing(10)

        # Reservorio
        grp_res = QGroupBox("🗺  Reservorio")
        rgl = QVBoxLayout(grp_res); rgl.setContentsMargins(10, 14, 10, 10)
        self.cmb_reservorio = QComboBox()
        self.cmb_reservorio.addItem("— Seleccionar —")
        self.cmb_reservorio.addItems([f"Reservorio {i}" for i in range(1, 11)])
        rgl.addWidget(self.cmb_reservorio)
        vl.addWidget(grp_res)

        # Archivos DEM
        grp_files = QGroupBox("📂  Archivos")
        fgl = QVBoxLayout(grp_files); fgl.setContentsMargins(10, 14, 10, 10); fgl.setSpacing(8)
        self.btn_pick_dem = QPushButton("Cargar DEM…"); self.btn_pick_dem.setObjectName("btnSecondary")
        fgl.addWidget(self.btn_pick_dem)
        self.lbl_paths = QLabel("Sin DEM cargado")
        self.lbl_paths.setWordWrap(True)
        fgl.addWidget(self.lbl_paths)
        vl.addWidget(grp_files)

        # Parámetros de cálculo
        grp_calc = QGroupBox("⚙  Parámetros de cálculo"); grp_calc.setProperty("accent", "true")
        cgl = QFormLayout(grp_calc); cgl.setSpacing(10); cgl.setContentsMargins(10, 14, 10, 12)
        cgl.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.txt_salt  = QLineEdit(); self.txt_salt.setPlaceholderText("ej. 3412.500")
        self.txt_water = QLineEdit(); self.txt_water.setPlaceholderText("ej. 3415.200")
        self.txt_occ   = QLineEdit(); self.txt_occ.setPlaceholderText("0.00 – 1.00")
        cgl.addRow("Cota sal (m):", self.txt_salt)
        cgl.addRow("Cota agua (m):", self.txt_water)
        cgl.addRow("Fracción ocluida:", self.txt_occ)
        vl.addWidget(grp_calc)

        # Acciones
        grp_act = QGroupBox("▶  Acciones")
        agl = QVBoxLayout(grp_act); agl.setContentsMargins(10, 14, 10, 10); agl.setSpacing(6)
        self.btn_calculate = QPushButton("⚡  Calcular volúmenes")
        self.btn_calculate.setObjectName("btnPrimary")
        self.btn_export_sheets = QPushButton("📝  Registrar medición")
        self.btn_export_sheets.setStyleSheet("""
            QPushButton {
                background-color: #38ab73; 
                color: white; 
                font-weight: bold; 
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover { background-color: #0d8a4d; }
            QPushButton:pressed { background-color: #0a693a; }
        """)
        
        self.btn_clear = QPushButton("🗑  Limpiar"); self.btn_clear.setObjectName("btnSecondary")
        
        agl.addWidget(self.btn_calculate)
        agl.addWidget(self.btn_export_sheets)
        agl.addWidget(self.btn_clear)
        vl.addWidget(grp_act)
        vl.addStretch()

        dock = QDockWidget("⚙  Parámetros", self)
        dock.setWidget(panel)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self._dock_params = dock

    # ── Dock: Resultados ──────────────────────────────────────────────────────

    def _build_results_dock(self):
        panel = QWidget(); panel.setMinimumWidth(260); panel.setMinimumHeight(200)
        vl = QVBoxLayout(panel); vl.setContentsMargins(0, 0, 0, 0); vl.setSpacing(0)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Parámetro", "Valor", "Unidad"])
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.setColumnWidth(1, 110); self.tree.setColumnWidth(2, 70)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(False)
        vl.addWidget(self.tree)

        dock = QDockWidget("📊  Resultados", self)
        dock.setWidget(panel)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self._dock_results = dock

    # ── Dock: Historial ───────────────────────────────────────────────────────

    def _build_history_dock(self):
        self.history_panel = HistoryPanel()
        dock = QDockWidget("📋  Historial", self)

        dock.setWidget(self.history_panel)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        dock.hide()  # oculto hasta que se seleccione reservorio
        self._dock_history = dock

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self):
        sb = self.statusBar()
        self._spinner = SpinnerLabel()
        self._status_label = QLabel("Listo")
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedSize(160, 12)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        user_str = self._user_nombre or self._user_username or "sin sesión"
        self._user_badge = QPushButton(f"  👤  {user_str}  ")
        self._user_badge.setObjectName("userBadge")
        self._user_badge.setCursor(Qt.PointingHandCursor)
        self._user_badge.clicked.connect(self._show_account_dialog)
        sb.addWidget(self._spinner, 0)
        sb.addWidget(self._status_label, 1)
        sb.addWidget(self._progress_bar, 0)
        sb.addPermanentWidget(self._user_badge, 0)

    def _set_busy(self, msg: str) -> None:
        self._status_label.setText(msg)
        self._spinner.start()
        self._progress_bar.setRange(0, 0); self._progress_bar.show()
        QApplication.processEvents()

    def _set_idle(self, msg: str = "Listo") -> None:
        self._status_label.setText(msg)
        self._spinner.stop()
        self._progress_bar.setRange(0, 1); self._progress_bar.setValue(1)
        QTimer.singleShot(1200, self._progress_bar.hide)

    # ── Menu bar ──────────────────────────────────────────────────────────────

    def _build_menu_bar(self):
        mb = self.menuBar()
        # Opciones
        menu_opt = mb.addMenu("Opciones")
        act_acct = QAction("👤  Gestión de cuenta", self)
        act_acct.triggered.connect(self._show_account_dialog)
        menu_opt.addAction(act_acct)
        act_pref = QAction("⚙  Preferencias", self)
        act_pref.triggered.connect(self._show_prefs_dialog)
        menu_opt.addAction(act_pref)
        menu_opt.addSeparator()
        act_help = QAction("❓  Ayuda / Manual", self)
        act_help.triggered.connect(self._show_help_dialog)
        menu_opt.addAction(act_help)
        # Admin-only: reset de base de datos
        if self._user_rol == "admin":
            menu_opt.addSeparator()
            act_reset_db = QAction("⚠  Reiniciar base de datos (Admin)", self)
            act_reset_db.triggered.connect(self._reset_database)
            menu_opt.addAction(act_reset_db)
        menu_opt.addSeparator()
        act_quit = QAction("✕  Salir", self)
        act_quit.triggered.connect(self.close)
        menu_opt.addAction(act_quit)

        # Vista
        menu_vista = mb.addMenu("Vista")
        for dock, label in [
            (self._dock_params,   "⚙  Parámetros"),
            (self._dock_results,  "📊  Resultados"),
            (self._dock_history,  "📋  Historial"),
        ]:
            act = dock.toggleViewAction()
            act.setText(f"Mostrar {label}")
            menu_vista.addAction(act)
        menu_vista.addSeparator()
        act_reset = QAction("↺  Restaurar diseño predeterminado", self)
        act_reset.triggered.connect(self._reset_layout)
        menu_vista.addAction(act_reset)

    # ── Señales ───────────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.btn_pick_dem.clicked.connect(self.pick_dem)
        self.btn_export_sheets.clicked.connect(self.register_and_export)
        self.btn_calculate.clicked.connect(self.calculate)
        self.btn_clear.clicked.connect(self.clear_results)
        self.cmb_reservorio.currentIndexChanged.connect(self._on_reservorio_changed)
        self.btn_cursor_poly.toggled.connect(self._on_cursor_poly_toggled)
        self.btn_elev_point.toggled.connect(self._on_elev_point_toggled)
        self.btn_limpiar.clicked.connect(self._on_limpiar)
        self.viewer.polygon_committed.connect(self._on_polygon_committed)
        self.viewer.poly_tool_changed.connect(self._on_viewer_poly_tool_changed)

    def closeEvent(self, event):
        self._audit("logout"); self.viewer.clear(); super().closeEvent(event)

    def _reset_database(self):
        """Admin-only: borra todas las tablas y las recrea desde cero."""
        if self._user_rol != "admin":
            QMessageBox.warning(self, "Acceso denegado", "Solo el administrador puede hacer esta acción."); return
        reply = QMessageBox.warning(
            self, "⚠ Reiniciar base de datos",
            "Esta acción BORRARÁ todos los datos (usuarios, mediciones, DEMs).\n\n"
            "Se creará un usuario admin por defecto (admin / Admin123!).\n\n"
            "¿Confirmas el reinicio?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes: return
        if not _DB_AVAILABLE:
            QMessageBox.critical(self, "DB", "Base de datos no disponible."); return
        try:
            from .db.engine import engine
            from .db.models import Base
            from .db.seed import seed_database
            Base.metadata.drop_all(engine)
            Base.metadata.create_all(engine)
            with get_session() as s:
                seed_database(s)
            QMessageBox.information(self, "Base de datos reiniciada",
                                    "La base de datos fue reiniciada correctamente.\n"
                                    "Usuario por defecto: admin / Admin123!")
            self.history_panel.clear()
        except Exception as e:
            QMessageBox.critical(self, "Error al reiniciar DB", str(e))

    # ── Handlers polígono ─────────────────────────────────────────────────────

    def _on_cursor_poly_toggled(self, checked: bool):
        if checked:
            if not self.viewer._poly_closed:
                self.btn_cursor_poly.blockSignals(True); self.btn_cursor_poly.setChecked(False); self.btn_cursor_poly.blockSignals(False)
                return
            self.viewer.set_poly_tool(PolyTool.CURSOR); self.viewer.setFocus()
        else:
            if self.viewer._poly_tool == PolyTool.CURSOR: self.viewer.clear_polygon()

    def _on_viewer_poly_tool_changed(self, tool_int: int):
        tool = PolyTool(tool_int)
        for btn in (self.btn_cursor_poly, self.btn_elev_point): btn.blockSignals(True)
        self.btn_cursor_poly.setChecked(tool == PolyTool.CURSOR)
        self.btn_elev_point.setChecked(tool == PolyTool.ELEV_POINT)
        self.btn_cursor_poly.setEnabled(self.viewer._poly_closed)
        for btn in (self.btn_cursor_poly, self.btn_elev_point): btn.blockSignals(False)

    def _on_elev_point_toggled(self, checked: bool):
        if checked:
            self.btn_cursor_poly.blockSignals(True); self.btn_cursor_poly.setChecked(False); self.btn_cursor_poly.blockSignals(False)
            self.btn_cursor_poly.setEnabled(False)
            self.viewer.set_poly_tool(PolyTool.ELEV_POINT); self.viewer.setFocus()
        else:
            if self.viewer._poly_tool == PolyTool.ELEV_POINT:
                self.viewer._poly_tool = PolyTool.IDLE
                self.viewer.poly_tool_changed.emit(0); self.viewer.update()

    def _on_limpiar(self):
        """Limpia puntos de cota y polígono cursor del visor."""
        self.viewer.clear_canvas()
        for b in (self.btn_cursor_poly, self.btn_elev_point):
            b.blockSignals(True); b.setChecked(False); b.blockSignals(False)
        self.btn_cursor_poly.setEnabled(False)

    def _on_polygon_committed(self, shapes: list):
        data_dir = self._dems_dir()
        try: data_dir.mkdir(parents=True, exist_ok=True)
        except Exception: data_dir = Path(__file__).parent.parent
        n = self.current_reservorio_codigo or "X"
        out = data_dir / f"poligono_dibujado_{n}.geojson"
        doc = {"type": "FeatureCollection",
               "features": [{"type": "Feature", "geometry": s, "properties": {}} for s in shapes]}
        try:
            out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "Polígono", f"No se pudo guardar:\n{e}"); return
        self.btn_cursor_poly.setEnabled(False)
        QMessageBox.information(self, "Polígono guardado",
                                f"Guardado como:\n{out.name}")

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _set_paths_label(self):
        dem = Path(self.dem_path).name if self.dem_path else "(sin DEM)"
        self.lbl_paths.setText(f"DEM: {dem}")

    def _get_float(self, s: str, name: str) -> float:
        try: return float((s or "").strip().replace(",", "."))
        except ValueError: raise ValueError(f"{name} debe ser numérico.")

    def _dems_dir(self) -> Path:
        return (Path(sys.executable).parent if getattr(sys, "frozen", False)
                else Path(__file__).parent.parent) / "DEMs"

    def _audit(self, accion: str, detalle: dict | None = None):
        # SQLite local audit
        if _DB_AVAILABLE and self._user_id is not None:
            try:
                with get_session() as s:
                    repo = Repository(s)
                    repo.log(accion, usuario=repo.get_user_by_id(self._user_id), detalle=detalle)
            except Exception: pass
        # Firestore activity log
        if _FB_AVAILABLE and self._user_uid:
            firebase_sync.log_activity_async(self._user_uid, accion, detalle)

    def _reset_layout(self):
        # Restaurar params y results en la columna derecha (apilados verticalmente)
        for dock in (self._dock_params, self._dock_results, self._dock_history):
            dock.setFloating(False)
        self.addDockWidget(Qt.RightDockWidgetArea, self._dock_params)
        self.addDockWidget(Qt.RightDockWidgetArea, self._dock_results)
        self.splitDockWidget(self._dock_params, self._dock_results, Qt.Vertical)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._dock_history)
        self._dock_params.show(); self._dock_results.show()
        self._dock_history.hide()
        QTimer.singleShot(150, self._apply_default_sizes)

    # ── Diálogos ──────────────────────────────────────────────────────────────

    def _show_account_dialog(self):
        dlg = AccountDialog(self._user_nombre, self._user_username,
                            user_rol=self._user_rol, user_id=self._user_id,
                            parent=self)
        dlg.exec()

    def _show_prefs_dialog(self):
        dlg = PreferencesDialog(self)
        if dlg.exec(): self._prefs = _load_prefs()

    def _show_help_dialog(self):
        HelpDialog(self).exec()

    # ── Cambio de reservorio ──────────────────────────────────────────────────

    def _on_reservorio_changed(self, index: int):
        if index <= 0:
            self.current_reservorio_codigo = self._current_dem_id = self.dem_path = None
            self.viewer.clear(); self.history_panel.clear()
            self._dock_history.hide(); self.lbl_paths.setText("Sin DEM cargado"); return
        self.current_reservorio_codigo = f"R{index}"; self._current_dem_id = None
        dem_file = self._dems_dir() / f"MDE_R{index}.tif"
        if dem_file.exists():
            self.dem_path = str(dem_file)
            self._set_busy(f"Cargando DEM R{index}…")
            try:
                r = DemRenderer(self.dem_path, scale_mode="minmax", stats_sample=1024)
                self.viewer.set_dem_renderer(r); self.viewer._reset_view(r)
                self._set_idle(f"DEM R{index} cargado")
            except Exception as e:
                QMessageBox.critical(self, "DEM", f"No se pudo cargar DEM:\n{e}")
                self.dem_path = None; self.viewer.clear(); self._set_idle("Error al cargar DEM")
        else:
            self.dem_path = None; self.viewer.clear()
        self._autoload_last_cotas(self.current_reservorio_codigo)
        self.history_panel.load_reservorio(self.current_reservorio_codigo)
        self._dock_history.show(); self._set_paths_label()

    def _autoload_last_cotas(self, codigo: str):
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

    def pick_dem(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecciona el DEM", "",
                                              "GeoTIFF (*.tif *.tiff);;Todos (*.*)")
        if not path: return

        # ── Diálogo de metadatos del DEM ──────────────────────────────────
        meta_dlg = QDialog(self)
        meta_dlg.setWindowTitle("Metadatos del DEM")
        meta_dlg.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        meta_dlg.setMinimumWidth(380)
        mdl = QVBoxLayout(meta_dlg); mdl.setContentsMargins(20, 16, 20, 16); mdl.setSpacing(10)
        mdl.addWidget(QLabel(f"<b>{Path(path).name}</b>"))
        mform = QFormLayout(); mform.setSpacing(8); mform.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        txt_fecha  = QLineEdit(); txt_fecha.setPlaceholderText("YYYY-MM-DD  (opcional)")
        txt_drone  = QLineEdit(); txt_drone.setPlaceholderText("Marca / modelo  (opcional)")
        txt_carpeta = QLineEdit(); txt_carpeta.setPlaceholderText("Ruta o URL de la carpeta de datos  (opcional)")
        mform.addRow("Fecha de vuelo:", txt_fecha)
        mform.addRow("Drone:", txt_drone)
        mform.addRow("Carpeta de datos:", txt_carpeta)
        mdl.addLayout(mform)
        mrow = QHBoxLayout()
        btn_ok  = QPushButton("Continuar"); btn_ok.setObjectName("btnPrimary"); btn_ok.setDefault(True)
        btn_skip = QPushButton("Omitir"); btn_skip.setObjectName("btnSecondary")
        btn_ok.clicked.connect(meta_dlg.accept); btn_skip.clicked.connect(meta_dlg.accept)
        mrow.addStretch(); mrow.addWidget(btn_skip); mrow.addWidget(btn_ok)
        mdl.addLayout(mrow)
        meta_dlg.exec()

        fecha_vuelo  = txt_fecha.text().strip()  or None
        drone        = txt_drone.text().strip()   or None
        carpeta_datos = txt_carpeta.text().strip() or None

        # ── Cargar DEM en el visor ────────────────────────────────────────
        self.dem_path = path
        self._set_busy("Cargando DEM…")
        try:
            r = DemRenderer(path, scale_mode="minmax", stats_sample=1024)
            self.viewer.set_dem_renderer(r); self.viewer._reset_view(r)
            self._set_idle(f"DEM cargado: {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "DEM", f"No se pudo cargar DEM:\n{e}")
            self._set_idle("Error al cargar DEM"); self._set_paths_label(); return

        # ── Registrar en SQLite ───────────────────────────────────────────
        dem_id_local: int | None = None
        if _DB_AVAILABLE and self.current_reservorio_codigo:
            try:
                with get_session() as s:
                    repo = Repository(s); rv = repo.get_reservorio_by_codigo(self.current_reservorio_codigo)
                    if rv:
                        dem_obj = repo.register_dem(
                            reservorio_id=rv.id, archivo=Path(path).name,
                            ruta=path, usuario_id=self._user_id,
                            fecha_vuelo=fecha_vuelo, drone=drone, carpeta_datos=carpeta_datos,
                        )
                        dem_id_local = dem_obj.id
                        self._current_dem_id = dem_id_local
                        repo.update_reservorio_defaults(rv.id, dem_path=path)
                        repo.log("dem_cargado", usuario=repo.get_user_by_id(self._user_id) if self._user_id else None,
                                 detalle={"reservorio": self.current_reservorio_codigo,
                                          "archivo": Path(path).name,
                                          "fecha_vuelo": fecha_vuelo, "drone": drone})
                        self.history_panel.load_reservorio(self.current_reservorio_codigo)
            except Exception: pass

        # ── Registrar metadatos en Firestore ──────────────────────────────
        if _FB_AVAILABLE and self.current_reservorio_codigo:
            firebase_sync.upload_dem_metadata_async(
                reservorio_codigo=self.current_reservorio_codigo,
                dem_id=dem_id_local or 0,
                archivo=Path(path).name,
                uid=self._user_uid or "local",
                fecha_vuelo=fecha_vuelo, drone=drone, carpeta_datos=carpeta_datos,
            )
        # Firestore audit
        self._audit("dem_cargado", detalle={
            "reservorio": self.current_reservorio_codigo,
            "archivo": Path(path).name, "fecha_vuelo": fecha_vuelo, "drone": drone,
        })
        self._set_paths_label()

    # ── Cálculo ───────────────────────────────────────────────────────────────

    def calculate(self):
        if not self.dem_path:
            QMessageBox.critical(self, "Falta DEM", "Selecciona un DEM primero."); return
        try:
            salt  = self._get_float(self.txt_salt.text(),  "Cota de sal")
            water = self._get_float(self.txt_water.text(), "Cota pelo de agua")
            occ   = self._get_float(self.txt_occ.text(),   "Fracción ocluida")
            if not (0.0 <= occ <= 1.0): raise ValueError("Fracción ocluida debe estar entre 0 y 1.")
        except ValueError as e:
            QMessageBox.critical(self, "Parámetros", str(e)); return
        self._set_busy("Calculando volúmenes…")
        try:
            res = PondVolumeCalculator(DemRaster(self.dem_path).load()).compute(
                salt, water, occluded_fraction=occ)
            self.latest_result = res; self.latest_rows = res.to_rows()
            self._populate_table(self.latest_rows)
            self._dock_results.show()
            # Habilitar botón de registro explícito
            self.btn_export_sheets.setEnabled(True)
            warns = []
            if res.salt_level  < res.dem_min or res.salt_level  > res.dem_max:
                warns.append(f"  • Cota sal ({res.salt_level:.2f} m) fuera del rango DEM.")
            if res.water_level < res.dem_min or res.water_level > res.dem_max:
                warns.append(f"  • Cota agua ({res.water_level:.2f} m) fuera del rango DEM.")
            if warns:
                QMessageBox.warning(self, "Advertencia de rango",
                                    f"DEM [{res.dem_min:.2f}–{res.dem_max:.2f} m]:\n\n"
                                    + "\n".join(warns) + "\n\nEl cálculo se realizó de todas formas.")
            self._set_idle(f"Cálculo completado  ·  Vol. salmuera: {fmt(res.brine_total_m3, 1)} m³")
        except DemError as e:
            QMessageBox.critical(self, "Error", str(e)); self._set_idle("Error en cálculo")
        except Exception as e:
            QMessageBox.critical(self, "Error inesperado", str(e)); self._set_idle("Error")

    def _save_cubicacion(self, res: PondVolumes):
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
        except Exception: pass
        if _FB_AVAILABLE and self.current_reservorio_codigo:
            dem_filename = Path(self.dem_path).name if self.dem_path else None
            firebase_sync.upload_cubicacion_history_async(
                self.current_reservorio_codigo,
                datos={
                    "cota_sal": res.salt_level, "cota_agua": res.water_level,
                    "fraccion_ocluida": res.occluded_fraction,
                    "vol_sal_m3": res.salt_total_m3,
                    "vol_salmuera_libre_m3": res.brine_free_m3,
                    "vol_salmuera_ocluida_m3": res.brine_occluded_m3,
                    "vol_salmuera_total_m3": res.brine_total_m3,
                    "area_espejo_m2": res.area_wet_m2,
                    "usuario": self._user_username,
                    "dem_id_local": self._current_dem_id,
                },
                dem_filename=dem_filename,
                uid=self._user_uid or "local",
                on_success=lambda _: self._set_idle("Cubicación sincronizada con la nube ☁"),
            )

    def _register_medicion(self):
        """Guarda explícitamente el resultado calculado en el historial (DB + Firebase)."""
        if not self.latest_result:
            QMessageBox.information(self, "Registrar", "Primero calcula los volúmenes."); return False
        self._set_busy("Registrando medición…")
        self._save_cubicacion(self.latest_result)
        self.btn_export_sheets.setEnabled(False)  # evitar doble registro
        self._set_idle("Medición registrada en el historial ✓")
        return True

    def register_and_export(self):
        if self._register_medicion():
            self.export_google_sheets()

    def _populate_table(self, rows):
        self.tree.clear()
        for item, value, unit in rows:
            v = fmt(value, 3) if unit in ("m³","m²","kL","ML") else fmt(value, 2) if unit in ("m","-") else str(value)
            self.tree.addTopLevelItem(QTreeWidgetItem([item, v, unit]))
        self.tree.resizeColumnToContents(0)

    def export_csv(self):
        if not self.latest_rows:
            QMessageBox.information(self, "Exportar", "Primero calcula resultados."); return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar CSV", default_output_name(), "CSV (*.csv)")
        if not path: return
        try:
            open_file_default_app(export_rows_to_csv(path, self.latest_rows))
            self._audit("csv_exportado", detalle={"reservorio": self.current_reservorio_codigo,
                                                  "archivo": Path(path).name})
            self._set_idle(f"CSV exportado: {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Exportar CSV", str(e))

    def export_google_sheets(self) -> None:
        if not self.latest_rows:
            QMessageBox.information(self, "Exportar", "Primero calcula resultados."); return
            
        import os
        from datetime import datetime
        import json
        
        # Usar SIEMPRE el credentials.json del proyecto para evitar credenciales equivocadas
        base_dir = Path(__file__).parent.parent
        local_cred = base_dir / "credentials.json"
        if not local_cred.exists():
            QMessageBox.warning(
                self,
                "Credenciales faltantes",
                "No se encontró 'credentials.json' en la carpeta del proyecto.\n\n"
                "Coloca tu archivo JSON de Service Account en la carpeta raíz con el nombre exacto 'credentials.json'."
            )
            return

        # Sobrescribir variable de entorno por si el usuario tenía otra configurada
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(local_cred)

        # Leer email de la Service Account (sin mostrar claves)
        service_account_email = None
        try:
            data = json.loads(local_cred.read_text(encoding="utf-8"))
            service_account_email = data.get("client_email")
        except Exception:
            service_account_email = None

        codigo = self.current_reservorio_codigo or "SIN_RESERVORIO"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fecha_legible = datetime.now().strftime("%Y-%m-%d %H:%M")
        sheet_title = f"Resultados_{codigo}_{ts}"

        # Filas de metadatos que se anteponen a los resultados
        operador = self._user_nombre or self._user_username or "sin sesión"
        meta_rows = [
            ("Fecha",     fecha_legible, ""),
            ("Operador",  operador,      ""),
            ("Reservorio", codigo,       ""),
        ]
        
        # Aplicamos exactamente el mismo formato visual de la tabla
        formatted_rows = []
        for item, value, unit in self.latest_rows:
            v = fmt(value, 3) if unit in ("m³","m²","kL","ML") else fmt(value, 2) if unit in ("m","-") else str(value)
            formatted_rows.append((item, v, unit))

        rows_to_export = meta_rows + formatted_rows

        self._set_busy("Exportando a Google Sheets...")
        QApplication.processEvents()

        try:
            res = export_rows_to_google_sheets(
                GOOGLE_SHEETS_SPREADSHEET_ID,
                rows_to_export,
                sheet_title=sheet_title,
                credentials_path=str(local_cred),
            )

            self._audit(
                "gsheets_exportado",
                detalle={
                    "reservorio": self.current_reservorio_codigo,
                    "spreadsheet_id": GOOGLE_SHEETS_SPREADSHEET_ID,
                    "worksheet": res.get("worksheet_title"),
                },
            )

            self._set_idle(f"Exportado a Sheets: {res.get('worksheet_title')}")
            
            QMessageBox.information(
                self,
                "Google Sheets",
                "Exportación completada.\n\n"
                f"Hoja creada/actualizada: {res.get('worksheet_title')}\n"
            )

        except Exception as e:
            self._set_idle("Error en exportación")
            extra = ""
            if service_account_email:
                extra += (
                    "\n\nImportante: comparte el Spreadsheet como *Editor* con esta cuenta de servicio:\n"
                    f"{service_account_email}"
                )
            QMessageBox.critical(
                self,
                "Exportar a Google Sheets",
                f"Error al exportar:\n{str(e) or repr(e)}\n\n"
                "Verifica permisos de edición, que la API de Google Sheets esté habilitada en el proyecto, "
                "y que las credenciales sean válidas."
                + extra
            )

    def clear_results(self):
        self.latest_result = None; self.latest_rows = []; self.tree.clear()
        self._set_idle("Resultados borrados")


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(_APP_NAME)
    if _ICON_PATH.exists():
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(str(_ICON_PATH)))
    # Aplicar tema guardado antes de mostrar cualquier ventana
    prefs = _load_prefs()
    _apply_theme(app, prefs.get("theme", "predeterminado"), prefs.get("custom_colors") or None)
    if _DB_AVAILABLE or _FB_AUTH_AVAILABLE:
        dlg = LoginDialog()
        dlg.setWindowTitle(f"{_APP_NAME} — Inicio de sesión")
        if dlg.exec() != QDialog.Accepted: sys.exit(0)
        win = MainWindow(
            user_id=dlg.user_id, user_uid=dlg.user_uid,
            user_nombre=dlg.user_nombre,
            user_username=dlg.user_username, user_rol=dlg.user_rol,
        )
    else:
        win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())
