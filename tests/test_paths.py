from __future__ import annotations

from pathlib import Path

from paddock import paths


def test_config_dir_under_xdg_config_home(xdg_base: Path):
    assert paths.config_dir() == xdg_base / "config" / "paddock"


def test_compose_file_is_packaged_image_file():
    assert (
        paths.compose_file()
        == Path(paths.__file__).resolve().parent / "image" / "docker-compose.yml"
    )


def test_override_file_under_config_dir(xdg_base: Path):
    assert paths.override_file() == paths.config_dir() / "docker-compose.override.yml"


def test_env_file_under_config_dir(xdg_base: Path):
    assert paths.env_file() == paths.config_dir() / ".env"


def test_authorized_keys_path_under_config_dir(xdg_base: Path):
    assert paths.authorized_keys_path() == paths.config_dir() / "authorized_keys"


def test_certs_dir_under_config_dir(xdg_base: Path):
    assert paths.certs_dir() == paths.config_dir() / "certs"
