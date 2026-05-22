"""Webhook delivery with retry logic and exponential backoff."""

import logging
import time
import warnings
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import requests

logger = logging.getLogger(__name__)


class WebhookDelivery:
    """HTTP POST delivery with retry logic for transient failures."""

    def __init__(
        self,
        webhook_url: str,
        jwt_passphrase: str | None = None,
        max_retries: int = 3,
        backoff_seconds: int = 10,
    ):
        self.webhook_url = webhook_url
        self.jwt_passphrase = jwt_passphrase
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def _generate_jwt_token(self) -> str:
        now = datetime.now(UTC)
        payload = {
            "iat": now,
            "exp": now + timedelta(minutes=5),
        }
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=jwt.InsecureKeyLengthWarning)
            return jwt.encode(payload, self.jwt_passphrase, algorithm="HS256")

    def send(self, payload: dict[str, Any]) -> bool:
        """Send JSON payload to webhook with exponential backoff retry."""
        headers = {"Content-Type": "application/json"}

        if self.jwt_passphrase:
            token = self._generate_jwt_token()
            headers["Authorization"] = f"Bearer {token}"

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    timeout=30,
                    headers=headers,
                )
                response.raise_for_status()
                logger.info(
                    "Webhook delivery successful (attempt %d/%d)",
                    attempt,
                    self.max_retries,
                )
                return True

            except requests.exceptions.RequestException as e:
                response_text = ""
                if hasattr(e, "response") and e.response is not None:
                    response_text = f" | Response Body: {e.response.text[:500]}"
                logger.warning(
                    "Webhook delivery failed (attempt %d/%d): %s%s",
                    attempt,
                    self.max_retries,
                    e,
                    response_text,
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
