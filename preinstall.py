#!/usr/bin/env python3
"""
preinstall.py — Hardware & environment check for VideoCheck.

This is the "light system-check step" that has to run BEFORE torch,
ultralytics, or openvino are installed. It uses ONLY the Python standard
library on purpose — it must work on a completely bare interpreter, since
its whole job is deciding *what* to install next.

What it does:
  1. Detects the OS (Windows / macOS / Linux).
  2. Detects an NVIDIA GPU via `nvidia-smi` — no torch import needed.
  3. Detects CPU vendor (Intel / AMD / Apple Silicon) for OpenVINO fit.
  4. Checks whether ffmpeg/ffprobe are already on PATH.
  5. Picks an install profile: "cuda" | "openvino" | "cpu"
  6. Writes hardware_report.json — videocheck.backends.get_backend() reads
     this at runtime to decide which DetectionBackend to load.
  7. With --install, editable-installs the package with the matching
     extra: `pip install -e .[cuda]`, `.[openvino]`, or plain `.` for cpu.

Usage:
    python preinstall.py             # detect only, write hardware_report.json
    python preinstall.py --install   # detect AND install matching deps
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys

REPORT_FILE = "hardware_report.json"


def _run(cmd, timeout=10):
    try:
        r = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout
        )
        return r.returncode, r.stdout.decode(errors="replace"), r.stderr.decode(errors="replace")
    except Exception:
        return None, "", ""


def detect_os():
    return {
        "system": platform.system(),  # 'Windows' | 'Darwin' | 'Linux'
        "release": platform.release(),
        "machine": platform.machine(),
    }


def detect_nvidia_gpu():
    """Shells out to nvidia-smi — works even without torch installed."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {"present": False}
    code, out, _ = _run(
        [exe, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]
    )
    if code != 0 or not out.strip():
        return {"present": False}
    parts = [p.strip() for p in out.strip().splitlines()[0].split(",")]
    return {
        "present": True,
        "name": parts[0] if len(parts) > 0 else None,
        "memory": parts[1] if len(parts) > 1 else None,
        "driver": parts[2] if len(parts) > 2 else None,
    }


def detect_cpu():
    info = {"name": platform.processor() or platform.machine(), "cores": os.cpu_count(), "vendor": ""}
    system = platform.system()

    if system == "Linux":
        try:
            with open("/proc/cpuinfo") as f:
                text = f.read()
            m = re.search(r"model name\s*:\s*(.+)", text)
            if m:
                info["name"] = m.group(1).strip()
            if "GenuineIntel" in text:
                info["vendor"] = "intel"
            elif "AuthenticAMD" in text:
                info["vendor"] = "amd"
        except Exception:
            pass

    elif system == "Darwin":
        code, out, _ = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if code == 0 and out.strip():
            info["name"] = out.strip()
        info["vendor"] = "apple" if "Apple" in info["name"] else ("intel" if "Intel" in info["name"] else "")

    elif system == "Windows":
        code, out, _ = _run(["wmic", "cpu", "get", "name"])
        if code == 0 and out.strip():
            lines = [l.strip() for l in out.splitlines() if l.strip() and l.strip() != "Name"]
            if lines:
                info["name"] = lines[0]
        low = info["name"].lower()
        info["vendor"] = "intel" if "intel" in low else ("amd" if "amd" in low else "")

    return info


def detect_ffmpeg():
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    return {
        "ffmpeg": bool(ffmpeg),
        "ffprobe": bool(ffprobe),
        "ffmpeg_path": ffmpeg,
        "ffprobe_path": ffprobe,
    }


def choose_profile(gpu: dict, cpu: dict) -> str:
    if gpu.get("present"):
        return "cuda"
    # OpenVINO's CPU plugin runs on any x86_64 (Intel or AMD) and is still
    # meaningfully faster than plain PyTorch-CPU thanks to graph fusion /
    # int8 quantization, so we default to it whenever there's no NVIDIA GPU
    # and we're not on Apple Silicon (which has no OpenVINO CPU plugin).
    if cpu.get("vendor") in ("intel", "amd"):
        return "openvino"
    return "cpu"


def print_report(report: dict) -> None:
    print("─" * 50)
    print(f"  OS      : {report['os']['system']} {report['os']['release']}")
    print(f"  CPU     : {report['cpu']['name']}")
    if report["gpu"]["present"]:
        print(f"  GPU     : {report['gpu']['name']} ({report['gpu']['memory']})")
    else:
        print("  GPU     : none detected (NVIDIA/CUDA)")
    print(f"  ffmpeg  : {'found' if report['ffmpeg']['ffmpeg'] else 'MISSING'}")
    print(f"  Profile : {report['profile']}")
    print("─" * 50)


def main():
    report = {
        "os": detect_os(),
        "gpu": detect_nvidia_gpu(),
        "cpu": detect_cpu(),
        "ffmpeg": detect_ffmpeg(),
    }
    report["profile"] = choose_profile(report["gpu"], report["cpu"])

    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2)

    print_report(report)

    if not report["ffmpeg"]["ffmpeg"]:
        print("\n⚠  ffmpeg was not found on PATH. VideoCheck needs it to cut clips.")
        print("   Windows: winget install ffmpeg   (or download from ffmpeg.org)")
        print("   macOS  : brew install ffmpeg")
        print("   Linux  : sudo apt install ffmpeg")

    if "--install" in sys.argv:
        if not os.path.exists("pyproject.toml"):
            print("\n✗  pyproject.toml not found next to preinstall.py — cannot auto-install.")
            sys.exit(1)
        profile = report["profile"]
        # Base deps (torch/ultralytics/opencv) are always installed; the
        # profile just adds the extra that matches this machine's hardware.
        extra = f"[{profile}]" if profile in ("cuda", "openvino") else ""
        print(f"\n📦  Installing package (profile: {profile}) ...")
        code, out, err = _run(
            [sys.executable, "-m", "pip", "install", "-e", f".{extra}"], timeout=1800
        )
        print(out)
        if code != 0:
            print(err)
            sys.exit(1)
        print("✅  Dependencies installed.")


if __name__ == "__main__":
    main()
