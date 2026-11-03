"""Tests for WorkspaceIndexer."""

from pathlib import Path
from hearthwren.workspace.indexer import WorkspaceIndexer


def test_indexing_and_fts_search(tmp_path: Path):
    indexer = WorkspaceIndexer(workspace_root=tmp_path)
    (tmp_path / "calc.py").write_text("class Calculator:\n    def add(self, a, b):\n        return a + b\n", encoding="utf-8")

    indexed = indexer.index_workspace()
    assert indexed >= 1

    # Search FTS
    results = indexer.search_fts("Calculator")
    assert len(results) >= 1
    assert "calc.py" in results[0]["path"]

    # Search symbol
    symbols = indexer.find_symbol("Calculator")
    assert len(symbols) >= 1
    assert symbols[0]["name"] == "Calculator"
    assert symbols[0]["kind"] == "class"

    func_symbols = indexer.find_symbol("add")
    assert len(func_symbols) >= 1
    assert func_symbols[0]["name"] == "add"
    assert func_symbols[0]["kind"] == "function"
