#!/usr/bin/env python3
"""CLI wrapper for the Harness batch scheduler control surface."""

from __future__ import annotations

# ruff: noqa: E402,I001

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.batch.scheduler import main

if __name__ == "__main__":
    main()
