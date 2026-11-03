"""Tests for AgentController."""

from pathlib import Path
from hearthwren.controller import AgentController, AgentState


def test_prompt_budgeting_within_ceiling(tmp_path: Path):
    controller = AgentController(workspace_root=tmp_path)
    # Huge user prompt
    huge_input = "word " * 5000
    system, prompt = controller.assemble_prompt_context(user_message=huge_input)

    total_tokens = controller.model_service.estimate_tokens(system) + controller.model_service.estimate_tokens(prompt)
    assert total_tokens <= controller.config.context_window


def test_plan_task_execution(tmp_path: Path):
    controller = AgentController(workspace_root=tmp_path)
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")

    result = controller.plan_task("Add logging feature")
    assert result["success"] is True
    assert result["state"] == AgentState.REPORT
    assert "Execution Plan" in result["plan"]


def test_guide_task_execution(tmp_path: Path):
    controller = AgentController(workspace_root=tmp_path)
    result = controller.guide_task("How do I structure my project?")
    assert result["success"] is True
    assert "Guidance" in result["guidance"]


def test_execute_task_and_resume(tmp_path: Path):
    controller = AgentController(workspace_root=tmp_path)
    (tmp_path / "main.py").write_text("print('test')", encoding="utf-8")

    exec_res = controller.execute_task("Inspect files and test")
    assert exec_res["success"] is True
    assert exec_res["state"] == AgentState.REPORT
    assert any("list_files" in a for a in exec_res["actions_taken"])

    # Resume from checkpoint
    resumed = controller.resume_task()
    assert resumed["success"] is True
    assert resumed["resumed"] is True
    assert resumed["task"] == "Inspect files and test"
