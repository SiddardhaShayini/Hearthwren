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


def test_parse_file_creation_task():
    from hearthwren.controller import parse_file_creation_task

    fn, topic = parse_file_creation_task("create md file for architecture overview")
    assert fn == "architecture_overview.md"
    assert "architecture" in topic

    fn2, topic2 = parse_file_creation_task("create a file named notes.md")
    assert fn2 == "notes.md"

    fn3, topic3 = parse_file_creation_task("generate python file for helper")
    assert fn3 == "helper.py"


def test_execute_task_creates_file_on_disk(tmp_path: Path):
    controller = AgentController(workspace_root=tmp_path)

    # Prompt matching the exact user pattern: "create md file for test"
    res = controller.execute_task("create md file for test guide")
    assert res["success"] is True
    assert res["file_created"] == "test_guide.md"

    created_file = tmp_path / "test_guide.md"
    assert created_file.is_file()
    content = created_file.read_text(encoding="utf-8")
    assert "# Test Guide" in content
    assert "Overview" in content


def test_execute_task_creates_html_application(tmp_path: Path):
    controller = AgentController(workspace_root=tmp_path)
    res = controller.execute_task("create index.html file and develop a static web application for Agentic AI application")
    assert res["success"] is True
    assert res["file_created"] == "index.html"

    created = tmp_path / "index.html"
    assert created.is_file()
    html_text = created.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html_text
    assert "stepper" in html_text
    assert "Agentic AI" in html_text
    assert "Understand" in html_text


def test_execute_task_creates_expert_plan(tmp_path: Path):
    controller = AgentController(workspace_root=tmp_path)
    res = controller.execute_task("create plan.md file and write a simple plan to develop a static web application for Agentic AI application")
    assert res["success"] is True
    assert res["file_created"] == "plan.md"

    created = tmp_path / "plan.md"
    assert created.is_file()
    plan_text = created.read_text(encoding="utf-8")
    assert "flowchart" in plan_text
    assert "Phased Implementation" in plan_text
    assert "Acceptance Criteria" in plan_text

