"""Tests for ModelDownloader."""

from pathlib import Path
from hearthwren.model_downloader import ModelDownloader


def test_download_approval_gate(tmp_path: Path):
    target = tmp_path / "model.gguf"
    downloader = ModelDownloader(target_path=target)

    # Unapproved call requires approval and does not access network
    res = downloader.download_model(approved=False)
    assert res["success"] is False
    assert res["needs_approval"] is True
    assert "Explicit approval required" in res["message"]
    assert not target.exists()


def test_streaming_sha256(tmp_path: Path):
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"Hearthwren Local AI Model Content")

    downloader = ModelDownloader(target_path=sample)
    hash_str = downloader.compute_sha256()
    assert len(hash_str) == 64  # Valid SHA-256 hex string
