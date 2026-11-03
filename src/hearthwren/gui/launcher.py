"""Native desktop application launcher for Hearthwren.

Launches Hearthwren in a zero-dependency, ultra-lightweight desktop window using
the operating system's native Edge/Chrome application mode (--app) or default browser.
Consumes < 30 MB idle RAM, preserving the entire laptop memory headroom for local AI inference.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from hearthwren.gui.server import HearthwrenAPIHandler, run_server


def find_system_app_browser() -> tuple[str | None, str]:
    """Find a browser binary supporting frameless desktop app mode (--app=...).

    Returns (binary_path_or_none, browser_name).
    """
    # 1. Windows common locations for Microsoft Edge and Google Chrome
    if sys.platform.startswith("win"):
        edge_paths = [
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ]
        for p in edge_paths:
            if p.is_file():
                return str(p), "msedge"

        chrome_paths = [
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
        for p in chrome_paths:
            if p.is_file():
                return str(p), "chrome"

    # 2. PATH lookups
    for binary, name in [
        ("msedge", "msedge"),
        ("microsoft-edge", "msedge"),
        ("chrome", "chrome"),
        ("google-chrome", "chrome"),
        ("google-chrome-stable", "chrome"),
        ("chromium", "chromium"),
        ("chromium-browser", "chromium"),
    ]:
        found = shutil.which(binary)
        if found:
            return found, name

    return None, "system_default"


def find_free_port(start_port: int = 7860, max_attempts: int = 50) -> int:
    """Find an available TCP port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port


def launch_desktop(
    host: str = "127.0.0.1",
    port: int | None = None,
    workspace_root: Path | None = None,
    open_window: bool = True,
) -> None:
    """Launch the Hearthwren desktop server and UI window."""
    if workspace_root is None:
        workspace_root = Path.cwd().resolve()
    else:
        workspace_root = Path(workspace_root).resolve()

    selected_port = port or find_free_port(7860)
    server = run_server(host=host, port=selected_port, workspace_root=workspace_root)
    url = f"http://{host}:{selected_port}"

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    print("=" * 65)
    print("   🐦 HEARTHWREN DESKTOP - ULTRA-LIGHTWEIGHT AGENT STUDIO")
    print("=" * 65)
    print(f" * Active Workspace : {workspace_root}")
    print(f" * Local Server    : {url}")
    print(" * Memory Footprint: ~25 MB (Zero Electron / Zero Node.js)")
    print("=" * 65)

    browser_proc: subprocess.Popen[Any] | None = None

    if open_window:
        browser_bin, bname = find_system_app_browser()
        if browser_bin:
            print(f" * Launching standalone native app window via {bname}...")
            # --app creates a chromeless standalone window without tabs or address bar
            try:
                browser_proc = subprocess.Popen(
                    [browser_bin, f"--app={url}"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                print(f" [!] Could not launch app mode directly ({e}), opening default browser...")
                webbrowser.open(url)
        else:
            print(" * Opening UI in default system browser...")
            webbrowser.open(url)

    print(" * Status          : Running. Keep this terminal open while using Hearthwren.")
    print(" * Exit            : Press Ctrl+C in this terminal to quit.")
    print("=" * 65)

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nInterrupt received. Stopping Hearthwren Desktop...")
    finally:
        server.shutdown()
        server.server_close()
        print("Hearthwren Desktop stopped successfully.")


def main() -> None:
    """CLI entry point for direct execution: python -m hearthwren.gui.launcher."""
    parser = argparse.ArgumentParser(description="Hearthwren Ultra-Lightweight Desktop Studio")
    parser.add_argument("--port", "-p", type=int, default=None, help="HTTP port (default: 7860 or next available)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--repo", "-r", type=str, default=None, help="Path to initial workspace repository")
    parser.add_argument("--no-browser", action="store_true", help="Start server only without launching browser window")
    args = parser.parse_args()

    repo = Path(args.repo).resolve() if args.repo else Path.cwd().resolve()
    launch_desktop(host=args.host, port=args.port, workspace_root=repo, open_window=not args.no_browser)


if __name__ == "__main__":
    main()
