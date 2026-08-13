# ─────────────────────────────────────────────────────────────
#  Makefile — video-check / person-clip extractor
#  Usage:  make <target>
#          make          (runs 'help' by default)
# ─────────────────────────────────────────────────────────────
PYTHON      := python3
VENV        := venv
PIP         := $(VENV)/bin/pip
PY          := $(VENV)/bin/python
SCRIPT      := video_check.py
INPUT_DIR   := videosrc

# Windows (Git Bash / MINGW) uses Scripts\ instead of bin/
ifeq ($(OS),Windows_NT)
	PIP := $(VENV)/Scripts/pip
	PY  := $(VENV)/Scripts/python
endif

.DEFAULT_GOAL := help

# ── Help ──────────────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "  make setup      Create venv, detect hardware, install matching deps, create folders"
	@echo "  make run        Launch the web dashboard (upload/start/download from the browser)"
	@echo "  make run-cli    Process whatever is already in videosrc/ and exit (headless)"
	@echo "  make check      Show detected hardware profile (cuda/openvino/cpu) + ffmpeg status"
	@echo "  make clean      Remove output folders and progress.json"
	@echo "  make clean-all  Also remove the venv"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────
# preinstall.py picks the fastest available backend for THIS machine:
#   NVIDIA GPU present      -> requirements-cuda.txt
#   Intel/AMD CPU, no GPU   -> requirements-openvino.txt
#   anything else           -> requirements-cpu.txt
.PHONY: setup
setup: $(VENV)/bin/activate

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PY) preinstall.py --install
	@mkdir -p videosrc clips empty_videos originals_processed corrupted
	@echo ""
	@echo "  ✅  venv ready. Folders created."
	@echo "  👉  Drop your videos into videosrc/ then run:  make run"
	@touch $(VENV)/bin/activate

# ── Run ───────────────────────────────────────────────────────
# Web dashboard: upload videos, click Start, download clips — no manual
# file-shuffling into videosrc/ needed.
.PHONY: run
run:
	@mkdir -p $(INPUT_DIR)
	$(PY) $(SCRIPT) --serve

# Headless: process whatever is already sitting in videosrc/ and exit.
# Useful for cron jobs / automation.
.PHONY: run-cli
run-cli:
	@mkdir -p $(INPUT_DIR)
	@if [ -z "$$(ls -A $(INPUT_DIR) 2>/dev/null)" ]; then \
		echo "  ⚠  '$(INPUT_DIR)/' is empty. Add some videos first."; \
		exit 1; \
	fi
	$(PY) $(SCRIPT)

# ── Dashboard ─────────────────────────────────────────────────
# Kept for convenience if the server is already running elsewhere.
.PHONY: dashboard
dashboard:
ifeq ($(OS),Windows_NT)
	start http://127.0.0.1:8765/
else ifeq ($(shell uname),Darwin)
	open http://127.0.0.1:8765/
else
	xdg-open http://127.0.0.1:8765/
endif

# ── Check dependencies / hardware profile ──────────────────────
.PHONY: check
check:
	@echo "Checking dependencies..."
	@$(PYTHON) --version || (echo "  ✗  python3 not found"; exit 1)
	@ffmpeg -version 2>&1 | head -1 || (echo "  ✗  ffmpeg not found — install it first"; exit 1)
	@ffprobe -version 2>&1 | head -1 || (echo "  ✗  ffprobe not found — comes with ffmpeg"; exit 1)
	@$(PYTHON) preinstall.py
	@echo "  ✅  All good."

# ── Clean ─────────────────────────────────────────────────────
.PHONY: clean
clean:
	rm -rf clips/ empty_videos/ originals_processed/ corrupted/ progress.json hardware_report.json
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "  🧹  Output folders cleared."

# ── Tests ─────────────────────────────────────────────────────
.PHONY: test
test:
	$(PY) -m pytest tests/ -v

.PHONY: clean-all
clean-all: clean
	rm -rf $(VENV)/
	@echo "  🧹  venv removed. Run 'make setup' to reinstall."
