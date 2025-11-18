"""Unit tests for the PinManager."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from lockport.config import LockPortConfig
from lockport.pin_store import PinLockedError, PinManager, PinValidationError


def build_manager(tmp_path: Path) -> PinManager:
    config = LockPortConfig(
        pin_store_path=tmp_path,
        log_path=tmp_path,
        pin_store_file="pin.json",
        log_file="test.log",
        pin_attempt_limit=2,
        pin_lockout_seconds=1,
    )
    return PinManager(config)


def test_default_pin(tmp_path: Path) -> None:
    manager = build_manager(tmp_path)
    assert manager.verify_pin("0000") is True


def test_set_and_verify_pin(tmp_path: Path) -> None:
    manager = build_manager(tmp_path)
    manager.set_pin("1234")
    assert manager.verify_pin("1234") is True


def test_invalid_pin_increments_counter(tmp_path: Path) -> None:
    manager = build_manager(tmp_path)
    try:
        manager.verify_pin("1111")
    except PinValidationError:
        pass
    status = manager.get_status()
    assert status["failed_attempts"] == 1


def test_lockout(tmp_path: Path) -> None:
    manager = build_manager(tmp_path)
    for _ in range(2):
        try:
            manager.verify_pin("9999")
        except PinValidationError:
            pass
    with pytest.raises(PinLockedError):
        manager.verify_pin("0000")
    time.sleep(1.1)
    assert manager.verify_pin("0000") is True


def test_store_file_exists(tmp_path: Path) -> None:
    manager = build_manager(tmp_path)
    store_file = manager.config.pin_store_location
    assert store_file.exists()
    data = json.loads(store_file.read_text())
    assert "pin" in data
