"""Abstract base class for log collectors.

All collector modules inherit from LogCollector and implement the collect() method.
"""

from abc import ABC, abstractmethod
from typing import Any


class LogCollector(ABC):
    """Abstract base class for log collection modules.

    Each collector is responsible for:
    1. Querying its specific log source
    2. Filtering for warnings/errors within the time window
    3. Returning logs as a list of dictionaries
    """

    def __init__(self, lookback_minutes: int = 60):
        """Initialize collector with time window.

        Args:
            lookback_minutes: How far back to collect logs (default: 60)
        """
        self.lookback_minutes = lookback_minutes

    @abstractmethod
    def collect(self) -> list[dict[str, Any]]:
        """Collect and return logs from this module's source.

        Returns:
            List of log entry dictionaries. Format is source-specific
            but typically includes: timestamp, message, priority/severity.

        Raises:
            Exception subclasses on critical failures. Collectors should
            gracefully degrade when possible (e.g., Docker daemon down).
        """
        pass

    def _format_entry(self, **fields) -> dict[str, Any]:
        """Helper to create a standardized log entry dictionary.

        Args:
            **fields: Arbitrary key-value pairs for the log entry

        Returns:
            Dictionary with provided fields
        """
        return fields
