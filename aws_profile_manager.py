#!/usr/bin/env python3
"""

AWS Profile Manager
====================
Aplicación de escritorio (multiplataforma: Windows, macOS, Linux) para
gestionar profiles de AWS CLI: crear, actualizar, verificar y borrar,
sin necesidad de usar la terminal.

Requisitos:
    - Python 3.8+
    - Tkinter (ya viene incluido con Python en Windows y macOS)
    - boto3 (opcional, pero recomendado para "Verificar conexión")
        pip install boto3

Uso:
    python3 aws_profile_manager.py
    (en Windows, doble clic si tienes Python asociado a .py, o:
     py aws_profile_manager.py)

Instalacion: 
    py -m pip install pyinstaller
    py -m PyInstaller --onefile --windowed --name AWSProfileManager aws_profile_manager.py     
"""

import configparser
import os
import re
import subprocess
import sys
import threading
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

# ---------------------------------------------------------------------------
# Rutas de los archivos de configuración de AWS (mismas en Win/Mac/Linux,
# expanduser resuelve correctamente en cada sistema operativo)
# ---------------------------------------------------------------------------
AWS_DIR = os.path.expanduser("~/.aws")
CRED_FILE = os.environ.get("AWS_SHARED_CREDENTIALS_FILE", os.path.join(AWS_DIR, "credentials"))
CONFIG_FILE = os.environ.get("AWS_CONFIG_FILE", os.path.join(AWS_DIR, "config"))

DEFAULT_REGION = "us-east-1"
DEFAULT_OUTPUT = "json"

# Intento opcional de boto3 para verificar conexión sin depender de la CLI de AWS
try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


# ---------------------------------------------------------------------------
# Utilidades de bajo nivel (leer/escribir archivos de AWS)
# ---------------------------------------------------------------------------
def ensure_aws_dir():
    os.makedirs(AWS_DIR, exist_ok=True)


def read_profiles():
    """Devuelve la lista de nombres de profile a partir de ~/.aws/credentials."""
    cp = configparser.RawConfigParser()
    if os.path.exists(CRED_FILE):
        cp.read(CRED_FILE)
    profiles = list(cp.sections())
    if "default" not in profiles and os.path.exists(CRED_FILE):
        # el default a veces solo vive en config, revisamos también
        pass
    return sorted(profiles, key=lambda x: (x != "default", x.lower()))


def get_profile_values(profile):
    """Lee lo que ya está guardado para un profile (para mostrar, no las claves completas)."""
    cp = configparser.RawConfigParser()
    if os.path.exists(CRED_FILE):
        cp.read(CRED_FILE)
    data = {}
    if cp.has_section(profile):
        data.update(dict(cp.items(profile)))

    cp2 = configparser.RawConfigParser()
    if os.path.exists(CONFIG_FILE):
        cp2.read(CONFIG_FILE)
    section = "default" if profile == "default" else f"profile {profile}"
    if cp2.has_section(section):
        data.update(dict(cp2.items(section)))
    return data


def write_profile(profile, access_key, secret_key, session_token, region, output):
    """Escribe/actualiza un profile en credentials y config."""
    ensure_aws_dir()

    cp = configparser.RawConfigParser()
    if os.path.exists(CRED_FILE):
        cp.read(CRED_FILE)
    if not cp.has_section(profile):
        cp.add_section(profile)
    cp.set(profile, "aws_access_key_id", access_key)
    cp.set(profile, "aws_secret_access_key", secret_key)
    if session_token:
        cp.set(profile, "aws_session_token", session_token)
    elif cp.has_option(profile, "aws_session_token"):
        cp.remove_option(profile, "aws_session_token")
    with open(CRED_FILE, "w") as f:
        cp.write(f)
    try:
        os.chmod(CRED_FILE, 0o600)
    except OSError:
        pass  # chmod puede no aplicar igual en Windows, no es crítico

    cp2 = configparser.RawConfigParser()
    if os.path.exists(CONFIG_FILE):
        cp2.read(CONFIG_FILE)
    section = "default" if profile == "default" else f"profile {profile}"
    if not cp2.has_section(section):
        cp2.add_section(section)
    cp2.set(section, "region", region or DEFAULT_REGION)
    cp2.set(section, "output", output or DEFAULT_OUTPUT)
    with open(CONFIG_FILE, "w") as f:
        cp2.write(f)


def delete_profiles(profiles, make_backup=False):
    """Borra uno o varios profiles de credentials y config. Devuelve la ruta de backup si se hizo."""
    backup_suffix = None
    if make_backup:
        backup_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
        if os.path.exists(CRED_FILE):
            with open(CRED_FILE, "rb") as src, open(f"{CRED_FILE}.bak.{backup_suffix}", "wb") as dst:
                dst.write(src.read())
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "rb") as src, open(f"{CONFIG_FILE}.bak.{backup_suffix}", "wb") as dst:
                dst.write(src.read())

    cp = configparser.RawConfigParser()
    if os.path.exists(CRED_FILE):
        cp.read(CRED_FILE)
    for name in profiles:
        if cp.has_section(name):
            cp.remove_section(name)
    with open(CRED_FILE, "w") as f:
        cp.write(f)

    cp2 = configparser.RawConfigParser()
    if os.path.exists(CONFIG_FILE):
        cp2.read(CONFIG_FILE)
    for name in profiles:
        section = "default" if name == "default" else f"profile {name}"
        if cp2.has_section(section):
            cp2.remove_section(section)
    with open(CONFIG_FILE, "w") as f:
        cp2.write(f)

    return backup_suffix


def mask(value):
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * 8
    return f"{value[:4]}{'•' * 8}{value[-4:]}"


def parse_pasted_credentials(text):
    """Extrae ACCESS_KEY, SECRET_KEY y SESSION_TOKEN de un bloque de texto pegado,
    aceptando tanto formato 'export VAR=valor' como 'VAR=valor' o 'VAR = valor'."""
    def find(var):
        m = re.search(rf'{var}\s*=\s*"?([^"\s]+)"?', text)
        return m.group(1) if m else ""

    return {
        "access_key": find("AWS_ACCESS_KEY_ID"),
        "secret_key": find("AWS_SECRET_ACCESS_KEY"),
        "session_token": find("AWS_SESSION_TOKEN"),
    }


def verify_identity(profile):
    """Intenta 'aws sts get-caller-identity'. Usa boto3 si está disponible,
    si no, intenta invocar el comando 'aws' de la CLI (si está instalado)."""
    if HAS_BOTO3:
        session = boto3.Session(profile_name=profile)
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        return {
            "Account": identity.get("Account", ""),
            "UserId": identity.get("UserId", ""),
            "Arn": identity.get("Arn", ""),
        }

    # Fallback: usar la CLI de aws si está en el PATH
    aws_cmd = "aws.exe" if sys.platform.startswith("win") else "aws"
    result = subprocess.run(
        [aws_cmd, "sts", "get-caller-identity", "--profile", profile, "--output", "json"],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "No se pudo verificar la identidad.")
    import json
    identity = json.loads(result.stdout)
    return {
        "Account": identity.get("Account", ""),
        "UserId": identity.get("UserId", ""),
        "Arn": identity.get("Arn", ""),
    }


# ---------------------------------------------------------------------------
# Interfaz gráfica
# ---------------------------------------------------------------------------
class AWSProfileManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AWS Profile Manager")
        self.geometry("1020x800")
        self.minsize(860, 760)
        self.configure(bg="#f3f6fb")
        resource_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        icon_name = "aws-profile-manager-icon.ico" if sys.platform.startswith("win") else "aws-profile-manager-icon.png"
        icon_path = os.path.join(resource_dir, icon_name)
        if os.path.isfile(icon_path):
            if sys.platform.startswith("win"):
                self.iconbitmap(icon_path)
            else:
                self._window_icon = tk.PhotoImage(file=icon_path)
                self.iconphoto(True, self._window_icon)

        self._build_style()
        self._build_layout()
        self.refresh_profiles()

        if not HAS_BOTO3:
            self.log(
                "⚠ boto3 no está instalado: la verificación de conexión usará la "
                "CLI de AWS si existe, o se omitirá. Para mejor soporte instala con:\n"
                "    pip install boto3"
            )

    # -- estilo ------------------------------------------------------------
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#f3f6fb")
        style.configure("Card.TFrame", background="#ffffff", borderwidth=1, relief="solid")
        style.configure("Inner.TFrame", background="#ffffff", borderwidth=0, relief="flat")
        style.configure("Header.TLabel", background="#f3f6fb", foreground="#172554",
                        font=("Segoe UI", 20, "bold"))
        style.configure("SubHeader.TLabel", background="#f3f6fb", foreground="#64748b",
                        font=("Segoe UI", 9))
        style.configure("Section.TLabel", background="#f3f6fb", foreground="#172554",
                        font=("Segoe UI", 10, "bold"))
        style.configure("CardTitle.TLabel", background="#ffffff", foreground="#172554",
                        font=("Segoe UI", 11, "bold"))
        style.configure("Field.TLabel", background="#ffffff", foreground="#334155",
                        font=("Segoe UI", 9, "bold"))
        style.configure("Hint.TLabel", background="#ffffff", foreground="#64748b",
                        font=("Segoe UI", 9))
        style.configure("TEntry", padding=(8, 4), fieldbackground="#ffffff",
                        foreground="#172554")
        style.map("TEntry", bordercolor=[("focus", "#3b82f6")])
        style.configure("TCombobox", padding=(8, 4), fieldbackground="#ffffff")
        style.configure("TButton", padding=(9, 5), font=("Segoe UI", 9))
        style.configure("Primary.TButton", background="#2563eb", foreground="#ffffff",
                        font=("Segoe UI", 9, "bold"), padding=(10, 6))
        style.map("Primary.TButton",
                  background=[("active", "#1d4ed8"), ("pressed", "#1e40af")],
                  foreground=[("disabled", "#cbd5e1")])
        style.configure("Secondary.TButton", background="#eff6ff", foreground="#1d4ed8")
        style.map("Secondary.TButton", background=[("active", "#dbeafe")])
        style.configure("Danger.TButton", background="#fff1f2", foreground="#be123c")
        style.map("Danger.TButton", background=[("active", "#ffe4e6")])
        style.map("Secondary.TButton", foreground=[("disabled", "#94a3b8")])

    # -- layout general ------------------------------------------------------
    def _build_layout(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=3)
        self.rowconfigure(3, weight=1, minsize=150)

        header = ttk.Frame(self, padding=(24, 20, 24, 12))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="AWS Profile Manager", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text=f"Administra tus perfiles de AWS CLI  ·  credentials: {CRED_FILE}  ·  config: {CONFIG_FILE}",
            style="SubHeader.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        body = ttk.Frame(self, padding=(24, 4, 24, 16))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=2, uniform="columns")
        body.rowconfigure(0, weight=1)

        # ---- columna izquierda: lista de profiles ----
        left = ttk.Frame(body, style="Card.TFrame", padding=16)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        ttk.Label(left, text="Perfiles", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )

        list_frame = ttk.Frame(left, style="Card.TFrame", padding=4)
        list_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(
            list_frame, exportselection=False, selectmode="extended", height=15,
            bg="#f8fafc", fg="#1e293b", selectbackground="#dbeafe",
            selectforeground="#1d4ed8", activestyle="none", relief="flat",
            highlightthickness=1, highlightbackground="#e2e8f0",
            highlightcolor="#93c5fd", font=("Segoe UI", 10), borderwidth=0,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self._on_select_profile)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=1)
        self.listbox.config(yscrollcommand=scrollbar.set)

        btn_row = ttk.Frame(left, style="Inner.TFrame")
        btn_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(btn_row, text="Actualizar", style="Secondary.TButton",
                   command=self.refresh_profiles).pack(fill="x", pady=(0, 6))
        ttk.Button(btn_row, text="＋  Nuevo perfil", style="Secondary.TButton",
                   command=self._new_profile).pack(fill="x", pady=(0, 6))
        ttk.Button(btn_row, text="Borrar seleccionados", style="Danger.TButton",
                   command=self._delete_selected).pack(fill="x")

        # ---- columna derecha: detalle / edición ----
        right = ttk.Frame(body, style="Card.TFrame", padding=16)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)

        ttk.Label(right, text="Editar perfil", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        ttk.Label(right, text="Nombre del perfil", style="Field.TLabel").grid(
            row=1, column=0, sticky="w", pady=4, padx=(0, 12)
        )
        self.profile_var = tk.StringVar()
        self.profile_entry = ttk.Entry(right, textvariable=self.profile_var)
        self.profile_entry.grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(right, text="Credenciales rápidas", style="Field.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 3)
        )
        ttk.Label(right, text="Pega aquí las variables AWS_... o usa los campos de abajo.",
                  style="Hint.TLabel").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        # Caja redimensionable: alto inicial fijo, se agranda arrastrando la barra inferior
        self._paste_min_h = 70
        paste_frame = tk.Frame(right, bg="#ffffff", height=self._paste_min_h)
        paste_frame.grid(row=4, column=0, columnspan=2, sticky="ew")
        paste_frame.pack_propagate(False)
        self._paste_frame = paste_frame

        grip = tk.Frame(paste_frame, bg="#e2e8f0", height=7, cursor="sb_v_double_arrow")
        grip.pack(side="bottom", fill="x")
        grip.bind("<Button-1>", self._grip_start)
        grip.bind("<B1-Motion>", self._grip_drag)

        self.paste_box = tk.Text(
            paste_frame, wrap="word", bg="#f8fafc", fg="#1e293b",
            insertbackground="#1e293b", relief="flat", highlightthickness=1,
            highlightbackground="#e2e8f0", highlightcolor="#93c5fd",
            font=("Consolas", 9), padx=9, pady=8,
        )
        self.paste_box.pack(side="top", fill="both", expand=True)

        form = ttk.Frame(right, style="Inner.TFrame", padding=(10, 0))
        form.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        form.columnconfigure(1, weight=1)

        self.access_key_var = tk.StringVar()
        self.secret_key_var = tk.StringVar()
        self.session_token_var = tk.StringVar()
        self.region_var = tk.StringVar(value=DEFAULT_REGION)
        self.output_var = tk.StringVar(value=DEFAULT_OUTPUT)

        ttk.Label(form, text="Access Key ID", style="Field.TLabel").grid(
            row=0, column=0, sticky="w", pady=2, padx=(0, 12)
        )
        ttk.Entry(form, textvariable=self.access_key_var).grid(
            row=0, column=1, sticky="ew", pady=2
        )

        ttk.Label(form, text="Secret Access Key", style="Field.TLabel").grid(
            row=1, column=0, sticky="w", pady=2, padx=(0, 12)
        )
        ttk.Entry(form, textvariable=self.secret_key_var, show="•").grid(
            row=1, column=1, sticky="ew", pady=2
        )

        ttk.Label(form, text="Session Token (opcional)", style="Field.TLabel").grid(
            row=2, column=0, sticky="w", pady=2, padx=(0, 12)
        )
        ttk.Entry(form, textvariable=self.session_token_var, show="•").grid(
            row=2, column=1, sticky="ew", pady=2
        )

        ttk.Label(form, text="Región", style="Field.TLabel").grid(
            row=3, column=0, sticky="w", pady=2, padx=(0, 12)
        )
        ttk.Entry(form, textvariable=self.region_var).grid(
            row=3, column=1, sticky="ew", pady=2
        )

        ttk.Label(form, text="Formato de salida", style="Field.TLabel").grid(
            row=4, column=0, sticky="w", pady=2, padx=(0, 12)
        )
        output_combo = ttk.Combobox(form, textvariable=self.output_var, values=["json", "text", "table"], state="readonly")
        output_combo.grid(row=4, column=1, sticky="ew", pady=2)

        action_row = ttk.Frame(right, style="Inner.TFrame", padding=(10, 0))
        action_row.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(action_row, text="Extraer credenciales", style="Secondary.TButton",
                   command=self._parse_pasted).pack(side="left")
        ttk.Button(action_row, text="Guardar perfil", style="Primary.TButton",
                   command=self._save_profile).pack(side="left", padx=(8, 0))
        self.verify_btn = ttk.Button(action_row, text="Verificar conexión", style="Secondary.TButton",
                                     command=self._verify_connection_async)
        self.verify_btn.pack(side="left", padx=(8, 0))

        # El botón solo se habilita si el perfil está guardado y el formulario no tiene cambios
        for var in (self.profile_var, self.access_key_var, self.secret_key_var,
                    self.session_token_var, self.region_var, self.output_var):
            var.trace_add("write", lambda *_: self._update_verify_state())
        self._update_verify_state()

        # ---- log / resultados ----
        ttk.Label(self, text="Actividad", style="Section.TLabel").grid(
            row=2, column=0, sticky="w", padx=24, pady=(0, 6)
        )
        log_frame = ttk.Frame(self, padding=(24, 0, 24, 20))
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_box = tk.Text(
            log_frame, height=8, state="disabled", wrap="word",
            bg="#172554", fg="#dbeafe", insertbackground="#dbeafe",
            relief="flat", font=("Consolas", 9), padx=12, pady=10,
        )
        self.log_box.grid(row=0, column=0, sticky="nsew")

    def _is_profile_saved(self):
        """True si el perfil existe en disco y el formulario coincide con lo guardado."""
        profile = self.profile_var.get().strip()
        if not profile or profile not in read_profiles():
            return False
        saved = get_profile_values(profile)
        return (
            self.access_key_var.get().strip() == saved.get("aws_access_key_id", "")
            and self.secret_key_var.get().strip() == saved.get("aws_secret_access_key", "")
            and self.session_token_var.get().strip() == saved.get("aws_session_token", "")
            and (self.region_var.get().strip() or DEFAULT_REGION) == saved.get("region", DEFAULT_REGION)
            and (self.output_var.get().strip() or DEFAULT_OUTPUT) == saved.get("output", DEFAULT_OUTPUT)
        )

    def _update_verify_state(self):
        self.verify_btn.state(["!disabled"] if self._is_profile_saved() else ["disabled"])

    # -- redimensionar caja de pegado --------------------------------------
    def _grip_start(self, event):
        self._grip_y0 = event.y_root
        self._grip_h0 = self._paste_frame.winfo_height()

    def _grip_drag(self, event):
        new_h = max(self._paste_min_h, self._grip_h0 + (event.y_root - self._grip_y0))
        self._paste_frame.configure(height=new_h)

    # -- helpers de log ------------------------------------------------------
    def log(self, message):
        self.log_box.config(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{timestamp}] {message}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    # -- acciones ------------------------------------------------------------
    def refresh_profiles(self):
        self.listbox.delete(0, "end")
        for p in read_profiles():
            label = f"{p}  (default)" if p == "default" else p
            self.listbox.insert("end", label)
        self.log("Lista de profiles actualizada.")
        if hasattr(self, "verify_btn"):
            self._update_verify_state()

    def _selected_profile_names(self):
        names = []
        for i in self.listbox.curselection():
            raw = self.listbox.get(i)
            names.append(raw.split("  (default)")[0] if raw.endswith("(default)") else raw)
        return names

    def _on_select_profile(self, _event=None):
        names = self._selected_profile_names()
        if len(names) != 1:
            return
        profile = names[0]
        self.profile_var.set(profile)
        values = get_profile_values(profile)
        self.access_key_var.set(values.get("aws_access_key_id", ""))
        self.secret_key_var.set(values.get("aws_secret_access_key", ""))
        self.session_token_var.set(values.get("aws_session_token", ""))
        self.region_var.set(values.get("region", DEFAULT_REGION))
        self.output_var.set(values.get("output", DEFAULT_OUTPUT))
        self.paste_box.delete("1.0", "end")

    def _new_profile(self):
        name = simpledialog.askstring("Nuevo profile", "Nombre del nuevo profile:", parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        self.profile_var.set(name)
        self.access_key_var.set("")
        self.secret_key_var.set("")
        self.session_token_var.set("")
        self.region_var.set(DEFAULT_REGION)
        self.output_var.set(DEFAULT_OUTPUT)
        self.paste_box.delete("1.0", "end")
        self.log(f"Listo para crear el profile '{name}'. Completa las credenciales y guarda.")

    def _parse_pasted(self):
        text = self.paste_box.get("1.0", "end")
        parsed = parse_pasted_credentials(text)
        if not parsed["access_key"] or not parsed["secret_key"]:
            messagebox.showwarning(
                "No se encontraron credenciales",
                "No pude encontrar AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY en el texto pegado.",
            )
            return
        self.access_key_var.set(parsed["access_key"])
        self.secret_key_var.set(parsed["secret_key"])
        self.session_token_var.set(parsed["session_token"])
        self.paste_box.delete("1.0", "end")
        self.log("Credenciales extraídas del texto pegado.")

    def _save_profile(self):
        profile = self.profile_var.get().strip()
        access_key = self.access_key_var.get().strip()
        secret_key = self.secret_key_var.get().strip()
        session_token = self.session_token_var.get().strip()
        region = self.region_var.get().strip() or DEFAULT_REGION
        output = self.output_var.get().strip() or DEFAULT_OUTPUT

        if not profile:
            messagebox.showerror("Falta el nombre", "Indica un nombre de profile.")
            return
        if not access_key or not secret_key:
            messagebox.showerror("Faltan credenciales", "Access Key y Secret Key son obligatorios.")
            return

        try:
            write_profile(profile, access_key, secret_key, session_token, region, output)
        except OSError as e:
            messagebox.showerror("Error al guardar", str(e))
            return

        self.log(
            f"✔ Profile '{profile}' guardado. "
            f"Access Key: {mask(access_key)}  Secret Key: {mask(secret_key)}  "
            f"Session Token: {'presente' if session_token else 'no incluido'}"
        )
        self.refresh_profiles()

    def _delete_selected(self):
        names = self._selected_profile_names()
        if not names:
            messagebox.showinfo("Nada seleccionado", "Selecciona uno o más profiles de la lista para borrar.")
            return

        if not messagebox.askyesno(
            "Confirmar borrado",
            f"¿Seguro que quieres borrar estos profiles?\n\n{', '.join(names)}",
        ):
            return

        make_backup = messagebox.askyesno(
            "Backup",
            "¿Quieres guardar un backup de credentials/config antes de borrar?",
        )

        try:
            backup_suffix = delete_profiles(names, make_backup=make_backup)
        except OSError as e:
            messagebox.showerror("Error al borrar", str(e))
            return

        if backup_suffix:
            self.log(f"🗑️  Borrados: {', '.join(names)}. Backup con sufijo .bak.{backup_suffix}")
        else:
            self.log(f"🗑️  Borrados: {', '.join(names)} (sin backup).")
        self.refresh_profiles()

    def _verify_connection_async(self):
        profile = self.profile_var.get().strip()
        if not self._is_profile_saved():
            return
        self.log(f"Verificando conexión para '{profile}'…")
        threading.Thread(target=self._verify_connection, args=(profile,), daemon=True).start()

    def _verify_connection(self, profile):
        try:
            identity = verify_identity(profile)
        except Exception as e:  # noqa: BLE001 - queremos mostrar cualquier error al usuario
            self.after(0, lambda: self.log(f"✖ No se pudo verificar la conexión: {e}"))
            return
        self.after(
            0,
            lambda: self.log(
                "✔ Conexión exitosa — "
                f"Account: {identity['Account']}  UserId: {identity['UserId']}  Arn: {identity['Arn']}"
            ),
        )


def main():
    app = AWSProfileManager()
    app.mainloop()


if __name__ == "__main__":
    main()
