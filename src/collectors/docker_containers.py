"""DockerContainerCollector - Extract logs from running Docker containers."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import docker
from docker.errors import DockerException, APIError
from requests.exceptions import ConnectionError, Timeout

from .base import LogCollector

logger = logging.getLogger(__name__)


class DockerContainerCollector(LogCollector):
    """Collect logs from all running Docker containers.
    
    Iterates through running containers and extracts logs with time filtering.
    Uses ThreadPoolExecutor for concurrent log fetching.
    Target events: Ollama VRAM limits, Paperless OCR failures,
    reverse proxy 502s, Redis disconnects.
    """

    def __init__(self, lookback_minutes: int = 60, max_workers: int = 10, docker_timeout: int = 60):
        super().__init__(lookback_minutes)
        self.max_workers = max_workers
        self.docker_timeout = docker_timeout

    def collect(self) -> List[Dict[str, Any]]:
        """Collect logs from all running Docker containers."""
        since_dt = datetime.now(timezone.utc) - timedelta(minutes=self.lookback_minutes)
        results = []

        try:
            client = self._connect()
        except RuntimeError as e:
            logger.error("Docker daemon unavailable: %s", e)
            return [self._format_entry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                container_name="docker_daemon",
                message=str(e),
                error=True,
            )]

        try:
            containers = client.containers.list(
                filters={"status": "running"},
                sparse=True,
                ignore_removed=True,
            )
        except APIError as e:
            logger.error("Failed to list containers: %s", e)
            return [self._format_entry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                container_name="docker_api",
                message=f"Failed to list containers: {e}",
                error=True,
            )]

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self._get_container_logs, c, since_dt): c
                for c in containers
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        results.extend(result)
                except Exception as e:
                    logger.warning("Container log fetch failed: %s", e)

        return results

    def _connect(self) -> docker.DockerClient:
        """Connect to Docker daemon with health check."""
        try:
            client = docker.from_env(timeout=self.docker_timeout)
            client.ping()
            return client
        except (DockerException, ConnectionError, Timeout) as e:
            raise RuntimeError(f"Docker daemon unavailable: {e}") from e

    def _get_container_logs(self, container, since_dt: datetime) -> List[Dict[str, Any]]:
        """Fetch and filter logs for a single container."""
        try:
            raw_logs = container.logs(
                since=since_dt,
                timestamps=True,
                stdout=True,
                stderr=True,
            )
            decoded = raw_logs.decode("utf-8", errors="replace")
            
            filtered_lines = self._filter_error_warning_lines(decoded)
            
            return [
                self._format_entry(
                    timestamp=self._extract_timestamp(line),
                    container_name=container.name,
                    container_id=container.short_id,
                    message=self._strip_timestamp(line),
                )
                for line in filtered_lines
            ]

        except APIError as e:
            logger.error("API error for container %s: %s", container.name, e)
            return [self._format_entry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                container_name=container.name,
                message=f"API error: {e}",
                error=True,
            )]
        except ConnectionError:
            logger.error("Docker connection lost for container %s", container.name)
            return [self._format_entry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                container_name=container.name,
                message="Docker connection lost",
                error=True,
            )]

    @staticmethod
    def _filter_error_warning_lines(log_text: str) -> List[str]:
        """Filter log lines containing error/warning keywords."""
        keywords = ["error", "warn", "fail", "timeout", "exception", "fatal", "critical"]
        lines = log_text.strip().splitlines()
        return [
            line for line in lines
            if any(keyword in line.lower() for keyword in keywords)
        ]

    @staticmethod
    def _extract_timestamp(line: str) -> str:
        """Extract ISO timestamp from Docker log line if present."""
        if line and len(line) > 30 and line[0].isdigit():
            timestamp_part = line.split()[0]
            try:
                dt = datetime.fromisoformat(timestamp_part.replace("Z", "+00:00"))
                return dt.isoformat()
            except ValueError:
                pass
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _strip_timestamp(line: str) -> str:
        """Remove timestamp prefix from Docker log line."""
        parts = line.split(maxsplit=1)
        return parts[1] if len(parts) > 1 else line
