"""Global configuration values for LockPort."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    program_data = os.environ.get("PROGRAMDATA")
    base = Path(program_data) if program_data else Path.cwd()
    return (base / "LockPort").expanduser()


@dataclass(slots=True)
class LockPortConfig:
    """Runtime configuration for the LockPort service."""

    pin_store_path: Path = field(default_factory=_default_data_dir)
    pin_store_file: str = "pin_store.json"
    log_path: Path = field(default_factory=_default_data_dir)
    log_file: str = "lockport.log"
    pin_attempt_limit: int = 5
    pin_lockout_seconds: int = 300
    pin_hash_iterations: int = 100_000
    monitor_poll_seconds: int = 0.5
    ui_timeout_seconds: int = 120
    device_state_file: str = "device_states.json"
    pin_cache_file: str = "pin_cache.json"

    def ensure_directories(self) -> None:
        """Create directories for application data if they do not exist."""
        self.pin_store_path.mkdir(parents=True, exist_ok=True)
        self.log_path.mkdir(parents=True, exist_ok=True)

    @property
    def pin_store_location(self) -> Path:
        return self.pin_store_path / self.pin_store_file

    @property
    def log_location(self) -> Path:
        return self.log_path / self.log_file

    @property
    def device_state_location(self) -> Path:
        return self.pin_store_path / self.device_state_file

    @property
    def pin_cache_location(self) -> Path:
        return self.pin_store_path / self.pin_cache_file


DEFAULT_CONFIG = LockPortConfig()
DEFAULT_CONFIG.ensure_directories()
