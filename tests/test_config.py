"""Tests for Hearthwren configuration."""

from pathlib import Path
import pytest
from hearthwren.config import HearthwrenConfig, init_workspace_dirs, load_config, save_config


def test_default_config_values():
    cfg = HearthwrenConfig()
    assert cfg.context_window == 4096
    assert cfg.ram_ceiling_gb == 3.5
    assert cfg.free_ram_headroom_gb == 1.5
    assert cfg.inference_timeout_seconds == 120
    assert cfg.subprocess_timeout_seconds == 60
    assert "pytest" in cfg.safe_commands
    assert cfg.validate() == []


def test_config_validation():
    # Context window > 8192 is invalid per PLAN.md
    invalid_cfg = HearthwrenConfig(context_window=16384)
    errors = invalid_cfg.validate()
    assert any("exceeds maximum 8192" in err for err in errors)

    # Unsafe RAM ceiling
    unsafe_ram = HearthwrenConfig(ram_ceiling_gb=6.0)
    assert any("exceeds recommended" in err for err in unsafe_ram.validate())


def test_save_and_load_config(tmp_path: Path):
    cfg = HearthwrenConfig(context_window=2048, ram_ceiling_gb=3.0)
    save_config(cfg, workspace_root=tmp_path)

    loaded = load_config(workspace_root=tmp_path)
    assert loaded.context_window == 2048
    assert loaded.ram_ceiling_gb == 3.0


def test_init_workspace_dirs(tmp_path: Path):
    dirs = init_workspace_dirs(tmp_path)
    assert dirs["hearthwren_dir"].exists()
    assert dirs["config_file"].exists()

    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    assert ".hearthwren" in gitignore.read_text(encoding="utf-8")
