"""Safe, bounded file operations for Hearthwren."""

from __future__ import annotations

import difflib
import os
from pathlib import Path
from typing import Any


PROTECTED_PATTERNS = {
    ".git",
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
}


class FileSafetyViolation(PermissionError):
    """Raised when an operation violates workspace boundary or targets protected paths."""


class FileOps:
    """Manages workspace-scoped file reading, diffing, and atomic writing."""

    def __init__(self, workspace_root: Path | None = None, max_read_lines: int = 200):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.max_read_lines = max_read_lines

    def resolve_path(self, relative_or_absolute_path: str | Path) -> Path:
        """Resolve and validate that a path is strictly inside the workspace root."""
        raw_path = Path(relative_or_absolute_path)
        if raw_path.is_absolute():
            resolved = raw_path.resolve()
        else:
            resolved = (self.workspace_root / raw_path).resolve()

        # Check path boundary
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            raise FileSafetyViolation(
                f"Access denied: Path '{relative_or_absolute_path}' resolves outside "
                f"workspace root '{self.workspace_root}'."
            )

        # Check protected paths
        rel_parts = resolved.relative_to(self.workspace_root).parts
        for part in rel_parts:
            if part.lower() in PROTECTED_PATTERNS or part.startswith(".env"):
                raise FileSafetyViolation(
                    f"Access denied: Target '{relative_or_absolute_path}' touches "
                    f"protected file or directory '{part}'."
                )

        return resolved

    def read_file(
        self,
        path: str | Path,
        start_line: int = 1,
        end_line: int | None = None,
        max_lines: int | None = None,
    ) -> dict[str, Any]:
        """Read a window of lines from a file. Prevents loading gigantic files into memory."""
        resolved = self.resolve_path(path)
        if not resolved.exists():
            return {
                "success": False,
                "error": f"File not found: {resolved}",
                "path": str(resolved.relative_to(self.workspace_root)),
            }
        if resolved.is_dir():
            return {
                "success": False,
                "error": f"Path is a directory: {resolved}",
                "path": str(resolved.relative_to(self.workspace_root)),
            }

        limit = max_lines or self.max_read_lines
        start_idx = max(1, start_line)

        try:
            lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            total_lines = len(lines)

            end_idx = end_line if end_line is not None else min(start_idx + limit - 1, total_lines)
            end_idx = min(end_idx, total_lines)

            if start_idx > total_lines:
                selected_lines = []
            else:
                selected_lines = lines[start_idx - 1 : end_idx]

            content = "".join(selected_lines)
            return {
                "success": True,
                "path": str(resolved.relative_to(self.workspace_root)),
                "content": content,
                "start_line": start_idx,
                "end_line": end_idx,
                "total_lines": total_lines,
                "truncated": (end_idx < total_lines),
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to read file: {e}",
                "path": str(resolved.relative_to(self.workspace_root)),
            }

    def generate_diff(self, path: str | Path, new_content: str) -> str:
        """Generate a unified diff comparing existing file content against proposed content."""
        resolved = self.resolve_path(path)
        rel_path = str(resolved.relative_to(self.workspace_root))

        if resolved.exists():
            old_lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        else:
            old_lines = []

        new_lines = new_content.splitlines(keepends=True)
        # Ensure trailing newline if needed
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"

        diff_gen = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{rel_path}" if resolved.exists() else "/dev/null",
            tofile=f"b/{rel_path}",
        )
        return "".join(diff_gen)

    def write_file(
        self,
        path: str | Path,
        content: str,
        approved: bool = False,
        create_backup: bool = True,
    ) -> dict[str, Any]:
        """Safely write content to a file. Requires approved=True to commit changes."""
        resolved = self.resolve_path(path)
        rel_path = str(resolved.relative_to(self.workspace_root))

        diff = self.generate_diff(path, content)

        if not approved:
            return {
                "success": False,
                "needs_approval": True,
                "diff": diff,
                "path": rel_path,
                "message": f"Write proposal generated for '{rel_path}'. Approval required before applying.",
            }

        # User approved: perform atomic backup and write
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            backup_path = None
            if resolved.exists() and create_backup:
                backup_path = resolved.with_name(f"{resolved.name}.hearthwren.bak")
                backup_path.write_bytes(resolved.read_bytes())

            # Atomic write using temp file
            temp_path = resolved.with_name(f".{resolved.name}.tmp")
            temp_path.write_text(content, encoding="utf-8")
            temp_path.replace(resolved)

            return {
                "success": True,
                "needs_approval": False,
                "path": rel_path,
                "diff": diff,
                "backup_path": str(backup_path.relative_to(self.workspace_root)) if backup_path else None,
                "bytes_written": len(content.encode("utf-8")),
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to write file '{rel_path}': {e}",
                "path": rel_path,
                "diff": diff,
            }

    def list_files(self, subpath: str = "", max_files: int = 200) -> list[str]:
        """List files in workspace, skipping ignored and hidden paths."""
        target = self.resolve_path(subpath) if subpath else self.workspace_root
        results: list[str] = []

        ignore_dirs = {".git", ".hearthwren", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache"}

        for root, dirs, files in os.walk(target):
            # Prune ignored directories
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            for file in files:
                if file.endswith(".hearthwren.bak") or file.startswith("."):
                    continue
                full_path = Path(root) / file
                try:
                    rel_path = str(full_path.relative_to(self.workspace_root))
                    results.append(rel_path)
                    if len(results) >= max_files:
                        return results
                except ValueError:
                    continue

        return sorted(results)
