"""Tests for SequentialSubtaskRunner."""

from pathlib import Path
from hearthwren.subtasks import SequentialSubtaskRunner, TaskPhase


def test_sequential_subtask_phases(tmp_path: Path):
    runner = SequentialSubtaskRunner(workspace_root=tmp_path)
    (tmp_path / "main.py").write_text("print('test')", encoding="utf-8")

    # Run understand phase
    res_understand = runner.run_phase(TaskPhase.UNDERSTAND, "Refactor logging")
    assert res_understand.success is True
    assert res_understand.phase == TaskPhase.UNDERSTAND
    assert any("Discovered" in a for a in res_understand.actions)

    # Run test spec phase
    res_test = runner.run_phase(TaskPhase.TEST_SPEC, "Refactor logging")
    assert res_test.success is True
    assert res_test.phase == TaskPhase.TEST_SPEC


def test_full_multi_phase_execution(tmp_path: Path):
    runner = SequentialSubtaskRunner(workspace_root=tmp_path)
    result = runner.run_all_phases("Implement user profile validation")

    assert result.success is True
    assert len(result.phase_results) == 5
    assert result.phase_results[0].phase == TaskPhase.UNDERSTAND
    assert result.phase_results[-1].phase == TaskPhase.REPORT
    assert result.final_report != ""


def test_multi_phase_creates_file_on_disk(tmp_path: Path):
    runner = SequentialSubtaskRunner(workspace_root=tmp_path)
    result = runner.run_all_phases("create md file for pipeline notes")

    assert result.success is True
    created = tmp_path / "pipeline_notes.md"
    assert created.is_file()
    content = created.read_text(encoding="utf-8")
    assert "Pipeline Notes" in content

