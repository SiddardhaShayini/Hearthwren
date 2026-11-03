"""Session state management for Hearthwren.

Persists task state in .hearthwren/session.json for clean resumption.
Ensures zero secrets or full source files are saved to the cache.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hearthwren.config import get_hearthwren_dir


@dataclass
class SessionState:
    """Bounded, safe operational state for the current or previous task."""

    task_description: str = ""
    state: str = "INITIAL"
    plan_steps: list[str] = field(default_factory=list)
    current_step_index: int = 0
    actions_taken: list[str] = field(default_factory=list)
    last_test_passed: bool | None = None
    repair_attempts: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionStateManager:
    """Loads and saves bounded session state to .hearthwren/session.json."""

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.session_file = get_hearthwren_dir(self.workspace_root) / "session.json"

    def exists(self) -> bool:
        """Check if session.json exists."""
        return self.session_file.exists()

    def load(self) -> SessionState:
        """Load session state from .hearthwren/session.json or return fresh state."""
        if not self.exists():
            return SessionState()
        try:
            content = self.session_file.read_text(encoding="utf-8")
            data = json.loads(content)
            return SessionState(
                task_description=data.get("task_description", ""),
                state=data.get("state", "INITIAL"),
                plan_steps=data.get("plan_steps", []),
                current_step_index=data.get("current_step_index", 0),
                actions_taken=data.get("actions_taken", []),
                last_test_passed=data.get("last_test_passed"),
                repair_attempts=data.get("repair_attempts", 0),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
            )
        except Exception:
            # Rebuild state if corrupted
            return SessionState()

    def save(self, session: SessionState) -> None:
        """Atomically persist session state to .hearthwren/session.json."""
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        session.updated_at = datetime.now(timezone.utc).isoformat()
        raw = json.dumps(asdict(session), indent=2)

        # Atomic temp write
        temp_file = self.session_file.with_suffix(".tmp")
        temp_file.write_text(raw, encoding="utf-8")
        temp_file.replace(self.session_file)

    def clear(self) -> None:
        """Clear active session file."""
        if self.exists():
            try:
                self.session_file.unlink()
            except OSError:
                pass
