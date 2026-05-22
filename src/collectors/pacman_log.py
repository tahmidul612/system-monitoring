"""PacmanLogCollector - Extract package manager warnings from /var/log/pacman.log."""

import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from ..state_manager import StateManager
from .base import LogCollector

logger = logging.getLogger(__name__)


class PacmanLogCollector(LogCollector):
    """Collect warnings and errors from pacman.log.

    Uses state tracking to avoid re-processing previously read lines.
    Target events: [ALPM-SCRIPTLET] errors, [WARNING] tags, missing PGP keys.
    """

    PACMAN_LOG_PATH = Path("/var/log/pacman.log")
    STATE_PATH = Path("/var/lib/system-monitoring/pacman_state.json")

    WARNING_PATTERNS: ClassVar[list[str]] = [
        r"\[WARNING\]",
        r"\[ALPM-SCRIPTLET\]",
        r"error:",
        r"failed",
        r"missing.*key",
    ]

    def __init__(self, lookback_minutes: int = 60):
        super().__init__(lookback_minutes)
        self.state = StateManager(self.STATE_PATH)
        self.warning_regex = re.compile("|".join(self.WARNING_PATTERNS), re.IGNORECASE)

    def collect(self) -> list[dict[str, Any]]:
        """Extract warnings/errors from pacman.log since last read position."""
        if not self.PACMAN_LOG_PATH.exists():
            logger.warning("Pacman log not found: %s", self.PACMAN_LOG_PATH)
            return []

        self.state.load()
        entries = []

        try:
            with open(self.PACMAN_LOG_PATH, encoding="utf-8", errors="replace") as f:
                last_line_num = self.state.get_last_line()
                current_line_num = 0

                for line_num, line in enumerate(f, start=1):
                    if line_num <= last_line_num:
                        continue

                    current_line_num = line_num

                    if self.warning_regex.search(line):
                        entry = self._parse_pacman_line(line)
                        if entry and self._is_within_lookback(entry.get("timestamp")):
                            entries.append(entry)

                self.state.set_last_line(current_line_num, f.tell())
                self.state.save()

        except OSError as e:
            logger.error("Failed to read pacman.log: %s", e)
            return [
                self._format_entry(
                    timestamp=datetime.now(UTC).isoformat(),
                    message=f"Failed to read pacman.log: {e}",
                    error=True,
                )
            ]

        return entries

    def _parse_pacman_line(self, line: str) -> dict[str, Any] | None:
        """Parse pacman.log line format: [YYYY-MM-DD HH:MM] [LEVEL] message."""
        match = re.match(
            r"\[(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}(?::\d{2})?)\]\s+\[?(\w+)\]?\s*(.*)",
            line,
        )
        if not match:
            return None

        timestamp_str, level, message = match.groups()

        try:
            timestamp_str = timestamp_str.replace(" ", "T")
            if len(timestamp_str) == 16:
                timestamp_str += ":00"
            dt = datetime.fromisoformat(timestamp_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
        except ValueError:
            dt = datetime.now(UTC)

        return self._format_entry(
            timestamp=dt.isoformat(),
            level=level,
            message=message.strip(),
            source="pacman",
        )

    def _is_within_lookback(self, timestamp_str: str | None) -> bool:
        """Check if timestamp is within the lookback window."""
        if not timestamp_str:
            return True

        try:
            dt = datetime.fromisoformat(timestamp_str)
            cutoff = datetime.now(UTC) - timedelta(minutes=self.lookback_minutes)
            return dt >= cutoff
        except (ValueError, TypeError):
            return True
