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
    cfg = HearthwrenConfig(
        context_window=2048,
        ram_ceiling_gb=3.0,
        gemini_api_key="AIzaSyTestKey456",
        openai_api_key="sk-test-key",
        llm_provider="gemini",
    )
    save_config(cfg, workspace_root=tmp_path)

    loaded = load_config(workspace_root=tmp_path)
    assert loaded.context_window == 2048
    assert loaded.ram_ceiling_gb == 3.0
    assert loaded.gemini_api_key == "AIzaSyTestKey456"
    assert loaded.openai_api_key == "sk-test-key"
    assert loaded.llm_provider == "gemini"


def test_model_service_provider_detection(tmp_path: Path):
    from hearthwren.model_service import LocalModelService

    # 1. Default without keys or model -> Offline Expert
    cfg_default = HearthwrenConfig()
    svc1 = LocalModelService(cfg_default, workspace_root=tmp_path)
    p1 = svc1.get_active_provider()
    assert p1["type"] == "offline"
    assert p1["badge"] == "Offline Expert"

    # 2. Configured with Gemini API key -> Gemini 2.0 Flash
    cfg_gemini = HearthwrenConfig(gemini_api_key="AIzaSyTest", llm_provider="gemini")
    svc2 = LocalModelService(cfg_gemini, workspace_root=tmp_path)
    p2 = svc2.get_active_provider()
    assert p2["type"] == "cloud"
    assert p2["badge"] == "Gemini 2.0"

    # 3. Configured with OpenAI API key -> GPT-4o-mini
    cfg_openai = HearthwrenConfig(openai_api_key="sk-test", llm_provider="openai")
    svc3 = LocalModelService(cfg_openai, workspace_root=tmp_path)
    p3 = svc3.get_active_provider()
    assert p3["type"] == "cloud"
    assert p3["badge"] == "GPT-4o-mini"


def test_init_workspace_dirs(tmp_path: Path):
    dirs = init_workspace_dirs(tmp_path)
    assert dirs["hearthwren_dir"].exists()
    assert dirs["config_file"].exists()

    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    assert ".hearthwren" in gitignore.read_text(encoding="utf-8")
