"""Git operations service for Hearthwren.

Invokes the system git CLI directly via subprocess.
Enforces explicit approval gates for stage, commit, and push actions.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


class GitService:
    """Safely executes git operations with approval enforcement."""

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()

    def _run_git(self, args: list[str], timeout_seconds: float = 20.0) -> subprocess.CompletedProcess[str]:
        """Execute a git command in the workspace directory."""
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(self.workspace_root),
        )

    def is_git_repo(self) -> bool:
        """Check if workspace root is inside a git repository."""
        try:
            res = self._run_git(["rev-parse", "--is-inside-work-tree"])
            return res.returncode == 0 and res.stdout.strip() == "true"
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        """Get git working tree status."""
        if not self.is_git_repo():
            return {
                "is_repo": False,
                "clean": True,
                "branch": None,
                "staged": [],
                "unstaged": [],
                "untracked": [],
            }

        branch_res = self._run_git(["branch", "--show-current"])
        current_branch = branch_res.stdout.strip() or "HEAD (detached)"

        status_res = self._run_git(["status", "--porcelain"])
        staged: list[str] = []
        unstaged: list[str] = []
        untracked: list[str] = []

        for line in status_res.stdout.splitlines():
            if not line:
                continue
            index_status = line[0]
            worktree_status = line[1]
            file_path = line[3:].strip()

            if index_status in ("M", "A", "D", "R"):
                staged.append(file_path)
            if worktree_status in ("M", "D"):
                unstaged.append(file_path)
            if index_status == "?" and worktree_status == "?":
                untracked.append(file_path)

        clean = not (staged or unstaged or untracked)
        return {
            "is_repo": True,
            "clean": clean,
            "branch": current_branch,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
            "raw": status_res.stdout,
        }

    def diff(self, staged: bool = False) -> str:
        """Return git unified diff."""
        if not self.is_git_repo():
            return ""
        args = ["diff", "--cached"] if staged else ["diff"]
        res = self._run_git(args)
        return res.stdout

    def log(self, max_count: int = 5) -> list[dict[str, str]]:
        """Return recent commit log entries."""
        if not self.is_git_repo():
            return []
        res = self._run_git([
            "log",
            f"-n{max_count}",
            "--pretty=format:%H|%an|%ad|%s",
            "--date=short",
        ])
        commits = []
        for line in res.stdout.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3],
                })
        return commits

    def stage(self, files: list[str] | str, approved: bool = False) -> dict[str, Any]:
        """Stage files for commit. Requires approval."""
        file_list = [files] if isinstance(files, str) else files
        if not approved:
            return {
                "success": False,
                "needs_approval": True,
                "action": "git add",
                "files": file_list,
                "message": f"Proposal to stage files: {file_list}. Approval required.",
            }

        res = self._run_git(["add", "--", *file_list])
        return {
            "success": res.returncode == 0,
            "exit_code": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }

    def commit(self, message: str, approved: bool = False) -> dict[str, Any]:
        """Commit staged changes. Requires explicit approval."""
        if not message.strip():
            return {"success": False, "error": "Commit message cannot be empty."}

        if not approved:
            staged_diff = self.diff(staged=True)
            return {
                "success": False,
                "needs_approval": True,
                "action": "git commit",
                "message": message,
                "staged_diff": staged_diff,
                "warning": "Commit requires explicit user confirmation.",
            }

        res = self._run_git(["commit", "-m", message])
        return {
            "success": res.returncode == 0,
            "exit_code": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "message": message,
        }

    def push(self, remote: str = "origin", branch: str | None = None, approved: bool = False) -> dict[str, Any]:
        """Push branch to remote. Requires explicit approval and verifies exit code."""
        cur_branch = branch or self.status().get("branch") or "main"

        if not approved:
            return {
                "success": False,
                "needs_approval": True,
                "action": "git push",
                "destination": f"{remote}/{cur_branch}",
                "warning": f"Explicit confirmation required to push to {remote}/{cur_branch}.",
            }

        res = self._run_git(["push", remote, cur_branch], timeout_seconds=60.0)
        success = res.returncode == 0
        return {
            "success": success,
            "destination": f"{remote}/{cur_branch}",
            "exit_code": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "verified": success,
        }
