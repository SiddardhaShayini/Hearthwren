"""Tests for Hearthwren Ultra-Lightweight Desktop Studio HTTP Server and Launcher."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from hearthwren.gui.launcher import find_free_port, find_system_app_browser
from hearthwren.gui.server import HearthwrenAPIHandler


class DummySocket:
    """Mock socket for testing BaseHTTPRequestHandler in memory without network permissions."""

    def __init__(self, data: bytes):
        self.r = io.BytesIO(data)
        self.w = io.BytesIO()

    def makefile(self, mode: str, *args, **kwargs) -> io.BytesIO:
        if "r" in mode:
            return self.r
        return self.w

    def sendall(self, b: bytes) -> None:
        self.w.write(b)


def simulate_request(
    path: str,
    method: str = "GET",
    body: bytes | dict | None = None,
    workspace: Path | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Execute an HTTP request against HearthwrenAPIHandler completely in memory."""
    if workspace:
        HearthwrenAPIHandler.workspace_root = workspace.resolve()

    body_bytes = b""
    content_headers = ""
    if body is not None:
        if isinstance(body, dict):
            body_bytes = json.dumps(body).encode("utf-8")
            content_headers = f"Content-Type: application/json\r\nContent-Length: {len(body_bytes)}\r\n"
        elif isinstance(body, (bytes, bytearray)):
            body_bytes = bytes(body)
            content_headers = f"Content-Length: {len(body_bytes)}\r\n"

    raw_req = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n{content_headers}\r\n".encode("utf-8") + body_bytes
    sock = DummySocket(raw_req)

    _ = HearthwrenAPIHandler(sock, ("127.0.0.1", 12345), None)

    response_bytes = sock.w.getvalue()
    header_part, _, body_part = response_bytes.partition(b"\r\n\r\n")
    lines = header_part.decode("utf-8", errors="replace").split("\r\n")
    status_line = lines[0]
    status_code = int(status_line.split()[1])

    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    return status_code, headers, body_part


@pytest.fixture
def test_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "gui_workspace"
    ws.mkdir()
    (ws / "main.py").write_text("def test(): pass\n", encoding="utf-8")
    (ws / "AGENT_MEMORY.md").write_text("# Project\n## Section\nContent\n", encoding="utf-8")
    return ws


def test_serve_static_html(test_workspace: Path) -> None:
    code, headers, body = simulate_request("/", workspace=test_workspace)
    assert code == 200
    assert "text/html" in headers.get("content-type", "")
    content = body.decode("utf-8")
    assert "Hearthwren" in content
    assert "Local. Lean. Built right." in content



def test_serve_static_css(test_workspace: Path) -> None:
    code, headers, body = simulate_request("/styles.css", workspace=test_workspace)
    assert code == 200
    assert "text/css" in headers.get("content-type", "")
    content = body.decode("utf-8")
    assert "--font-family" in content or "body" in content


def test_serve_static_js(test_workspace: Path) -> None:
    code, headers, body = simulate_request("/app.js", workspace=test_workspace)
    assert code == 200
    assert "javascript" in headers.get("content-type", "")
    content = body.decode("utf-8")
    assert "loadStatus" in content or "fetch" in content


def test_serve_favicon(test_workspace: Path) -> None:
    code, headers, body = simulate_request("/favicon.ico", workspace=test_workspace)
    assert code == 200
    assert "image/svg+xml" in headers.get("content-type", "")
    assert b"<svg" in body


def test_serve_brand_assets(test_workspace: Path) -> None:
    code, headers, body = simulate_request("/assets/hearthwren-icon.svg", workspace=test_workspace)
    assert code == 200
    assert "image/svg+xml" in headers.get("content-type", "")
    assert b"Hearthwren icon" in body or b"<svg" in body

    code2, headers2, body2 = simulate_request("/assets/hearthwren-logo.svg", workspace=test_workspace)
    assert code2 == 200
    assert "image/svg+xml" in headers2.get("content-type", "")
    assert b"Hearthwren logo" in body2 or b"<svg" in body2



def test_api_status_endpoint(test_workspace: Path) -> None:
    code, _, body = simulate_request("/api/status", workspace=test_workspace)
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert "workspace" in data
    assert "project" in data
    assert "resources" in data
    assert data["resources"]["ram_ceiling_gb"] == 3.5


def test_api_doctor_endpoint(test_workspace: Path) -> None:
    code, _, body = simulate_request("/api/doctor", workspace=test_workspace)
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert "checks" in data
    assert any(c["name"].startswith("Python") for c in data["checks"])


def test_api_diff_endpoint(test_workspace: Path) -> None:
    code, _, body = simulate_request("/api/diff", workspace=test_workspace)
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert "unstaged" in data
    assert "staged" in data


def test_api_search_endpoint(test_workspace: Path) -> None:
    code, _, body = simulate_request("/api/search?q=test", workspace=test_workspace)
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert data["query"] == "test"
    assert "symbols" in data
    assert "matches" in data


def test_api_memory_endpoint(test_workspace: Path) -> None:
    code, _, body = simulate_request("/api/memory", workspace=test_workspace)
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert data["exists"] is True
    assert "sections" in data


def test_api_browse_endpoint(test_workspace: Path) -> None:
    code, _, body = simulate_request("/api/browse", workspace=test_workspace)
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert "current" in data
    assert "drives" in data
    assert "subdirectories" in data

    # Test browsing specific dir
    code2, _, body2 = simulate_request(f"/api/browse?dir={test_workspace}", workspace=test_workspace)
    assert code2 == 200
    data2 = json.loads(body2.decode("utf-8"))
    assert data2["current"] == str(test_workspace)


def test_api_browse_dialog_endpoint(test_workspace: Path) -> None:
    code, _, body = simulate_request(
        "/api/browse-dialog",
        method="POST",
        body={"current": str(test_workspace)},
        workspace=test_workspace,
    )
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert "path" in data


def test_api_set_repo_endpoint(test_workspace: Path, tmp_path: Path) -> None:
    new_repo = tmp_path / "another_project"
    new_repo.mkdir()
    (new_repo / "main.py").write_text("print('test')", encoding="utf-8")

    # POST valid dir
    code, _, body = simulate_request(
        "/api/set-repo",
        method="POST",
        body={"path": str(new_repo)},
        workspace=test_workspace,
    )
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert data["success"] is True
    assert data["workspace"] == str(new_repo)

    # POST invalid dir
    bad_code, _, bad_body = simulate_request(
        "/api/set-repo",
        method="POST",
        body={"path": str(tmp_path / "nonexistent_dir")},
        workspace=test_workspace,
    )
    assert bad_code == 400
    bad_data = json.loads(bad_body.decode("utf-8"))
    assert bad_data["success"] is False


def test_api_plan_endpoint(test_workspace: Path) -> None:
    code, _, body = simulate_request(
        "/api/plan",
        method="POST",
        body={"task": "add logging"},
        workspace=test_workspace,
    )
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert "task" in data
    assert "plan" in data


def test_api_guide_endpoint(test_workspace: Path) -> None:
    code, _, body = simulate_request(
        "/api/guide",
        method="POST",
        body={"query": "how to add a test"},
        workspace=test_workspace,
    )
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert "guidance" in data


def test_api_run_endpoint(test_workspace: Path) -> None:
    code, _, body = simulate_request(
        "/api/run",
        method="POST",
        body={"task": "create md file for quick start guide", "multi_phase": False},
        workspace=test_workspace,
    )
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert data["success"] is True
    assert data["file_created"] == "quick_start_guide.md"
    assert (test_workspace / "quick_start_guide.md").is_file()



def test_launcher_helpers() -> None:
    port = find_free_port(8990)
    assert 8990 <= port <= 9050

    browser, name = find_system_app_browser()
    assert name in ("msedge", "chrome", "chromium", "system_default")


def test_api_engine_status_endpoint(test_workspace: Path) -> None:
    code, _, body = simulate_request(
        "/api/engine-status",
        method="GET",
        workspace=test_workspace,
    )
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert "active_engine" in data
    assert "badge" in data["active_engine"]
    assert "has_gemini" in data
    assert "has_openai" in data
    assert "llm_provider" in data


def test_api_save_api_key_endpoint(test_workspace: Path) -> None:
    code, _, body = simulate_request(
        "/api/save-api-key",
        method="POST",
        body={"provider": "gemini", "key": "AIzaSyTestKey123", "llm_provider": "gemini"},
        workspace=test_workspace,
    )
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert data["success"] is True

    # Verify status reflects the saved key
    st_code, _, st_body = simulate_request(
        "/api/engine-status",
        method="GET",
        workspace=test_workspace,
    )
    assert st_code == 200
    st_data = json.loads(st_body.decode("utf-8"))
    assert st_data["has_gemini"] is True
    assert st_data["active_engine"]["badge"] == "Gemini 2.0"


def test_api_status_includes_engine_info(test_workspace: Path) -> None:
    code, _, body = simulate_request(
        "/api/status",
        method="GET",
        workspace=test_workspace,
    )
    assert code == 200
    data = json.loads(body.decode("utf-8"))
    assert "engine" in data
    assert "badge" in data["engine"]
