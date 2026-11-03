"""Test discovery and execution service for Hearthwren.

Discovers project-native test suites and captures exact exit codes and failure logs.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


class TestRunner:
    """Discovers and runs project tests safely with bounded output capture."""

    def __init__(self, workspace_root: Path | None = None, output_line_ceiling: int = 200):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.output_line_ceiling = output_line_ceiling

    def discover_test_command(self) -> list[str] | None:
        """Auto-detect project type and default test command."""
        # 1. Python
        if (self.workspace_root / "pytest.ini").exists() or (self.workspace_root / "pyproject.toml").exists():
            return ["pytest", "-v"]
        if (self.workspace_root / "tests").is_dir():
            return ["pytest", "-v"]
        if (self.workspace_root / "setup.py").exists():
            return ["python", "-m", "unittest"]

        # 2. Node.js
        pkg_json = self.workspace_root / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8"))
                if "scripts" in data and "test" in data["scripts"]:
                    return ["npm", "test"]
            except Exception:
                pass

        # 3. Rust
        if (self.workspace_root / "Cargo.toml").exists():
            return ["cargo", "test"]

        # 4. Go
        if (self.workspace_root / "go.mod").exists():
            return ["go", "test", "./..."]

        return None

    def run_tests(
        self,
        command: list[str] | str | None = None,
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        """Execute project tests and extract verified exit code and diagnostic lines."""
        if command is None:
            cmd = self.discover_test_command()
            if cmd is None:
                return {
                    "executed": False,
                    "passed": False,
                    "error": "No test framework or test directory automatically discovered in workspace.",
                }
        elif isinstance(command, str):
            cmd = command.split()
        else:
            cmd = command

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(self.workspace_root),
            )
            raw_stdout = res.stdout or ""
            raw_stderr = res.stderr or ""

            # Bound output lines
            stdout_lines = raw_stdout.splitlines()
            stderr_lines = raw_stderr.splitlines()

            bounded_stdout = "\n".join(stdout_lines[: self.output_line_ceiling])
            bounded_stderr = "\n".join(stderr_lines[: self.output_line_ceiling])

            passed = (res.returncode == 0)
            failures = self._extract_failure_evidence(stdout_lines + stderr_lines) if not passed else []

            return {
                "executed": True,
                "command": " ".join(cmd),
                "passed": passed,
                "exit_code": res.returncode,
                "stdout": bounded_stdout,
                "stderr": bounded_stderr,
                "failures_detected": failures,
                "truncated": len(stdout_lines) > self.output_line_ceiling or len(stderr_lines) > self.output_line_ceiling,
            }
        except subprocess.TimeoutExpired:
            return {
                "executed": True,
                "command": " ".join(cmd),
                "passed": False,
                "exit_code": -1,
                "error": f"Test run timed out after {timeout_seconds} seconds.",
            }
        except Exception as e:
            return {
                "executed": False,
                "command": " ".join(cmd) if cmd else "",
                "passed": False,
                "error": f"Failed to invoke test command: {e}",
            }

    def _extract_failure_evidence(self, output_lines: list[str]) -> list[str]:
        """Extract lines likely pointing to assertion errors or failed tests."""
        evidence: list[str] = []
        failure_patterns = [
            re.compile(r"FAILED\s+([^\s]+)"),
            re.compile(r"AssertionError:\s*(.*)"),
            re.compile(r"Error:\s*(.*)"),
            re.compile(r"FAIL:\s*([^\s]+)"),
            re.compile(r"File\s+\"([^\"]+)\",\s+line\s+(\d+)"),
        ]

        for line in output_lines:
            line_str = line.strip()
            for pat in failure_patterns:
                if pat.search(line_str):
                    evidence.append(line_str)
                    break
            if len(evidence) >= 15:
                break
        return evidence
