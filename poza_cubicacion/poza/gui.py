from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk

from .core import DemRaster, PondVolumeCalculator, DemError, PondVolumes
from .masks import load_mask_shapes, MaskError
from .export import export_rows_to_csv, open_file_default_app, default_output_name
from .viz import DemRenderer


COLOR_PRIMARY = "#29306A"
COLOR_SECONDARY = "#808B96"
COLOR_ACCENT = "#F75C03"
COLOR_TEXT = "#333333"
COLOR_BG = "#F6F6F6"
COLOR_WHITE = "#FFFFFF"


def resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return str(Path(base) / relative)
    return str(Path(__file__).resolve().parent.parent / relative)


def fmt(x: float, decimals=3) -> str:
    return f"{x:,.{decimals}f}"


class Card(tk.Frame):
    def __init__(self, master, title: str | None = None, **kwargs):
        super().__init__(master, bg=COLOR_WHITE, highlightbackground="#E3E3E3", highlightthickness=1, **kwargs)
        self.columnconfigure(0, weight=1)
        if title:
            tk.Label(self, text=title, bg=COLOR_WHITE, fg=COLOR_TEXT, font=("Segoe UI", 11, "bold")).grid(
                row=0, column=0, sticky="w", padx=12, pady=(10, 6)
            )


class DemViewer(tk.Frame):
    """
    FAST mientras mueves (cache) + HQ cuando te detienes.
    """
    def __init__(self, master):
        super().__init__(master, bg=COLOR_WHITE)
        self.canvas = tk.Canvas(self, bg=COLOR_WHITE, highlightthickness=1, highlightbackground="#E3E3E3")
        self.canvas.pack(fill="both", expand=True)

        self.renderer: DemRenderer | None = None

        self.zoom = 1.0
        self.zoom_min = 0.35
        self.zoom_max = 12.0
        self.center_x = 0.0
        self.center_y = 0.0

        self._photo: ImageTk.PhotoImage | None = None
        self._render_info = {"x0": 0.0, "y0": 0.0, "scale": 1.0, "base_scale": 1.0}

        # jobs
        self._fast_job = None
        self._hq_job = None

        # leyenda overlay (solo max y min)
        self.legend = tk.Frame(self, bg=COLOR_WHITE, highlightbackground="#E3E3E3", highlightthickness=1)
        self.legend.place(x=14, y=14)

        self.lbl_max = tk.Label(self.legend, text="", bg=COLOR_WHITE, fg=COLOR_TEXT, font=("Segoe UI", 9))
        self.lbl_max.pack(anchor="w", padx=8, pady=(6, 0))

        self.legend_bar = tk.Label(self.legend, bg=COLOR_WHITE)
        self.legend_bar.pack(padx=8, pady=6)

        self.lbl_min = tk.Label(self.legend, text="", bg=COLOR_WHITE, fg=COLOR_TEXT, font=("Segoe UI", 9))
        self.lbl_min.pack(anchor="w", padx=8, pady=(0, 6))

        self._legend_photo: ImageTk.PhotoImage | None = None
        self._legend_last_h = 0

        # events
        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<ButtonPress-1>", self._pan_start)
        self.canvas.bind("<B1-Motion>", self._pan_move)
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._schedule_hq())

        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._zoom_at(1.10, e.x, e.y))
        self.canvas.bind("<Button-5>", lambda e: self._zoom_at(1/1.10, e.x, e.y))

        self._pan_anchor = None

    def set_renderer(self, renderer: DemRenderer):
        if self.renderer:
            self.renderer.close()
        self.renderer = renderer

        # cache para fluidez
        self.renderer.build_cache(max_tex=2048, levels=4)

        self.zoom = 1.0
        self.center_x = renderer.width / 2
        self.center_y = renderer.height / 2

        self._update_legend()
        self._render_fast()
        self._schedule_hq(delay_ms=60)  # primer HQ rápido

    def clear(self):
        if self.renderer:
            self.renderer.close()
        self.renderer = None
        self.canvas.delete("all")

    def _on_configure(self, event):
        self._position_legend()
        self._render_fast()
        self._schedule_hq()

    def _position_legend(self):
        ch = max(1, self.canvas.winfo_height())
        # 35% alto, clamp
        desired = int(ch * 0.35)
        desired = max(90, min(desired, 260))
        desired = min(desired, max(90, ch - 40))
        if self.renderer and abs(desired - self._legend_last_h) >= 8:
            self._update_legend(desired)

        # abajo-izq
        self.legend.place_configure(x=14, y=ch - 14, anchor="sw")

    def _update_legend(self, height: int | None = None):
        if not self.renderer:
            return
        if height is None:
            h = max(90, min(int(self.canvas.winfo_height() * 0.35), 260))
        else:
            h = height

        legend_rgb, labels = self.renderer.legend(height=h, width=18)
        legend_img = Image.fromarray(legend_rgb, mode="RGB")
        self._legend_photo = ImageTk.PhotoImage(legend_img)
        self.legend_bar.configure(image=self._legend_photo)

        self.lbl_max.configure(text=labels.get("max", ""))
        self.lbl_min.configure(text=labels.get("min", ""))

        self._legend_last_h = h

    def _render_fast(self):
        if self._fast_job:
            self.after_cancel(self._fast_job)
        # throttle muy leve para que no intente 200 renders/seg en drag
        self._fast_job = self.after(8, self._do_render_fast)

    def _do_render_fast(self):
        self._fast_job = None
        if not self.renderer:
            return
        cw = max(2, self.canvas.winfo_width())
        ch = max(2, self.canvas.winfo_height())

        rgb, info = self.renderer.render_view_cached(
            center_x=self.center_x,
            center_y=self.center_y,
            zoom=self.zoom,
            canvas_w=cw,
            canvas_h=ch,
        )
        self._render_info = info
        img = Image.fromarray(rgb, mode="RGB")
        self._photo = ImageTk.PhotoImage(img)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")

    def _schedule_hq(self, delay_ms: int = 220):
        if self._hq_job:
            self.after_cancel(self._hq_job)
        self._hq_job = self.after(delay_ms, self._render_hq)

    def _render_hq(self):
        self._hq_job = None
        if not self.renderer:
            return
        cw = max(2, self.canvas.winfo_width())
        ch = max(2, self.canvas.winfo_height())

        rgb, info = self.renderer.render_view_hq(
            center_x=self.center_x,
            center_y=self.center_y,
            zoom=self.zoom,
            canvas_w=cw,
            canvas_h=ch,
            hillshade=True,
        )
        self._render_info = info
        img = Image.fromarray(rgb, mode="RGB")
        self._photo = ImageTk.PhotoImage(img)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")

    def _pan_start(self, event):
        self._pan_anchor = (event.x, event.y, self.center_x, self.center_y)

    def _pan_move(self, event):
        if not self._pan_anchor or not self.renderer:
            return
        x0, y0, cx0, cy0 = self._pan_anchor
        dx = event.x - x0
        dy = event.y - y0

        scale = float(self._render_info.get("scale", 1.0))
        self.center_x = cx0 - dx / scale
        self.center_y = cy0 - dy / scale

        self.center_x = max(0.0, min(self.center_x, self.renderer.width))
        self.center_y = max(0.0, min(self.center_y, self.renderer.height))

        # FAST durante drag, HQ después
        self._render_fast()
        self._schedule_hq()

    def _on_wheel(self, event):
        factor = 1.10 if event.delta > 0 else 1 / 1.10
        self._zoom_at(factor, event.x, event.y)

    def _zoom_at(self, factor: float, mx: int, my: int):
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

        cw = max(2, self.canvas.winfo_width())
        ch = max(2, self.canvas.winfo_height())

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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cubicador de Pozas")
        self.minsize(1200, 720)
        self.configure(bg=COLOR_BG)

        self._apply_ttk_style()

        self.dem_path: str | None = None
        self.mask_path: str | None = None

        self.latest_result: PondVolumes | None = None
        self.latest_rows: list[tuple[str, float, str]] = []

        self.var_use_mask = tk.BooleanVar(value=True)
        self.var_salt = tk.StringVar(value="")
        self.var_water = tk.StringVar(value="")
        self.var_occ = tk.StringVar(value="0.20")

        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        try:
            self.viewer.clear()
        finally:
            self.destroy()

    def _apply_ttk_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 10))
        style.configure("TCheckbutton", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 10))
        style.configure("TEntry", font=("Segoe UI", 10))
        style.configure("TFrame", background=COLOR_BG)

        style.configure("Accent.TButton", background=COLOR_ACCENT, foreground="white",
                        font=("Segoe UI", 10, "bold"), padding=(12, 8), borderwidth=0)
        style.map("Accent.TButton", background=[("active", COLOR_ACCENT)])

        style.configure("Primary.TButton", background=COLOR_PRIMARY, foreground="white",
                        font=("Segoe UI", 10, "bold"), padding=(12, 8), borderwidth=0)
        style.map("Primary.TButton", background=[("active", COLOR_PRIMARY)])

        style.configure("Neutral.TButton", background="#EDEDED", foreground=COLOR_TEXT,
                        font=("Segoe UI", 10), padding=(12, 8), borderwidth=0)
        style.map("Neutral.TButton", background=[("active", "#E6E6E6")])

        style.configure("Treeview", font=("Segoe UI", 10), rowheight=28,
                        fieldbackground=COLOR_WHITE, background=COLOR_WHITE, foreground=COLOR_TEXT)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    def _build_layout(self):
        header = tk.Frame(self, bg=COLOR_PRIMARY, height=60)
        header.pack(fill="x", side="top")

        # Dropdown de Reservorio (solo UI por ahora)
        self.var_reservorio = tk.StringVar(value="Reservorio")

        reservorios = ["Reservorio"] + [f"Reservorio {i}" for i in range(1, 11)]

        # Estilo del combobox para que se vea “integrado” al header
        style = ttk.Style()
        style.configure(
            "Header.TCombobox",
            padding=(10, 6),
            foreground=COLOR_TEXT,
            fieldbackground=COLOR_WHITE,
            background=COLOR_WHITE,
        )
        style.map("Header.TCombobox", fieldbackground=[("readonly", COLOR_WHITE)])

        tk.Label(
            header,
            text="Cubicador de Pozas",
            bg=COLOR_PRIMARY,
            fg="white",
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left", padx=(14, 10), pady=12)

        cb = ttk.Combobox(
            header,
            textvariable=self.var_reservorio,
            values=reservorios,
            state="readonly",
            width=16,
            style="Header.TCombobox",
        )
        cb.pack(side="left", pady=12)
        cb.bind("<<ComboboxSelected>>", self._on_reservorio_changed)


        body = tk.Frame(self, bg=COLOR_BG)
        body.pack(fill="both", expand=True, padx=16, pady=16)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=COLOR_BG)
        right = tk.Frame(body, bg=COLOR_BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right.grid(row=0, column=1, sticky="nsew")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        dem_card = Card(left, title="Vista DEM")
        dem_card.grid(row=0, column=0, sticky="nsew")
        dem_card.rowconfigure(2, weight=1)
        dem_card.columnconfigure(0, weight=1)

        actions = tk.Frame(dem_card, bg=COLOR_WHITE)
        actions.grid(row=1, column=0, sticky="we", padx=12, pady=(0, 10))
        actions.columnconfigure(3, weight=1)

        ttk.Button(actions, text="Elegir DEM…", style="Primary.TButton", command=self.pick_dem)\
            .grid(row=0, column=0, sticky="w")
        ttk.Button(actions, text="Subir contorno…", style="Neutral.TButton", command=self.pick_mask)\
            .grid(row=0, column=1, padx=8, sticky="w")
        ttk.Checkbutton(actions, text="Usar contorno", variable=self.var_use_mask, command=self._set_paths_label)\
            .grid(row=0, column=2, padx=8, sticky="w")

        self.lbl_paths = tk.Label(actions, text="Sin DEM cargado", bg=COLOR_WHITE, fg=COLOR_SECONDARY, anchor="w")
        self.lbl_paths.grid(row=1, column=0, columnspan=4, sticky="we", pady=(8, 0))

        viewer_container = tk.Frame(dem_card, bg=COLOR_WHITE)
        viewer_container.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        viewer_container.rowconfigure(0, weight=1)
        viewer_container.columnconfigure(0, weight=1)

        self.viewer = DemViewer(viewer_container)
        self.viewer.grid(row=0, column=0, sticky="nsew")

        params_card = Card(right, title="Parámetros")
        params_card.grid(row=0, column=0, sticky="we", pady=(0, 12))
        params_card.columnconfigure(1, weight=1)

        self._add_param_row(params_card, 1, "Cota de sal (m):", self.var_salt)
        self._add_param_row(params_card, 2, "Cota pelo de agua (m):", self.var_water)
        self._add_param_row(params_card, 3, "Fracción ocluida (0-1):", self.var_occ)

        btns = tk.Frame(params_card, bg=COLOR_WHITE)
        btns.grid(row=4, column=0, columnspan=2, sticky="we", padx=12, pady=(8, 12))
        ttk.Button(btns, text="Calcular", style="Accent.TButton", command=self.calculate).pack(side="left")
        ttk.Button(btns, text="Exportar CSV (Abrir)", style="Primary.TButton", command=self.export_csv).pack(side="left", padx=8)
        ttk.Button(btns, text="Limpiar", style="Neutral.TButton", command=self.clear_results).pack(side="left")

        results_card = Card(right, title="Resultados")
        results_card.grid(row=1, column=0, sticky="nsew")
        results_card.rowconfigure(1, weight=1)
        results_card.columnconfigure(0, weight=1)

        table_frame = tk.Frame(results_card, bg=COLOR_WHITE)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        cols = ("valor", "unidad")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        self.tree.heading("valor", text="Valor")
        self.tree.heading("unidad", text="Unidad")
        self.tree.column("valor", width=180, anchor="e")
        self.tree.column("unidad", width=70, anchor="center")
        self.tree["show"] = "tree headings"
        self.tree.heading("#0", text="Item")
        self.tree.column("#0", width=330, anchor="w")

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self._set_paths_label()

    def _add_param_row(self, parent: tk.Frame, row: int, label: str, var: tk.StringVar):
        tk.Label(parent, text=label, bg=COLOR_WHITE, fg=COLOR_TEXT).grid(row=row, column=0, sticky="w", padx=12, pady=6)
        e = ttk.Entry(parent, textvariable=var)
        e.grid(row=row, column=1, sticky="we", padx=12, pady=6)

    def _set_paths_label(self):
        dem = self.dem_path if self.dem_path else "(sin DEM)"
        mask = self.mask_path if self.mask_path else "(sin contorno)"
        use = "Sí" if self.var_use_mask.get() and self.mask_path else "No"
        self.lbl_paths.config(text=f"DEM: {dem}   |   Contorno: {mask}   |   Usar contorno: {use}")

    def _dems_dir(self) -> Path:
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base) / "DEMs"
        return Path(__file__).resolve().parent.parent / "DEMs"

    def _on_reservorio_changed(self, event=None):
        value = self.var_reservorio.get()
        if value == "Reservorio":  # placeholder, sin selección real
            self.dem_path = None
            self.viewer.clear()
            self._set_paths_label()
            return
        # Extraer número del texto "Reservorio N"
        number = value.split()[-1]
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
        except Exception as e:
            messagebox.showerror("DEM", f"No se pudo cargar DEM:\n{e}")
            self.dem_path = None
        self._set_paths_label()

    def pick_dem(self):
        path = filedialog.askopenfilename(
            title="Selecciona el DEM",
            filetypes=[("GeoTIFF", "*.tif *.tiff"), ("Todos", "*.*")]
        )
        if not path:
            return
        self.dem_path = path
        try:
            renderer = DemRenderer(self.dem_path, scale_mode="minmax", stats_sample=1024)
            self.viewer.set_renderer(renderer)
        except Exception as e:
            messagebox.showerror("DEM", f"No se pudo cargar DEM:\n{e}")
        self._set_paths_label()

    def pick_mask(self):
        path = filedialog.askopenfilename(
            title="Selecciona contorno (GeoJSON recomendado)",
            filetypes=[("GeoJSON", "*.geojson *.json"), ("Shapefile", "*.shp"), ("Todos", "*.*")]
        )
        if not path:
            return
        self.mask_path = path
        self._set_paths_label()

    def _get_float(self, s: str, name: str) -> float:
        s = (s or "").strip().replace(",", ".")
        try:
            return float(s)
        except ValueError:
            raise ValueError(f"{name} debe ser numérico (ej. 2301.02).")

    def calculate(self):
        if not self.dem_path:
            messagebox.showerror("Falta DEM", "Selecciona un DEM primero.")
            return

        try:
            salt = self._get_float(self.var_salt.get(), "Cota de sal")
            water = self._get_float(self.var_water.get(), "Cota pelo de agua")
            occ = self._get_float(self.var_occ.get(), "Fracción ocluida")
            if not (0.0 <= occ <= 1.0):
                raise ValueError("Fracción ocluida debe estar entre 0 y 1 (ej. 0.20).")

            shapes = None
            if self.var_use_mask.get() and self.mask_path:
                shapes = load_mask_shapes(self.mask_path)

            dem = DemRaster(self.dem_path, mask_shapes=shapes).load()
            calc = PondVolumeCalculator(dem)
            res = calc.compute(salt, water, occluded_fraction=occ)

            self.latest_result = res
            self.latest_rows = res.to_rows()
            self._populate_table(self.latest_rows)

            # Advertencias de rango
            warnings = []
            if res.salt_level < res.dem_min or res.salt_level > res.dem_max:
                warnings.append(
                    f"  • Cota de sal ({res.salt_level:.2f} m) fuera del rango DEM "
                    f"[{res.dem_min:.2f} – {res.dem_max:.2f} m]."
                )
            if res.water_level < res.dem_min or res.water_level > res.dem_max:
                warnings.append(
                    f"  • Cota pelo de agua ({res.water_level:.2f} m) fuera del rango DEM "
                    f"[{res.dem_min:.2f} – {res.dem_max:.2f} m]."
                )
            if warnings:
                messagebox.showwarning(
                    "Advertencia de rango",
                    "Las siguientes cotas están fuera del rango de elevación del DEM\n"
                    f"(mín: {res.dem_min:.2f} m, máx: {res.dem_max:.2f} m):\n\n"
                    + "\n".join(warnings)
                    + "\n\nEl cálculo se realizó de todas formas, pero los resultados "
                    "pueden ser cero o incorrectos.",
                )

        except MaskError as e:
            messagebox.showerror("Contorno", str(e))
        except DemError as e:
            messagebox.showerror("DEM", str(e))
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _populate_table(self, rows: list[tuple[str, float, str]]):
        self.tree.delete(*self.tree.get_children())
        for item, value, unit in rows:
            if unit in ("m³", "m²", "kL", "ML"):
                v = fmt(value, 3)
            elif unit == "m":
                v = fmt(value, 2)
            elif unit == "-":
                v = fmt(value, 2)
            else:
                v = str(value)
            self.tree.insert("", "end", text=item, values=(v, unit))

    def export_csv(self):
        if not self.latest_rows:
            messagebox.showinfo("Exportar", "Primero calcula resultados.")
            return
        initial = default_output_name()
        path = filedialog.asksaveasfilename(
            title="Guardar CSV",
            defaultextension=".csv",
            initialfile=initial,
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            out = export_rows_to_csv(path, self.latest_rows)
            open_file_default_app(out)
        except Exception as e:
            messagebox.showerror("Exportar CSV", str(e))

    def clear_results(self):
        self.latest_result = None
        self.latest_rows = []
        self.tree.delete(*self.tree.get_children())


def main():
    app = App()
    app.mainloop()
