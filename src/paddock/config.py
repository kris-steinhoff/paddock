"""Settings models, discovery/merge, and environment resolution."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError


class ConfigError(Exception):
    """Raised when settings cannot be loaded, merged, or resolved."""


class CommandValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str


EnvValue = str | CommandValue


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: dict[str, EnvValue] = {}


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Merge ``overlay`` onto ``base``, recursing into nested dicts."""
    result = dict(base)
    for key, value in overlay.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            result[key] = _deep_merge(existing, value)
        else:
            result[key] = value
    return result


def load_merged(paths: list[Path]) -> Settings:
    """Read and deep-merge settings files, least to most specific, then validate.

    The most specific file wins per ``environment`` key.
    """
    merged: dict = {}
    for path in paths:
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"failed to parse {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"{path}: top level must be a hash")
        merged = _deep_merge(merged, data)

    try:
        return Settings.model_validate(merged)
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
