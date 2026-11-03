"""Evidence-based error recovery engine for Hearthwren.

Correlates test failures with source code, extracts error lines,
and formulates bounded repair proposals (capped at max_repair_attempts).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hearthwren.config import HearthwrenConfig
from hearthwren.workspace.file_ops import FileOps


@dataclass
class FailureAnalysis:
    """Structured breakdown of a test or build failure."""

    error_type: str
    message: str
    culprit_file: str | None
    culprit_line: int | None
    code_snippet: str | None
    raw_evidence: list[str]


@dataclass
class RepairProposal:
    """Evidence-based proposal to fix an identified failure."""

    analysis: FailureAnalysis
    attempt: int
    max_attempts: int
    recommendation: str
    can_auto_retry: bool


class ErrorRecoveryEngine:
    """Inspects failures, correlates with workspace files, and proposes bounded repairs."""

    def __init__(
        self,
        workspace_root: Path | None = None,
        config: HearthwrenConfig | None = None,
    ):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.config = config or HearthwrenConfig()
        self.file_ops = FileOps(self.workspace_root)

    def analyze_failure(self, test_result: dict[str, Any]) -> FailureAnalysis:
        """Parse raw failure output and correlate with workspace source code."""
        stdout = test_result.get("stdout", "")
        stderr = test_result.get("stderr", "")
        combined = stdout + "\n" + stderr

        evidence: list[str] = test_result.get("failures_detected", [])
        if not evidence and combined.strip():
            evidence = combined.splitlines()[-10:]

        culprit_file: str | None = None
        culprit_line: int | None = None
        error_type = "ExecutionFailure"
        message = "Unknown test failure"

        # Look for standard Python traceback patterns: File "...", line 123
        file_line_re = re.compile(r'File\s+"([^"]+)",\s+line\s+(\d+)(?:,\s+in\s+([a-zA-Z0-9_]+))?')
        matches = list(file_line_re.finditer(combined))
        if matches:
            # Pick the last in-workspace traceback frame
            for m in reversed(matches):
                f_path = m.group(1)
                try:
                    resolved = Path(f_path).resolve()
                    if resolved.is_relative_to(self.workspace_root):
                        culprit_file = str(resolved.relative_to(self.workspace_root))
                        culprit_line = int(m.group(2))
                        break
                except Exception:
                    continue

            # Fallback if no frame was inside workspace
            if culprit_file is None and matches:
                culprit_file = matches[-1].group(1)
                culprit_line = int(matches[-1].group(2))

        # Look for error message like AssertionError: ... or TypeError: ...
        err_match = re.search(r"([A-Za-z0-9_]*Error|Exception|FAILED):\s*(.*)", combined)
        if err_match:
            error_type = err_match.group(1)
            message = err_match.group(2).strip()

        # Fetch snippet if culprit file and line are found
        code_snippet: str | None = None
        if culprit_file and culprit_line:
            read_res = self.file_ops.read_file(
                culprit_file,
                start_line=max(1, culprit_line - 3),
                end_line=culprit_line + 3,
            )
            if read_res.get("success"):
                code_snippet = read_res.get("content")

        return FailureAnalysis(
            error_type=error_type,
            message=message,
            culprit_file=culprit_file,
            culprit_line=culprit_line,
            code_snippet=code_snippet,
            raw_evidence=evidence[:10],
        )

    def propose_repair(self, analysis: FailureAnalysis, attempt: int = 1) -> RepairProposal:
        """Formulate bounded repair proposal. Stops if attempt exceeds max_repair_attempts."""
        max_attempts = self.config.max_repair_attempts

        if attempt > max_attempts:
            rec = (
                f"STOPPING REPAIR LOOP: Exceeded maximum allowed repair attempts ({max_attempts}).\n"
                f"Failure remains in '{analysis.culprit_file}' at line {analysis.culprit_line}: "
                f"{analysis.error_type} - {analysis.message}.\n"
                f"Manual intervention required."
            )
            return RepairProposal(
                analysis=analysis,
                attempt=attempt,
                max_attempts=max_attempts,
                recommendation=rec,
                can_auto_retry=False,
            )

        if analysis.culprit_file and analysis.culprit_line:
            rec = (
                f"Repair Attempt {attempt}/{max_attempts}:\n"
                f"Evidence identified error {analysis.error_type} in '{analysis.culprit_file}' "
                f"at line {analysis.culprit_line}: '{analysis.message}'.\n"
                f"Inspect the offending lines and formulate a surgical patch."
            )
        else:
            rec = (
                f"Repair Attempt {attempt}/{max_attempts}:\n"
                f"Error detected: {analysis.error_type}: {analysis.message}.\n"
                f"Review test output logs and check configuration."
            )

        return RepairProposal(
            analysis=analysis,
            attempt=attempt,
            max_attempts=max_attempts,
            recommendation=rec,
            can_auto_retry=(attempt < max_attempts),
        )
