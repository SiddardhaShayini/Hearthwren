"""Benchmark measurement script for Hearthwren.

Measures:
- Cold-start process RSS and memory overhead
- Tool dispatch latency
- Token estimation throughput
- File read and diff generation speed
"""

from __future__ import annotations

import time
from pathlib import Path

from hearthwren.config import HearthwrenConfig
from hearthwren.model_service import LocalModelService
from hearthwren.resource_supervisor import ResourceSupervisor
from hearthwren.tool_broker import ToolBroker
from hearthwren.workspace.file_ops import FileOps


def run_all_benchmarks() -> dict[str, float]:
    print("Running Hearthwren Resource & Latency Benchmarks...")
    results: dict[str, float] = {}

    # 1. Process Memory
    supervisor = ResourceSupervisor()
    proc_mem = supervisor.get_process_memory()
    sys_mem = supervisor.get_system_memory()
    results["cold_start_rss_mb"] = proc_mem["rss_mb"]
    results["available_ram_gb"] = sys_mem["available_gb"]

    # 2. Token Estimation Speed
    model_service = LocalModelService()
    test_text = "Hearthwren is a local-first resource-disciplined AI coding agent for CPU-only laptops. " * 50
    t0 = time.perf_counter()
    for _ in range(100):
        _ = model_service.estimate_tokens(test_text)
    t1 = time.perf_counter()
    results["token_estimate_ms_per_op"] = round(((t1 - t0) / 100) * 1000, 3)

    # 3. Tool Broker Validation Latency
    broker = ToolBroker()
    t0 = time.perf_counter()
    for _ in range(200):
        _ = broker.execute_tool("list_files", {})
    t1 = time.perf_counter()
    results["tool_dispatch_ms_per_op"] = round(((t1 - t0) / 200) * 1000, 3)

    # 4. Diff Generation Latency
    file_ops = FileOps()
    old_content = "def calculate(x):\n    return x * 2\n" * 20
    new_content = "def calculate(x):\n    return x * 3\n" * 20
    t0 = time.perf_counter()
    for _ in range(50):
        _ = file_ops.generate_diff("math.py", new_content)
    t1 = time.perf_counter()
    results["diff_generation_ms_per_op"] = round(((t1 - t0) / 50) * 1000, 3)

    print("\nBenchmark Results:")
    for k, v in results.items():
        print(f"  - {k}: {v}")

    return results


if __name__ == "__main__":
    run_all_benchmarks()
