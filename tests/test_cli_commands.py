"""Tests for CLI subcommands."""

from pathlib import Path
from typer.testing import CliRunner
from hearthwren.cli import app

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "Hearthwren" in result.stdout


def test_cli_status():
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Resource Health & Memory" in result.stdout
    assert "Detected Project Structure" in result.stdout


def test_cli_config():
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "Hearthwren Configuration" in result.stdout


def test_cli_plan():
    result = runner.invoke(app, ["plan", "Add payment processing"])
    assert result.exit_code == 0
    assert "Planning Task:" in result.stdout


def test_cli_guide():
    result = runner.invoke(app, ["guide", "How to run tests?"])
    assert result.exit_code == 0
    assert "Guidance Query:" in result.stdout


def test_cli_diff():
    result = runner.invoke(app, ["diff"])
    assert result.exit_code == 0


def test_cli_resume():
    result = runner.invoke(app, ["resume"])
    assert result.exit_code == 0


def test_cli_status_json():
    import json
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "project" in data
    assert "resources" in data
    assert "available_ram_gb" in data["resources"]


def test_cli_doctor():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Hearthwren Environment Diagnostics (Doctor)" in result.stdout
    assert "Python Runtime" in result.stdout
    assert "Memory (RAM)" in result.stdout


def test_cli_doctor_json():
    import json
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "checks" in data
    assert any(c["category"] == "Python Runtime" for c in data["checks"])
    assert any(c["category"] == "Memory (RAM)" for c in data["checks"])

