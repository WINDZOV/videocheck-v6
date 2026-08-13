# Installing & building VideoCheck (developer + end-user paths)

This documents what changed vs. the original single-file script:

0. **Modular package** (`src/videocheck/`) instead of one monolithic `video_check.py` —
   see the "Architecture" section below.
1. **OpenVINO support** for machines with no NVIDIA GPU (much faster than plain PyTorch-CPU).
2. **Hardware-aware pre-installer** (`preinstall.py`) that decides what to install *before* any heavy library goes on disk.
3. **One-click installers** (`VideoCheck-Setup.exe` for Windows, `VideoCheck-Setup.dmg` for macOS) for non-technical users.

---

## 0. Architecture

```
src/videocheck/
├── config.py            Config dataclass — every tunable in one place,
│                         overridable via VIDEOCHECK_* env vars or CLI flags
├── backends/
│   ├── base.py           DetectionBackend interface (load, infer)
│   ├── cuda_backend.py    \
│   ├── openvino_backend.py > one class each, all interchangeable
│   ├── cpu_backend.py     /
│   └── factory.py        picks one based on hardware_report.json
├── video_io.py           VideoInspector — duration + corruption checks
├── detector.py           PersonDetector — samples frames, calls a backend,
│                         returns time intervals (pure logic, backend-agnostic)
├── clipper.py            ClipCutter — cuts intervals into clips via ffmpeg
├── progress.py           ProgressTracker interface + JSON-file / no-op impls
├── server.py             Flask app — upload/start/progress/clips API + serves dashboard.html
├── desktop.py            Wraps server.py in a native OS window via pywebview
├── pipeline.py           VideoPipeline — wires the above, walks a folder
└── cli.py                the ONLY place that constructs concrete classes
```

**Why this is flexible:** nothing outside `backends/` knows torch, ultralytics,
or openvino exist. `PersonDetector` and `ClipCutter` only see `DetectionBackend`
and `ProgressTracker` interfaces — swap either one without touching them.
Likewise, `desktop.py` and `server.py` share one Flask app — a native window
is just a different front door onto the exact same API a browser tab uses.

**Why this is scalable:**
- New hardware backend (Apple MPS, TensorRT, a remote inference API)? Write one
  class implementing `DetectionBackend`, add one line to `backends/factory.py`.
  `detector.py` doesn't change.
- New progress sink (websocket, database row, plain stdout)? Implement
  `ProgressTracker`. `pipeline.py` doesn't change.
- Want to detect something other than "person"? Change `Config.target_class_id`
  (or subclass `PersonDetector`) — the sampling/merging logic is generic.
- Every tunable lives in `Config`, overridable per-run via env vars
  (`VIDEOCHECK_MIN_INTERVAL=5`) or CLI flags, without editing source.
- `tests/` shows the payoff: `PersonDetector` and `ProgressTracker` are unit
  tested with fakes — no real video files, no torch, no ffmpeg required.
  Run them with `make test`.

Old habit still works: `python video_check.py` is now a 10-line shim that
just calls into the package, so nothing breaks if you keep typing that.
`python -m videocheck` and the installed `videocheck` command do the same
thing.

---

## 1. For you (developer), day to day

Nothing changes in how you use it:

```bash
make setup   # now runs preinstall.py first, then installs the right pyproject extra
make run     # opens VideoCheck as a native desktop window (pywebview)
```

`make check` now also prints the detected hardware profile.

### Desktop window vs. browser tab

`python video_check.py --serve` opens a **native OS window** (via `pywebview` —
WebView2 on Windows, WKWebView on macOS, WebKitGTK on Linux) instead of a browser
tab. It's the exact same Flask app and dashboard.html either way — `desktop.py`
just wraps `server.py` in a window instead of calling `webbrowser.open()`.

If `pywebview` isn't installed, or its native runtime is missing (a bare Windows
VM without the WebView2 Runtime is a common case — most real Windows 10/11
machines already have it), it automatically falls back to opening a regular
browser tab with an explanatory message, rather than crashing. To force the
browser-tab behavior on purpose: `python video_check.py --serve --browser`.

### Frame sampling — why it's fast now

`PersonDetector.find_intervals` used to seek (`cap.set(CAP_PROP_POS_MSEC, ...)`)
to every sample timestamp individually. For inter-frame-coded video (H.264/H.265 —
basically all security/dashcam footage), each seek forces the decoder back to
the nearest keyframe and forward-decodes from there, turning what should be a
sequential read into thousands of tiny rewind-and-replay operations. That's
usually the real bottleneck on long files, not the GPU.

It now seeks **once** to the start, then walks forward sequentially: `cap.grab()`
(cheap, skips the color-conversion/copy step) for frames it's skipping, and
`cap.read()` only on the frames it actually analyses. If a file is still slow,
the next cheap lever is raising `frame_skip_sec` (fewer samples per video) —
see the env var override below.

### What preinstall.py actually does

It's stdlib-only on purpose — it has to run *before* torch/ultralytics/openvino exist in the
environment, since its whole job is deciding which of those to install:

- Shells out to `nvidia-smi` to check for an NVIDIA GPU (no `torch` import needed).
- Reads `/proc/cpuinfo` / `sysctl` / `wmic` to get CPU vendor (Intel/AMD/Apple).
- Checks `ffmpeg`/`ffprobe` on PATH.
- Writes `hardware_report.json` with a `profile` field: `"cuda"`, `"openvino"`, or `"cpu"`.
- With `--install`, runs `pip install -e .[<profile>]` — dependencies live in one place
  (`pyproject.toml`), the profile just adds the matching extra (`openvino` or `cuda`;
  the `cpu` profile needs no extra, base deps already cover it).

`backends/factory.get_backend()` reads that same `hardware_report.json` at startup and
picks a `DetectionBackend` accordingly — CUDA GPU first, OpenVINO second (auto-exports
the `.pt` to OpenVINO IR format once, caches it on disk), plain CPU as the last resort —
double-checking with a real import in case the report is stale.

**Note on CUDA:** the `cuda` extra still pulls in the generic (CPU-only) PyPI `torch`
wheel — pip has no way to know your exact CUDA driver version. After `make setup` on a
CUDA machine, run the one-time command PyTorch's site gives you, e.g.:
```bash
venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cu121
```

---

## 2. Building the one-click installers (you do this once per release)

### Windows — the real one-click installer

```
cd installer
build_windows.bat
```

This does two things:

1. Builds `dist\VideoCheckInstallerCore.exe` via PyInstaller — a windowed
   (no console) app that does the actual work: finds/installs Python,
   copies the project, creates a venv, detects hardware, installs matching
   dependencies. It shows its own dark progress window with a log, and ends
   with an "Abrir VideoCheck" button.
2. If **Inno Setup** is installed (free — https://jrsoftware.org/isdl.php,
   one-time setup on your build machine), it automatically wraps that core
   exe into `dist\VideoCheck-Setup.exe` using `installer\VideoCheck.iss` —
   a genuine Windows installer wizard:
   - Welcome screen → license/info → **progress page** (runs the core
     installer while showing its own status) → **Finish page** with a
     "Launch VideoCheck now" checkbox, exactly like commercial software.
   - A **Start Menu** entry and an optional **Desktop icon** (checkbox
     during install).
   - A real entry in **"Add or Remove Programs"** with a working
     uninstaller that removes everything (`[UninstallDelete]` in the .iss
     deletes the whole install folder — venv, model, clips, all of it).
   - No admin rights needed — installs per-user under
     `%LocalAppData%\VideoCheck`, no UAC prompt.

   If Inno Setup isn't installed, the script tells you so and stops after
   step 1 — `VideoCheckInstallerCore.exe` still works fine standalone, it
   just won't have the Start Menu/uninstaller polish.

**What you hand out to a normal Windows user:** just `VideoCheck-Setup.exe`.
Download → double-click → Next → Next → Finish. That's the whole
experience — no terminal, no `pip`, no "what's a venv".

### macOS

```
cd installer
./build_mac.sh
```

### What the installer does when a non-technical user double-clicks it (Windows)

1. Inno Setup's wizard runs: Welcome → (progress page runs
   `VideoCheckInstallerCore.exe --install-dir "<chosen folder>" --no-shortcut`
   in the background, showing its own graphical progress window on top) →
   Finish page with a "Launch VideoCheck now" checkbox.
2. The core installer: looks for Python 3.10+ (silently installs one,
   per-user, if missing); copies the bundled project files into the chosen
   folder; creates a `venv`; runs `preinstall.py --install` (same hardware
   detection as the CLI path — CUDA vs OpenVINO vs CPU); writes
   `run_videocheck.vbs`.
3. Inno creates the Start Menu entry, optional Desktop icon (checked by
   default), and registers the uninstaller.
4. `run_videocheck.vbs` launches `video_check.py --serve` through
   `pythonw.exe` (no console subsystem) via `WScript.Shell.Run(..., 0,
   False)` (hidden window) — no black terminal flashes, ever. It opens
   VideoCheck as a native desktop window (pywebview), no browser tab.

### Known limitations (worth knowing before shipping this to end users)

- **I can't compile/test the .iss on this machine.** Inno Setup only runs on Windows, so
  the `.iss` syntax is written carefully but genuinely untested end-to-end — build it and
  walk through the wizard once yourself before handing `VideoCheck-Setup.exe` to anyone else.
- **No app icon yet.** `VideoCheck.iss` has `SetupIconFile`/`UninstallDisplayIcon` commented
  out — add a `.ico` file and uncomment those two lines for a custom icon instead of the
  generic Inno one.
- **Not code-signed.** Windows SmartScreen will likely show an "unknown publisher" warning
  on first run (click "More info" → "Run anyway"). Removing that needs a code-signing
  certificate (~$100+/yr). Same story for macOS Gatekeeper on the `.dmg` — needs an Apple
  Developer ID ($99/yr) to sign + notarize.
- **ffmpeg isn't bundled.** The installer checks for it and shows a warning with install
  instructions rather than silently installing it, since that needs elevated permissions we
  shouldn't assume.
- **CUDA wheel isn't auto-installed**, for the same reason (pip can't infer the driver
  version). A CUDA user still gets working — just CPU/OpenVINO-speed — clip detection until
  they run the one PyTorch command manually (see above).
