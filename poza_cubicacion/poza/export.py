from __future__ import annotations

import csv
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable, Tuple


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
