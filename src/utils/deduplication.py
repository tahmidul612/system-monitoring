"""Log deduplication utility to group similar or identical log entries.

Reduces noise by:
- Grouping exact duplicate messages
- Normalizing messages to detect similar patterns (timestamps, PIDs, IDs)
- Tracking occurrence count and time range (first_seen, last_seen)
"""

import re
from typing import Any


def _normalize_message(message: str) -> str:
    """Normalize log message by removing variable parts.

    Removes:
    - ISO 8601 timestamps (2024-05-21T10:30:15Z, 2024-05-21 10:30:15, etc.)
    - Unix timestamps (1716285015, 1716285015.123)
    - Process IDs (pid: 1234, PID=5678, [12345])
    - Memory addresses (0x7f8a3c4b2000)
    - UUIDs and hex IDs (abc123def456, 550e8400-e29b-41d4-a716-446655440000)
    - IPv4 addresses (192.168.1.100)
    - Port numbers (:8080, :3000)
    - File paths with line numbers (file.py:42, /path/to/file:123)
    - Container/Docker IDs (12-char hex)
    - Numeric values in brackets [42], (1234)

    Args:
        message: Original log message

    Returns:
        Normalized message with variable parts replaced by placeholders
    """
    # ISO 8601 timestamps
    normalized = re.sub(
        r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b",
        "<TIMESTAMP>",
        message,
    )

    # Unix timestamps (10+ digits, optional decimal)
    normalized = re.sub(r"\b\d{10,}(?:\.\d+)?\b", "<UNIX_TS>", normalized)

    # Memory addresses
    normalized = re.sub(r"\b0x[0-9a-fA-F]{8,}\b", "<ADDR>", normalized)

    # UUIDs (8-4-4-4-12 hex format)
    normalized = re.sub(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        "<UUID>",
        normalized,
    )

    # Long hex IDs (12+ chars, common in Docker/container IDs)
    normalized = re.sub(r"\b[0-9a-fA-F]{12,}\b", "<HEX_ID>", normalized)

    # IPv4 addresses
    normalized = re.sub(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "<IP>",
        normalized,
    )

    # Port numbers
    normalized = re.sub(r":\d{2,5}\b", ":<PORT>", normalized)

    # File paths with line numbers
    normalized = re.sub(
        r"(/[\w\-./]+\.[\w]+):\d+",
        r"\1:<LINE>",
        normalized,
    )

    # Process IDs in various formats
    normalized = re.sub(
        r"\bpid[:\s=]+\d+", "pid <PID>", normalized, flags=re.IGNORECASE
    )
    normalized = re.sub(r"\[(\d{3,})\]", "[<PID>]", normalized)

    # Numbers in parentheses (often counts, IDs, etc.)
    normalized = re.sub(r"\((\d+)\)", "(<NUM>)", normalized)

    return normalized.strip()


def deduplicate_logs(
    logs: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Deduplicate and group similar log entries within each category.

    Groups logs by normalized message, tracking:
    - count: Number of occurrences
    - first_seen: Timestamp of the first occurrence
    - last_seen: Timestamp of the most recent occurrence

    Preserves the original message from the latest occurrence.

    Args:
        logs: Dictionary with log categories as keys, each containing a list of log entries

    Returns:
        Dictionary with same structure but deduplicated entries
    """
    deduplicated: dict[str, list[dict[str, Any]]] = {}

    for category, entries in logs.items():
        if not entries:
            deduplicated[category] = []
            continue

        # Group entries by normalized message
        groups: dict[str, list[dict[str, Any]]] = {}

        for entry in entries:
            message = entry.get("message", "")
            normalized = _normalize_message(message)

            if normalized not in groups:
                groups[normalized] = []
            groups[normalized].append(entry)

        # Build deduplicated entries
        deduplicated_entries = []

        for _normalized_msg, group_entries in groups.items():
            if len(group_entries) == 1:
                # Single occurrence - no deduplication needed
                deduplicated_entries.append(group_entries[0])
            else:
                # Multiple occurrences - create grouped entry
                # Sort by timestamp to get first and last
                sorted_entries = sorted(
                    group_entries,
                    key=lambda e: e.get("timestamp", ""),
                )

                first_entry = sorted_entries[0]
                last_entry = sorted_entries[-1]

                # Build deduplicated entry from the latest occurrence
                deduplicated_entry = last_entry.copy()

                # Add deduplication metadata
                deduplicated_entry["count"] = len(group_entries)
                deduplicated_entry["first_seen"] = first_entry.get("timestamp")
                deduplicated_entry["last_seen"] = last_entry.get("timestamp")

                # Move original timestamp field to preserve last occurrence
                if (
                    "timestamp" in deduplicated_entry
                    and deduplicated_entry["timestamp"]
                    != deduplicated_entry["last_seen"]
                ):
                    # If timestamp differs from last_seen (shouldn't happen, but defensive)
                    deduplicated_entry["timestamp"] = deduplicated_entry["last_seen"]

                deduplicated_entries.append(deduplicated_entry)

        # Sort by last_seen (or timestamp if no last_seen) descending
        deduplicated_entries.sort(
            key=lambda e: e.get("last_seen") or e.get("timestamp", ""),
            reverse=True,
        )

        deduplicated[category] = deduplicated_entries

    return deduplicated
