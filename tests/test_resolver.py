from __future__ import annotations

from pathlib import Path

import pytest

from paddock.resolver import RepoError, image_tag, parse_repo, resolve


def test_parse_repo_segments():
    assert parse_repo("github.com/kris-steinhoff/paddock") == [
        "github.com",
        "kris-steinhoff",
        "paddock",
    ]


def test_parse_repo_strips_surrounding_slashes():
    assert parse_repo("/github.com/org/name/") == ["github.com", "org", "name"]


def test_parse_repo_arbitrary_depth():
    assert parse_repo("gitlab.com/org/subgroup/project") == [
        "gitlab.com",
        "org",
        "subgroup",
        "project",
    ]


@pytest.mark.parametrize("bad", ["", "name", "host//name", "/"])
def test_parse_repo_rejects_invalid(bad):
    with pytest.raises(RepoError):
        parse_repo(bad)


def test_image_tag_is_lowercased():
    assert image_tag(["GitHub.com", "Kris-Steinhoff", "Paddock"]) == (
        "paddock/github.com/kris-steinhoff/paddock"
    )


def test_resolve_paths(xdg_base: Path):
    target = resolve("github.com/kris-steinhoff/paddock")
    repos = xdg_base / "repos"
    leaf = repos / "github.com" / "kris-steinhoff" / "paddock"
    assert target.repos_dir == repos
    assert target.leaf_dir == leaf
    assert target.dockerfile == leaf / "Dockerfile"
    assert target.image == "paddock/github.com/kris-steinhoff/paddock"


def test_resolve_settings_paths_ordered_and_existing(xdg_base: Path):
    from conftest import write_settings

    # global and per-org exist; per-provider and per-project do not.
    write_settings(xdg_base, "", "environment: {}")
    write_settings(xdg_base, "github.com/kris-steinhoff", "environment: {}")

    target = resolve("github.com/kris-steinhoff/paddock")
    repos = xdg_base / "repos"
    assert target.settings_paths == [
        repos / "settings.yaml",
        repos / "github.com" / "kris-steinhoff" / "settings.yaml",
    ]
