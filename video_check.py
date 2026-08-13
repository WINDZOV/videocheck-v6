#!/usr/bin/env python3
"""
Backward-compatible entrypoint. All real logic now lives in src/videocheck/
as a proper package (see that folder for the architecture). This file just
lets you keep running `python video_check.py` out of habit — it's
equivalent to `python -m videocheck` or the installed `videocheck` command.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from videocheck.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
