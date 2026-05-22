"""State management for tracking pacman.log read position."""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional


class StateManager:
    """Atomic state persistence for pacman.log position tracking.
    
    Uses JSON with atomic writes (tempfile + fsync + os.replace) and
    rolling .bak recovery for crash safety.
    """

    def __init__(self, state_path: Path):
        self._path = state_path
        self._data: dict = {}

    def load(self) -> dict:
        """Load state with recovery fallback: main → .bak → empty."""
        bak = self._path.with_suffix(self._path.suffix + ".bak")

        if self._path.exists():
            try:
                with open(self._path) as f:
                    self._data = json.load(f)
                return self._data
            except (json.JSONDecodeError, OSError, ValueError):
                pass

        if bak.exists():
            try:
                with open(bak) as f:
                    self._data = json.load(f)
                self._atomic_write(backup=False)
                return self._data
            except (json.JSONDecodeError, OSError, ValueError):
                pass

        self._data = {}
        return self._data

    def save(self) -> None:
        """Persist state atomically with rolling .bak."""
        self._atomic_write(backup=True)

    def _atomic_write(self, backup: bool = True) -> None:
        """Write state using tempfile + fsync + os.replace for atomicity."""
        path = self._path
        bak = path.with_suffix(path.suffix + ".bak")

        if backup and path.exists():
            import shutil
            shutil.copy2(path, bak)

        path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as tf:
            json.dump(self._data, tf, indent=2)
            tf.flush()
            os.fsync(tf.fileno())

        os.replace(tf.name, str(path))

    def get_last_line(self) -> int:
        return self._data.get("last_line", 0)

    def set_last_line(self, line: int, file_size: Optional[int] = None) -> None:
        self._data["last_line"] = line
        if file_size is not None:
            self._data["last_file_size"] = file_size
        from datetime import datetime
        self._data["updated_at"] = datetime.now().isoformat()

    def get_last_file_size(self) -> int:
        return self._data.get("last_file_size", 0)

    @property
    def data(self) -> dict:
        return self._data
