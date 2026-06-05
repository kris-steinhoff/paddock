"""Resolve a repo path into its Dockerfile, image tag, and settings files.

The repo path is the convention: ``<host>/<org>/<name>`` (to arbitrary depth) maps
directly to a directory under ``repos/`` and to a lowercased ``paddock/<repo-path>``
image tag. No mapping file, no aliasing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SETTINGS_FILENAME = "settings.yaml"
DOCKERFILE_NAME = "Dockerfile"


class RepoError(ValueError):
    """Raised when a repo argument cannot be resolved to a target."""


def config_base() -> Path:
    """Return ``${XDG_CONFIG_HOME:-~/.config}/paddock``."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "paddock"


def parse_repo(repo: str) -> list[str]:
    """Split a repo argument into path segments.

    Rejects empty segments and requires at least a host and a name (two segments).
    """
    segments = repo.strip("/").split("/")
    if any(s == "" for s in segments):
        raise RepoError(f"repo path has an empty segment: {repo!r}")
    if len(segments) < 2:
        raise RepoError(f"repo path needs at least <host>/<name>: {repo!r}")
    return segments


def image_tag(segments: list[str]) -> str:
    """Return the lowercased ``paddock/<repo-path>`` image tag."""
    return "paddock/" + "/".join(segments).lower()


@dataclass(frozen=True)
class RepoTarget:
    segments: list[str]
    repos_dir: Path
    leaf_dir: Path
    dockerfile: Path
    image: str
    settings_paths: list[Path]


def resolve(repo: str, base: Path | None = None) -> RepoTarget:
    """Resolve a repo argument into a :class:`RepoTarget`.

    ``settings_paths`` are ordered least to most specific and include only files that
    exist: ``repos/settings.yaml`` first, then one ``settings.yaml`` per directory level
    down to the leaf.
    """
    segments = parse_repo(repo)
    repos_dir = (base if base is not None else config_base()) / "repos"
    leaf_dir = repos_dir.joinpath(*segments)

    candidates = [repos_dir / SETTINGS_FILENAME]
    current = repos_dir
    for segment in segments:
        current = current / segment
        candidates.append(current / SETTINGS_FILENAME)
    settings_paths = [p for p in candidates if p.is_file()]

    return RepoTarget(
        segments=segments,
        repos_dir=repos_dir,
        leaf_dir=leaf_dir,
        dockerfile=leaf_dir / DOCKERFILE_NAME,
        image=image_tag(segments),
        settings_paths=settings_paths,
    )
