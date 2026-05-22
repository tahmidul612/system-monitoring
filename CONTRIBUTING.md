# Contributing to System Monitoring

Thank you for your interest in contributing! This document covers everything you need to set up a development environment, follow project conventions, and submit changes.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Repository Structure](#repository-structure)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Adding a New Collector](#adding-a-new-collector)
- [Testing](#testing)
- [Commit Message Conventions](#commit-message-conventions)
- [Pull Request Process](#pull-request-process)
- [Getting Help](#getting-help)

---

## Getting Started

### Prerequisites

- Arch Linux (or compatible) with `systemd`, `journalctl`, and `docker`
- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) package manager

### Setup

```bash
# Clone the repository
git clone https://github.com/tahmidul612/system-monitoring.git
cd system-monitoring

# Install all dependencies (including dev extras)
uv sync

# Install pre-commit hooks
pre-commit install
```

Verify the hooks are wired up correctly:

```bash
pre-commit run --all-files
```

---

## Repository Structure

```
system-monitoring/
├── src/
│   ├── collectors/
│   │   ├── base.py                 # Abstract LogCollector base class
│   │   ├── system_kernel.py        # journalctl --system collector
│   │   ├── user_session.py         # journalctl --user collector
│   │   ├── docker_containers.py    # docker logs (concurrent)
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
│   └── PRE_COMMIT_SETUP.md         # Pre-commit hooks reference
└── pyproject.toml                  # Project metadata, dependencies, tool config
```

---

## Development Workflow

### Running Locally

```bash
# One-off run (requires N8N_WEBHOOK_URL and root/journal group)
export N8N_WEBHOOK_URL="https://your-n8n-instance.com/webhook/system-monitoring"
sudo uv run python main.py
```

### Syntax Check

```bash
python3 -m py_compile main.py
python3 -m py_compile src/collectors/*.py src/state_manager.py src/webhook.py
```

### Linting and Formatting

```bash
# Lint (with auto-fix)
uv run ruff check --fix .

# Format
uv run ruff format .

# Type-check (slow — run manually or in CI)
pre-commit run --hook-stage manual mypy
```

All of these run automatically on `git commit` via the pre-commit hooks. See [`docs/PRE_COMMIT_SETUP.md`](docs/PRE_COMMIT_SETUP.md) for details.

---

## Coding Standards

- **Python 3.11+** — use modern syntax (`match`, `|` union types, `datetime.UTC`)
- **Ruff** enforces formatting (88-char lines, double quotes) and linting rules — do not bypass it
- **Type hints** are encouraged for all public functions and collector `collect()` methods
- **No secrets in code** — configuration is loaded from environment variables only
- **UTC timestamps everywhere** — use `datetime.now(UTC).isoformat()` consistently
- **Collector contract** — `collect()` must never raise; catch internally and return an error entry

---

## Adding a New Collector

Follow these steps to add a new log source:

1. **Create the collector** in `src/collectors/your_source.py`:

```python
from datetime import UTC, datetime
from typing import Any

from .base import LogCollector


class YourSourceCollector(LogCollector):
    def collect(self) -> list[dict[str, Any]]:
        try:
            # Query your log source using self.lookback_minutes
            # Return a list of log dictionaries
            return [...]
        except Exception as e:
            return [self._format_entry(
                timestamp=datetime.now(UTC).isoformat(),
                message=f"Collection failed: {e}",
                error=True,
            )]
```

2. **Export it** from `src/collectors/__init__.py`.

3. **Register it** in `main.py`:
   - Import in the collector import block
   - Instantiate in `LogAggregator.__init__`
   - Add a mapping entry in `collect_all_logs()`
   - Add the key to the `results` dict

4. **Update configuration** — if the collector needs a new env variable, add it to `config/.env.template` and document it in `README.md`.

5. **Syntax-check and test** your new file:

```bash
python3 -m py_compile src/collectors/your_source.py
uv run pytest
```

---

## Testing

```bash
# Run the test suite
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing
```

When adding a collector or changing existing logic, include tests that:

- Cover the normal (happy-path) return structure
- Verify the error-entry fallback when the source is unavailable
- Check that no exceptions escape `collect()`

---

## Commit Message Conventions

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]
```

Common types:

| Type | When to use |
|---|---|
| `feat` | New feature or collector |
| `fix` | Bug fix |
| `docs` | Documentation changes only |
| `refactor` | Code change that is not a fix or feature |
| `test` | Adding or updating tests |
| `chore` | Tooling, deps, CI changes |

Examples:

```
feat(collectors): add GPU metrics collector via sysfs
fix(pacman): handle missing state file on first run
docs: add troubleshooting section to README
chore: update pre-commit hooks to latest versions
```

---

## Pull Request Process

1. **Fork** the repository and create a branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Make your changes** following the standards above.

3. **Run checks locally** before pushing:
   ```bash
   pre-commit run --all-files
   uv run pytest
   ```

4. **Open a pull request** against `main` with:
   - A clear title following the commit convention
   - A description of *what* changed and *why*
   - Reference to any related issue (`Closes #123`)

5. **Code review** — at least one approval is required before merging.

### What Makes a Good First Issue

Look for issues labelled `good first issue`. These typically involve:

- Adding a new keyword filter to an existing collector
- Improving log entry formatting
- Expanding test coverage
- Documentation improvements

---

## Getting Help

- Open a [GitHub Issue](https://github.com/tahmidul612/system-monitoring/issues) for bugs or feature requests
- Check existing issues and the [README](README.md) troubleshooting section before filing a new one
