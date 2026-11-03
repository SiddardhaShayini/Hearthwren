"""Configuration management for Hearthwren."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Standard Python 3.11+ includes tomllib; fallback if needed
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


DEFAULT_MODEL_NAME = "Nanbeige4.1-3B-Q4_K_M.gguf"
USER_MODEL_DIR = Path.home() / ".hearthwren" / "models"
DEFAULT_MODEL_PATH = USER_MODEL_DIR / DEFAULT_MODEL_NAME


@dataclass
class HearthwrenConfig:
    """Runtime configuration for Hearthwren."""

    model_path: str = field(default_factory=lambda: str(DEFAULT_MODEL_PATH))
    context_window: int = 4096
    ram_ceiling_gb: float = 3.5
    free_ram_headroom_gb: float = 1.5
    inference_timeout_seconds: int = 120
    subprocess_timeout_seconds: int = 60
    max_repair_attempts: int = 3
    output_line_ceiling: int = 200
    safe_commands: list[str] = field(
        default_factory=lambda: [
            "python",
            "pytest",
            "npm",
            "cargo",
            "git",
            "go",
            "make",
            "ruff",
            "pip",
            "uv",
            "node",
        ]
    )
    temperature: float = 0.2
    threads: int = 4
    gemini_api_key: str = ""
    openai_api_key: str = ""
    ollama_host: str = ""
    llm_provider: str = "auto"

    def validate(self) -> list[str]:
        """Validate config constraints specified in PLAN.md."""
        errors = []
        if self.context_window > 8192:
            errors.append(f"Context window {self.context_window} exceeds maximum 8192 allowed by PLAN.md.")
        if self.context_window < 1024:
            errors.append(f"Context window {self.context_window} is too small (< 1024).")
        if self.ram_ceiling_gb > 4.5:
            errors.append(f"RAM ceiling {self.ram_ceiling_gb}GB exceeds recommended maximum 4.5GB for 8GB laptops.")
        if self.free_ram_headroom_gb < 1.0:
            errors.append(f"Headroom {self.free_ram_headroom_gb}GB is unsafe (< 1.0GB).")
        return errors


def get_hearthwren_dir(workspace_root: Path | None = None) -> Path:
    """Return path to .hearthwren directory in workspace."""
    root = workspace_root or Path.cwd()
    return root / ".hearthwren"


def load_config(workspace_root: Path | None = None) -> HearthwrenConfig:
    """Load config from .hearthwren/config.toml, falling back to defaults."""
    hwren_dir = get_hearthwren_dir(workspace_root)
    config_file = hwren_dir / "config.toml"

    if not config_file.exists():
        return HearthwrenConfig()

    try:
        content = config_file.read_text(encoding="utf-8")
        if tomllib:
            data = tomllib.loads(content)
        else:
            # Simple fallback parser for key = value format
            data = _parse_simple_toml(content)

        # Merge with defaults
        cfg = HearthwrenConfig(
            model_path=str(data.get("model_path", DEFAULT_MODEL_PATH)),
            context_window=int(data.get("context_window", 4096)),
            ram_ceiling_gb=float(data.get("ram_ceiling_gb", 3.5)),
            free_ram_headroom_gb=float(data.get("free_ram_headroom_gb", 1.5)),
            inference_timeout_seconds=int(data.get("inference_timeout_seconds", 120)),
            subprocess_timeout_seconds=int(data.get("subprocess_timeout_seconds", 60)),
            max_repair_attempts=int(data.get("max_repair_attempts", 3)),
            output_line_ceiling=int(data.get("output_line_ceiling", 200)),
            safe_commands=list(data.get("safe_commands", HearthwrenConfig().safe_commands)),
            temperature=float(data.get("temperature", 0.2)),
            threads=int(data.get("threads", 4)),
            gemini_api_key=str(data.get("gemini_api_key", "")),
            openai_api_key=str(data.get("openai_api_key", "")),
            ollama_host=str(data.get("ollama_host", "")),
            llm_provider=str(data.get("llm_provider", "auto")),
        )
        return cfg
    except Exception:
        # Fall back to defaults on corrupt config
        return HearthwrenConfig()


def save_config(config: HearthwrenConfig, workspace_root: Path | None = None) -> Path:
    """Save config to .hearthwren/config.toml."""
    hwren_dir = get_hearthwren_dir(workspace_root)
    hwren_dir.mkdir(parents=True, exist_ok=True)
    config_file = hwren_dir / "config.toml"

    safe_model_path = str(config.model_path).replace("\\", "/")
    toml_content = f"""# Hearthwren configuration file
# Automatically generated. Safe to edit.

model_path = "{safe_model_path}"
context_window = {config.context_window}
ram_ceiling_gb = {config.ram_ceiling_gb}
free_ram_headroom_gb = {config.free_ram_headroom_gb}
inference_timeout_seconds = {config.inference_timeout_seconds}
subprocess_timeout_seconds = {config.subprocess_timeout_seconds}
max_repair_attempts = {config.max_repair_attempts}
output_line_ceiling = {config.output_line_ceiling}
safe_commands = {config.safe_commands!r}
temperature = {config.temperature}
threads = {config.threads}
gemini_api_key = "{config.gemini_api_key}"
openai_api_key = "{config.openai_api_key}"
ollama_host = "{config.ollama_host}"
llm_provider = "{config.llm_provider}"
"""
    config_file.write_text(toml_content, encoding="utf-8")
    return config_file


def init_workspace_dirs(workspace_root: Path | None = None) -> dict[str, Path]:
    """Initialize .hearthwren directory structure and ensure .gitignore protection."""
    root = (workspace_root or Path.cwd()).resolve()
    hwren_dir = root / ".hearthwren"
    hwren_dir.mkdir(parents=True, exist_ok=True)

    config_path = hwren_dir / "config.toml"
    if not config_path.exists():
        save_config(HearthwrenConfig(), root)

    # Ensure .gitignore ignores .hearthwren/
    gitignore_path = root / ".gitignore"
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        if ".hearthwren" not in content:
            with gitignore_path.open("a", encoding="utf-8") as f:
                f.write("\n# Hearthwren operational files\n.hearthwren/\n*.hearthwren.bak\n")
    else:
        gitignore_path.write_text(".hearthwren/\n*.hearthwren.bak\n", encoding="utf-8")

    return {
        "hearthwren_dir": hwren_dir,
        "config_file": config_path,
        "index_db": hwren_dir / "index.db",
        "diagnostics_log": hwren_dir / "diagnostics.log",
        "session_json": hwren_dir / "session.json",
    }


def _parse_simple_toml(content: str) -> dict[str, Any]:
    """Rudimentary parser for simple flat key = value TOML files."""
    data: dict[str, Any] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if val.startswith('"') and val.endswith('"'):
                data[key] = val[1:-1]
            elif val.startswith("[") and val.endswith("]"):
                items = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
                data[key] = items
            elif val.lower() in ("true", "false"):
                data[key] = val.lower() == "true"
            else:
                try:
                    if "." in val:
                        data[key] = float(val)
                    else:
                        data[key] = int(val)
                except ValueError:
                    data[key] = val
    return data
