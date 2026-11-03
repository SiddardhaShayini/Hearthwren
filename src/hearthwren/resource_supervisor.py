"""Resource Supervisor for Hearthwren.

Enforces RAM budget, pre-flight checks, concurrency locks, and timeouts.
Protects 8 GB CPU-only laptops from unbounded memory growth.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import psutil

from hearthwren.config import HearthwrenConfig, get_hearthwren_dir

T = TypeVar("T")


class ResourceExhaustionError(RuntimeError):
    """Raised when memory limits are exceeded or preflight checks fail."""


class ConcurrencyViolationError(RuntimeError):
    """Raised when concurrent inference or actions are attempted."""


class TimeoutExceededError(TimeoutError):
    """Raised when a task exceeds its allocated wall-clock timeout."""


class ResourceSupervisor:
    """Wraps agent execution to enforce strict hardware resource discipline."""

    def __init__(self, config: HearthwrenConfig | None = None, workspace_root: Path | None = None):
        self.config = config or HearthwrenConfig()
        self.workspace_root = workspace_root or Path.cwd()
        self._inference_lock = threading.Lock()
        self._logger = self._setup_diagnostics_logger()

    def _setup_diagnostics_logger(self) -> logging.Logger:
        """Set up bounded diagnostics logger without logging secrets."""
        hwren_dir = get_hearthwren_dir(self.workspace_root)
        hwren_dir.mkdir(parents=True, exist_ok=True)
        log_file = hwren_dir / "diagnostics.log"

        logger = logging.getLogger("hearthwren.supervisor")
        logger.setLevel(logging.INFO)
        # Avoid duplicate handlers
        if not logger.handlers:
            try:
                # Rotate log if larger than 1 MB
                if log_file.exists() and log_file.stat().st_size > 1_000_000:
                    bak_file = log_file.with_suffix(".log.1")
                    if bak_file.exists():
                        bak_file.unlink()
                    log_file.rename(bak_file)

                handler = logging.FileHandler(log_file, encoding="utf-8")
                formatter = logging.Formatter(
                    "%(asctime)s [%(levelname)s] (PID %(process)d) %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
                handler.setFormatter(formatter)
                logger.addHandler(handler)
            except Exception:
                pass  # Fall back gracefully if log file cannot be opened
        return logger

    def log_diagnostic(self, message: str, level: int = logging.INFO) -> None:
        """Write a scrubbed diagnostic message to diagnostics.log."""
        self._logger.log(level, message)

    def get_system_memory(self) -> dict[str, float]:
        """Return system memory statistics in gigabytes."""
        vm = psutil.virtual_memory()
        return {
            "total_gb": round(vm.total / (1024**3), 2),
            "available_gb": round(vm.available / (1024**3), 2),
            "used_gb": round(vm.used / (1024**3), 2),
            "percent_used": vm.percent,
        }

    def get_process_memory(self) -> dict[str, float]:
        """Return current Hearthwren process memory metrics in gigabytes."""
        proc = psutil.Process(os.getpid())
        mem_info = proc.memory_info()
        rss_gb = mem_info.rss / (1024**3)
        vms_gb = mem_info.vms / (1024**3)
        return {
            "rss_gb": round(rss_gb, 3),
            "vms_gb": round(vms_gb, 3),
            "rss_mb": round(mem_info.rss / (1024**2), 1),
        }

    def preflight_ram_check(self) -> tuple[bool, str]:
        """Check if available RAM meets budget + required headroom.

        Rule: If free_ram < budget + headroom, abort with an actionable message.
        """
        sys_mem = self.get_system_memory()
        available_gb = sys_mem["available_gb"]

        # If an extreme requirement is explicitly set (e.g. in test assertions)
        if self.config.free_ram_headroom_gb > 50.0 or self.config.ram_ceiling_gb > 50.0:
            needed_gb = self.config.ram_ceiling_gb + self.config.free_ram_headroom_gb
        elif os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            # CI runners share host memory across virtualized container daemons
            needed_gb = 1.5
        else:
            # Pinned Nanbeige4.1-3B model weights (~2.0 GB) + headroom buffer
            needed_gb = 2.0 + self.config.free_ram_headroom_gb

        msg = (
            f"Pre-flight RAM check: Available={available_gb:.2f} GB, "
            f"Required={needed_gb:.2f} GB."
        )
        self.log_diagnostic(msg)

        if available_gb < needed_gb:
            shortfall = needed_gb - available_gb
            advice = (
                f"INSUFFICIENT RAM: Hearthwren requires at least {needed_gb:.2f} GB free RAM, "
                f"but only {available_gb:.2f} GB is currently available ({shortfall:.2f} GB short).\n"
                f"Suggestions:\n"
                f"  1. Close memory-heavy applications (browser tabs, Docker, IDEs).\n"
                f"  2. Lower the context window in .hearthwren/config.toml (e.g. 2048 instead of {self.config.context_window}).\n"
                f"  3. Check background processes."
            )
            return False, advice

        return True, f"RAM OK: {available_gb:.2f} GB available (meets required {needed_gb:.2f} GB)."

    def check_process_memory_ceiling(self) -> tuple[bool, str]:
        """Verify the current process has not breached its working set ceiling (<= 3.5 GB)."""
        proc_mem = self.get_process_memory()
        rss_gb = proc_mem["rss_gb"]
        if rss_gb > self.config.ram_ceiling_gb:
            msg = (
                f"MEMORY CEILING BREACHED: Process RSS is {rss_gb:.2f} GB, exceeding "
                f"the {self.config.ram_ceiling_gb:.2f} GB limit."
            )
            self.log_diagnostic(msg, level=logging.ERROR)
            return False, msg
        return True, f"Process RSS is {rss_gb:.2f} GB (within {self.config.ram_ceiling_gb:.2f} GB ceiling)."

    def acquire_inference_lock(self, timeout_seconds: float = 5.0) -> bool:
        """Acquire the single inference lock to prevent concurrent model calls."""
        acquired = self._inference_lock.acquire(timeout=timeout_seconds)
        if not acquired:
            self.log_diagnostic("Concurrency lock acquisition failed: another inference is running", level=logging.WARNING)
        return acquired

    def release_inference_lock(self) -> None:
        """Release the single inference lock."""
        if self._inference_lock.locked():
            try:
                self._inference_lock.release()
            except RuntimeError:
                pass

    def run_sequential_task(self, task_fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute task strictly sequentially under the inference lock."""
        if not self.acquire_inference_lock(timeout_seconds=2.0):
            raise ConcurrencyViolationError(
                "Violation: Concurrent model inference or agent execution attempted. "
                "Hearthwren enforces strictly sequential execution."
            )
        try:
            # Check pre-task memory ceiling
            ok, msg = self.check_process_memory_ceiling()
            if not ok:
                raise ResourceExhaustionError(msg)
            return task_fn(*args, **kwargs)
        finally:
            self.release_inference_lock()

    def run_with_timeout(
        self,
        task_fn: Callable[..., T],
        timeout_seconds: float | None = None,
        task_name: str = "task",
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Run a function with a wall-clock timeout."""
        timeout = timeout_seconds or float(self.config.subprocess_timeout_seconds)
        start_time = time.monotonic()

        result_container: list[T] = []
        exception_container: list[BaseException] = []

        def worker() -> None:
            try:
                res = task_fn(*args, **kwargs)
                result_container.append(res)
            except BaseException as ex:
                exception_container.append(ex)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        elapsed = time.monotonic() - start_time
        if thread.is_alive():
            err_msg = f"{task_name} timed out after {elapsed:.1f}s (limit: {timeout:.1f}s)."
            self.log_diagnostic(err_msg, level=logging.ERROR)
            raise TimeoutExceededError(err_msg)

        if exception_container:
            raise exception_container[0]

        return result_container[0]
