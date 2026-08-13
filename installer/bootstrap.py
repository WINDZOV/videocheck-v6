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
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

APP_NAME = "VideoCheck"
MIN_PYTHON = (3, 10)

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
                [path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10
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
            check=True,
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
        subprocess.run([python_exe, "-m", "venv", str(venv_dir)], check=True)
    return venv_dir / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")


def install_dependencies(venv_python: Path, install_dir: Path) -> None:
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
        check=True, cwd=install_dir,
    )
    subprocess.run(
        [str(venv_python), "preinstall.py", "--install"], check=True, cwd=install_dir,
    )


def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


# ── Launcher + shortcut ─────────────────────────────────────────────────

def write_launchers(install_dir: Path, venv_python: Path) -> Path:
    system = platform.system()
    if system == "Windows":
        launcher = install_dir / "run_videocheck.bat"
        launcher.write_text(
            f'@echo off\r\n'
            f'cd /d "{install_dir}"\r\n'
            f'"{venv_python}" video_check.py --serve\r\n'
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


def create_desktop_shortcut(launcher: Path) -> None:
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
    try:
        if platform.system() == "Windows":
            shutil.copy2(launcher, desktop / launcher.name)
        else:
            shortcut = desktop / launcher.name
            if shortcut.exists():
                shortcut.unlink()
            shortcut.symlink_to(launcher)
        log(f"Acceso directo creado: {desktop / launcher.name}")
    except Exception as exc:
        log(f"(no se pudo crear el acceso directo: {exc} — puedes ejecutar {launcher} directamente)")


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

    report(5, "Buscando una instalación de Python...")
    python_exe = ensure_python()

    install_dir = Path(install_dir_override) if install_dir_override else default_install_dir()
    report(15, f"Instalando en: {install_dir}")
    copy_project_files(install_dir)
    report(30, "Archivos del programa copiados.")

    report(35, "Creando un entorno de Python aislado...")
    venv_python = create_venv(python_exe, install_dir)
    report(45, "Entorno listo.")

    report(50, "Detectando tu hardware (GPU/CPU) e instalando componentes — esto puede tardar varios minutos...")
    install_dependencies(venv_python, install_dir)
    report(90, "Componentes instalados.")

    launcher = write_launchers(install_dir, venv_python)
    if not skip_shortcut:
        create_desktop_shortcut(launcher)
    report(97, "Configuración final...")

    if not check_ffmpeg():
        report(98, "Aviso: no se encontró ffmpeg. VideoCheck lo necesita para recortar clips "
                    "(instálalo con 'winget install ffmpeg' o desde ffmpeg.org).")

    report(100, f"Instalación completada en {install_dir}")
    return launcher


# ── Console front end (fallback / dev testing) ──────────────────────────

def main_console(install_dir_override: str | None, skip_shortcut: bool) -> None:
    stdin_available = sys.stdin is not None and sys.stdin.isatty()

    def _pause() -> None:
        if stdin_available:
            try:
                input("\nPulsa Enter para cerrar esta ventana...")
            except RuntimeError:
                pass  # no attached console — nothing to wait on

    try:
        launcher = run_install(install_dir_override, skip_shortcut=skip_shortcut)
        log("")
        log(f"👉  Haz doble clic en '{launcher.name}' para abrir VideoCheck.")
        if stdin_available:
            _pause()
        else:
            _native_message_box(
                "VideoCheck instalado",
                f"Instalación completada.\n\nHaz doble clic en '{launcher.name}' para abrir VideoCheck.",
            )
    except Exception as exc:
        log(f"\n✗  La instalación falló: {exc}")
        if stdin_available:
            _pause()
            sys.exit(1)
        else:
            _native_message_box("Error de instalación", f"La instalación de VideoCheck falló:\n\n{exc}")


# ── Graphical front end (what end users see) ────────────────────────────

_INSTALLER_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { background:#0f1115; color:#e6e8ec; font-family:-apple-system,"Segoe UI",Roboto,sans-serif;
         margin:0; padding:2rem; }
  h1 { font-size:1.15rem; margin:0 0 1rem; }
  .bar-outer { background:#262b36; border-radius:6px; height:10px; overflow:hidden; }
  .bar-inner { background:#4f8cff; height:100%; width:0%; transition:width .3s; }
  #status { margin-top:0.8rem; font-size:0.9rem; color:#8b909c; min-height:1.2em; }
  #log { margin-top:1rem; background:#171a21; border:1px solid #2a2e38; border-radius:8px;
         padding:0.7rem; height:150px; overflow-y:auto; font-size:0.76rem;
         font-family:Consolas,monospace; color:#8b909c; }
  #log div { margin-bottom:0.2rem; }
  #actions { margin-top:1.2rem; text-align:right; display:none; }
  button { background:#4f8cff; color:#fff; border:none; padding:0.6rem 1.2rem; border-radius:7px;
           font-weight:600; cursor:pointer; }
  button.secondary { background:#262b36; color:#e6e8ec; margin-right:0.5rem; }
</style></head>
<body>
  <h1>Instalando VideoCheck</h1>
  <div class="bar-outer"><div class="bar-inner" id="bar"></div></div>
  <div id="status">Preparando...</div>
  <div id="log"></div>
  <div id="actions">
    <button class="secondary" onclick="window.pywebview.api.close_window()">Cerrar</button>
    <button id="launchBtn" onclick="launchNow()">Abrir VideoCheck</button>
  </div>
<script>
function setProgress(pct, msg) {
  document.getElementById('bar').style.width = pct + '%';
  document.getElementById('status').textContent = msg;
  const logEl = document.getElementById('log');
  const line = document.createElement('div');
  line.textContent = msg;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}
function installDone() {
  document.getElementById('status').textContent = 'Instalación completada.';
  document.getElementById('actions').style.display = 'block';
}
function installFailed(msg) {
  document.getElementById('status').textContent = 'La instalación falló: ' + msg;
  document.getElementById('status').style.color = '#e05c5c';
  document.getElementById('actions').style.display = 'block';
  document.getElementById('launchBtn').style.display = 'none';
}
async function launchNow() {
  await window.pywebview.api.launch_now();
  window.pywebview.api.close_window();
}
</script>
</body></html>"""


class _InstallerApi:
    """Exposed to the pywebview JS side as `window.pywebview.api.<method>`."""

    def __init__(self, window):
        self._window = window
        self.launcher: Path | None = None

    def launch_now(self) -> None:
        if not self.launcher:
            return
        try:
            if platform.system() == "Windows":
                os.startfile(str(self.launcher))  # noqa: S606 — launching our own generated script
            else:
                subprocess.Popen(["open", str(self.launcher)])
        except Exception as exc:
            log(f"No se pudo abrir VideoCheck automáticamente: {exc}")

    def close_window(self) -> None:
        self._window.destroy()


def main_gui(install_dir_override: str | None, skip_shortcut: bool) -> None:
    import webview

    window = webview.create_window(
        "Instalando VideoCheck", html=_INSTALLER_HTML, width=560, height=440, resizable=False,
    )
    api = _InstallerApi(window)
    window.expose(api.launch_now, api.close_window)

    def worker(win):
        def on_progress(pct: int, msg: str) -> None:
            win.evaluate_js(f"setProgress({pct}, {json.dumps(msg)})")

        try:
            api.launcher = run_install(install_dir_override, skip_shortcut, on_progress)
            win.evaluate_js("installDone()")
        except Exception as exc:
            win.evaluate_js(f"installFailed({json.dumps(str(exc))})")

    webview.start(worker, window)


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


def main() -> None:
    args = build_arg_parser().parse_args()

    if args.console:
        main_console(args.install_dir, args.no_shortcut)
        return

    try:
        import webview  # noqa: F401
    except ImportError:
        main_console(args.install_dir, args.no_shortcut)
        return

    try:
        main_gui(args.install_dir, args.no_shortcut)
    except Exception:
        # Native webview runtime broken/missing (e.g. a bare VM without
        # WebView2/GTK) — fall back to plain console rather than hanging.
        main_console(args.install_dir, args.no_shortcut)


if __name__ == "__main__":
    main()
