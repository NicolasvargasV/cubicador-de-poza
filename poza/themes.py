"""
poza/themes.py
──────────────
Sistema centralizado de temas visuales para V-Metric.
Todos los colores de la interfaz se generan desde ThemeTokens.

Uso básico:
    from .themes import THEME_CLARO, THEMES, build_qss, get_theme_by_name

    # Aplicar tema global
    app.setStyleSheet(build_qss(THEME_CLARO))

    # El login SIEMPRE usa Claro (fijado por marca)
    login_dlg.setStyleSheet(build_qss(THEME_CLARO))

    # Obtener tema por nombre (incluyendo personalizado)
    tokens = get_theme_by_name("oscuro")
    tokens = get_theme_by_name("custom", custom_colors={"primary": "#8B0000"})

Agregar un nuevo tema:
    1. Crear instancia ThemeTokens
    2. Añadir al dict THEMES
    3. Listo — el sistema lo distribuirá automáticamente.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict, fields
from typing import Dict, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Estructura de tokens
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ThemeTokens:
    """
    Todos los tokens de color que consume build_qss().
    Cambiar estos valores cambia el 100% del aspecto visual de la app.
    """
    name: str = "Claro"

    # ── Fondos ────────────────────────────────────────────────────────────────
    bg_base:       str = "#F6F6F6"   # Ventana principal
    bg_secondary:  str = "#EAECF4"   # Paneles, dock, toolbar
    bg_surface:    str = "#FFFFFF"   # Cards, groupboxes, diálogos
    bg_input:      str = "#F7F8FC"   # LineEdit, ComboBox
    bg_header_a:   str = "#1A2052"   # Gradiente header inicio
    bg_header_b:   str = "#3D4A9A"   # Gradiente header fin
    bg_status:     str = "#EAECF4"   # Status bar

    # ── Texto ─────────────────────────────────────────────────────────────────
    text_base:        str = "#333333"   # Texto principal
    text_muted:       str = "#808B96"   # Texto secundario / ayuda
    text_disabled:    str = "#AAAAAA"   # Deshabilitado
    text_on_primary:  str = "#FFFFFF"   # Texto sobre color primario
    text_placeholder: str = "#B0B5C8"   # Placeholder inputs
    text_header:      str = "#FFFFFF"   # Texto en header bar

    # ── Bordes ────────────────────────────────────────────────────────────────
    border_main:   str = "#C8CBE0"   # Borde estándar
    border_light:  str = "#E0E3F0"   # Borde suave
    border_focus:  str = "#29306A"   # Anillo de foco

    # ── Colores de marca ──────────────────────────────────────────────────────
    primary:        str = "#29306A"   # Color corporativo principal
    primary_dark:   str = "#1A2052"   # Variante oscura
    primary_light:  str = "#3D4A9A"   # Variante clara
    secondary:      str = "#808B96"   # Color secundario
    accent_pos:     str = "#35F2A0"   # Positivo / confirmación
    accent_pos_d:   str = "#1DC880"   # Variante oscura positivo
    accent_warn:    str = "#F75C03"   # Advertencia / acción
    accent_warn_d:  str = "#D44800"   # Variante oscura advertencia

    # ── Botón base ────────────────────────────────────────────────────────────
    btn_bg:        str = "#F0F2FA"
    btn_text:      str = "#29306A"
    btn_border:    str = "#C8CBE0"
    btn_hover_bg:  str = "#E0E4F0"
    btn_hover_brd: str = "#29306A"
    btn_checked_bg:   str = "#29306A"
    btn_checked_text: str = "#FFFFFF"
    btn_pressed_bg:   str = "#F75C03"
    btn_pressed_text: str = "#FFFFFF"
    btn_dis_bg:    str = "#F0F0F4"
    btn_dis_text:  str = "#AAAAAA"
    btn_dis_brd:   str = "#E0E0E8"

    # ── Botón primario (Calcular, Guardar, Acceder) ───────────────────────────
    btn_pri_bg:       str = "#29306A"
    btn_pri_bg2:      str = "#3D4A9A"
    btn_pri_text:     str = "#FFFFFF"
    btn_pri_hov_bg:   str = "#3D4A9A"
    btn_pri_hov_bg2:  str = "#4A58B8"
    btn_pri_prs_bg:   str = "#F75C03"
    btn_pri_dis_bg:   str = "#9BA3C8"

    # ── Botón acento (Registrar medición) ─────────────────────────────────────
    btn_acc_bg:     str = "#C04500"
    btn_acc_bg2:    str = "#E05A00"
    btn_acc_text:   str = "#FFFFFF"
    btn_acc_hov:    str = "#F75C03"
    btn_acc_prs:    str = "#D44000"
    btn_acc_dis_bg: str = "#DDB8A0"

    # ── Tablas y árboles ──────────────────────────────────────────────────────
    tbl_bg:          str = "#FAFBFF"
    tbl_alt:         str = "#F0F2FA"
    tbl_grid:        str = "#E8EAF6"
    tbl_hdr_bg:      str = "#29306A"
    tbl_hdr_bg2:     str = "#3D4A9A"
    tbl_hdr_text:    str = "#FFFFFF"
    tbl_sel_bg:      str = "#29306A"
    tbl_sel_text:    str = "#FFFFFF"
    tbl_hover_bg:    str = "#E4E8F4"
    tbl_hover_text:  str = "#29306A"

    # ── Dock widgets ──────────────────────────────────────────────────────────
    dock_hdr_a:     str = "#1A2052"
    dock_hdr_b:     str = "#29306A"
    dock_hdr_brd:   str = "#F75C03"
    dock_hdr_text:  str = "#FFFFFF"

    # ── Menú ──────────────────────────────────────────────────────────────────
    menu_bar_bg:     str = "#29306A"
    menu_bar_text:   str = "#FFFFFF"
    menu_bg:         str = "#29306A"
    menu_text:       str = "#FFFFFF"
    menu_hov_bg:     str = "#F75C03"
    menu_hov_text:   str = "#FFFFFF"
    menu_sep:        str = "rgba(255,255,255,0.18)"

    # ── GroupBox default ──────────────────────────────────────────────────────
    grp_bg:          str = "#FFFFFF"
    grp_border:      str = "#D0D4E8"
    grp_top_brd:     str = "#29306A"
    grp_title:       str = "#29306A"

    # ── GroupBox acento (parámetros de cálculo) ───────────────────────────────
    grp_acc_top_brd: str = "#F75C03"
    grp_acc_title:   str = "#F75C03"

    # ── Scrollbar ─────────────────────────────────────────────────────────────
    scrl_track:  str = "#EAECf4"
    scrl_handle: str = "#C0C5E0"
    scrl_hover:  str = "#29306A"

    # ── Progress bar ──────────────────────────────────────────────────────────
    prog_track:  str = "#E8EAF2"
    prog_border: str = "#C8CBE0"
    prog_chunk:  str = "#29306A"
    prog_chunk2: str = "#F75C03"

    # ── Tooltip ───────────────────────────────────────────────────────────────
    tip_bg:     str = "#29306A"
    tip_text:   str = "#FFFFFF"
    tip_border: str = "#1A2052"

    # ── Badge de usuario ──────────────────────────────────────────────────────
    badge_bg:      str = "#29306A"
    badge_text:    str = "#FFFFFF"
    badge_hov_bg:  str = "#3D4A9A"
    badge_prs_bg:  str = "#F75C03"

    # ── Misc ──────────────────────────────────────────────────────────────────
    splitter:     str = "#C8CBE0"
    frame_sep:    str = "#C8CBE0"
    spinner_text: str = "#F75C03"

    # ── Tabs (AccountDialog / HistoryPanel) ───────────────────────────────────
    tab_header_bg:   str = "#29306A"   # Fondo del header de tabs
    tab_btn_text:    str = "rgba(255,255,255,0.65)"
    tab_btn_active:  str = "#FFFFFF"
    tab_btn_brd:     str = "#F75C03"
    hist_tab_bg:     str = "#EAECF4"
    hist_tab_text:   str = "#555577"
    hist_tab_hover:  str = "#D8DBF0"
    hist_tab_hover_text: str = "#29306A"
    hist_tab_active: str = "#29306A"
    hist_tab_active_text: str = "#FFFFFF"
    hist_tab_brd:    str = "#F75C03"


# ─────────────────────────────────────────────────────────────────────────────
# Temas predefinidos
# ─────────────────────────────────────────────────────────────────────────────

#: Tema corporativo — paleta oficial de la empresa
THEME_CLARO = ThemeTokens(name="Claro")  # Defaults = Claro

#: Tema oscuro — escala de grises, acentos mínimos
THEME_OSCURO = ThemeTokens(
    name="Oscuro",
    bg_base="#121212",     bg_secondary="#1B1B1B",  bg_surface="#232323",
    bg_input="#2C2C2C",    bg_header_a="#0A0A0A",   bg_header_b="#1B1B1B",
    bg_status="#0A0A0A",
    text_base="#F2F2F2",   text_muted="#B0B0B0",    text_disabled="#7A7A7A",
    text_on_primary="#F2F2F2", text_placeholder="#555555", text_header="#EBEBEB",
    border_main="#3A3A3A", border_light="#2A2A2A",   border_focus="#5C6BBF",
    primary="#4C5AA8",     primary_dark="#3A4590",   primary_light="#5C6BBF",
    secondary="#787878",   accent_pos="#35F2A0",      accent_pos_d="#1DC880",
    accent_warn="#F75C03", accent_warn_d="#D44800",
    btn_bg="#2A2A2A",      btn_text="#D8D8D8",       btn_border="#3A3A3A",
    btn_hover_bg="#363636",btn_hover_brd="#5C6BBF",
    btn_checked_bg="#4C5AA8", btn_checked_text="#FFFFFF",
    btn_pressed_bg="#F75C03", btn_pressed_text="#FFFFFF",
    btn_dis_bg="#1F1F1F",  btn_dis_text="#7A7A7A",   btn_dis_brd="#2A2A2A",
    btn_pri_bg="#3A4590",  btn_pri_bg2="#4C5AA8",    btn_pri_text="#FFFFFF",
    btn_pri_hov_bg="#4C5AA8", btn_pri_hov_bg2="#5C6BBF",
    btn_pri_prs_bg="#F75C03", btn_pri_dis_bg="#2A3060",
    btn_acc_bg="#B04000",  btn_acc_bg2="#D04A00",    btn_acc_text="#FFFFFF",
    btn_acc_hov="#F75C03", btn_acc_prs="#C04000",    btn_acc_dis_bg="#6A3020",
    tbl_bg="#1B1B1B",      tbl_alt="#232323",        tbl_grid="#2E2E2E",
    tbl_hdr_bg="#1B1B1B",  tbl_hdr_bg2="#2A2A2A",   tbl_hdr_text="#B0B0B0",
    tbl_sel_bg="#4C5AA8",  tbl_sel_text="#FFFFFF",
    tbl_hover_bg="#2E2E2E",tbl_hover_text="#F2F2F2",
    dock_hdr_a="#0A0A0A",  dock_hdr_b="#1B1B1B",
    dock_hdr_brd="#4C5AA8",dock_hdr_text="#F2F2F2",
    menu_bar_bg="#111111", menu_bar_text="#E0E0E0",
    menu_bg="#1F1F1F",     menu_text="#E0E0E0",
    menu_hov_bg="#4C5AA8", menu_hov_text="#FFFFFF",
    menu_sep="rgba(255,255,255,0.08)",
    grp_bg="#232323",      grp_border="#3A3A3A",
    grp_top_brd="#4C5AA8", grp_title="#9AAAF0",
    grp_acc_top_brd="#F75C03", grp_acc_title="#FF8040",
    scrl_track="#1B1B1B",  scrl_handle="#3A3A3A",    scrl_hover="#4C5AA8",
    prog_track="#1B1B1B",  prog_border="#3A3A3A",
    prog_chunk="#4C5AA8",  prog_chunk2="#35F2A0",
    tip_bg="#2A2A2A",      tip_text="#F2F2F2",       tip_border="#3A3A3A",
    badge_bg="#3A4590",    badge_text="#F2F2F2",
    badge_hov_bg="#4C5AA8",badge_prs_bg="#F75C03",
    splitter="#3A3A3A",    frame_sep="#3A3A3A",      spinner_text="#35F2A0",
    tab_header_bg="#1B1B1B",   tab_btn_text="rgba(224,224,224,0.55)",
    tab_btn_active="#F2F2F2",  tab_btn_brd="#4C5AA8",
    hist_tab_bg="#1B1B1B",     hist_tab_text="#B0B0B0",
    hist_tab_hover="#2A2A2A",  hist_tab_hover_text="#E0E0E0",
    hist_tab_active="#4C5AA8", hist_tab_active_text="#FFFFFF",
    hist_tab_brd="#4C5AA8",
)

#: Tema soft — tonos cálidos y terrosos, ideal para jornadas largas
THEME_SOFT = ThemeTokens(
    name="Soft",
    bg_base="#EEE9E2",     bg_secondary="#E3DDD4",   bg_surface="#F5F1EB",
    bg_input="#FAF7F2",    bg_header_a="#4A4F63",    bg_header_b="#737A91",
    bg_status="#E3DDD4",
    text_base="#3E3A37",   text_muted="#6E6862",     text_disabled="#A09A92",
    text_on_primary="#F5F1EB", text_placeholder="#B0AA9E", text_header="#F5F1EB",
    border_main="#D4CCC2", border_light="#E8E2D8",   border_focus="#5E647A",
    primary="#5E647A",     primary_dark="#4A4F63",   primary_light="#737A91",
    secondary="#8C877F",   accent_pos="#7FBFA8",      accent_pos_d="#5AA089",
    accent_warn="#C47A4A", accent_warn_d="#A86335",
    btn_bg="#EAE5DC",      btn_text="#3E3A37",        btn_border="#D4CCC2",
    btn_hover_bg="#DDD7CE",btn_hover_brd="#5E647A",
    btn_checked_bg="#5E647A", btn_checked_text="#F5F1EB",
    btn_pressed_bg="#C47A4A", btn_pressed_text="#F5F1EB",
    btn_dis_bg="#DDD9D2",  btn_dis_text="#A09A92",   btn_dis_brd="#CECCBE",
    btn_pri_bg="#5E647A",  btn_pri_bg2="#737A91",    btn_pri_text="#F5F1EB",
    btn_pri_hov_bg="#737A91", btn_pri_hov_bg2="#848C9F",
    btn_pri_prs_bg="#C47A4A", btn_pri_dis_bg="#B0B5C4",
    btn_acc_bg="#A86335",  btn_acc_bg2="#C47A4A",    btn_acc_text="#F5F1EB",
    btn_acc_hov="#C47A4A", btn_acc_prs="#8C5025",    btn_acc_dis_bg="#D8B89A",
    tbl_bg="#F5F1EB",      tbl_alt="#EAE5DC",        tbl_grid="#D4CCC2",
    tbl_hdr_bg="#5E647A",  tbl_hdr_bg2="#737A91",   tbl_hdr_text="#F5F1EB",
    tbl_sel_bg="#5E647A",  tbl_sel_text="#F5F1EB",
    tbl_hover_bg="#DDD7CE",tbl_hover_text="#3E3A37",
    dock_hdr_a="#4A4F63",  dock_hdr_b="#5E647A",
    dock_hdr_brd="#C47A4A",dock_hdr_text="#F5F1EB",
    menu_bar_bg="#5E647A", menu_bar_text="#F5F1EB",
    menu_bg="#4A4F63",     menu_text="#F5F1EB",
    menu_hov_bg="#C47A4A", menu_hov_text="#F5F1EB",
    menu_sep="rgba(245,241,235,0.2)",
    grp_bg="#F5F1EB",      grp_border="#D4CCC2",
    grp_top_brd="#5E647A", grp_title="#5E647A",
    grp_acc_top_brd="#C47A4A", grp_acc_title="#C47A4A",
    scrl_track="#E3DDD4",  scrl_handle="#C8C0B4",    scrl_hover="#5E647A",
    prog_track="#E3DDD4",  prog_border="#D4CCC2",
    prog_chunk="#5E647A",  prog_chunk2="#C47A4A",
    tip_bg="#5E647A",      tip_text="#F5F1EB",        tip_border="#4A4F63",
    badge_bg="#5E647A",    badge_text="#F5F1EB",
    badge_hov_bg="#737A91",badge_prs_bg="#C47A4A",
    splitter="#D4CCC2",    frame_sep="#D4CCC2",       spinner_text="#C47A4A",
    tab_header_bg="#5E647A",   tab_btn_text="rgba(245,241,235,0.6)",
    tab_btn_active="#F5F1EB",  tab_btn_brd="#C47A4A",
    hist_tab_bg="#E3DDD4",     hist_tab_text="#6E6862",
    hist_tab_hover="#D8D2C8",  hist_tab_hover_text="#3E3A37",
    hist_tab_active="#5E647A", hist_tab_active_text="#F5F1EB",
    hist_tab_brd="#C47A4A",
)

#: Tema personalizado — copia de Claro que el usuario puede modificar
THEME_CUSTOM_BASE = ThemeTokens(name="Personalizado")

#: Registro de todos los temas disponibles (orden = orden en ComboBox)
THEMES: Dict[str, ThemeTokens] = {
    "claro":        THEME_CLARO,
    "oscuro":       THEME_OSCURO,
    "soft":         THEME_SOFT,
    "personalizado": THEME_CUSTOM_BASE,
}

#: Campos modificables en el tema personalizado
CUSTOM_FIELDS = [
    ("primary",    "Color principal"),
    ("secondary",  "Color secundario"),
    ("bg_base",    "Fondo principal"),
    ("text_base",  "Texto principal"),
    ("accent_pos", "Acento positivo"),
    ("accent_warn","Acento advertencia"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Contraste WCAG 2.1
# ─────────────────────────────────────────────────────────────────────────────

def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    r, g, b = int(h[0:2], 16)/255.0, int(h[2:4], 16)/255.0, int(h[4:6], 16)/255.0
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two hex colours."""
    try:
        l1, l2 = _luminance(fg), _luminance(bg)
        lighter, darker = max(l1, l2), min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)
    except Exception:
        return 1.0


def contrast_ok(fg: str, bg: str, level: str = "AA") -> bool:
    """True if the contrast is acceptable (AA = 4.5:1, AA_large = 3:1)."""
    threshold = 4.5 if level == "AA" else 3.0
    return contrast_ratio(fg, bg) >= threshold


# ─────────────────────────────────────────────────────────────────────────────
# Constructor de temas personalizados
# ─────────────────────────────────────────────────────────────────────────────

def build_custom_tokens(overrides: dict) -> ThemeTokens:
    """
    Crea un ThemeTokens basado en THEME_CLARO con los campos sobreescritos.
    Solo modifica los campos definidos en overrides.
    Aplica validación de contraste mínimo.
    """
    import dataclasses
    base = dataclasses.replace(THEME_CLARO, name="Personalizado")
    for key, val in overrides.items():
        if hasattr(base, key) and isinstance(val, str) and val.startswith("#"):
            object.__setattr__(base, key, val)
    return base


def get_theme_by_name(name: str, custom_colors: Optional[dict] = None) -> ThemeTokens:
    """
    Devuelve un ThemeTokens para el nombre dado.
    Para 'personalizado', aplica custom_colors sobre la base Claro.
    """
    key = (name or "claro").lower()
    if key == "personalizado" or key == "custom":
        return build_custom_tokens(custom_colors or {})
    return THEMES.get(key, THEME_CLARO)


# ─────────────────────────────────────────────────────────────────────────────
# Generador de QSS
# ─────────────────────────────────────────────────────────────────────────────

def build_qss(t: ThemeTokens) -> str:
    """
    Genera la hoja de estilos Qt completa para el tema dado.
    Cubre TODOS los widgets usados en V-Metric.
    """
    return f"""
/* ═══════════════════════════════════════════════════════════════════════════
   V-Metric — Tema: {t.name}
   Generado por poza/themes.py — no editar directamente en gui_qt.py
   ═══════════════════════════════════════════════════════════════════════════ */

/* ─── Base global ────────────────────────────────────────────────────────── */
QMainWindow {{
    background: {t.bg_base};
}}
QDialog {{
    background: {t.bg_base};
    color: {t.text_base};
}}
QWidget {{
    background: transparent;
    color: {t.text_base};
    font-family: "Segoe UI", "SF Pro Text", "Ubuntu", sans-serif;
    font-size: 10pt;
}}

/* Fondos reales para contenedores de primer nivel */
QMainWindow > QWidget#qt_centralwidget,
QMainWindow > QWidget {{
    background: {t.bg_base};
}}
QDockWidget > QWidget {{
    background: {t.bg_secondary};
}}
QStackedWidget {{
    background: {t.bg_surface};
}}
QScrollArea > QWidget > QWidget {{
    background: {t.bg_surface};
}}

/* ─── Label ──────────────────────────────────────────────────────────────── */
QLabel {{
    background: transparent;
    color: {t.text_base};
}}
QLabel:disabled {{
    color: {t.text_disabled};
}}

/* ─── GroupBox ───────────────────────────────────────────────────────────── */
QGroupBox {{
    background: {t.grp_bg};
    border: 1px solid {t.grp_border};
    border-top: 3px solid {t.grp_top_brd};
    border-radius: 6px;
    margin-top: 14px;
    font: bold 10pt "Segoe UI";
    color: {t.grp_title};
    padding-top: 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    background: {t.grp_bg};
}}
QGroupBox > QWidget {{
    background: {t.grp_bg};
}}
QGroupBox > QLabel {{
    color: {t.text_base};
    background: transparent;
}}
/* GroupBox acento (ej. Parámetros de cálculo) */
QGroupBox[accent="true"] {{
    border-top: 3px solid {t.grp_acc_top_brd};
    color: {t.grp_acc_title};
}}
QGroupBox[accent="true"]::title {{
    background: {t.grp_bg};
}}

/* ─── LineEdit ───────────────────────────────────────────────────────────── */
QLineEdit {{
    font: 10pt "Segoe UI";
    padding: 5px 8px;
    border: 1px solid {t.border_main};
    border-radius: 4px;
    background: {t.bg_input};
    color: {t.text_base};
    selection-background-color: {t.tbl_sel_bg};
    selection-color: {t.tbl_sel_text};
}}
QLineEdit:focus {{
    border: 2px solid {t.border_focus};
    background: {t.bg_surface};
}}
QLineEdit:disabled {{
    background: {t.bg_secondary};
    color: {t.text_disabled};
    border-color: {t.border_light};
}}
QLineEdit[readOnly="true"] {{
    background: {t.bg_secondary};
    color: {t.text_muted};
}}

/* ─── ComboBox ───────────────────────────────────────────────────────────── */
QComboBox {{
    font: 10pt "Segoe UI";
    padding: 4px 8px;
    border: 1px solid {t.border_main};
    border-radius: 4px;
    background: {t.bg_input};
    color: {t.text_base};
}}
QComboBox:focus {{
    border: 2px solid {t.border_focus};
}}
QComboBox:hover {{
    border-color: {t.border_focus};
}}
QComboBox:disabled {{
    background: {t.bg_secondary};
    color: {t.text_disabled};
    border-color: {t.border_light};
}}
QComboBox::drop-down {{
    border-left: 1px solid {t.border_main};
    background: {t.btn_bg};
    width: 22px;
    border-radius: 0 4px 4px 0;
}}
QComboBox::down-arrow {{
    width: 0; height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid {t.text_muted};
}}
QComboBox QAbstractItemView {{
    background: {t.bg_surface};
    color: {t.text_base};
    border: 1px solid {t.border_main};
    selection-background-color: {t.tbl_sel_bg};
    selection-color: {t.tbl_sel_text};
    outline: none;
    padding: 2px;
}}
QComboBox QAbstractItemView::item {{
    padding: 4px 8px;
    min-height: 22px;
}}

/* ─── CheckBox ───────────────────────────────────────────────────────────── */
QCheckBox {{
    color: {t.text_base};
    spacing: 6px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 2px solid {t.border_focus};
    border-radius: 3px;
    background: {t.bg_input};
}}
QCheckBox::indicator:checked {{
    background: {t.primary};
    border-color: {t.primary};
}}
QCheckBox::indicator:hover {{
    border-color: {t.primary_light};
}}
QCheckBox:disabled {{
    color: {t.text_disabled};
}}
QCheckBox::indicator:disabled {{
    border-color: {t.text_disabled};
    background: {t.bg_secondary};
}}

/* ─── SpinBox ────────────────────────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {{
    font: 10pt "Segoe UI";
    padding: 4px 6px;
    border: 1px solid {t.border_main};
    border-radius: 4px;
    background: {t.bg_input};
    color: {t.text_base};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {t.border_focus};
}}

/* ─── Botones base ───────────────────────────────────────────────────────── */
QPushButton {{
    font: 9pt "Segoe UI";
    padding: 5px 12px;
    min-height: 24px;
    border: 1px solid {t.btn_border};
    border-radius: 4px;
    background: {t.btn_bg};
    color: {t.btn_text};
}}
QPushButton:hover {{
    background: {t.btn_hover_bg};
    border-color: {t.btn_hover_brd};
}}
QPushButton:pressed {{
    background: {t.btn_pressed_bg};
    color: {t.btn_pressed_text};
    border-color: {t.btn_pressed_bg};
}}
QPushButton:checked {{
    background: {t.btn_checked_bg};
    color: {t.btn_checked_text};
    border-color: {t.btn_checked_bg};
}}
QPushButton:disabled {{
    background: {t.btn_dis_bg};
    color: {t.btn_dis_text};
    border-color: {t.btn_dis_brd};
}}
QPushButton:focus {{
    outline: none;
    border: 2px solid {t.border_focus};
}}

/* ─── Botón PRIMARIO (objectName="btnPrimary") ───────────────────────────── */
QPushButton#btnPrimary {{
    font: bold 10pt "Segoe UI";
    color: {t.btn_pri_text};
    border: none;
    border-radius: 5px;
    padding: 8px 16px;
    min-height: 32px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 {t.btn_pri_bg2}, stop:1 {t.btn_pri_bg});
}}
QPushButton#btnPrimary:hover {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 {t.btn_pri_hov_bg2}, stop:1 {t.btn_pri_hov_bg});
}}
QPushButton#btnPrimary:pressed {{
    background: {t.btn_pri_prs_bg};
    color: #FFFFFF;
}}
QPushButton#btnPrimary:disabled {{
    background: {t.btn_pri_dis_bg};
    color: {t.text_on_primary};
}}

/* ─── Botón ACENTO (objectName="btnAccent") ──────────────────────────────── */
QPushButton#btnAccent {{
    font: bold 10pt "Segoe UI";
    color: {t.btn_acc_text};
    border: none;
    border-radius: 5px;
    padding: 7px 14px;
    min-height: 28px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 {t.btn_acc_bg2}, stop:1 {t.btn_acc_bg});
}}
QPushButton#btnAccent:hover {{
    background: {t.btn_acc_hov};
}}
QPushButton#btnAccent:pressed {{
    background: {t.btn_acc_prs};
}}
QPushButton#btnAccent:disabled {{
    background: {t.btn_acc_dis_bg};
    color: rgba(255,255,255,0.5);
}}

/* ─── Botón SECUNDARIO (objectName="btnSecondary") ──────────────────────── */
QPushButton#btnSecondary {{
    font: 9pt "Segoe UI";
    color: {t.primary};
    border: 1px solid {t.border_main};
    border-radius: 5px;
    padding: 6px 14px;
    background: {t.bg_secondary};
}}
QPushButton#btnSecondary:hover {{
    background: {t.btn_hover_bg};
    border-color: {t.primary};
}}
QPushButton#btnSecondary:pressed {{
    background: {t.btn_pressed_bg};
    color: {t.btn_pressed_text};
}}
QPushButton#btnSecondary:disabled {{
    color: {t.text_disabled};
    background: {t.btn_dis_bg};
    border-color: {t.btn_dis_brd};
}}

/* ─── Badge de usuario (objectName="userBadge") ─────────────────────────── */
QPushButton#userBadge {{
    background: {t.badge_bg};
    color: {t.badge_text};
    font: bold 9pt "Segoe UI";
    border: none;
    border-radius: 3px;
    padding: 2px 10px;
    margin: 2px 4px;
}}
QPushButton#userBadge:hover {{
    background: {t.badge_hov_bg};
}}
QPushButton#userBadge:pressed {{
    background: {t.badge_prs_bg};
}}

/* ─── Botón de pestaña de historial (objectName="histTab") ──────────────── */
QPushButton#histTab {{
    font: bold 9pt "Segoe UI";
    padding: 5px 14px;
    border: none;
    border-radius: 4px 4px 0 0;
    background: {t.hist_tab_bg};
    color: {t.hist_tab_text};
}}
QPushButton#histTab:hover {{
    background: {t.hist_tab_hover};
    color: {t.hist_tab_hover_text};
}}
QPushButton#histTab:checked {{
    background: {t.hist_tab_active};
    color: {t.hist_tab_active_text};
    border-bottom: 3px solid {t.hist_tab_brd};
}}

/* ─── Botón de pestaña en header (objectName="dialogTab") ───────────────── */
QPushButton#dialogTab {{
    font: 9pt "Segoe UI";
    color: {t.tab_btn_text};
    background: transparent;
    border: none;
    border-bottom: 3px solid transparent;
    padding: 6px 14px;
}}
QPushButton#dialogTab:checked {{
    color: {t.tab_btn_active};
    border-bottom: 3px solid {t.tab_btn_brd};
}}
QPushButton#dialogTab:hover {{
    color: {t.tab_btn_active};
}}

/* ─── Botón de selector de color (objectName="colorSwatch") ─────────────── */
QPushButton#colorSwatch {{
    border: 2px solid {t.border_main};
    border-radius: 4px;
    min-width: 40px;
    min-height: 22px;
    padding: 0;
}}
QPushButton#colorSwatch:hover {{
    border-color: {t.border_focus};
}}

/* ─── Header bar (objectName="headerBar") ───────────────────────────────── */
QWidget#headerBar {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {t.bg_header_a}, stop:0.55 {t.primary}, stop:1 {t.bg_header_b});
    border-bottom: 2px solid {t.accent_warn};
}}
QWidget#headerBar > QLabel {{
    background: transparent;
    color: {t.text_header};
}}

/* ─── Toolbar del visor (objectName="viewerToolbar") ────────────────────── */
QWidget#viewerToolbar {{
    background: {t.bg_secondary};
    border-bottom: 1px solid {t.border_main};
}}

/* ─── Header de diálogos con tabs (objectName="dialogHeader") ───────────── */
QWidget#dialogHeader {{
    background: {t.tab_header_bg};
}}
QWidget#dialogHeader > QLabel {{
    color: {t.text_header};
    background: transparent;
}}

/* ─── Panel del visor DEM ────────────────────────────────────────────────── */
QWidget#demViewer {{
    background: {t.bg_base};
    border: 1px solid {t.border_main};
}}

/* ─── DockWidget ─────────────────────────────────────────────────────────── */
QDockWidget {{
    font: bold 10pt "Segoe UI";
    border: 1px solid {t.border_main};
}}
QDockWidget::title {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {t.dock_hdr_a}, stop:1 {t.dock_hdr_b});
    padding: 6px 12px;
    border-bottom: 2px solid {t.dock_hdr_brd};
    color: {t.dock_hdr_text};
    text-align: left;
}}
QDockWidget::close-button,
QDockWidget::float-button {{
    background: transparent;
    border: none;
    padding: 2px;
    icon-size: 13px;
}}
QDockWidget::close-button:hover,
QDockWidget::float-button:hover {{
    background: rgba(255,255,255,0.2);
    border-radius: 3px;
}}

/* ─── MenuBar ────────────────────────────────────────────────────────────── */
QMenuBar {{
    background: {t.menu_bar_bg};
    color: {t.menu_bar_text};
    font: 9pt "Segoe UI";
    padding: 2px 0;
    border-bottom: 1px solid {t.primary_dark};
}}
QMenuBar::item {{
    padding: 4px 12px;
    border-radius: 3px;
    background: transparent;
}}
QMenuBar::item:selected {{
    background: rgba(255,255,255,0.15);
}}
QMenuBar::item:pressed {{
    background: rgba(255,255,255,0.25);
}}

/* ─── Menu popup ─────────────────────────────────────────────────────────── */
QMenu {{
    background: {t.menu_bg};
    color: {t.menu_text};
    border: 1px solid {t.primary_dark};
    font: 9pt "Segoe UI";
    padding: 4px 0;
}}
QMenu::item {{
    padding: 6px 20px 6px 12px;
}}
QMenu::item:selected {{
    background: {t.menu_hov_bg};
    color: {t.menu_hov_text};
    border-radius: 3px;
    margin: 0 3px;
}}
QMenu::separator {{
    height: 1px;
    background: {t.menu_sep};
    margin: 3px 8px;
}}
QMenu::icon {{
    padding-left: 8px;
}}

/* ─── StatusBar ──────────────────────────────────────────────────────────── */
QStatusBar {{
    background: {t.bg_status};
    color: {t.text_muted};
    border-top: 1px solid {t.border_main};
    font: 9pt "Segoe UI";
}}
QStatusBar::item {{
    border: none;
}}

/* ─── ProgressBar ────────────────────────────────────────────────────────── */
QProgressBar {{
    border: 1px solid {t.prog_border};
    border-radius: 4px;
    background: {t.prog_track};
    text-align: center;
    color: transparent;
    font-size: 0pt;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {t.prog_chunk}, stop:1 {t.prog_chunk2});
    border-radius: 3px;
}}

/* ─── Tables / Trees ─────────────────────────────────────────────────────── */
QTableWidget, QTreeWidget, QTableView, QTreeView {{
    font: 9pt "Segoe UI";
    border: none;
    background: {t.tbl_bg};
    alternate-background-color: {t.tbl_alt};
    gridline-color: {t.tbl_grid};
    color: {t.text_base};
    outline: none;
}}
QTableWidget::item, QTreeWidget::item,
QTableView::item, QTreeView::item {{
    padding: 3px 6px;
    border: none;
}}
QTableWidget::item:selected, QTreeWidget::item:selected,
QTableView::item:selected, QTreeView::item:selected {{
    background: {t.tbl_sel_bg};
    color: {t.tbl_sel_text};
}}
QTableWidget::item:hover, QTreeWidget::item:hover,
QTableView::item:hover, QTreeView::item:hover {{
    background: {t.tbl_hover_bg};
    color: {t.tbl_hover_text};
}}
QHeaderView {{
    background: {t.tbl_hdr_bg};
    border: none;
}}
QHeaderView::section {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 {t.tbl_hdr_bg2}, stop:1 {t.tbl_hdr_bg});
    color: {t.tbl_hdr_text};
    font: bold 9pt "Segoe UI";
    padding: 5px 6px;
    border: none;
    border-right: 1px solid {t.primary_light};
}}
QHeaderView::section:hover {{
    background: {t.primary_light};
}}
QTableCornerButton::section {{
    background: {t.tbl_hdr_bg};
    border: none;
}}

/* ─── ScrollBar ──────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {t.scrl_track};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t.scrl_handle};
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t.scrl_hover};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QScrollBar:horizontal {{
    background: {t.scrl_track};
    height: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {t.scrl_handle};
    border-radius: 4px;
    min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t.scrl_hover};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; border: none; }}

/* ─── ToolTip ────────────────────────────────────────────────────────────── */
QToolTip {{
    background: {t.tip_bg};
    color: {t.tip_text};
    border: 1px solid {t.tip_border};
    border-radius: 4px;
    padding: 4px 8px;
    font: 9pt "Segoe UI";
    opacity: 230;
}}

/* ─── Splitter ───────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {t.splitter};
}}
QSplitter::handle:horizontal {{ width: 4px; }}
QSplitter::handle:vertical   {{ height: 4px; }}
QSplitter::handle:hover {{
    background: {t.border_focus};
}}

/* ─── Frame separador ────────────────────────────────────────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {t.frame_sep};
    background: {t.frame_sep};
    border: none;
}}

/* ─── TextBrowser / TextEdit ─────────────────────────────────────────────── */
QTextBrowser, QTextEdit, QPlainTextEdit {{
    background: {t.bg_surface};
    color: {t.text_base};
    border: 1px solid {t.border_light};
    border-radius: 4px;
    font: 10pt "Segoe UI";
    selection-background-color: {t.tbl_sel_bg};
    selection-color: {t.tbl_sel_text};
}}

/* ─── TabWidget (estándar Qt) ────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {t.border_main};
    background: {t.bg_surface};
    border-radius: 0 4px 4px 4px;
}}
QTabBar::tab {{
    background: {t.hist_tab_bg};
    color: {t.hist_tab_text};
    padding: 6px 16px;
    border: 1px solid {t.border_main};
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    font: 9pt "Segoe UI";
    min-width: 80px;
}}
QTabBar::tab:selected {{
    background: {t.hist_tab_active};
    color: {t.hist_tab_active_text};
    border-bottom: 3px solid {t.hist_tab_brd};
}}
QTabBar::tab:hover:!selected {{
    background: {t.hist_tab_hover};
    color: {t.hist_tab_hover_text};
}}

/* ─── MessageBox ─────────────────────────────────────────────────────────── */
QMessageBox {{
    background: {t.bg_surface};
    color: {t.text_base};
}}
QMessageBox QLabel {{
    color: {t.text_base};
    background: transparent;
}}
QMessageBox QPushButton {{
    min-width: 80px;
    padding: 5px 16px;
}}

/* ─── FileDialog ─────────────────────────────────────────────────────────── */
QFileDialog {{
    background: {t.bg_base};
    color: {t.text_base};
}}

/* ─── FormLayout labels ──────────────────────────────────────────────────── */
QFormLayout QLabel {{
    color: {t.text_muted};
    font: 9pt "Segoe UI";
}}
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# QSS fijo para el login (siempre tema Claro)
# ─────────────────────────────────────────────────────────────────────────────

def build_login_qss() -> str:
    """
    Siempre devuelve el QSS del tema Claro para la pantalla de login.
    Independiente del tema activo en la app — identidad de marca fija.
    """
    t = THEME_CLARO
    return f"""
QDialog {{
    background: #F6F6F6;
    color: #333333;
}}
QWidget {{
    background: transparent;
    color: #333333;
    font-family: "Segoe UI";
}}
QLabel {{
    background: transparent;
    color: #333333;
}}
QLabel#loginTitle {{
    font: bold 18pt "Segoe UI";
    color: {t.primary};
    background: transparent;
}}
QLabel#loginSubtitle {{
    font: 9pt "Segoe UI";
    color: {t.secondary};
    background: transparent;
}}
QLabel#loginError {{
    font: bold 9pt "Segoe UI";
    color: #C0392B;
    background: transparent;
}}
QLineEdit {{
    font: 10pt "Segoe UI";
    padding: 6px 8px;
    border: 1px solid {t.border_main};
    border-radius: 5px;
    background: white;
    color: #333333;
}}
QLineEdit:focus {{
    border: 2px solid {t.primary};
    background: white;
}}
QPushButton#btnLoginAcceder {{
    font: bold 11pt "Segoe UI";
    color: white;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 {t.primary_light}, stop:1 {t.primary});
    border: none;
    border-radius: 5px;
    padding: 9px 28px;
    min-height: 38px;
}}
QPushButton#btnLoginAcceder:hover {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 {t.primary_light}, stop:1 {t.primary_light});
}}
QPushButton#btnLoginAcceder:pressed {{
    background: {t.accent_warn};
}}
""".strip()
