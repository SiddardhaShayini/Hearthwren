"""Model downloader and integrity verifier for Hearthwren.

Manages downloading Nanbeige4.1-3B GGUF weights to ~/.hearthwren/models/
with streaming SHA-256 integrity verification. Offline by default.
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path
from typing import Any, Callable

from hearthwren.config import DEFAULT_MODEL_PATH, USER_MODEL_DIR

# Pinned default download target
DEFAULT_MODEL_URL = (
    "https://huggingface.co/mradermacher/Nanbeige4.1-3B-GGUF/resolve/main/Nanbeige4.1-3B.Q4_K_M.gguf"
)


class ModelDownloader:
    """Safely downloads and verifies GGUF model weights."""

    def __init__(self, target_path: Path | None = None):
        self.target_path = (target_path or DEFAULT_MODEL_PATH).resolve()

    def check_installed(self) -> bool:
        """Check if model weights exist and have non-trivial size (> 100 MB)."""
        return self.target_path.is_file() and self.target_path.stat().st_size > 100_000_000

    def compute_sha256(self, file_path: Path | None = None, chunk_size: int = 1_048_576) -> str:
        """Stream SHA-256 calculation chunk-by-chunk without exhausting RAM."""
        path = file_path or self.target_path
        if not path.is_file():
            return ""

        hasher = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()

    def download_model(
        self,
        url: str = DEFAULT_MODEL_URL,
        approved: bool = False,
        expected_sha256: str | None = None,
        progress_hook: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Download model file with explicit user approval gate."""
        if not approved:
            return {
                "success": False,
                "needs_approval": True,
                "url": url,
                "destination": str(self.target_path),
                "estimated_size": "~2.0 GB",
                "message": (
                    f"Model weights download requires network permission.\n"
                    f"Source: {url}\n"
                    f"Destination: {self.target_path}\n"
                    f"Explicit approval required."
                ),
            }

        self.target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_dest = self.target_path.with_suffix(".download.tmp")

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Hearthwren-CLI/0.1.0"})
            with urllib.request.urlopen(req, timeout=30.0) as response, temp_dest.open("wb") as out_file:
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 524_288  # 512 KB chunks

                while chunk := response.read(chunk_size):
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if progress_hook:
                        progress_hook(downloaded, total_size)

            # Verification
            if expected_sha256:
                computed_hash = self.compute_sha256(temp_dest)
                if computed_hash.lower() != expected_sha256.lower():
                    temp_dest.unlink()
                    return {
                        "success": False,
                        "error": f"SHA-256 hash mismatch: expected {expected_sha256}, got {computed_hash}",
                    }

            temp_dest.replace(self.target_path)
            return {
                "success": True,
                "destination": str(self.target_path),
                "size_bytes": self.target_path.stat().st_size,
            }
        except Exception as e:
            if temp_dest.exists():
                temp_dest.unlink()
            return {"success": False, "error": f"Download failed: {e}"}
