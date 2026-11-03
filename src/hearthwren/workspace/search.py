"""Workspace search service for Hearthwren.

Uses ripgrep (rg) when available with an automatic pure-Python fallback.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


IGNORE_DIRS = {
    ".git",
    ".hearthwren",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "dist",
    "build",
}

BINARY_EXTENSIONS = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".gguf",
    ".pkl",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".zip",
    ".tar",
    ".gz",
    ".pyc",
}


class SearchService:
    """Provides bounded, ignore-aware search across workspace files."""

    def __init__(self, workspace_root: Path | None = None, max_results: int = 50):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.max_results = max_results
        self.has_ripgrep = shutil.which("rg") is not None

    def search(
        self,
        query: str,
        is_regex: bool = False,
        max_results: int | None = None,
        file_pattern: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search workspace files for pattern."""
        limit = max_results or self.max_results

        if self.has_ripgrep:
            try:
                results = self._search_ripgrep(query, is_regex=is_regex, limit=limit, file_pattern=file_pattern)
                if results is not None:
                    return results
            except Exception:
                # Ripgrep invocation error; fall back to python search
                pass

        return self._search_python_fallback(query, is_regex=is_regex, limit=limit, file_pattern=file_pattern)

    def _search_ripgrep(
        self,
        query: str,
        is_regex: bool,
        limit: int,
        file_pattern: str | None,
    ) -> list[dict[str, Any]] | None:
        """Execute ripgrep subprocess."""
        cmd = [
            "rg",
            "--line-number",
            "--color",
            "never",
            "--max-count",
            str(limit),
            "--max-columns",
            "300",
        ]
        if not is_regex:
            cmd.append("--fixed-strings")
        if file_pattern:
            cmd.extend(["--glob", file_pattern])

        cmd.extend(["--", query, str(self.workspace_root)])

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15.0,
                cwd=str(self.workspace_root),
            )
            matches: list[dict[str, Any]] = []
            for line in res.stdout.splitlines():
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    file_path_raw = parts[0]
                    try:
                        rel_file = str(Path(file_path_raw).resolve().relative_to(self.workspace_root))
                    except ValueError:
                        rel_file = file_path_raw

                    try:
                        line_num = int(parts[1])
                    except ValueError:
                        line_num = 1

                    match_text = parts[2].strip()
                    matches.append({"file": rel_file, "line": line_num, "text": match_text})
                    if len(matches) >= limit:
                        break
            return matches
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def _search_python_fallback(
        self,
        query: str,
        is_regex: bool,
        limit: int,
        file_pattern: str | None,
    ) -> list[dict[str, Any]]:
        """Pure-Python search fallback when ripgrep is unavailable."""
        matches: list[dict[str, Any]] = []

        if is_regex:
            try:
                pattern = re.compile(query)
            except re.error:
                pattern = re.compile(re.escape(query))
        else:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        glob_pattern = re.compile(file_pattern.replace(".", r"\.").replace("*", ".*")) if file_pattern else None

        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            for file in files:
                if any(file.endswith(ext) for ext in BINARY_EXTENSIONS):
                    continue
                if file.startswith("."):
                    continue
                if glob_pattern and not glob_pattern.search(file):
                    continue

                full_path = Path(root) / file
                try:
                    rel_path = str(full_path.relative_to(self.workspace_root))
                    # Avoid reading files larger than 1 MB in fallback
                    if full_path.stat().st_size > 1_000_000:
                        continue

                    lines = full_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                    for idx, line_text in enumerate(lines, start=1):
                        if pattern.search(line_text):
                            matches.append({
                                "file": rel_path,
                                "line": idx,
                                "text": line_text.strip()[:200],
                            })
                            if len(matches) >= limit:
                                return matches
                except Exception:
                    continue

        return matches
