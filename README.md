# System Monitoring - Arch Linux Log Aggregation

Automated log extraction tool that aggregates system, container, and package manager logs into a unified JSON payload for webhook delivery.

## Architecture

**Target Environment:** Arch Linux (CachyOS) with systemd, journalctl, and Docker

**Log Sources:**
- **System/Kernel**: `journalctl --system` (OOM kills, GPU faults, storage errors, Tailscale, Docker daemon)
- **User Session**: `journalctl --user` (Wayland compositor, PipeWire, app crashes)
- **Docker Containers**: `docker logs` (Ollama VRAM limits, Paperless OCR failures, proxy errors)
- **Package Manager**: `/var/log/pacman.log` ([ALPM-SCRIPTLET] errors, warnings, PGP issues)

## Installation

### Prerequisites

```bash
# Install system dependencies
sudo pacman -S python-systemd docker

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Setup

1. **Clone and install dependencies:**

```bash
git clone <repository-url> /opt/system-monitoring
cd /opt/system-monitoring
uv sync
```

2. **Configure webhook URL:**

```bash
sudo mkdir -p /etc/system-monitoring
sudo cp config/.env.template /etc/system-monitoring/.env
sudo chmod 600 /etc/system-monitoring/.env
sudo nano /etc/system-monitoring/.env
```

Edit `.env` and set your n8n webhook URL and JWT passphrase:
```
N8N_WEBHOOK_URL=https://your-n8n-instance.com/webhook/system-monitoring
JWT_PASSPHRASE=your-jwt-passphrase-here
LOOKBACK_MINUTES=60
```

**JWT Authentication Setup:**
- The JWT_PASSPHRASE must match the secret configured in your n8n JWT Auth account
- Uses HS256 algorithm with 5-minute token expiration
- Tokens are automatically generated and included in the `Authorization: Bearer` header
- If JWT_PASSPHRASE is not set, webhooks will be sent without authentication

3. **Create state directory:**

```bash
sudo mkdir -p /var/lib/system-monitoring
```

4. **Install systemd timer:**

```bash
sudo cp systemd/system-monitoring.service /etc/systemd/system/
sudo cp systemd/system-monitoring.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now system-monitoring.timer
```

## Usage

### Manual Execution

```bash
# Set webhook URL and JWT passphrase
export N8N_WEBHOOK_URL="https://your-n8n-instance.com/webhook/system-monitoring"
export JWT_PASSPHRASE="your-jwt-passphrase-here"

# Run extraction
sudo uv run python main.py
```

### Automated (via systemd timer)

```bash
# Check timer status
systemctl status system-monitoring.timer

# View recent runs
journalctl -u system-monitoring.service -n 50

# Trigger manual run (outside schedule)
sudo systemctl start system-monitoring.service
```

## JSON Payload Schema

```json
{
  "timestamp": "2026-05-21T21:24:01Z",
  "system_environment": "Arch-CachyOS",
  "logs": {
    "system_kernel": [
      {
        "timestamp": "2026-05-21T20:30:15Z",
        "message": "...",
        "priority": "warning",
        "unit": "tailscaled.service",
        "pid": 1234
      }
    ],
    "user_session": [...],
    "docker_containers": [
      {
        "timestamp": "2026-05-21T20:45:22Z",
        "container_name": "ollama",
        "container_id": "abc123",
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

## Project Structure

```
system-monitoring/
├── src/
│   ├── collectors/
│   │   ├── base.py                 # Abstract LogCollector base class
│   │   ├── system_kernel.py        # journalctl --system
│   │   ├── user_session.py         # journalctl --user
│   │   ├── docker_containers.py    # docker logs (concurrent)
│   │   └── pacman_log.py           # /var/log/pacman.log (stateful)
│   ├── state_manager.py            # Atomic JSON state persistence
│   └── webhook.py                  # HTTP delivery with retry logic
├── main.py                         # Main orchestrator
├── systemd/
│   ├── system-monitoring.service   # Systemd service unit
│   └── system-monitoring.timer     # Hourly execution timer
├── config/
│   └── .env.template               # Environment variable template
├── pyproject.toml                  # uv/Python dependencies
└── README.md
```

## Security & Fail-Safes

- **Read-only operations**: All log queries are strictly non-destructive
- **Atomic state writes**: Pacman log position tracking uses tempfile + fsync + os.replace
- **Graceful degradation**: Docker daemon unavailability doesn't crash the entire run
- **Webhook retries**: 3 attempts with exponential backoff (10s, 20s, 40s)
- **Timeout protection**: Systemd enforces 300-second execution limit
- **Permission isolation**: Runs as root for journal/Docker access (required)

## Troubleshooting

### Permission Denied on Journal

Ensure the service runs as root or user is in `systemd-journal` group:
```bash
sudo usermod -aG systemd-journal $USER
```

### Docker Daemon Unavailable

Check Docker service status:
```bash
systemctl status docker
```

### State File Corruption

State file includes `.bak` recovery:
```bash
sudo cat /var/lib/system-monitoring/pacman_state.json
sudo cat /var/lib/system-monitoring/pacman_state.json.bak
```

## Development

Run linters and tests:
```bash
uv run pytest
```
