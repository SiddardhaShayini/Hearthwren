"""Tests for MemoryManager."""

from pathlib import Path
from hearthwren.workspace.memory import MemoryManager


def test_memory_generation_and_parsing(tmp_path: Path):
    mem_mgr = MemoryManager(tmp_path)
    assert not mem_mgr.exists()

    scaffold = mem_mgr.generate_initial_memory("TestProject", "A test project description.")
    (tmp_path / "AGENT_MEMORY.md").write_text(scaffold, encoding="utf-8")

    assert mem_mgr.exists()
    sections = mem_mgr.parse_sections()
    assert any("Project Summary" in s for s in sections.keys())


def test_stale_file_detection(tmp_path: Path):
    mem_mgr = MemoryManager(tmp_path)
    content = """# AGENT MEMORY
## 1. Entry Points
- Non-existent: `nonexistent_module/app.py`
"""
    (tmp_path / "AGENT_MEMORY.md").write_text(content, encoding="utf-8")

    stale = mem_mgr.check_stale_entries()
    assert any("nonexistent_module/app.py" in s for s in stale)


def test_session_log_requires_approval(tmp_path: Path):
    mem_mgr = MemoryManager(tmp_path)
    (tmp_path / "AGENT_MEMORY.md").write_text("# AGENT MEMORY\n\n## Session Log\n<!-- END OF AGENT_MEMORY.md — Append new session entries above this line -->", encoding="utf-8")

    # Unapproved returns diff preview
    unapproved = mem_mgr.append_session_log(
        agent_model="Hearthwren-Test",
        task="Test task",
        phase="Phase 1",
        files_read=["a.py"],
        files_written=["b.py"],
        commands_run=["pytest"],
        outcome="success",
        approved=False,
    )
    assert unapproved["success"] is False
    assert unapproved["needs_approval"] is True
    assert "+- **Agent/Model:** Hearthwren-Test" in unapproved["diff"]

    # Approved writes to file
    approved = mem_mgr.append_session_log(
        agent_model="Hearthwren-Test",
        task="Test task",
        phase="Phase 1",
        files_read=["a.py"],
        files_written=["b.py"],
        commands_run=["pytest"],
        outcome="success",
        approved=True,
    )
    assert approved["success"] is True
    assert "Hearthwren-Test" in mem_mgr.read_raw()
