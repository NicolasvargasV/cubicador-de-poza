from __future__ import annotations

import csv
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable, Tuple


GOOGLE_SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def default_output_name(prefix="resultados_poza") -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}.csv"


def export_rows_to_csv(csv_path: str, rows: Iterable[Tuple[str, float, str]]) -> str:
    """
    rows: iterable de (Item, Valor, Unidad)
    """
    p = Path(csv_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")  # Chile/Excel suele abrir mejor con ;
        w.writerow(["Item", "Valor", "Unidad"])
        for item, value, unit in rows:
            w.writerow([item, value, unit])

    return str(p.resolve())


def export_rows_to_google_sheets(
    spreadsheet_id: str,
    rows: Iterable[Tuple[str, float, str]],
    *,
    sheet_title: str | None = None,
    credentials_path: str | None = None,
) -> dict:
    """Exporta filas a Google Sheets creando una nueva hoja (worksheet).

    Requisitos:
      - Instalar dependencias: `gspread` y `google-auth`.
      - Proveer credenciales:
          * Service Account: setear `GOOGLE_APPLICATION_CREDENTIALS` apuntando
            al JSON, o pasar `credentials_path`.
          * Alternativamente, usar ADC (Application Default Credentials) si
            está configurado en el equipo (p.ej. `gcloud auth application-default login`).

    Retorna un dict con `spreadsheet_url` y `worksheet_title`.
    """

    try:
        import gspread  # type: ignore
        import google.auth._helpers  # type: ignore
        from google.auth import default as google_auth_default  # type: ignore
        from google.oauth2.service_account import Credentials  # type: ignore
        
        # ── MONKEY PATCH ──
        # Restamos 365 días porque el sistema está en 2026 y Google requiere año 2025 aprox.
        # Además restamos unos 10 minutos por la zona horaria real.
        _original_utcnow = google.auth._helpers.utcnow
        def _patched_utcnow():
            import datetime
            import urllib.request
            from urllib.error import HTTPError
            import email.utils
            
            # Intentar obtener la hora real directo de los servidores de Google para
            # evitar fallos por desfase de años enteros, meses u horas.
            try:
                urllib.request.urlopen("https://oauth2.googleapis.com/token", data=b"", timeout=3)
            except HTTPError as e:
                if "Date" in e.headers:
                    dt = email.utils.parsedate_to_datetime(e.headers["Date"])
                    return dt.replace(tzinfo=None)
            except Exception:
                pass
                
            # Fallback (restar 365 días)
            return _original_utcnow() - datetime.timedelta(days=365)
            
        google.auth._helpers.utcnow = _patched_utcnow

    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Dependencias faltantes para Google Sheets. Instala: `pip install gspread google-auth`. "
            "(o agrega estas dependencias a tu entorno)"
        ) from e

    def _get_creds():
        # 1) ruta explícita
        if credentials_path:
            return Credentials.from_service_account_file(credentials_path, scopes=GOOGLE_SHEETS_SCOPES)

        # 2) env var estándar
        env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        if env_path:
            p = Path(env_path)
            if p.exists():
                return Credentials.from_service_account_file(str(p), scopes=GOOGLE_SHEETS_SCOPES)

        # 3) Application Default Credentials (gcloud / workload identity)
        creds, _ = google_auth_default(scopes=GOOGLE_SHEETS_SCOPES)
        return creds

    creds = _get_creds()
    client = gspread.authorize(creds)

    sh = client.open_by_key(spreadsheet_id)

    # Buscar si ya existe la hoja o crear una nueva llamada "Cubicaciones"
    target_sheet_title = "Cubicaciones"
    existing_titles = {ws.title for ws in sh.worksheets()}
    
    is_new = False
    if target_sheet_title in existing_titles:
        ws = sh.worksheet(target_sheet_title)
        # Por si la hoja existe pero la borraron manualmente (está vacía)
        if not ws.get_all_values():
            is_new = True
    else:
        ws = sh.add_worksheet(title=target_sheet_title, rows="1000", cols="20")
        is_new = True
        
    rows_list = list(rows)
    
    # Extraer encabezados (Items de la primera columna) y los valores
    headers = [row[0] for row in rows_list]
    values_row = [row[1] for row in rows_list]

    if is_new:
        # Escribimos los títulos y la primera fila de datos al mismo tiempo en A1 para asegurar
        ws.update("A1", [headers, values_row], value_input_option="USER_ENTERED")
    else:
        # Agregar solo los valores como una nueva fila al final
        ws.append_row(values_row, value_input_option="USER_ENTERED")

    return {
        "spreadsheet_url": sh.url,
        "worksheet_title": ws.title,
        "spreadsheet_id": spreadsheet_id,
    }


def open_file_default_app(path: str) -> None:
    """
    Abre archivo con la app por defecto (Windows: Excel si está asociado a CSV).
    """
    p = str(Path(path).resolve())

    if sys.platform.startswith("win"):
        os.startfile(p)  # noqa: S606
        return

    if sys.platform == "darwin":
        subprocess.call(["open", p])
        return

    subprocess.call(["xdg-open", p])


def open_url_default_app(url: str) -> None:
    """Abre una URL en el navegador por defecto."""
    if not url:
        return

    if sys.platform.startswith("win"):
        os.startfile(url)  # noqa: S606
        return

    if sys.platform == "darwin":
        subprocess.call(["open", url])
        return

    subprocess.call(["xdg-open", url])
