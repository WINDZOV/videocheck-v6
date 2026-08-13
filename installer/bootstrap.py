#!/usr/bin/env python3
"""
bootstrap.py — the "no tech-savvy required" installer core for VideoCheck.

This is frozen by PyInstaller into VideoCheckInstallerCore.exe, which in
turn gets wrapped by Inno Setup (see installer/VideoCheck.iss) into the
final VideoCheck-Setup.exe a normal Windows user downloads and double-clicks
— Welcome screen, progress, Start Menu + Desktop icon, and a real entry in
"Add or Remove Programs" with a working uninstaller. This script is the
part that does the actual work behind that wizard: find/install Python,
copy the project, create a venv, detect hardware, install the matching
dependencies, and set up launchers.

It does NOT bundle torch/ultralytics directly — those are multi-GB and
hardware-specific (CUDA vs CPU vs Apple Silicon), so shipping one binary
with all of them would either be enormous or wrong for most machines.

Two front ends share the same run_install() logic:
  - main_gui()      a small pywebview progress window (used by default —
                     this is what end users see, no console at all)
  - main_console()  plain stdout, used automatically as a fallback if
                     pywebview/its native runtime isn't available, or
                     explicitly for developer testing with --console

Run standalone for testing:
    python bootstrap.py                    # graphical, installs to ~/VideoCheck
    python bootstrap.py --console          # plain console output
    python bootstrap.py --install-dir "C:\\Some\\Path"   # custom target (Inno passes this)
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

APP_NAME = "VideoCheck"
MIN_PYTHON = (3, 10)


def _hidden_subprocess_kwargs() -> dict:
    """
    Every subprocess.run() call below would otherwise flash its own console
    window — Windows spawns a fresh console for each child process by
    default, EVEN when the parent itself was built with --windowed (no
    console). This is what was showing cmd after pressing the .exe: not the
    installer's own window, but each 'python -m venv', 'pip install', etc.
    call underneath it.
    """
    if platform.system() == "Windows":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}

# When frozen by PyInstaller, bundled files live under sys._MEIPASS.
# When run as a plain script, they live at the project root (one level up
# from installer/) — see build_windows.bat / build_mac.sh for --add-data.
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))

PROJECT_FILES = [
    "video_check.py",
    "preinstall.py",
    "pyproject.toml",
    "dashboard.html",
    "Makefile",
]
PROJECT_DIRS = [
    "src",  # the videocheck/ package: backends, detector, clipper, pipeline...
]


def log(msg: str) -> None:
    print(f"[VideoCheck installer] {msg}", flush=True)


def _native_message_box(title: str, msg: str) -> None:
    """Last-resort feedback when there's no console AND no webview available
    (e.g. --windowed build with pywebview missing/broken). Uses only the
    stdlib so it always works."""
    try:
        if platform.system() == "Windows":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, title, 0x40)  # MB_ICONINFORMATION
        elif platform.system() == "Darwin":
            subprocess.run([
                "osascript", "-e",
                f'display dialog "{msg}" with title "{title}" buttons {{"OK"}}',
            ])
        else:
            log(f"{title}: {msg}")
    except Exception:
        log(f"{title}: {msg}")


def default_install_dir() -> Path:
    return Path.home() / APP_NAME


# ── Find or fetch Python ──────────────────────────────────────────────────

def find_system_python() -> str | None:
    candidates = ["python3", "python"]
    if platform.system() == "Windows":
        candidates = ["python", "py"]
    for exe in candidates:
        path = shutil.which(exe)
        if not path:
            continue
        try:
            out = subprocess.run(
                [path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10,
                **_hidden_subprocess_kwargs(),
            ).stdout.decode()
            ver = tuple(int(p) for p in out.strip().split()[1].split(".")[:2])
            if ver >= MIN_PYTHON:
                return path
        except Exception:
            continue
    return None


def fetch_windows_python_installer(dest: Path) -> Path:
    url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
    log(f"Descargando instalador de Python desde {url} ...")
    urllib.request.urlretrieve(url, dest)
    return dest


def ensure_python() -> str:
    py = find_system_python()
    if py:
        log(f"Python encontrado: {py}")
        return py

    system = platform.system()
    log("No se encontró un Python adecuado (se necesita 3.10+).")

    if system == "Windows":
        installer = Path.home() / "AppData" / "Local" / "Temp" / "python-installer.exe"
        fetch_windows_python_installer(installer)
        log("Instalando Python (esto puede tardar un minuto)...")
        subprocess.run(
            [str(installer), "/quiet", "InstallAllUsers=0", "PrependPath=1"],
            check=True, **_hidden_subprocess_kwargs(),
        )
        py = find_system_python()
        if py:
            return py
        raise RuntimeError(
            "Python se instaló pero 'python' sigue sin encontrarse. "
            "Reinicia el ordenador y vuelve a ejecutar el instalador."
        )

    if system == "Darwin":
        raise RuntimeError(
            "Se necesita Python 3.10+ y no se encontró.\n"
            "Instálalo desde https://www.python.org/downloads/macos/\n"
            "(o con 'brew install python') y vuelve a ejecutar el instalador."
        )

    raise RuntimeError("Se necesita Python 3.10+ y no se encontró.")


# ── Copy project / venv / deps ──────────────────────────────────────────

def copy_project_files(install_dir: Path) -> None:
    install_dir.mkdir(parents=True, exist_ok=True)
    for name in PROJECT_FILES:
        src = BUNDLE_DIR / name
        if src.exists():
            shutil.copy2(src, install_dir / name)
    for name in PROJECT_DIRS:
        src = BUNDLE_DIR / name
        if not src.exists():
            continue
        dest = install_dir / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
    for sub in ("videosrc", "clips", "empty_videos", "originals_processed", "corrupted"):
        (install_dir / sub).mkdir(exist_ok=True)


def create_venv(python_exe: str, install_dir: Path) -> Path:
    venv_dir = install_dir / "venv"
    if not venv_dir.exists():
        subprocess.run([python_exe, "-m", "venv", str(venv_dir)], check=True,
                         **_hidden_subprocess_kwargs())
    return venv_dir / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")


def install_dependencies(venv_python: Path, install_dir: Path) -> None:
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
        check=True, cwd=install_dir, **_hidden_subprocess_kwargs(),
    )
    subprocess.run(
        [str(venv_python), "preinstall.py", "--install"], check=True, cwd=install_dir,
        **_hidden_subprocess_kwargs(),
    )


def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


# ── Launcher + shortcut ─────────────────────────────────────────────────

def write_launchers(install_dir: Path, venv_python: Path) -> Path:
    system = platform.system()
    if system == "Windows":
        # pythonw.exe has no console subsystem at all — that (plus running
        # a raw .bat, which Windows always flashes a console window for) is
        # exactly why a black terminal was showing up. venv creates
        # pythonw.exe right alongside python.exe. Launching through a .vbs
        # with WScript.Shell.Run(..., 0, False) additionally guarantees no
        # window of any kind flashes, regardless of file-association quirks.
        pythonw = venv_python.parent / "pythonw.exe"
        if not pythonw.exists():
            pythonw = venv_python  # unusual venv without pythonw — fall back

        launcher = install_dir / "run_videocheck.vbs"
        launcher.write_text(
            'Set objShell = CreateObject("WScript.Shell")\r\n'
            f'objShell.CurrentDirectory = "{install_dir}"\r\n'
            f'objShell.Run """{pythonw}"" ""video_check.py"" --serve", 0, False\r\n'
        )
    else:
        launcher = install_dir / "run_videocheck.command"
        launcher.write_text(
            f'#!/bin/bash\n'
            f'cd "{install_dir}"\n'
            f'"{venv_python}" video_check.py --serve\n'
        )
        launcher.chmod(0o755)
    return launcher


def _find_desktop() -> Path | None:
    """Classic Desktop, or OneDrive-redirected Desktop (common on Windows
    machines signed in with a Microsoft account)."""
    for candidate in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        if candidate.exists():
            return candidate
    return None


_OLD_SHORTCUT_NAMES = ("run_videocheck.bat", "run_videocheck.vbs", "VideoCheck.lnk")


def create_desktop_shortcut(launcher: Path, venv_python: Path) -> None:
    """
    Only used when running WITHOUT the Inno Setup wrapper (e.g. standalone
    testing) — Inno's own [Icons] section creates a proper Start Menu +
    Desktop shortcut, so run_install() skips calling this when invoked
    with --no-shortcut (Inno passes that flag).
    """
    desktop = _find_desktop()
    if not desktop:
        log(f"(no se encontró carpeta de Escritorio — omitiendo acceso directo. Ejecuta directamente: {launcher})")
        return

    # Clean up whatever a previous run/version left behind, so re-running
    # the installer never leaves two (or three) icons on the Desktop.
    for name in _OLD_SHORTCUT_NAMES:
        old = desktop / name
        if old.exists():
            try:
                old.unlink()
            except Exception:
                pass

    if platform.system() == "Windows":
        _create_windows_lnk(launcher, venv_python, desktop / "VideoCheck.lnk")
        return

    try:
        shortcut = desktop / launcher.name
        if shortcut.exists():
            shortcut.unlink()
        shortcut.symlink_to(launcher)
        log(f"Acceso directo creado: {shortcut}")
    except Exception as exc:
        log(f"(no se pudo crear el acceso directo: {exc} — puedes ejecutar {launcher} directamente)")


def _create_windows_lnk(launcher: Path, venv_python: Path, lnk_path: Path) -> None:
    """
    A real Windows .lnk shortcut — proper icon, proper name in Explorer —
    instead of just copying the .vbs launcher file (which shows up with the
    generic "script file" icon). Created via WScript.Shell.CreateShortcut,
    run once through wscript.exe (the windowless VBScript host, as opposed
    to cscript.exe which would flash a console) — no extra dependency,
    no window of any kind.
    """
    pythonw = venv_python.parent / "pythonw.exe"
    icon_source = pythonw if pythonw.exists() else venv_python

    vbs_helper = Path(os.environ.get("TEMP", str(launcher.parent))) / "videocheck_make_shortcut.vbs"
    vbs_helper.write_text(
        'Set WshShell = WScript.CreateObject("WScript.Shell")\r\n'
        f'Set link = WshShell.CreateShortcut("{lnk_path}")\r\n'
        f'link.TargetPath = "{launcher}"\r\n'
        f'link.WorkingDirectory = "{launcher.parent}"\r\n'
        f'link.IconLocation = "{icon_source}, 0"\r\n'
        'link.Description = "VideoCheck"\r\n'
        'link.Save\r\n'
    )
    try:
        subprocess.run(["wscript.exe", str(vbs_helper)], check=True, **_hidden_subprocess_kwargs())
        log(f"Direct access created: {lnk_path}")
    except Exception as exc:
        log(f"(the direct access couldn't be created: {exc} — you can execute {launcher} directly)")
    finally:
        try:
            vbs_helper.unlink()
        except Exception:
            pass


# ── Orchestration ─────────────────────────────────────────────────────

def run_install(install_dir_override: str | None = None,
                 skip_shortcut: bool = False, on_progress=None) -> Path:
    """
    Runs every install step, reporting (pct: int, message: str) through
    on_progress if given. Returns the launcher path. Raises on failure.
    """
    def report(pct: int, msg: str) -> None:
        log(msg)
        if on_progress:
            on_progress(pct, msg)

    report(5, "Searching the Python installation...")
    python_exe = ensure_python()

    install_dir = Path(install_dir_override) if install_dir_override else default_install_dir()
    report(15, f"Instalando en: {install_dir}")
    copy_project_files(install_dir)
    report(30, "Program files copied.")

    report(35, "Creating isolated Pyton env...")
    venv_python = create_venv(python_exe, install_dir)
    report(45, "Environement ready.")

    report(50, "Detecting your hardware (GPU/CPU) and installing components — this may take a few minuts...")
    install_dependencies(venv_python, install_dir)
    report(90, "Componentes intsalled.")

    launcher = write_launchers(install_dir, venv_python)
    if not skip_shortcut:
        create_desktop_shortcut(launcher, venv_python)
    report(97, "Final configuraton...")

    if not check_ffmpeg():
        report(98, "Attention: ffmpeg not found. VideoCheck needs it to cut the video into clips "
                    "(install it with 'winget install ffmpeg' o from ffmpeg.org).")

    report(100, f"Installation completed in  {install_dir}")
    return launcher


# ── Console front end (fallback / dev testing) ──────────────────────────

def main_console(install_dir_override: str | None, skip_shortcut: bool) -> None:
    stdin_available = sys.stdin is not None and sys.stdin.isatty()

    def _pause() -> None:
        if stdin_available:
            try:
                input("\nPress Enter to close this window...")
            except RuntimeError:
                pass  # no attached console — nothing to wait on

    try:
        launcher = run_install(install_dir_override, skip_shortcut=skip_shortcut)
        log("")
        log(f"👉  Double click on '{launcher.name}' to open the program.")
        if stdin_available:
            _pause()
        else:
            _native_message_box(
                "VideoCheck Installed",
                f"Installation completed.\n\nHaz double click '{launcher.name}' to open th eprogram.",
            )
    except Exception as exc:
        log(f"\n✗  La instalación falló: {exc}")
        if stdin_available:
            _pause()
            sys.exit(1)
        else:
            _native_message_box("Installation error", f"The installation failed:\n\n{exc}")


# ── Graphical front end (what end users see) ────────────────────────────
#
# Tkinter, not pywebview, on purpose: it ships with the Python standard
# library, so it works on every Windows machine with zero extra runtime —
# no dependency on the Microsoft Edge WebView2 Runtime being present, which
# a bare/minimal Windows install (e.g. a fresh VM) may not have. The actual
# VideoCheck app (desktop.py, launched AFTER install) uses pywebview, which
# is the right call there — a normal end user's real Windows almost
# certainly has WebView2 — but the installer itself is the one place that
# has to work everywhere, unconditionally.

_BG = "#0f1115"
_PANEL = "#171a21"
_BORDER = "#2a2e38"
_TEXT = "#e6e8ec"
_MUTED = "#8b909c"
_ACCENT = "#4f8cff"
_BAD = "#e05c5c"


def main_gui(install_dir_override: str | None, skip_shortcut: bool) -> None:
    import queue
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("VideoCheck — Installation")
    root.geometry("560x460")
    root.resizable(False, False)
    root.configure(bg=_BG)

    tk.Label(root, text="🎬  Installing VideoCheck", bg=_BG, fg=_TEXT,
              font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=24, pady=(24, 4))
    tk.Label(root, text="Prearing packages to install — this may take a few minutes.",
              bg=_BG, fg=_MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=24, pady=(0, 16))

    style = ttk.Style(root)
    style.theme_use("default")
    style.configure("VC.Horizontal.TProgressbar", troughcolor=_PANEL,
                     background=_ACCENT, bordercolor=_PANEL, lightcolor=_ACCENT, darkcolor=_ACCENT)

    bar_row = tk.Frame(root, bg=_BG)
    bar_row.pack(fill="x", padx=24)
    progress_var = tk.DoubleVar(value=0)
    bar = ttk.Progressbar(bar_row, variable=progress_var, maximum=100,
                            style="VC.Horizontal.TProgressbar", length=460)
    bar.pack(side="left")
    pct_label = tk.Label(bar_row, text="0%", bg=_BG, fg=_ACCENT, font=("Segoe UI", 9, "bold"), width=5)
    pct_label.pack(side="left", padx=(8, 0))

    status_var = tk.StringVar(value="Iniciando...")
    status_label = tk.Label(root, textvariable=status_var, bg=_BG, fg=_MUTED, font=("Segoe UI", 9),
                              anchor="w", justify="left", wraplength=512)
    status_label.pack(fill="x", padx=24, pady=(10, 12))

    log_frame = tk.Frame(root, bg=_PANEL, highlightbackground=_BORDER, highlightthickness=1)
    log_frame.pack(padx=24, fill="both", expand=True)
    log_text = tk.Text(log_frame, bg=_PANEL, fg=_MUTED, font=("Consolas", 9), height=9,
                         wrap="word", relief="flat", state="disabled", bd=0, padx=8, pady=8)
    log_text.pack(fill="both", expand=True)

    actions = tk.Frame(root, bg=_BG)
    launch_state: dict = {"launcher": None}

    def _open_launcher() -> None:
        launcher = launch_state.get("launcher")
        if not launcher:
            return
        try:
            if platform.system() == "Windows":
                os.startfile(str(launcher))  # noqa: S606 — launching our own generated script
            else:
                subprocess.Popen(["open", str(launcher)])
        except Exception as exc:
            log(f"No se pudo abrir VideoCheck automáticamente: {exc}")
        root.destroy()

    def _close() -> None:
        root.destroy()

    launch_btn = tk.Button(actions, text="Abrir VideoCheck", command=_open_launcher,
                             bg=_ACCENT, fg="white", relief="flat", padx=16, pady=6,
                             font=("Segoe UI", 9, "bold"), cursor="hand2")
    close_btn = tk.Button(actions, text="Cerrar", command=_close,
                            bg="#262b36", fg=_TEXT, relief="flat", padx=16, pady=6,
                            font=("Segoe UI", 9), cursor="hand2")

    q: "queue.Queue[tuple]" = queue.Queue()

    def worker() -> None:
        def on_progress(pct: int, msg: str) -> None:
            q.put(("progress", pct, msg))

        try:
            launcher = run_install(install_dir_override, skip_shortcut, on_progress)
            q.put(("done", launcher))
        except Exception as exc:
            q.put(("failed", str(exc)))

    threading.Thread(target=worker, daemon=True).start()

    def poll() -> None:
        try:
            while True:
                kind, *rest = q.get_nowait()
                if kind == "progress":
                    pct, msg = rest
                    progress_var.set(pct)
                    pct_label.configure(text=f"{pct}%")
                    status_var.set(msg)
                    log_text.configure(state="normal")
                    log_text.insert("end", f"{msg}\n")
                    log_text.see("end")
                    log_text.configure(state="disabled")
                elif kind == "done":
                    (launcher,) = rest
                    launch_state["launcher"] = launcher
                    progress_var.set(100)
                    pct_label.configure(text="100%")
                    status_var.set("✅The installation completeda.")
                    actions.pack(anchor="e", padx=24, pady=(14, 20))
                    launch_btn.pack(side="right", padx=(8, 0))
                    close_btn.pack(side="right")
                elif kind == "failed":
                    (err,) = rest
                    status_var.set(f"the installation failed: {err}")
                    status_label.configure(fg=_BAD)
                    actions.pack(anchor="e", padx=24, pady=(14, 20))
                    close_btn.pack(side="right")
        except queue.Empty:
            pass
        root.after(150, poll)

    root.after(150, poll)
    root.mainloop()


# ── Entry point ───────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="VideoCheck installer core")
    p.add_argument("--install-dir", default=None,
                    help="Target install directory (Inno Setup passes its chosen {app} here)")
    p.add_argument("--no-shortcut", action="store_true",
                    help="Skip creating our own Desktop shortcut (used when Inno Setup "
                         "already creates a proper one)")
    p.add_argument("--console", action="store_true",
                    help="Force plain console output instead of the graphical installer window")
    return p


def _acquire_single_instance_lock() -> bool:
    """
    Prevents two copies of the installer running concurrently — running
    twice at once causes exactly the race condition you just hit: both
    instances try to create the same venv and write the same files at the
    same time, and whichever loses the race exits with a non-zero code.
    Uses a named Windows mutex, the standard OS-level way to do this
    (survives even if the two processes have no other way to talk to each
    other, unlike a lock file that a crashed process could leave stale).
    """
    if platform.system() != "Windows":
        return True  # not handling this on macOS/Linux yet, I mean, I didn't checked it yet
    import ctypes

    ERROR_ALREADY_EXISTS = 183
    ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\VideoCheckInstallerMutex")
    return ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def main() -> None:
    args = build_arg_parser().parse_args()

    if not _acquire_single_instance_lock():
        _native_message_box(
            "VideoCheck ya se está instalando",
            "Ya hay una instalación de VideoCheck en curso.\n\n"
            "Espera a que termine antes de abrir el instalador otra vez.",
        )
        return

    if args.console:
        main_console(args.install_dir, args.no_shortcut)
        return

    try:
        main_gui(args.install_dir, args.no_shortcut)
    except Exception:
        # Tcl/Tk missing or broken — extremely rare (would mean a Python
        # build without the standard 'tkinter' component), but don't leave
        # the user with a silently-doing-nothing installer.
        main_console(args.install_dir, args.no_shortcut)


if __name__ == "__main__":
    main()
