#!/usr/bin/env python3
"""Convenience runner for backend/scripts/import_telemetry.py."""

import runpy
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
backend_script = repo_root / "backend" / "scripts" / "import_telemetry.py"
sys.path.insert(0, str(repo_root / "backend"))

if __name__ == "__main__":
    runpy.run_path(str(backend_script), run_name="__main__")
