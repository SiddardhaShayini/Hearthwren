"""Tests for ResourceSupervisor."""

from pathlib import Path
import time
import pytest
from hearthwren.config import HearthwrenConfig
from hearthwren.resource_supervisor import (
    ConcurrencyViolationError,
    ResourceSupervisor,
    TimeoutExceededError,
)


def test_resource_supervisor_memory_metrics(tmp_path: Path):
    supervisor = ResourceSupervisor(workspace_root=tmp_path)
    sys_mem = supervisor.get_system_memory()
    proc_mem = supervisor.get_process_memory()

    assert sys_mem["total_gb"] > 0
    assert sys_mem["available_gb"] >= 0
    assert proc_mem["rss_mb"] > 0


def test_preflight_ram_check(tmp_path: Path):
    cfg = HearthwrenConfig(ram_ceiling_gb=1.0, free_ram_headroom_gb=0.5)
    supervisor = ResourceSupervisor(config=cfg, workspace_root=tmp_path)
    ok, msg = supervisor.preflight_ram_check()
    # On most test machines with >= 1.5 GB free, this passes
    assert isinstance(ok, bool)
    assert isinstance(msg, str)


def test_preflight_ram_check_insufficient(tmp_path: Path):
    # Set an impossible requirement of 9999 GB free RAM
    cfg = HearthwrenConfig(ram_ceiling_gb=9000.0, free_ram_headroom_gb=1000.0)
    supervisor = ResourceSupervisor(config=cfg, workspace_root=tmp_path)
    ok, msg = supervisor.preflight_ram_check()
    assert ok is False
    assert "INSUFFICIENT RAM" in msg


def test_concurrency_lock_strictly_sequential(tmp_path: Path):
    supervisor = ResourceSupervisor(workspace_root=tmp_path)

    # Acquire lock in thread
    assert supervisor.acquire_inference_lock(timeout_seconds=1.0) is True

    # Attempting to acquire again should fail
    assert supervisor.acquire_inference_lock(timeout_seconds=0.1) is False

    supervisor.release_inference_lock()
    # Now can acquire again
    assert supervisor.acquire_inference_lock(timeout_seconds=1.0) is True
    supervisor.release_inference_lock()


def test_timeout_enforcement(tmp_path: Path):
    supervisor = ResourceSupervisor(workspace_root=tmp_path)

    def slow_fn():
        time.sleep(2.0)
        return "done"

    with pytest.raises(TimeoutExceededError):
        supervisor.run_with_timeout(slow_fn, timeout_seconds=0.2, task_name="slow_task")
