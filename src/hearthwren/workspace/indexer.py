"""Lightweight SQLite FTS indexer for Hearthwren.

Provides fast, local, bounded full-text and symbol search.
Runs incrementally during idle time without consuming unbounded RAM.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from hearthwren.config import get_hearthwren_dir

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

TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".toml",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".rs",
    ".go",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".sh",
}


class WorkspaceIndexer:
    """Manages SQLite FTS5 index for fast keyword search and symbol lookups."""

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.db_path = get_hearthwren_dir(self.workspace_root) / "index.db"
        self._init_db()

    def _init_db(self) -> None:
        """Create database tables if they do not exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_meta (
                    path TEXT PRIMARY KEY,
                    mtime REAL,
                    size INTEGER
                )
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS file_fts USING fts5(
                    path UNINDEXED,
                    content,
                    tokenize='porter unicode61'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS symbols (
                    path TEXT,
                    name TEXT,
                    kind TEXT,
                    line INTEGER,
                    PRIMARY KEY (path, name, line)
                )
            """)
            conn.commit()

    def index_workspace(self, yield_check: Any = None, max_files: int = 100) -> int:
        """Index changed files one at a time. Can be interrupted via yield_check callable."""
        indexed_count = 0

        with sqlite3.connect(self.db_path) as conn:
            for root, dirs, files in os.walk(self.workspace_root):
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

                for file in files:
                    if yield_check and yield_check():
                        # Yield to inference or user request immediately
                        return indexed_count

                    ext = Path(file).suffix.lower()
                    if ext not in TEXT_EXTENSIONS or file.startswith("."):
                        continue

                    full_path = Path(root) / file
                    try:
                        rel_path = str(full_path.relative_to(self.workspace_root))
                        stat = full_path.stat()
                        # Skip files over 500 KB to preserve memory
                        if stat.st_size > 500_000:
                            continue

                        # Check if already indexed with same mtime
                        cursor = conn.cursor()
                        cursor.execute("SELECT mtime, size FROM file_meta WHERE path = ?", (rel_path,))
                        row = cursor.fetchone()

                        if row and row[0] == stat.st_mtime and row[1] == stat.st_size:
                            continue  # File unchanged

                        # Read and index
                        content = full_path.read_text(encoding="utf-8", errors="replace")

                        # Remove old entries
                        conn.execute("DELETE FROM file_fts WHERE path = ?", (rel_path,))
                        conn.execute("DELETE FROM symbols WHERE path = ?", (rel_path,))

                        # Insert into FTS
                        conn.execute("INSERT INTO file_fts (path, content) VALUES (?, ?)", (rel_path, content))

                        # Extract basic symbols (def/class in Python, function/fn in other langs)
                        self._index_symbols(conn, rel_path, content)

                        # Update metadata
                        conn.execute(
                            "INSERT OR REPLACE INTO file_meta (path, mtime, size) VALUES (?, ?, ?)",
                            (rel_path, stat.st_mtime, stat.st_size),
                        )
                        indexed_count += 1

                        if indexed_count >= max_files:
                            conn.commit()
                            return indexed_count

                    except Exception:
                        continue

            conn.commit()
        return indexed_count

    def _index_symbols(self, conn: sqlite3.Connection, rel_path: str, content: str) -> None:
        """Lightweight regex-based symbol extractor (classes and functions)."""
        lines = content.splitlines()
        py_func_re = re.compile(r"^\s*def\s+([a-zA-Z0-9_]+)\s*\(")
        py_class_re = re.compile(r"^\s*class\s+([a-zA-Z0-9_]+)")
        js_func_re = re.compile(r"^\s*(?:async\s+)?function\s+([a-zA-Z0-9_]+)\s*\(")

        for line_num, line in enumerate(lines, start=1):
            f_match = py_func_re.match(line) or js_func_re.match(line)
            if f_match:
                conn.execute(
                    "INSERT OR IGNORE INTO symbols (path, name, kind, line) VALUES (?, ?, ?, ?)",
                    (rel_path, f_match.group(1), "function", line_num),
                )
                continue

            c_match = py_class_re.match(line)
            if c_match:
                conn.execute(
                    "INSERT OR IGNORE INTO symbols (path, name, kind, line) VALUES (?, ?, ?, ?)",
                    (rel_path, c_match.group(1), "class", line_num),
                )

    def search_fts(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Query full-text SQLite search index."""
        # Clean query for FTS5 syntax
        clean_q = re.sub(r"[^\w\s]", "", query).strip()
        if not clean_q:
            return []

        results: list[dict[str, Any]] = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT path, snippet(file_fts, 1, '<b>', '</b>', '...', 10) as snip
                    FROM file_fts
                    WHERE file_fts MATCH ?
                    LIMIT ?
                    """,
                    (f"{clean_q}*", limit),
                )
                for row in cursor.fetchall():
                    results.append({"path": row[0], "snippet": row[1]})
        except sqlite3.OperationalError:
            pass
        return results

    def find_symbol(self, name: str) -> list[dict[str, Any]]:
        """Look up symbols by name."""
        results: list[dict[str, Any]] = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT path, name, kind, line FROM symbols WHERE name LIKE ? LIMIT 30",
                    (f"%{name}%",),
                )
                for row in cursor.fetchall():
                    results.append({"path": row[0], "name": row[1], "kind": row[2], "line": row[3]})
        except sqlite3.OperationalError:
            pass
        return results
