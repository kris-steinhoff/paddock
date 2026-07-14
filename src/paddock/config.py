"""Settings model, single-file load, and environment resolution."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError


class ConfigError(Exception):
    """Raised when settings cannot be loaded or resolved."""


class CommandValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str


EnvValue = str | CommandValue


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: dict[str, EnvValue] = {}
    ca_certificates: list[str] = []


def load_settings(path: Path) -> Settings:
    """Load settings from ``path``. A missing file is treated as empty settings."""
    if not path.is_file():
        return Settings()

    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"failed to parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a hash")

    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid settings: {exc}") from exc


def resolve_environment(settings: Settings) -> dict[str, str]:
    """Resolve each environment value to a string, running ``command`` entries."""
    resolved: dict[str, str] = {}
    for name, value in settings.environment.items():
        if isinstance(value, CommandValue):
            try:
                completed = subprocess.run(
                    ["sh", "-c", value.command],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                raise ConfigError(
                    f"command for {name} failed (exit {exc.returncode}): "
                    f"{value.command}\n{exc.stderr.strip()}"
                ) from exc
            resolved[name] = completed.stdout.rstrip("\n")
        else:
            resolved[name] = value
    return resolved


def ca_certificate_paths(settings: Settings) -> list[Path]:
    """Expand and validate each configured CA certificate path.

    Raises ``ConfigError`` early (rather than failing later inside a
    ``docker build``) if a configured path doesn't exist.
    """
    resolved: list[Path] = []
    for raw in settings.ca_certificates:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise ConfigError(f"ca_certificates entry not found: {path}")
        resolved.append(path)
    return resolved
