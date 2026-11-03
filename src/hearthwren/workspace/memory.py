"""Memory management for Hearthwren.

Manages AGENT_MEMORY.md reading, section parsing, stale entry detection,
diff previews, and structured session logging.
"""

from __future__ import annotations

import difflib
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


class MemoryManager:
    """Reads, verifies, and safely updates AGENT_MEMORY.md."""

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.memory_path = self.workspace_root / "AGENT_MEMORY.md"

    def exists(self) -> bool:
        """Check if AGENT_MEMORY.md exists."""
        return self.memory_path.exists()

    def read_raw(self) -> str:
        """Read full content of AGENT_MEMORY.md."""
        if not self.exists():
            return ""
        return self.memory_path.read_text(encoding="utf-8")

    def parse_sections(self) -> dict[str, str]:
        """Parse AGENT_MEMORY.md into major markdown sections."""
        content = self.read_raw()
        if not content:
            return {}

        sections: dict[str, str] = {}
        # Match ## Headers
        pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
        matches = list(pattern.finditer(content))

        for i, match in enumerate(matches):
            title = match.group(1).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            sections[title] = content[start:end].strip()

        return sections

    def check_stale_entries(self) -> list[str]:
        """Cross-check files and directories mentioned in memory against actual workspace."""
        if not self.exists():
            return ["AGENT_MEMORY.md does not exist in workspace."]

        content = self.read_raw()
        stale_flags: list[str] = []

        # Find backtick-wrapped paths like `src/...` or `tests/...`
        path_matches = re.findall(r"`([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)`", content)
        for p in set(path_matches):
            # Skip URLs, generic names, or config keys
            if "/" in p or "\\" in p or p.endswith(".md") or p.endswith(".toml") or p.endswith(".py"):
                full_p = self.workspace_root / p
                if not full_p.exists():
                    stale_flags.append(f"Mentioned file does not exist on disk: '{p}'")

        return stale_flags

    def update_section(
        self,
        section_title: str,
        new_content: str,
        approved: bool = False,
    ) -> dict[str, Any]:
        """Update a specific section in AGENT_MEMORY.md with diff preview and approval."""
        if not self.exists():
            return {"success": False, "error": "AGENT_MEMORY.md does not exist."}

        current_content = self.read_raw()
        pattern = re.compile(r"^(##\s+.*" + re.escape(section_title) + r".*)$", re.MULTILINE | re.IGNORECASE)
        match = pattern.search(current_content)
        if not match:
            return {
                "success": False,
                "error": f"Section matching '{section_title}' not found in AGENT_MEMORY.md.",
            }

        start_header = match.end()
        # Find next ## header or EOF
        next_header_pattern = re.compile(r"^##\s+", re.MULTILINE)
        next_match = next_header_pattern.search(current_content, start_header)
        end_idx = next_match.start() if next_match else len(current_content)

        # Build proposed content
        formatted_new = f"\n\n{new_content.strip()}\n\n"
        proposed = current_content[:start_header] + formatted_new + current_content[end_idx:]

        diff = "".join(
            difflib.unified_diff(
                current_content.splitlines(keepends=True),
                proposed.splitlines(keepends=True),
                fromfile="a/AGENT_MEMORY.md",
                tofile="b/AGENT_MEMORY.md",
            )
        )

        if not approved:
            return {
                "success": False,
                "needs_approval": True,
                "section": match.group(1),
                "diff": diff,
                "message": f"Proposal to update section '{match.group(1)}'. Approval required.",
            }

        self.memory_path.write_text(proposed, encoding="utf-8")
        return {
            "success": True,
            "needs_approval": False,
            "section": match.group(1),
            "diff": diff,
            "message": f"Section '{match.group(1)}' successfully updated.",
        }

    def append_session_log(
        self,
        agent_model: str,
        task: str,
        phase: str,
        files_read: list[str],
        files_written: list[str],
        commands_run: list[str],
        outcome: str,
        mistakes: str = "None",
        lessons: str = "None",
        approved_by_user: str = "Yes",
        approved: bool = False,
    ) -> dict[str, Any]:
        """Format and append a structured session entry to Agent Session Log in AGENT_MEMORY.md."""
        if not self.exists():
            return {"success": False, "error": "AGENT_MEMORY.md does not exist."}

        # Calculate IST time (UTC+5:30)
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist_tz).strftime("%Y-%m-%d %H:%M IST")

        log_entry = f"""
### Session — {now_ist}
- **Agent/Model:** {agent_model}
- **Task:** {task}
- **Phase:** {phase}
- **Files read:** {", ".join(files_read) if files_read else "None"}
- **Files written/modified:** {", ".join(files_written) if files_written else "None"}
- **Commands run:** {", ".join(commands_run) if commands_run else "None"}
- **Outcome:** {outcome}
- **Mistakes / wrong assumptions:** {mistakes}
- **Lessons:** {lessons}
- **Approved by user:** {approved_by_user}
"""

        current_content = self.read_raw()
        marker = "<!-- END OF AGENT_MEMORY.md — Append new session entries above this line -->"

        if marker in current_content:
            new_content = current_content.replace(marker, f"{log_entry.strip()}\n\n---\n\n{marker}")
        else:
            new_content = current_content + f"\n\n---\n{log_entry}\n"

        diff = "".join(
            difflib.unified_diff(
                current_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile="a/AGENT_MEMORY.md",
                tofile="b/AGENT_MEMORY.md",
            )
        )

        if not approved:
            return {
                "success": False,
                "needs_approval": True,
                "diff": diff,
                "message": "Session log update prepared. User approval required before writing.",
            }

        self.memory_path.write_text(new_content, encoding="utf-8")
        return {
            "success": True,
            "needs_approval": False,
            "diff": diff,
            "message": "Session log appended to AGENT_MEMORY.md.",
        }

    def generate_initial_memory(self, project_name: str, description: str = "") -> str:
        """Scaffold a fresh AGENT_MEMORY.md file for a new project."""
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        date_str = datetime.now(ist_tz).strftime("%Y-%m-%d")

        return f"""# AGENT MEMORY — {project_name}
_Last updated: {date_str} by Hearthwren v0.1.0_

## 1. Project Summary
{description or f"Project {project_name} managed with Hearthwren."}

## 2. Architecture Snapshot
- Entry points: TBD
- Key directories: TBD

## 3. Setup & Test Commands
- Install: TBD
- Test: TBD
- Run: TBD

## 4. Conventions
- Code style: TBD

## 5. Constraints
- Hardware: CPU-only, 8 GB RAM target
- Local-first execution

## 6. Known Issues & Past Failures
| Date | Task | Issue / Mistake | What Happened | Lesson |
|---|---|---|---|---|

## 7. Open Questions
| # | Question | Status |
|---|---|---|

## 8. Key Decisions Log
| Date | Decision | Rationale | Alternatives Rejected |
|---|---|---|---|

## 9. Agent Session Log

<!-- END OF AGENT_MEMORY.md — Append new session entries above this line -->
"""
