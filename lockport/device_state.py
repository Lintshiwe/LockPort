"""Persistent tracking of USB device states."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, cast

from .config import DEFAULT_CONFIG, LockPortConfig


@dataclass(slots=True)
class DeviceState:
    instance_id: str
    drive: str
    volume: str
    status: str
    updated_at: float

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class DeviceStateStore:
    """Thread-safe helper to persist device states to disk."""

    def __init__(self, config: LockPortConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG
        self.config.ensure_directories()
        self.path: Path = self.config.device_state_location
        self._lock = threading.RLock()
        self._cache: Dict[str, DeviceState] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            return
        data_dict = cast(Dict[str, Dict[str, object]], data)
        for raw_key, value in data_dict.items():
            try:
                raw_updated = value.get("updated_at", 0.0)
                updated_at = float(raw_updated) if isinstance(raw_updated, (int, float, str)) else 0.0
                self._cache[raw_key] = DeviceState(
                    instance_id=str(value.get("instance_id", raw_key)),
                    drive=str(value.get("drive", "") or ""),
                    volume=str(value.get("volume", "") or ""),
                    status=str(value.get("status", "unknown") or "unknown"),
                    updated_at=updated_at,
                )
            except (TypeError, ValueError):
                continue

    def reload(self) -> None:
        """Force a fresh read from disk for observers."""
        with self._lock:
            self._cache.clear()
            self._load()

    def _persist(self) -> None:
        with self._lock:
            serializable = {key: state.to_dict() for key, state in self._cache.items()}
            self.path.write_text(json.dumps(serializable, indent=2))

    def upsert(
        self,
        *,
        instance_id: str,
        drive: str | None,
        volume: str | None,
        status: str,
    ) -> None:
        with self._lock:
            self._cache[instance_id] = DeviceState(
                instance_id=instance_id,
                drive=drive or "",
                volume=volume or "",
                status=status,
                updated_at=time.time(),
            )
            self._persist()

    def list_states(self) -> List[DeviceState]:
        with self._lock:
            return list(self._cache.values())

    def as_dict(self) -> Dict[str, DeviceState]:
        with self._lock:
            return dict(self._cache)

    def get(self, instance_id: str) -> DeviceState | None:
        with self._lock:
            return self._cache.get(instance_id)
