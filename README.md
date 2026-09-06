# VideoCheck 🎥🔍

**VideoCheck** is a local, hardware-adaptive person-detection clip extractor and surveillance video organizer. It automates scanning through long video files (such as CCTV, dashcam, or security footage), identifies frames containing people using YOLO-based computer vision, extracts the relevant segments as standalone clips using lossless FFmpeg stream copying, and sorts source videos by status.

It runs locally with zero cloud dependencies, adapts automatically to your CPU or GPU hardware, and offers both a graphical interface (Desktop & Web) and a headless CLI.

---

## 🌟 Key Features

- **Hardware-Adaptive AI Inference**:
  - Automatically identifies your hardware and selects the fastest backend:
    - **NVIDIA GPU (CUDA)**: High-speed acceleration via PyTorch.
    - **Intel / AMD CPU (OpenVINO)**: Graph-fused, quantized CPU inference (significantly faster than standard PyTorch-CPU; automatically converts and caches models to OpenVINO IR format).
    - **Standard CPU**: Universal fallback for any environment.
- **Fast Sequential Frame Sampling**:
  - Eliminates slow video decoder seek bottlenecks (`cap.set`) on H.264/H.265 inter-frame codecs by seeking once and advancing sequentially with lightweight `cap.grab()`, decoding (`cap.read()`) only sampled frames.
- **Lossless & Fast Clip Extraction**:
  - Cuts video segments via FFmpeg stream copy (`-c copy`) without re-encoding. Processing is virtually instantaneous and preserves original video quality.
- **Automated Video Sorting & Integrity Check**:
  - Pre-scans for bitstream and container corruption (e.g., missing `moov` atom, invalid EBML headers) before deep processing.
  - Automatically organizes files into dedicated directories:
    - `clips/`: Extracted video clips containing detected targets.
    - `originals_processed/`: Original videos where people were found and clips were generated.
    - `empty_videos/`: Videos scanned where no targets were found.
    - `corrupted/`: Damaged or unreadable video files.
- **Flexible Interfaces**:
  - **Native Desktop App**: Built-in OS window via `pywebview` (WebView2 on Windows, WKWebView on macOS, WebKitGTK on Linux).
  - **Web Dashboard**: Local web interface with drag-and-drop video upload, real-time progress tracking, and direct clip downloads.
  - **Headless CLI**: Command-line mode with automated flags and environment variable overrides for scripting, cron jobs, and background workers.
- **Smart Clip Merging & Padding**:
  - Automatically merges detections that occur close together within a configurable time window and adds pre-/post-roll padding around events.

---

## 🏗️ Architecture Overview

```
videocheck/
├── src/videocheck/
│   ├── backends/          # Hardware detection backends (CUDA, OpenVINO, CPU)
│   │   ├── base.py        # DetectionBackend interface & Detection dataclass
│   │   ├── cuda_backend.py
│   │   ├── openvino_backend.py
│   │   ├── cpu_backend.py
│   │   └── factory.py     # Dynamically loads best available backend
│   ├── config.py          # Central Config dataclass & environment variable loader
│   ├── video_io.py        # VideoInspector: Duration & FFmpeg corruption validation
│   ├── detector.py        # PersonDetector: Frame sampling, inference & interval merging
│   ├── clipper.py         # ClipCutter: Lossless FFmpeg stream-copy clipping
│   ├── progress.py        # ProgressTracker interface & JSON progress reporter
│   ├── server.py          # Flask REST API & Web UI server
│   ├── desktop.py         # Native desktop window runner (pywebview wrapper)
│   ├── pipeline.py        # VideoPipeline orchestrator
│   └── cli.py             # CLI parser & dependency injection entrypoint
├── installer/             # One-click installer scripts for Windows (.exe) & macOS (.dmg)
├── tests/                 # Unit tests (with test doubles/fakes for offline CI)
├── dashboard.html         # Web UI frontend dashboard
├── preinstall.py          # Standard-library hardware probe & installer
├── video_check.py         # Backward-compatible entrypoint shim
└── pyproject.toml         # Packaging & dependency specifications
```

---

## 💻 System Requirements

### Prerequisites

| Requirement | Details |
| :--- | :--- |
| **Operating System** | Linux (Ubuntu, Debian, Fedora, Arch, etc.), Windows 10/11 (64-bit), or macOS 11+ (Intel / Apple Silicon) |
| **Python** | Python **3.10** or higher |
| **FFmpeg** | `ffmpeg` and `ffprobe` must be installed and available on your system `PATH` |

### Installing FFmpeg

- **Ubuntu / Debian**:
  ```bash
  sudo apt update && sudo apt install -y ffmpeg
  ```
- **macOS** (via [Homebrew](https://brew.sh)):
  ```bash
  brew install ffmpeg
  ```
- **Windows** (via [winget](https://learn.microsoft.com/en-us/windows/package-manager/winget/) or [Chocolatey](https://chocolatey.org/)):
  ```cmd
  winget install ffmpeg
  # or
  choco install ffmpeg
  ```

---

## 📦 Installation

### Option 1: Quick Setup via `Makefile` (Linux / macOS / Git Bash)

The included `Makefile` handles virtual environment creation, hardware probing, and package installation automatically:

```bash
# Clone repository and enter directory
git clone https://github.com/WINDZOV/videocheck-v6.git
cd videocheck-v6

# Run automated setup
make setup
```

To verify your system hardware profile and FFmpeg availability:
```bash
make check
```

---

### Option 2: Manual Python Installation

1. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv venv

   # On Linux / macOS:
   source venv/bin/activate

   # On Windows (Command Prompt / PowerShell):
   venv\Scripts\activate
   ```

2. **Run the hardware detector & installer**:
   ```bash
   python preinstall.py --install
   ```

3. *(Optional)* **Manual pip install by hardware profile**:
   - **Intel / AMD CPU (OpenVINO acceleration)**:
     ```bash
     pip install -e .[openvino]
     ```
   - **NVIDIA GPU (CUDA)**:
     ```bash
     pip install -e .[cuda]
     # Install matching CUDA PyTorch wheel (example for CUDA 12.1):
     pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
     ```
   - **Standard CPU**:
     ```bash
     pip install -e .
     ```

---

## 🚀 Usage

### 1. Graphical Application (Desktop & Web Dashboard)

To launch VideoCheck in interactive mode (GUI):

```bash
# Run using Make:
make run

# Or run directly with Python:
python video_check.py --serve
```

- **Desktop Window**: Opens as a native desktop window using `pywebview`.
- **Browser Mode**: If you prefer opening in your default web browser (or if `pywebview` runtime is missing), use:
  ```bash
  python video_check.py --serve --browser
  ```
  The dashboard will be available at `http://127.0.0.1:8765/`.

**Dashboard Features:**
1. **Upload Videos**: Drag and drop video files (`.mp4`, `.mkv`, `.webm`, `.mov`, `.avi`, `.mpg`).
2. **Start Processing**: Click **Start** to begin the detection and clipping pipeline.
3. **Live Progress**: Track real-time progress, stages, and file statistics.
4. **Download Clips**: Download individual output clips directly from the browser.

---

### 2. Command Line / Headless Batch Mode

For server environments, cron jobs, or batch processing existing files:

```bash
# Process all videos in videosrc/ folder and exit:
make run-cli

# Or via Python / CLI:
python video_check.py

# Or using the installed package executable:
videocheck
```

#### CLI Options:

```
usage: videocheck [-h] [--input INPUT_FOLDER] [--no-dashboard]
                  [--model MODEL_NAME] [--conf CONF_THRESHOLD]
                  [--serve] [--browser] [--port PORT] [--no-browser]

options:
  -h, --help            show this help message and exit
  --input INPUT_FOLDER  Folder to scan (default: videosrc)
  --no-dashboard        Skip writing progress.json (headless/batch mode)
  --model MODEL_NAME    YOLO model file (default: yolov8n.pt)
  --conf CONF_THRESHOLD Detection confidence threshold 0-1 (default: 0.5)
  --serve               Launch VideoCheck as an app (Desktop/Web UI)
  --browser             With --serve: open in a browser tab instead of a native desktop window
  --port PORT           Web UI port (default: 8765)
  --no-browser          With --serve --browser: don't auto-open a browser tab
```

**Example Commands:**
```bash
# Process a custom input directory with higher confidence:
videocheck --input /path/to/cctv_dumps --conf 0.65 --model yolov8s.pt

# Run headless server on a custom port without launching a browser:
videocheck --serve --browser --no-browser --port 9000
```

---

## ⚙️ Configuration & Environment Variables

All settings in `videocheck/config.py` can be overridden without modifying code using environment variables prefixed with `VIDEOCHECK_`:

| Parameter | Env Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| `input_folder` | `VIDEOCHECK_INPUT_FOLDER` | `videosrc` | Source directory to scan for videos |
| `output_clips` | `VIDEOCHECK_OUTPUT_CLIPS` | `clips` | Directory for extracted video clips |
| `output_processed`| `VIDEOCHECK_OUTPUT_PROCESSED`| `originals_processed`| Destination for processed source videos |
| `output_empty` | `VIDEOCHECK_OUTPUT_EMPTY` | `empty_videos` | Destination for videos without targets |
| `output_corrupted`| `VIDEOCHECK_OUTPUT_CORRUPTED`| `corrupted` | Destination for damaged/corrupt video files |
| `model_name` | `VIDEOCHECK_MODEL_NAME` | `yolov8n.pt` | YOLO model weights (`yolov8n.pt`, `yolov8s.pt`, etc.) |
| `conf_threshold` | `VIDEOCHECK_CONF_THRESHOLD` | `0.5` | Minimum detection confidence score (0.0 – 1.0) |
| `target_class_id`| `VIDEOCHECK_TARGET_CLASS_ID` | `0` | COCO target class ID (`0` = person) |
| `frame_skip_sec` | `VIDEOCHECK_FRAME_SKIP_SEC` | `2.0` | Sampling interval in seconds (e.g. 1 frame every 2s) |
| `start_skip` | `VIDEOCHECK_START_SKIP` | `600.0` (10m) | Skip first N seconds of video from analysis |
| `end_skip` | `VIDEOCHECK_END_SKIP` | `300.0` (5m) | Skip last N seconds of video from analysis |
| `min_interval` | `VIDEOCHECK_MIN_INTERVAL` | `3.0` | Minimum duration (seconds) of detection to keep |
| `merge_gap` | `VIDEOCHECK_MERGE_GAP` | `90.0` | Merge intervals if gap between detections ≤ N seconds |
| `pad_before` | `VIDEOCHECK_PAD_BEFORE` | `5.0` | Seconds of video included before detection start |
| `pad_after` | `VIDEOCHECK_PAD_AFTER` | `15.0` | Seconds of video included after detection end |
| `ffmpeg_timeout` | `VIDEOCHECK_FFMPEG_TIMEOUT` | `300` | Max timeout (seconds) for FFmpeg clip operations |

**Example using Environment Variables:**
```bash
VIDEOCHECK_FRAME_SKIP_SEC=1 \
VIDEOCHECK_MIN_INTERVAL=5 \
VIDEOCHECK_MODEL_NAME=yolov8m.pt \
videocheck
```

---

## 🧪 Testing

VideoCheck includes automated unit tests that verify interval merging logic, configuration overrides, and progress tracker state using test doubles (no GPU, real video files, or FFmpeg required):

```bash
# Run tests with Make:
make test

# Or via pytest directly:
pytest tests/ -v
```

---

## 📦 Building Standalone Installers

VideoCheck includes bundling scripts to produce single-click desktop installers for non-technical users:

### Windows (`VideoCheck-Setup.exe`)
1. Open Windows Command Prompt / PowerShell.
2. *(Optional)* Install [Inno Setup 6](https://jrsoftware.org/isdl.php) for full installer wizard generation.
3. Run:
   ```cmd
   cd installer
   build_windows.bat
   ```
   *Output*: `installer\dist\VideoCheck-Setup.exe` (with Inno Setup) or `VideoCheckInstallerCore.exe`.

### macOS (`VideoCheck-Setup.dmg`)
1. On a macOS machine, run:
   ```bash
   cd installer
   ./build_mac.sh
   ```
   *Output*: `installer/dist/VideoCheck-Setup.dmg`.

---

## 📄 License

This project is open source and available under the standard project terms. Feel free to modify and adapt it to your workflow.
