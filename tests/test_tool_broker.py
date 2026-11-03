"""Tests for ToolBroker."""

from pathlib import Path
from hearthwren.tool_broker import ToolBroker


def test_tool_schemas_registered(tmp_path: Path):
    broker = ToolBroker(workspace_root=tmp_path)
    schemas = broker.get_tool_schemas()
    names = [s["name"] for s in schemas]

    assert "read_file" in names
    assert "write_file" in names
    assert "search_code" in names
    assert "list_files" in names
    assert "run_tests" in names
    assert "git_status" in names


def test_reject_unknown_tool(tmp_path: Path):
    broker = ToolBroker(workspace_root=tmp_path)
    res = broker.execute_tool("launch_missiles", {})
    assert res["success"] is False
    assert "Unknown tool" in res["error"]


def test_reject_malformed_arguments(tmp_path: Path):
    broker = ToolBroker(workspace_root=tmp_path)
    # read_file requires 'path'
    res = broker.execute_tool("read_file", {})
    assert res["success"] is False
    assert "Missing required parameter 'path'" in res["error"]


def test_execute_read_and_write_flow(tmp_path: Path):
    broker = ToolBroker(workspace_root=tmp_path)

    # Propose write without approval
    res_prop = broker.execute_tool("write_file", {"path": "hello.txt", "content": "world\n", "approved": False})
    assert res_prop["needs_approval"] is True

    # Approve write
    res_write = broker.execute_tool("write_file", {"path": "hello.txt", "content": "world\n", "approved": True})
    assert res_write["success"] is True

    # Read written file
    res_read = broker.execute_tool("read_file", {"path": "hello.txt"})
    assert res_read["success"] is True
    assert res_read["content"] == "world\n"
