# Pre-commit Setup Guide

This project uses [pre-commit](https://pre-commit.com/) to automatically enforce code quality standards before commits.

## What's Configured

### Tools (Latest Versions as of May 2026)

- **pre-commit v4.6.0** - Hook framework
- **pre-commit-hooks v6.0.0** - Universal file checks (trailing whitespace, YAML/TOML syntax, etc.)
- **ruff v0.15.13** - Linting + formatting (replaces Black, flake8, isort, pyupgrade, autoflake)
- **mypy v2.1.0** - Type checking (manual stage only)

### What Runs on Every Commit

1. **File Sanity Checks**:
   - Remove trailing whitespace
   - Fix missing final newlines
   - Validate YAML/TOML/JSON syntax
   - Prevent large files (>500KB)
   - Detect merge conflicts
   - Detect private keys

2. **Python Linting** (ruff-check):
   - Code quality rules (Pyflakes, pycodestyle)
   - Import sorting (replaces isort)
   - Syntax modernization (replaces pyupgrade)
   - Bug detection (flake8-bugbear)
   - Auto-fixes applied automatically

3. **Python Formatting** (ruff-format):
   - Consistent code style (replaces Black)
   - Double quotes enforced
   - 88 character line length

### What Runs Manually (Slow Checks)

- **mypy** - Type checking (run with `pre-commit run --hook-stage manual mypy`)

## Installation

### 1. Install pre-commit and dependencies

```bash
# Using uv (recommended for this project)
uv sync

# Or using pip
pip install pre-commit ruff mypy
```

### 2. Install the git hooks

```bash
pre-commit install
```

This creates the git pre-commit hook at `.git/hooks/pre-commit`.

### 3. Run on all files (first time)

```bash
pre-commit run --all-files
```

This will format all Python files and fix any issues. Review and commit the changes.

## Usage

### Automatic (Default)

Pre-commit hooks run automatically when you `git commit`. If any hook fails:

1. The commit is blocked
2. Auto-fixes are applied (for ruff)
3. Review the changes: `git diff`
4. Stage the fixes: `git add .`
5. Commit again: `git commit`

### Manual Execution

```bash
# Run all hooks on staged files
pre-commit run

# Run all hooks on all files
pre-commit run --all-files

# Run specific hook
pre-commit run ruff-check
pre-commit run ruff-format

# Run type checking (manual stage)
pre-commit run --hook-stage manual mypy

# Skip hooks for emergency commits (use sparingly!)
git commit --no-verify -m "Emergency fix"
```

### Update Hook Versions

```bash
# Update to latest versions
pre-commit autoupdate

# Review changes
git diff .pre-commit-config.yaml

# Commit the updates
git add .pre-commit-config.yaml
git commit -m "chore: update pre-commit hooks"
```

## Configuration

### Ruff Configuration (`pyproject.toml`)

```toml
[tool.ruff]
target-version = "py311"
line-length = 88

[tool.ruff.lint]
select = [
    "E4", "E7", "E9", "F",  # Default: pycodestyle + Pyflakes
    "I",     # isort
    "UP",    # pyupgrade
    "B",     # flake8-bugbear
    "SIM",   # flake8-simplify
    "C4",    # flake8-comprehensions
    "N",     # pep8-naming
    "ARG",   # flake8-unused-arguments
    "RUF",   # Ruff-specific rules
]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["ARG001", "ARG002"]  # Allow unused args in tests
```

### Mypy Configuration (`pyproject.toml`)

```toml
[tool.mypy]
python_version = "3.11"
warn_unused_ignores = true
ignore_missing_imports = true
strict_optional = true
warn_redundant_casts = true
```

## Troubleshooting

### Hook Fails with "executable not found"

Reinstall pre-commit environments:
```bash
pre-commit clean
pre-commit install-hooks
```

### Ruff Conflicts with Existing Code Style

The ruff configuration in `pyproject.toml` matches your existing code style (88 chars, double quotes). If you see unexpected changes, review the ruff rules in `[tool.ruff.lint]`.

### Mypy Fails with Missing Type Stubs

Add type stubs to `additional_dependencies` in `.pre-commit-config.yaml`:
```yaml
- id: mypy
  additional_dependencies:
    - types-requests  # Already included
    - types-other-package
```

### Pre-commit is Slow

Mypy is intentionally in the `manual` stage to avoid slowing down commits. Run it separately:
```bash
pre-commit run --hook-stage manual mypy
```

Or integrate it into CI instead of local commits.

## CI Integration

If using GitHub Actions, add this workflow:

```yaml
name: Pre-commit

on: [push, pull_request]

jobs:
  pre-commit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - uses: pre-commit/action@v3.0.1
```

## Uninstallation

```bash
# Remove git hooks
pre-commit uninstall

# Remove pre-commit cache
pre-commit clean
```

## References

- [pre-commit documentation](https://pre-commit.com/)
- [ruff documentation](https://docs.astral.sh/ruff/)
- [mypy documentation](https://mypy.readthedocs.io/)
