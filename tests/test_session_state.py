"""Tests for SessionStateManager."""

from pathlib import Path
from hearthwren.session_state import SessionState, SessionStateManager


def test_session_state_lifecycle(tmp_path: Path):
    mgr = SessionStateManager(workspace_root=tmp_path)
    assert not mgr.exists()

    state = SessionState(
        task_description="Add user auth",
        state="PLAN",
        plan_steps=["1. Inspect models", "2. Add tests", "3. Implement routes"],
        current_step_index=1,
        actions_taken=["read_file: models.py"],
    )

    mgr.save(state)
    assert mgr.exists()

    loaded = mgr.load()
    assert loaded.task_description == "Add user auth"
    assert loaded.state == "PLAN"
    assert len(loaded.plan_steps) == 3
    assert loaded.current_step_index == 1
    assert loaded.actions_taken == ["read_file: models.py"]

    mgr.clear()
    assert not mgr.exists()


def test_corrupted_session_recovery(tmp_path: Path):
    mgr = SessionStateManager(workspace_root=tmp_path)
    session_file = tmp_path / ".hearthwren" / "session.json"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text("{invalid json", encoding="utf-8")

    # Should recover gracefully with fresh default state rather than crashing
    recovered = mgr.load()
    assert recovered.state == "INITIAL"
    assert recovered.task_description == ""
