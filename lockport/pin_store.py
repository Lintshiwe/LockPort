"""PIN hashing, storage, validation, and secure caching utilities."""
from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, cast

from .config import DEFAULT_CONFIG, LockPortConfig

try:
    import hashlib
    import secrets
except ImportError as exc:  # pragma: no cover - stdlib expected
    raise RuntimeError("Missing standard libraries for cryptography") from exc

try:  # pragma: no cover - Windows-only DPAPI support
    import win32crypt  # type: ignore[import]
except Exception:  # pragma: no cover - pywin32 not available (tests/non-Windows)
    win32crypt = None  # type: ignore[assignment]


logger = logging.getLogger("lockport.pin_store")


class PinLockedError(Exception):
    """Raised when PIN verification is temporarily locked out."""


class PinValidationError(Exception):
    """Raised when PIN validation fails."""


@dataclass(slots=True)
class PinStoreRecord:
    hash_value: str
    salt: str
    iterations: int

    @classmethod
    def from_pin(cls, pin: str, *, iterations: int) -> "PinStoreRecord":
        salt = secrets.token_bytes(16)
        hash_bytes = hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), salt, iterations
        )
        return cls(
            hash_value=base64.b64encode(hash_bytes).decode("ascii"),
            salt=base64.b64encode(salt).decode("ascii"),
            iterations=iterations,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hash_value": self.hash_value,
            "salt": self.salt,
            "iterations": self.iterations,
        }

    def verify(self, pin: str) -> bool:
        salt_bytes = base64.b64decode(self.salt.encode("ascii"))
        expected_hash = base64.b64decode(self.hash_value.encode("ascii"))
        test_hash = hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), salt_bytes, self.iterations
        )
        return secrets.compare_digest(expected_hash, test_hash)


class PinManager:
    """Thread-safe PIN storage manager."""

    def __init__(self, config: LockPortConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG
        self.config.ensure_directories()
        self._store_path = self.config.pin_store_location
        self._cache_path = self.config.pin_cache_location
        self._lock = threading.RLock()
        if not self._store_path.exists():
            self._initialize_store()

    def _initialize_store(self) -> None:
        with self._lock:
            record = PinStoreRecord.from_pin(
                "0000", iterations=self.config.pin_hash_iterations
            )
            payload: Dict[str, Any] = {
                "pin": record.to_dict(),
                "failed_attempts": 0,
                "lock_until": 0,
                "updated_at": time.time(),
            }
            self._write(payload)

    def _read(self) -> Dict[str, Any]:
        with self._lock:
            if self._store_path.exists():
                return json.loads(self._store_path.read_text())
            self._initialize_store()
            return json.loads(self._store_path.read_text())

    def _write(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._store_path.write_text(json.dumps(payload, indent=2))

    def verify_pin(self, candidate: str) -> bool:
        data = self._read()
        now = time.time()
        if data.get("lock_until", 0) > now:
            raise PinLockedError("PIN entry temporarily locked")

        record = PinStoreRecord(**data["pin"])
        if record.verify(candidate):
            data["failed_attempts"] = 0
            data["lock_until"] = 0
            data["updated_at"] = now
            self._write(data)
            self._cache_last_pin(candidate)
            return True

        data["failed_attempts"] = data.get("failed_attempts", 0) + 1
        if data["failed_attempts"] >= self.config.pin_attempt_limit:
            data["lock_until"] = now + self.config.pin_lockout_seconds
            data["failed_attempts"] = 0
        self._write(data)
        raise PinValidationError("Invalid PIN")

    def set_pin(self, new_pin: str, *, current_pin: str | None = None) -> None:
        if not new_pin.isdigit() or not (4 <= len(new_pin) <= 8):
            raise ValueError("PIN must be 4-8 numeric digits")

        if current_pin is not None:
            try:
                self.verify_pin(current_pin)
            except (PinValidationError, PinLockedError) as exc:
                raise PinValidationError("Current PIN validation failed") from exc

        record = PinStoreRecord.from_pin(
            new_pin, iterations=self.config.pin_hash_iterations
        )
        payload: Dict[str, Any] = self._read()
        payload["pin"] = record.to_dict()
        payload["updated_at"] = time.time()
        payload["failed_attempts"] = 0
        payload["lock_until"] = 0
        self._write(payload)
        self._clear_cached_pin()

    def reset_lockout(self) -> None:
        payload = self._read()
        payload["failed_attempts"] = 0
        payload["lock_until"] = 0
        self._write(payload)

    def get_status(self) -> Dict[str, Any]:
        data = self._read()
        return {
            "failed_attempts": data.get("failed_attempts", 0),
            "lock_until": data.get("lock_until", 0),
            "locked": data.get("lock_until", 0) > time.time(),
            "updated_at": data.get("updated_at"),
        }

    # --- PIN caching helpers -------------------------------------------------
    def _cache_last_pin(self, pin: str) -> None:
        if win32crypt is None:
            return
        try:
            result_protect: tuple[str, bytes] = win32crypt.CryptProtectData(  # type: ignore[attr-defined]
                pin.encode("utf-8"), None, None, None, None, 0
            )
            encrypted = cast(bytes, result_protect[1])
            payload: Dict[str, float | str] = {
                "ts": time.time(),
                "blob": base64.b64encode(encrypted).decode("ascii"),
            }
            self._cache_path.write_text(json.dumps(payload))
        except Exception as exc:  # pragma: no cover - best effort cache
            logger.debug("Failed to cache PIN: %s", exc)

    def _clear_cached_pin(self) -> None:
        try:
            if self._cache_path.exists():
                self._cache_path.unlink()
        except OSError as exc:  # pragma: no cover - best effort
            logger.debug("Failed to clear PIN cache: %s", exc)

    def get_cached_pin(self, max_age_seconds: int = 120) -> str | None:
        if win32crypt is None:
            return None
        try:
            raw = json.loads(self._cache_path.read_text())
            timestamp = float(raw.get("ts", 0))
            if time.time() - timestamp > max_age_seconds:
                return None
            blob = base64.b64decode(raw["blob"].encode("ascii"))
            result_unprotect: tuple[str, bytes] = win32crypt.CryptUnprotectData(  # type: ignore[attr-defined]
                blob, None, None, None, 0
            )
            return result_unprotect[1].decode("utf-8")
        except FileNotFoundError:
            return None
        except Exception as exc:  # pragma: no cover
            logger.debug("Failed to read cached PIN: %s", exc)
            return None
