#!/usr/bin/env python3
"""Hearthwren Single-File Standalone Runner.

Run without arguments to launch the Ultra-Lightweight Desktop Studio:
    python run_hearthwren.py

Run with CLI commands for terminal operations:
    python run_hearthwren.py doctor
    python run_hearthwren.py plan "implement feature"
    python run_hearthwren.py run "task"
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is in sys.path for direct execution without installation
SRC_DIR = Path(__file__).parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    if len(sys.argv) > 1:
        # CLI invocation
        from hearthwren.cli import main as cli_main
        cli_main()
    else:
        # Default zero-argument invocation: launch Desktop Application
        from hearthwren.gui.launcher import launch_desktop
        launch_desktop()


if __name__ == "__main__":
    main()
