"""Tests for SearchService."""

from pathlib import Path
from hearthwren.workspace.search import SearchService


def test_python_fallback_search(tmp_path: Path):
    search_svc = SearchService(workspace_root=tmp_path)
    (tmp_path / "hello.py").write_text("def find_me():\n    return 'secret_keyword'\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("def other():\n    return 'nothing'\n", encoding="utf-8")

    results = search_svc._search_python_fallback("secret_keyword", is_regex=False, limit=10, file_pattern=None)
    assert len(results) == 1
    assert results[0]["file"] == "hello.py"
    assert "secret_keyword" in results[0]["text"]


def test_search_respects_ignore_dirs(tmp_path: Path):
    search_svc = SearchService(workspace_root=tmp_path)
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "packed.txt").write_text("ignore_me_here", encoding="utf-8")

    results = search_svc.search("ignore_me_here")
    assert len(results) == 0
