#!/usr/bin/env python3
"""Main orchestrator for system monitoring log extraction.

Coordinates all collectors, builds JSON payload, and delivers to webhook.
"""

import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any, ClassVar

from src.collectors import (
    DockerContainerCollector,
    PacmanLogCollector,
    SystemKernelCollector,
    UserSessionCollector,
)
from src.webhook import WebhookDelivery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class DependencyChecker:
    """Validate required system dependencies before execution."""

    REQUIRED_COMMANDS: ClassVar[list[str]] = ["docker"]

    @staticmethod
    def check_all() -> bool:
        """Verify all required commands are available."""
        import shutil

        missing = []
        for cmd in DependencyChecker.REQUIRED_COMMANDS:
            if not shutil.which(cmd):
                missing.append(cmd)

        if missing:
            logger.error("Missing required dependencies: %s", ", ".join(missing))
            logger.error("Install with: sudo pacman -S %s", " ".join(missing))
            return False

        return True


class LogAggregator:
    """Main orchestrator for log collection and webhook delivery."""

    def __init__(
        self,
        webhook_url: str,
        jwt_passphrase: str | None = None,
        lookback_minutes: int = 60,
    ):
        self.webhook_url = webhook_url
        self.jwt_passphrase = jwt_passphrase
        self.lookback_minutes = lookback_minutes
        self.collectors = [
            SystemKernelCollector(lookback_minutes),
            UserSessionCollector(lookback_minutes),
            DockerContainerCollector(lookback_minutes),
            PacmanLogCollector(lookback_minutes),
        ]

    def collect_all_logs(self) -> dict[str, list[dict[str, Any]]]:
        """Execute all collectors and aggregate results."""
        results: dict[str, list[dict[str, Any]]] = {
            "system_kernel": [],
            "user_session": [],
            "docker_containers": [],
            "pacman_updates": [],
        }

        collector_mapping = [
            (self.collectors[0], "system_kernel"),
            (self.collectors[1], "user_session"),
            (self.collectors[2], "docker_containers"),
            (self.collectors[3], "pacman_updates"),
        ]

        for collector, key in collector_mapping:
            try:
                logs = collector.collect()
                results[key] = logs
                logger.info("Collected %d entries from %s", len(logs), key)
            except Exception as e:
                logger.exception("Collector %s failed: %s", key, e)
                results[key] = [
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "message": f"Collector failed: {e}",
                        "error": True,
                    }
                ]

        return results

    def build_payload(self, logs: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        """Construct final JSON payload matching required schema."""
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "system_environment": "Arch-CachyOS",
            "logs": logs,
        }

    def run(self) -> int:
        """Execute full pipeline: collect → build → deliver."""
        logger.info(
            "Starting log collection (lookback: %d minutes)", self.lookback_minutes
        )

        logs = self.collect_all_logs()
        payload = self.build_payload(logs)

        total_entries = sum(len(v) for v in logs.values())
        logger.info("Total log entries collected: %d", total_entries)

        webhook = WebhookDelivery(self.webhook_url, self.jwt_passphrase)
        success = webhook.send(payload)

        if success:
            logger.info("Log delivery completed successfully")
            return 0
        else:
            logger.error("Log delivery failed")
            return 1


def main():
    """Entry point with dependency checks and environment validation."""
    webhook_url = os.getenv("N8N_WEBHOOK_URL")
    if not webhook_url:
        logger.error("N8N_WEBHOOK_URL environment variable not set")
        logger.error(
            "Set in /etc/system-monitoring/.env or via systemd EnvironmentFile"
        )
        sys.exit(1)

    if not DependencyChecker.check_all():
        sys.exit(1)

    jwt_passphrase = os.getenv("JWT_PASSPHRASE")
    lookback_minutes = int(os.getenv("LOOKBACK_MINUTES", "60"))

    aggregator = LogAggregator(webhook_url, jwt_passphrase, lookback_minutes)
    sys.exit(aggregator.run())


if __name__ == "__main__":
    main()
