"""UserSessionCollector - Extract user-level application logs via journalctl --user."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

from systemd import journal

from .base import LogCollector

logger = logging.getLogger(__name__)


class UserSessionCollector(LogCollector):
    """Collect user-session logs from systemd journal.
    
    Queries journalctl --user for priority warning..emerg entries.
    Target events: Wayland compositor crashes, PipeWire errors,
    media player faults, user-space application crashes.
    """

    def collect(self) -> List[Dict[str, Any]]:
        """Query systemd journal for user-level warnings and errors."""
        since_dt = datetime.now(timezone.utc) - timedelta(minutes=self.lookback_minutes)
        entries = []

        try:
            with journal.Reader(journal.CURRENT_USER) as j:
                j.this_boot()
                j.log_level(journal.LOG_WARNING)
                j.seek_realtime(since_dt)

                for entry in j:
                    entries.append(self._format_journal_entry(entry))

        except (OSError, RuntimeError) as e:
            logger.error("Failed to read user journal: %s", e)
            return [self._format_entry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                message=f"User journal unavailable: {e}",
                priority="error",
                error=True,
            )]

        return entries

    def _format_journal_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Convert systemd journal entry to standardized format."""
        timestamp = entry.get("__REALTIME_TIMESTAMP")
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        return self._format_entry(
            timestamp=timestamp,
            message=entry.get("MESSAGE", ""),
            priority=self._priority_to_string(entry.get("PRIORITY", 6)),
            unit=entry.get("_SYSTEMD_UNIT", ""),
            pid=entry.get("_PID"),
        )

    @staticmethod
    def _priority_to_string(priority: int) -> str:
        """Map syslog priority int to string label."""
        mapping = {
            0: "emerg",
            1: "alert",
            2: "crit",
            3: "err",
            4: "warning",
            5: "notice",
            6: "info",
            7: "debug",
        }
        return mapping.get(priority, "unknown")
