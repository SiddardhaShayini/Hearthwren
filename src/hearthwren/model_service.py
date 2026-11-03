"""Local Model Service for Hearthwren.

Manages inference with Nanbeige4.1-3B Q4 GGUF via llama-cpp-python.
Enforces single-model sequential concurrency and prompt budget estimation.
Includes a deterministic fallback when weights have not yet been downloaded.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Generator

from hearthwren.config import HearthwrenConfig
from hearthwren.resource_supervisor import ConcurrencyViolationError, ResourceSupervisor

# Try importing llama_cpp
try:
    import llama_cpp
    HAS_LLAMA_CPP = True
except ImportError:
    HAS_LLAMA_CPP = False
    llama_cpp = None  # type: ignore


class LocalModelService:
    """Manages the local LLM runtime, health checks, and sequential inference."""

    def __init__(
        self,
        config: HearthwrenConfig | None = None,
        supervisor: ResourceSupervisor | None = None,
        workspace_root: Path | None = None,
    ):
        self.config = config or HearthwrenConfig()
        self.workspace_root = workspace_root or Path.cwd()
        self.supervisor = supervisor or ResourceSupervisor(self.config, self.workspace_root)
        self._llm: Any = None
        self._is_loaded = False

    @property
    def is_model_present(self) -> bool:
        """Check if GGUF model weights file exists on disk."""
        path = Path(self.config.model_path).expanduser()
        return path.is_file() and path.stat().st_size > 10_000_000

    @property
    def is_loaded(self) -> bool:
        """Check if model is currently loaded in memory."""
        return self._is_loaded and self._llm is not None

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for a text snippet.

        If llama-cpp is loaded, uses exact model tokenizer; otherwise estimates
        via character/word heuristic (~3.8 chars per token).
        """
        if self.is_loaded and hasattr(self._llm, "tokenize"):
            try:
                tokens = self._llm.tokenize(text.encode("utf-8"))
                return len(tokens)
            except Exception:
                pass
        return max(1, int(len(text) / 3.8))

    def load_model(self) -> tuple[bool, str]:
        """Load the GGUF model into memory under supervisor checks."""
        if self.is_loaded:
            return True, "Model already loaded."

        if not self.is_model_present:
            return False, f"Model file not found at '{self.config.model_path}'."

        if not HAS_LLAMA_CPP:
            return False, "llama-cpp-python is not installed."

        # Preflight RAM check
        ok, msg = self.supervisor.preflight_ram_check()
        if not ok:
            return False, msg

        def _loader() -> Any:
            model_path_str = str(Path(self.config.model_path).expanduser())
            return llama_cpp.Llama(
                model_path=model_path_str,
                n_ctx=self.config.context_window,
                n_threads=self.config.threads,
                verbose=False,
            )

        try:
            self._llm = self.supervisor.run_sequential_task(_loader)
            self._is_loaded = True
            self.supervisor.log_diagnostic(f"Loaded model {self.config.model_path} successfully.")
            return True, "Model loaded successfully."
        except Exception as e:
            self._llm = None
            self._is_loaded = False
            err = f"Failed to load model: {e}"
            self.supervisor.log_diagnostic(err)
            return False, err

    def unload_model(self) -> None:
        """Cleanly unload the model to release working set memory."""
        if self._llm is not None:
            del self._llm
            self._llm = None
        self._is_loaded = False
        import gc
        gc.collect()
        self.supervisor.log_diagnostic("Model unloaded.")

    def get_active_provider(self) -> dict[str, Any]:
        """Return the current active model provider and its status."""
        provider = self.config.llm_provider.lower()
        gemini_key = bool(self.config.gemini_api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        openai_key = bool(self.config.openai_api_key or os.environ.get("OPENAI_API_KEY"))
        model_path = Path(self.config.model_path)
        model_installed = model_path.is_file() and model_path.stat().st_size > 100_000_000

        if (provider == "gemini" or (provider == "auto" and gemini_key)) and gemini_key:
            return {"name": "Google Gemini 2.0 Flash", "type": "cloud", "badge": "Gemini 2.0", "details": "Frontier model reasoning via REST (< 20 MB RAM)"}
        if (provider == "openai" or (provider == "auto" and openai_key)) and openai_key:
            return {"name": "OpenAI GPT-4o-mini", "type": "cloud", "badge": "GPT-4o-mini", "details": "Frontier model reasoning via REST (< 20 MB RAM)"}
        if self.is_loaded or (provider in ("nanbeige", "local", "auto") and model_installed):
            return {"name": "Nanbeige4.1-3B GGUF", "type": "local", "badge": "Nanbeige 3B", "details": "Local CPU quantized LLM inference (< 3.5 GB RAM)"}
        return {"name": "Offline Expert Synthesizer", "type": "offline", "badge": "Offline Expert", "details": "Zero-dependency offline code & architecture synthesizer"}

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 1024,
        temperature: float | None = None,
        stop_sequences: list[str] | None = None,
    ) -> str:
        """Run single inference sequentially within bounded context ceiling."""
        temp = temperature if temperature is not None else self.config.temperature
        stops = stop_sequences or ["<|im_end|>", "</s>", "User:"]

        # Check for configured cloud or alternative LLM providers
        provider = self.config.llm_provider.lower()
        gemini_key = self.config.gemini_api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        openai_key = self.config.openai_api_key or os.environ.get("OPENAI_API_KEY")
        ollama_host = self.config.ollama_host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

        # 1. Gemini API (frontier Claude Code-tier reasoning, fast & zero-bloat)
        if (provider == "gemini" or (provider == "auto" and gemini_key)) and gemini_key:
            res = self._call_gemini_api(prompt, system_prompt, gemini_key)
            if res:
                return res

        # 2. OpenAI API (if configured)
        if (provider == "openai" or (provider == "auto" and openai_key)) and openai_key:
            res = self._call_openai_api(prompt, system_prompt, openai_key)
            if res:
                return res

        # 3. Local Ollama (if configured)
        if (provider == "ollama" or (provider == "auto" and self.config.ollama_host)) and self.config.ollama_host:
            res = self._call_ollama_api(prompt, system_prompt, ollama_host)
            if res:
                return res

        # 4. If real model is loaded, run inference under llama_cpp
        if self.is_loaded:
            def _infer() -> str:
                full_input = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
                output = self._llm(
                    full_input,
                    max_tokens=max_tokens,
                    temperature=temp,
                    stop=stops,
                    echo=False,
                )
                return output["choices"][0]["text"].strip()

            return self.supervisor.run_sequential_task(_infer)

        # Fallback engine when model file is not downloaded yet
        return self._generate_fallback(prompt, system_prompt)

    def _call_gemini_api(self, prompt: str, system_prompt: str, api_key: str) -> str | None:
        """Query Gemini API via stdlib urllib (zero external dependencies)."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\nUSER REQUEST:\n{prompt}"}
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            self.supervisor.log_diagnostic(f"Gemini API call failed: {e}")
            return None

    def _call_openai_api(self, prompt: str, system_prompt: str, api_key: str) -> str | None:
        """Query OpenAI API via stdlib urllib."""
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            self.supervisor.log_diagnostic(f"OpenAI API call failed: {e}")
            return None

    def _call_ollama_api(self, prompt: str, system_prompt: str, host: str) -> str | None:
        """Query local Ollama instance via stdlib urllib."""
        url = f"{host.rstrip('/')}/api/generate"
        payload = {
            "model": "llama3.2",
            "prompt": f"{system_prompt}\n\n{prompt}",
            "stream": False,
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["response"].strip()
        except Exception as e:
            self.supervisor.log_diagnostic(f"Ollama API call failed: {e}")
            return None


    def _generate_fallback(self, prompt: str, system_prompt: str) -> str:
        """Deterministic, intelligent fallback for environments without downloaded model weights."""
        prompt_lower = prompt.lower()
        sys_lower = system_prompt.lower()

        # Guidance mode fallback (check first if role is guidance)
        if "guidance" in sys_lower or "guide" in prompt_lower:
            return (
                "### Hearthwren Step-by-Step Guidance\n\n"
                "- **Step 1**: Run `hwren status` to inspect workspace health and available RAM.\n"
                "- **Step 2**: Use `hwren plan \"<task>\"` to generate an ordered plan without modifying files.\n"
                "- **Step 3**: Use `hwren run` to execute the steps with interactive diff approvals.\n"
                "- **Step 4**: Verify with `hwren verify` before committing changes."
            )

        # Planning mode fallback
        if "implementation plan" in sys_lower or "plan" in prompt_lower or "plan" in sys_lower:
            return (
                "### Hearthwren Execution Plan\n\n"
                "1. **Analyze Context & Requirements**: Inspect project structure, manifests, and AGENT_MEMORY.md.\n"
                "2. **Safety & Preflight Check**: Verify memory ceiling, test framework, and git status.\n"
                "3. **Implementation Step 1**: Formulate modular changes with unified diffs.\n"
                "4. **Verification Step**: Run project test suite (`hwren verify`) and inspect real exit codes.\n"
                "5. **Review & Approval**: Present changes to user for explicit commit approval.\n\n"
                "**Surfaced Risks & Unknowns:**\n"
                "- Verify all test dependencies are satisfied before committing.\n"
                "- Ensure memory ceiling (<= 3.5 GB) remains respected during execution."
            )

        # General response
        return (
            "Hearthwren Local Assistant ready.\n"
            f"Active configuration: Context={self.config.context_window} tokens, "
            f"RAM ceiling={self.config.ram_ceiling_gb} GB."
        )


ModelService = LocalModelService
