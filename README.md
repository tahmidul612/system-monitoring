# System Monitoring — Arch Linux Log Aggregation

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Arch Linux](https://img.shields.io/badge/Arch_Linux-1793D1?style=for-the-badge&logo=arch-linux&logoColor=white)
![systemd](https://img.shields.io/badge/systemd-oneshot_timer-black?style=for-the-badge&logo=linux&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-supported-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![n8n](https://img.shields.io/badge/n8n-webhook_target-EA4B71?style=for-the-badge&logo=n8n&logoColor=white)

Automated log extraction tool that aggregates system, container, and package manager logs into a unified JSON payload for webhook delivery — runs hourly as a `systemd` oneshot timer.

</div>

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [JSON Payload Schema](#json-payload-schema)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Security & Fail-Safes](#security--fail-safes)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- 🖥️ **System & Kernel logs** — captures OOM kills, GPU faults, storage errors, Tailscale, and Docker daemon events via `journalctl --system`
- 👤 **User session logs** — collects Wayland compositor, PipeWire, and application crashes via `journalctl --user`
- 🐳 **Docker container logs** — concurrent per-container log tailing, filtered for errors, VRAM limits, and crashes
- 📦 **Pacman package manager logs** — stateful position tracking on `/var/log/pacman.log` to capture warnings, PGP issues, and ALPM script errors without duplicates
- 🔁 **Webhook delivery with retries** — exponential backoff (3 attempts, up to 70 seconds)
- ⚡ **Graceful degradation** — a failing collector never blocks the others or the webhook

---

## Architecture

**Target Environment:** Arch Linux (CachyOS) with systemd, journalctl, and Docker

**Execution model:** This is **not a daemon**. It runs once per hour via a `systemd` timer (`OnCalendar=hourly`), collects logs, POSTs to the configured webhook, and exits cleanly.

**Log Sources:**

| Source | Collector | Details |
|---|---|---|
| System / Kernel | `journalctl --system` | OOM kills, GPU faults, storage errors, Tailscale, Docker daemon |
| User Session | `journalctl --user` | Wayland compositor, PipeWire, app crashes |
| Docker Containers | `docker logs` | Ollama VRAM limits, Paperless OCR failures, proxy errors — concurrent via `ThreadPoolExecutor` |
| Package Manager | `/var/log/pacman.log` | `[ALPM-SCRIPTLET]` errors, warnings, PGP issues — stateful cursor tracking |

---

## Installation

### Prerequisites

```bash
# Install system dependencies
sudo pacman -S python-systemd docker

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Setup

**1. Clone and install dependencies:**

```bash
git clone <repository-url> /opt/system-monitoring
cd /opt/system-monitoring
uv sync
```

**2. Configure webhook URL:**

```bash
sudo mkdir -p /etc/system-monitoring
sudo cp config/.env.template /etc/system-monitoring/.env
sudo chmod 600 /etc/system-monitoring/.env
sudo nano /etc/system-monitoring/.env
```

Set your n8n webhook URL inside `.env`:

```ini
N8N_WEBHOOK_URL=https://your-n8n-instance.com/webhook/system-monitoring
LOOKBACK_MINUTES=60
```

**3. Create state directory:**

```bash
sudo mkdir -p /var/lib/system-monitoring
```

**4. Install and enable the systemd timer:**

```bash
sudo cp systemd/system-monitoring.service /etc/systemd/system/
sudo cp systemd/system-monitoring.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now system-monitoring.timer
```

---

## Quick Start

After completing installation, verify everything is working:

```bash
# Run a one-off collection immediately
export N8N_WEBHOOK_URL="https://your-n8n-instance.com/webhook/system-monitoring"
sudo uv run python main.py

# Check the timer is scheduled
systemctl list-timers system-monitoring.timer

# Inspect the last run's logs
journalctl -u system-monitoring.service -n 50
```

A successful run produces output like:

```
2026-05-21 22:00:01 system-monitoring[12345]: Collected 14 entries from system_kernel
2026-05-21 22:00:01 system-monitoring[12345]: Collected 3 entries from user_session
2026-05-21 22:00:01 system-monitoring[12345]: Collected 7 entries from docker_containers
2026-05-21 22:00:01 system-monitoring[12345]: Collected 0 entries from pacman_updates
2026-05-21 22:00:01 system-monitoring[12345]: Total log entries collected: 24
2026-05-21 22:00:01 system-monitoring[12345]: Log delivery completed successfully
```

---

## Usage

### Manual Execution

```bash
# Set webhook URL and run
export N8N_WEBHOOK_URL="https://your-n8n-instance.com/webhook/system-monitoring"
sudo uv run python main.py
```

### Automated via systemd Timer

```bash
# Check timer status and next trigger time
systemctl status system-monitoring.timer
systemctl list-timers system-monitoring.timer

# View logs from recent runs
journalctl -u system-monitoring.service -n 50

# Trigger a manual run outside the schedule
sudo systemctl start system-monitoring.service
```

---

## JSON Payload Schema

Every webhook POST delivers a payload with this fixed structure:

```json
{
  "timestamp": "2026-05-21T21:24:01Z",
  "system_environment": "Arch-CachyOS",
  "logs": {
    "system_kernel": [
      {
        "timestamp": "2026-05-21T20:30:15Z",
        "message": "oom-kill event ...",
        "priority": "warning",
        "unit": "tailscaled.service",
        "pid": 1234
      }
    ],
    "user_session": [
      {
        "timestamp": "2026-05-21T20:42:00Z",
        "message": "pipewire: failed to connect",
        "priority": "err",
        "unit": "pipewire.service",
        "pid": 5678
      }
    ],
    "docker_containers": [
      {
        "timestamp": "2026-05-21T20:45:22Z",
        "container_name": "ollama",
        "container_id": "abc123def456",
        "message": "VRAM allocation failed"
      }
    ],
    "pacman_updates": [
      {
        "timestamp": "2026-05-21T19:15:00Z",
        "level": "WARNING",
        "message": "...",
        "source": "pacman"
      }
    ]
  }
}
```

> ⚠️ **Do not rename the top-level keys** (`system_kernel`, `user_session`, `docker_containers`, `pacman_updates`) without updating your downstream n8n workflow.

---

## Configuration

All configuration is loaded from `/etc/system-monitoring/.env` (read as a systemd `EnvironmentFile`).

| Variable | Required | Default | Description |
|---|---|---|---|
| `N8N_WEBHOOK_URL` | ✅ Yes | — | Full URL of the n8n webhook endpoint |
| `LOOKBACK_MINUTES` | No | `60` | Time window (minutes) to query for each collector |

The service will exit immediately with an error if `N8N_WEBHOOK_URL` is not set.

---

## Project Structure

```
system-monitoring/
├── src/
│   ├── collectors/
│   │   ├── base.py                 # Abstract LogCollector base class
│   │   ├── system_kernel.py        # journalctl --system collector
│   │   ├── user_session.py         # journalctl --user collector
│   │   ├── docker_containers.py    # docker logs (concurrent, keyword-filtered)
│   │   └── pacman_log.py           # /var/log/pacman.log (stateful cursor)
│   ├── state_manager.py            # Atomic JSON state persistence
│   └── webhook.py                  # HTTP delivery with exponential backoff
├── main.py                         # Orchestrator: collect → build → deliver
├── systemd/
│   ├── system-monitoring.service   # oneshot service unit
│   └── system-monitoring.timer     # hourly execution timer
├── config/
│   └── .env.template               # Environment variable template
├── docs/
│   └── PRE_COMMIT_SETUP.md         # Pre-commit hooks guide
├── pyproject.toml                  # Project metadata and uv/dev dependencies
└── README.md
```

---

## Security & Fail-Safes

| Feature | Detail |
|---|---|
| 🔒 Read-only operations | All log queries are strictly non-destructive |
| 🛡️ Atomic state writes | Pacman cursor uses `tempfile → fsync → os.replace` to survive crashes |
| 🔄 Graceful degradation | Each collector runs independently; one failure doesn't stop others |
| 🔁 Webhook retries | 3 attempts with exponential backoff: 10s → 20s → 40s |
| ⏱️ Timeout protection | systemd enforces a 300-second execution limit |
| 🔑 Permission isolation | Runs as root for journal and Docker access (required by the APIs) |

---

## Troubleshooting

### Permission Denied on Journal

The service requires root or membership in the `systemd-journal` group:

```bash
sudo usermod -aG systemd-journal $USER
# Log out and back in for group membership to take effect
```

### Docker Daemon Unavailable

Check that Docker is running:

```bash
systemctl status docker
sudo systemctl start docker
```

When the Docker daemon is unreachable, the `docker_containers` key will contain a single error entry rather than crashing the run.

### State File Corruption

The state manager automatically falls back to the `.bak` file on corruption. Inspect both:

```bash
sudo cat /var/lib/system-monitoring/pacman_state.json
sudo cat /var/lib/system-monitoring/pacman_state.json.bak
```

To reset the cursor (will re-collect the full log on the next run):

```bash
sudo rm /var/lib/system-monitoring/pacman_state.json
sudo rm /var/lib/system-monitoring/pacman_state.json.bak
```

### Webhook Delivery Failure

Check for network connectivity issues and verify the URL in `/etc/system-monitoring/.env`. The service will log each retry attempt:

```bash
journalctl -u system-monitoring.service -n 100 --no-pager
```

---

## Development

### Environment Setup

```bash
git clone <repository-url>
cd system-monitoring
uv sync
```

### Running Tests

```bash
uv run pytest
```

### Linting and Formatting

```bash
# Lint with auto-fix
uv run ruff check --fix .

# Format
uv run ruff format .

# Type-check (slow — run separately)
pre-commit run --hook-stage manual mypy
```

### Pre-commit Hooks

```bash
# Install hooks
pre-commit install

# Run all hooks against all files
pre-commit run --all-files
```

See [`docs/PRE_COMMIT_SETUP.md`](docs/PRE_COMMIT_SETUP.md) for full details.

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow, coding standards, and the pull request process.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
