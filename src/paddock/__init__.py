"""paddock: build, run, and remove a per-repo container with configured env injected."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("paddock")
except PackageNotFoundError:  # not installed (e.g. running from a source tree)
    __version__ = "0+unknown"
