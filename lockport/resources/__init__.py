"""LockPort package assets (icons, imagery, etc.)."""
from __future__ import annotations

from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Iterator


def _resource(name: str) -> resources.abc.Traversable:
    return resources.files(__name__).joinpath(name)


def load_asset_bytes(name: str) -> bytes:
    """Return the raw bytes for a packaged resource."""
    return _resource(name).read_bytes()


@contextmanager
def asset_path(name: str) -> Iterator[Path]:
    """Expose a resource on disk (e.g., for tooling that needs a path)."""
    with resources.as_file(_resource(name)) as path:
        yield Path(path)
