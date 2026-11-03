"""Tests for FileOps."""

from pathlib import Path
import pytest
from hearthwren.workspace.file_ops import FileOps, FileSafetyViolation


def test_path_boundary_enforcement(tmp_path: Path):
    file_ops = FileOps(workspace_root=tmp_path)

    # Path traversal outside workspace root
    with pytest.raises(FileSafetyViolation):
        file_ops.resolve_path("../outside.txt")


def test_protected_files_enforcement(tmp_path: Path):
    file_ops = FileOps(workspace_root=tmp_path)

    # .env access blocked
    with pytest.raises(FileSafetyViolation):
        file_ops.resolve_path(".env")

    # .git access blocked
    with pytest.raises(FileSafetyViolation):
        file_ops.resolve_path(".git/config")


def test_windowed_read(tmp_path: Path):
    file_ops = FileOps(workspace_root=tmp_path)
    sample_file = tmp_path / "sample.txt"
    lines = [f"Line {i}\n" for i in range(1, 101)]
    sample_file.write_text("".join(lines), encoding="utf-8")

    # Read window: lines 10 to 20
    res = file_ops.read_file("sample.txt", start_line=10, end_line=20)
    assert res["success"] is True
    assert res["start_line"] == 10
    assert res["end_line"] == 20
    assert res["total_lines"] == 100
    assert "Line 10" in res["content"]
    assert "Line 20" in res["content"]
    assert "Line 21" not in res["content"]


def test_diff_and_safe_write_requires_approval(tmp_path: Path):
    file_ops = FileOps(workspace_root=tmp_path)
    target = tmp_path / "code.py"
    target.write_text("def hello():\n    return 1\n", encoding="utf-8")

    new_code = "def hello():\n    return 42\n"

    # Write without approval returns diff preview without modifying file
    unapproved = file_ops.write_file("code.py", new_code, approved=False)
    assert unapproved["success"] is False
    assert unapproved["needs_approval"] is True
    assert "+    return 42" in unapproved["diff"]
    assert "-    return 1" in unapproved["diff"]
    assert target.read_text(encoding="utf-8") == "def hello():\n    return 1\n"

    # Write with approval applies change and creates backup
    approved = file_ops.write_file("code.py", new_code, approved=True, create_backup=True)
    assert approved["success"] is True
    assert target.read_text(encoding="utf-8") == new_code

    backup_file = tmp_path / "code.py.hearthwren.bak"
    assert backup_file.exists()
    assert backup_file.read_text(encoding="utf-8") == "def hello():\n    return 1\n"
