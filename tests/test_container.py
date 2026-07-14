from __future__ import annotations

from pathlib import Path

import pytest

from paddock import container


def test_build_context_includes_packaged_image_files(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Path] = {}

    def fake_run(args: list[str]) -> None:
        captured["context_dir"] = Path(args[-1])
        assert (captured["context_dir"] / "Dockerfile").is_file()
        assert (captured["context_dir"] / "entrypoint.sh").is_file()
        assert (captured["context_dir"] / "sshd_config").is_file()
        assert (captured["context_dir"] / "ca-certificates").is_dir()

    monkeypatch.setattr(container, "_run", fake_run)
    container.build([])

    assert captured


def test_build_context_includes_configured_certs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cert = tmp_path / "corp-ca.pem"
    cert.write_text("fake cert contents")

    def fake_run(args: list[str]) -> None:
        copied = Path(args[-1]) / "ca-certificates" / "corp-ca.crt"
        assert copied.is_file()
        assert copied.read_text() == "fake cert contents"

    monkeypatch.setattr(container, "_run", fake_run)
    container.build([cert])
