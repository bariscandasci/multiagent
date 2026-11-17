"""JSON dosyalarını kilit altında, geçici dosyadan yeniden adlandırarak yazar."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path

_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}


def json_lock(path: Path | str) -> threading.RLock:
    key = str(Path(path).resolve())
    with _guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _locks[key] = lock
        return lock


def save_json_safe(path: Path | str, payload: object) -> None:
    """Aynı dosyaya eşzamanlı yazmayı sıraya alır ve yarım JSON bırakmaz."""
    target = Path(path)
    lock = json_lock(target)
    blob = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with lock:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(blob)
                handle.flush()
                os.fsync(handle.fileno())
            _replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def _replace(source: Path, target: Path) -> None:
    """Windows, yeni kapanmış dosyada os.replace için kısa süre erişim reddi verebilir."""
    delay = 0.02
    for attempt in range(6):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(delay)
            delay *= 2
