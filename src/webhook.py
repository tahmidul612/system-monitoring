"""Webhook delivery with retry logic and exponential backoff."""

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


class WebhookDelivery:
    """HTTP POST delivery with retry logic for transient failures."""

    def __init__(
        self, webhook_url: str, max_retries: int = 3, backoff_seconds: int = 10
    ):
        self.webhook_url = webhook_url
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def send(self, payload: dict[str, Any]) -> bool:
        """Send JSON payload to webhook with exponential backoff retry."""
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    timeout=30,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                logger.info(
                    "Webhook delivery successful (attempt %d/%d)",
                    attempt,
                    self.max_retries,
                )
                return True

            except requests.exceptions.RequestException as e:
                logger.warning(
                    "Webhook delivery failed (attempt %d/%d): %s",
                    attempt,
                    self.max_retries,
                    e,
                )
                if attempt < self.max_retries:
                    sleep_time = self.backoff_seconds * (2 ** (attempt - 1))
                    logger.info("Retrying in %d seconds...", sleep_time)
                    time.sleep(sleep_time)
                else:
                    logger.error(
                        "Webhook delivery failed after %d attempts", self.max_retries
                    )
                    return False

        return False
