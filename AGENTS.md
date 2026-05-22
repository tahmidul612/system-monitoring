This file provides guidance to AI coding agents like Claude Code (claude.ai/code), Cursor AI, Codex, Gemini CLI, GitHub Copilot, and other AI coding assistants when working with code in this repository.

# System Monitoring - Arch Linux Log Aggregation

## Development Commands

```bash
# Install dependencies
uv sync

# Run manually (requires systemd, docker, /var/log/pacman.log)
export N8N_WEBHOOK_URL="https://your-webhook-url"
sudo uv run python main.py

# Syntax check all Python files
python3 -m py_compile main.py src/**/*.py

# Test systemd service (dry run without webhook)
sudo systemctl start system-monitoring.service
journalctl -u system-monitoring.service -n 50

# View timer status
systemctl status system-monitoring.timer
systemctl list-timers system-monitoring.timer
```

## Architecture Overview

**Single Execution Model**: This is NOT a daemon. It runs once per hour via systemd timer, collects logs, POSTs to webhook, and exits.

**Four Log Sources**:
1. **System/Kernel** → `journalctl --system` (systemd.journal.Reader)
2. **User Session** → `journalctl --user` (systemd.journal.Reader)
3. **Docker Containers** → `docker logs` (docker SDK, concurrent via ThreadPoolExecutor)
4. **Pacman** → `/var/log/pacman.log` (file parsing with stateful position tracking)

**Graceful Degradation Flow** (main.py:81-92):
- Each collector runs independently in main orchestrator
- Collector failure → converted to error log entry in payload
- One collector crash → others continue, webhook still fires
- **Never throw exceptions from `collect()`** - catch internally and return error entry

## Critical Patterns

### 1. Atomic State Writes (StateManager)

**WHY**: Pacman log position must survive crashes. Corrupted state = duplicate or missing logs.

**HOW** (state_manager.py:49-72):
```python
# Atomic write sequence:
1. Copy current file to .bak
2. Write to tempfile in same directory
3. fsync() to force disk write
4. os.replace() for atomic rename (POSIX guarantees)
```

**Recovery**: Load attempts `main → .bak → empty dict` fallback (lines 21-43).

**When Extending**:
- **DO**: Use StateManager for any persistent state (cursor positions, timestamps)
- **DON'T**: Write directly to state files - breaks atomicity guarantee

### 2. Collector Error Handling

**Pattern**: All collectors inherit from `LogCollector` (base.py) and follow:
```python
def collect(self) -> List[Dict[str, Any]]:
    try:
        # Query log source
        # Filter by time window (self.lookback_minutes)
        # Return list of log dictionaries
    except (OSError, RuntimeError) as e:
        # Convert to error entry - DON'T raise
        return [self._format_entry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            message=f"Collection failed: {e}",
            error=True
        )]
```

**Multi-Level Error Handling** (DockerContainerCollector):
1. **Connection errors** → return daemon unavailable entry
2. **API errors** → return API failure entry
3. **Per-container errors** → log warning, continue with others (ThreadPoolExecutor isolates failures)

### 3. Webhook Retry Logic

**Exponential Backoff** (webhook.py:41):
```python
sleep_time = backoff_seconds * (2 ** (attempt - 1))
# Default backoff_seconds=10 → delays: 10s, 20s, 40s
```

**Total: 3 attempts, max 70s wait, then fail.**

**When Modifying**:
- Timeout per request: 30s (line 26)
- Max retries: 3 (init default)
- Backoff base: 10s (init default)

### 4. Environment Configuration

**Load Order** (main.py:125-139):
1. Systemd reads `/etc/system-monitoring/.env` (EnvironmentFile)
2. main.py reads `N8N_WEBHOOK_URL` (required) and `LOOKBACK_MINUTES` (default: 60)
3. Fails fast if `N8N_WEBHOOK_URL` missing

**Adding New Config**:
1. Add to `config/.env.template`
2. Read in `main()` with `os.getenv()`
3. Document in README.md installation section

### 5. Systemd Integration

**Service**: `Type=oneshot` - runs to completion, exits, no daemon.
**Dynamic executable discovery**: Resolves the path to the `uv` executable dynamically (checking `PATH`, `/usr/bin/uv`, and `/home/*/.local/bin/uv` or `/root/.local/bin/uv`) so that it works seamlessly with both global and local user installations of `uv`.
**Timer**: `OnCalendar=hourly` + `RandomizedDelaySec=5m` (prevent thundering herd)
**Execution Limit**: `TimeoutStartSec=300` (5 minutes max)

**Why oneshot**:
- No daemon overhead between hourly runs
- Clean resource release after each execution
- Journal logs each run separately

## JSON Payload Schema

**Fixed structure** (main.py:98-113):
```json
{
  "timestamp": "ISO8601 UTC",
  "system_environment": "Arch-CachyOS",
  "logs": {
    "system_kernel": [...],
    "user_session": [...],
    "docker_containers": [...],
    "pacman_updates": [...]
  }
}
```

**DO NOT change** these key names without updating downstream n8n workflow.

## Adding New Collectors

1. Inherit from `LogCollector` (src/collectors/base.py)
2. Implement `collect() -> List[Dict[str, Any]]`
3. Use `self.lookback_minutes` for time filtering
4. Catch exceptions internally - return error entries, don't raise
5. Add to `main.py`:
   - Import in line 14-19 block
   - Instantiate in `LogAggregator.__init__` (line 58-63)
   - Map to payload key in `run()` (line 79-80)
6. Update `config/.env.template` if new config needed
7. Document in README.md architecture section

## Testing Checklist

Before committing collector changes:
1. Run `python3 -m py_compile` on modified files
2. Test with real logs: `sudo uv run python main.py`
3. Verify JSON schema unchanged (unless intentional)
4. Check logs: `journalctl -u system-monitoring.service -n 50`
5. Confirm no secrets in logs or code

## Common Gotchas

**StateManager paths**:
- Default: `/var/lib/system-monitoring/pacman_state.json`
- Directory must exist (created in README installation step 3)
- Requires write permissions (service runs as root)

**Docker SDK**:
- Requires `docker` command available (`shutil.which("docker")`)
- ThreadPoolExecutor with 10 workers, 60s timeout per container
- Container logs filtered by keywords: error, fail, crash, timeout, vram, killed

**Systemd journal**:
- `SystemKernelCollector` requires root or `systemd-journal` group
- Uses `journal.Reader` native API, not subprocess
- Filter: `LOG_WARNING` priority (skips INFO/DEBUG)

**Time zones**:
- All timestamps in UTC (datetime.now(timezone.utc))
- systemd journal timestamps auto-converted to UTC
- Pacman log timestamps parsed with timezone awareness

## File Locations

**Critical paths** (hardcoded):
- State file: `/var/lib/system-monitoring/pacman_state.json`
- Pacman log: `/var/log/pacman.log`
- Environment: `/etc/system-monitoring/.env` (systemd EnvironmentFile)
- Installation: `/opt/system-monitoring` (assumed in service ExecStart)

**Change these in**:
- `src/collectors/pacman_log.py` (state and log paths)
- `systemd/system-monitoring.service` (env file, install path, ExecStart)
