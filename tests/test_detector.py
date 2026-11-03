"""Tests for ProjectDetector."""

from pathlib import Path
from hearthwren.workspace.detector import ProjectDetector


def test_detect_python_project(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="demo"', encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text("def test_dummy(): pass", encoding="utf-8")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hello')", encoding="utf-8")

    detector = ProjectDetector(workspace_root=tmp_path)
    summary = detector.detect()

    assert summary.primary_language == "Python"
    assert "pyproject.toml" in summary.manifests
    assert summary.test_framework == "pytest"
    assert any("main.py" in ep for ep in summary.entry_points)
    assert summary.total_source_files >= 2

    md = detector.generate_markdown_summary(summary)
    assert "Python" in md
    assert "pyproject.toml" in md


def test_detect_empty_project(tmp_path: Path):
    detector = ProjectDetector(workspace_root=tmp_path)
    summary = detector.detect()

    assert summary.primary_language == "Generic / Unknown"
    assert summary.manifests == []
    assert summary.total_source_files == 0
