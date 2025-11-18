"""Tests for DeviceStateStore."""
from __future__ import annotations

from pathlib import Path

from lockport.config import LockPortConfig
from lockport.device_state import DeviceStateStore


def build_store(tmp_path: Path) -> DeviceStateStore:
    cfg = LockPortConfig(
        pin_store_path=tmp_path,
        log_path=tmp_path,
        pin_store_file="pin.json",
        log_file="log.txt",
        device_state_file="devices.json",
    )
    return DeviceStateStore(cfg)


def test_upsert_records(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    store.upsert(instance_id="USB#001", drive="E:", volume="USB", status="locked")
    states = store.list_states()
    assert len(states) == 1
    state = states[0]
    assert state.instance_id == "USB#001"
    assert state.drive == "E:"
    assert state.status == "locked"


def test_store_persists(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    store.upsert(instance_id="USB#002", drive=None, volume=None, status="unlocked")
    new_store = build_store(tmp_path)
    states = new_store.list_states()
    assert states and states[0].instance_id == "USB#002"
    assert states[0].status == "unlocked"
