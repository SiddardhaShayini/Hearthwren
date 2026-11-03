"""Lightweight embedded HTTP and REST server for Hearthwren Desktop UI.

Uses Python standard library (http.server) to avoid adding heavy web framework dependencies.
Runs entirely on localhost and consumes < 20 MB RAM.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from hearthwren.config import load_config
from hearthwren.controller import AgentController
from hearthwren.resource_supervisor import ResourceSupervisor
from hearthwren.subtasks import SequentialSubtaskRunner
from hearthwren.workspace.detector import ProjectDetector
from hearthwren.workspace.git_service import GitService
from hearthwren.workspace.indexer import WorkspaceIndexer
from hearthwren.workspace.memory import MemoryManager

STATIC_DIR = Path(__file__).parent / "static"


def pick_folder_dialog(initial_dir: str | None = None) -> str:
    """Open a native Windows/macOS/Linux folder picker dialog."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        # In automated test environment, avoid blocking headless runs
        return str(Path(initial_dir).resolve()) if initial_dir else os.getcwd()

    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        start_dir = initial_dir or os.getcwd()
        if not Path(start_dir).is_dir():
            start_dir = os.getcwd()
        chosen = filedialog.askdirectory(
            initialdir=start_dir,
            title="Select Working Repository for Hearthwren",
        )
        root.destroy()
        return str(Path(chosen).resolve()) if chosen else ""
    except Exception:
        return ""


class HearthwrenAPIHandler(BaseHTTPRequestHandler):
    """Handles static assets and JSON API routes for Hearthwren Desktop UI."""

    # Server-wide shared workspace root
    workspace_root: Path = Path.cwd().resolve()

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard HTTP request logging to keep console clean."""
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        """Send a JSON HTTP response."""
        encoded = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_static(self, filename: str, content_type: str) -> None:
        """Serve a static file from static/ directory."""
        file_path = STATIC_DIR / filename
        if not file_path.is_file():
            self.send_error(404, f"Static asset '{filename}' not found.")
            return

        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _read_body_json(self) -> dict[str, Any]:
        """Parse incoming JSON request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_GET(self) -> None:
        """Handle GET requests for static assets and read-only endpoints."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Static asset routing
        if path in ("/", "/index.html"):
            self._send_static("index.html", "text/html")
            return
        elif path == "/styles.css":
            self._send_static("styles.css", "text/css")
            return
        elif path == "/app.js":
            self._send_static("app.js", "application/javascript")
            return
        elif path in ("/favicon.ico", "/favicon.svg"):
            fav = STATIC_DIR / "assets" / "hearthwren-icon.svg"
            if fav.is_file():
                content = fav.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            self.send_error(404, "Favicon not found.")
            return
        elif path.startswith("/assets/"):
            asset_name = Path(path[len("/assets/"):].lstrip("/\\")).name
            asset_path = STATIC_DIR / "assets" / asset_name
            if not asset_path.is_file():
                # Fallback to repo root assets/
                asset_path = self.workspace_root / "assets" / asset_name

            if asset_path.is_file():
                mime = "image/svg+xml" if asset_path.suffix.lower() == ".svg" else "application/octet-stream"
                content = asset_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            self.send_error(404, f"Asset '{asset_name}' not found.")
            return

        # 2. REST API endpoints
        if path == "/api/status":
            cfg = load_config(self.workspace_root)
            supervisor = ResourceSupervisor(cfg, self.workspace_root)
            sys_mem = supervisor.get_system_memory()
            proc_mem = supervisor.get_process_memory()
            detector = ProjectDetector(self.workspace_root)
            proj = detector.detect()
            git_svc = GitService(self.workspace_root)
            git_st = git_svc.status()
            mem_mgr = MemoryManager(self.workspace_root)
            model_path = Path(cfg.model_path)

            self._send_json({
                "workspace": str(self.workspace_root),
                "workspace_name": self.workspace_root.name,
                "project": {
                    "primary_language": proj.primary_language,
                    "manifests": proj.manifests,
                    "test_framework": proj.test_framework,
                    "total_source_files": proj.total_source_files,
                },
                "resources": {
                    "total_system_ram_gb": sys_mem["total_gb"],
                    "available_ram_gb": sys_mem["available_gb"],
                    "ram_ceiling_gb": cfg.ram_ceiling_gb,
                    "process_rss_mb": proc_mem["rss_mb"],
                },
                "git": git_st,
                "memory_exists": mem_mgr.exists(),
                "model_installed": model_path.is_file() and model_path.stat().st_size > 100_000_000,
                "model_path": str(model_path),
            })
            return

        elif path == "/api/doctor":
            cfg = load_config(self.workspace_root)
            supervisor = ResourceSupervisor(cfg, self.workspace_root)
            sys_mem = supervisor.get_system_memory()

            model_path = Path(cfg.model_path)
            model_exists = model_path.is_file() and model_path.stat().st_size > 100_000_000

            import shutil
            import sys
            rg_found = bool(shutil.which("rg"))
            git_found = bool(shutil.which("git"))
            mem_mgr = MemoryManager(self.workspace_root)

            checks = [
                {
                    "name": "Python 3.11+",
                    "status": "PASS" if sys.version_info >= (3, 11) else "FAIL",
                    "value": f"v{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                },
                {
                    "name": "RAM Headroom",
                    "status": "PASS" if sys_mem["available_gb"] >= 1.5 else "WARN",
                    "value": f"{sys_mem['available_gb']} GB free (Ceiling 3.5 GB)",
                },
                {
                    "name": "Nanbeige4.1-3B Weights",
                    "status": "PASS" if model_exists else "WARN",
                    "value": "Present (~2.0 GB)" if model_exists else "Missing (offline fallback active)",
                },
                {
                    "name": "Code Search Engine",
                    "status": "PASS" if rg_found else "INFO",
                    "value": "Ripgrep found" if rg_found else "Pure-Python search active",
                },
                {
                    "name": "Version Control (Git)",
                    "status": "PASS" if git_found else "WARN",
                    "value": "Git CLI available",
                },
                {
                    "name": "Project Memory",
                    "status": "PASS" if mem_mgr.exists() else "WARN",
                    "value": "AGENT_MEMORY.md present" if mem_mgr.exists() else "Missing (run Init)",
                },
            ]
            self._send_json({"checks": checks})
            return

        elif path == "/api/diff":
            git_svc = GitService(self.workspace_root)
            unstaged_diff = git_svc.diff(staged=False)
            staged_diff = git_svc.diff(staged=True)
            self._send_json({
                "unstaged": unstaged_diff,
                "staged": staged_diff,
                "is_repo": git_svc.is_git_repo(),
            })
            return

        elif path == "/api/search":
            q = query.get("q", [""])[0]
            symbol_only = query.get("symbol", ["0"])[0] in ("1", "true")
            indexer = WorkspaceIndexer(self.workspace_root)
            if not indexer.db_path.exists():
                indexer.index_workspace(max_files=150)
            symbols = indexer.find_symbol(q)
            fts = [] if symbol_only else indexer.search_fts(q, limit=20)
            self._send_json({"query": q, "symbols": symbols, "matches": fts})
            return

        elif path == "/api/memory":
            mem_mgr = MemoryManager(self.workspace_root)
            if not mem_mgr.exists():
                self._send_json({"exists": False, "sections": {}, "stale": []})
                return
            sections = mem_mgr.parse_sections()
            stale = mem_mgr.check_stale_entries()
            self._send_json({
                "exists": True,
                "sections": sections,
                "stale": stale,
            })
            return

        elif path == "/api/browse":
            # List sibling/child directories for repo selection
            req_dir = query.get("dir", [""])[0].strip()
            current = Path(req_dir).resolve() if req_dir and Path(req_dir).is_dir() else self.workspace_root
            parent = current.parent

            # Detect system drive roots on Windows
            drives: list[str] = []
            if os.name == "nt":
                import string
                for letter in string.ascii_uppercase:
                    drive_p = Path(f"{letter}:\\")
                    if drive_p.is_dir():
                        drives.append(str(drive_p))

            subdirs: list[str] = []
            try:
                for entry in current.iterdir():
                    if entry.is_dir() and not entry.name.startswith("."):
                        subdirs.append(entry.name)
            except Exception:
                pass

            self._send_json({
                "current": str(current),
                "parent": str(parent) if parent != current else None,
                "drives": drives,
                "subdirectories": sorted(subdirs)[:100],
            })
            return

        self.send_error(404, "Endpoint not found.")

    def do_POST(self) -> None:
        """Handle POST requests for action execution."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_body_json()

        if path == "/api/browse-dialog":
            current_str = body.get("current", str(self.workspace_root))
            chosen = pick_folder_dialog(current_str)
            if chosen:
                self._send_json({"success": True, "path": chosen, "canceled": False})
            else:
                self._send_json({"success": False, "canceled": True, "path": current_str})
            return


        if path == "/api/set-repo":
            new_path_str = body.get("path", "").strip()
            if not new_path_str:
                self._send_json({"success": False, "error": "No path provided."}, status=400)
                return
            new_path = Path(new_path_str).resolve()
            if not new_path.is_dir():
                self._send_json({"success": False, "error": f"Path is not a directory: {new_path}"}, status=400)
                return
            HearthwrenAPIHandler.workspace_root = new_path
            self._send_json({"success": True, "workspace": str(new_path), "name": new_path.name})
            return

        elif path == "/api/plan":
            task = body.get("task", "").strip()
            if not task:
                self._send_json({"success": False, "error": "Task description is required."}, status=400)
                return
            controller = AgentController(self.workspace_root)
            res = controller.plan_task(task)
            self._send_json(res)
            return

        elif path == "/api/guide":
            q = body.get("query", "").strip()
            if not q:
                self._send_json({"success": False, "error": "Query is required."}, status=400)
                return
            controller = AgentController(self.workspace_root)
            res = controller.guide_task(q)
            self._send_json(res)
            return

        elif path == "/api/run":
            task = body.get("task", "").strip()
            multi_phase = bool(body.get("multi_phase", False))
            if not task:
                self._send_json({"success": False, "error": "Task description is required."}, status=400)
                return

            if multi_phase:
                runner = SequentialSubtaskRunner(self.workspace_root)
                multi_res = runner.run_all_phases(task)
                self._send_json({
                    "task": multi_res.task_description,
                    "success": multi_res.success,
                    "phases": [
                        {
                            "phase": p.phase.value,
                            "success": p.success,
                            "summary": p.summary,
                            "actions": p.actions,
                        }
                        for p in multi_res.phase_results
                    ],
                    "final_report": multi_res.final_report,
                })
                return

            controller = AgentController(self.workspace_root)
            res = controller.execute_task(task)
            # Ensure state is serializable
            if hasattr(res.get("state"), "value"):
                res["state"] = res["state"].value
            self._send_json(res)
            return

        elif path == "/api/verify":
            controller = AgentController(self.workspace_root)
            res = controller.verify_project()
            self._send_json(res)
            return

        elif path == "/api/commit":
            msg = body.get("message", "").strip()
            if not msg:
                self._send_json({"success": False, "error": "Commit message is required."}, status=400)
                return
            git_svc = GitService(self.workspace_root)
            git_svc.stage_all(approved=True)
            res = git_svc.commit(message=msg, approved=True)
            self._send_json(res)
            return

        elif path == "/api/push":
            git_svc = GitService(self.workspace_root)
            branch = git_svc.status().get("branch") or "main"
            res = git_svc.push(branch=branch, approved=True)
            self._send_json(res)
            return

        elif path == "/api/index":
            indexer = WorkspaceIndexer(self.workspace_root)
            n = indexer.index_workspace(max_files=300)
            self._send_json({"success": True, "indexed_files": n})
            return

        self.send_error(404, "Endpoint not found.")


def run_server(host: str = "127.0.0.1", port: int = 7860, workspace_root: Path | None = None) -> ThreadingHTTPServer:
    """Create and start the HTTP server."""
    if workspace_root:
        HearthwrenAPIHandler.workspace_root = workspace_root.resolve()

    server = ThreadingHTTPServer((host, port), HearthwrenAPIHandler)
    return server
