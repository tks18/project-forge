# Project Forge (`pforge` / `pforge-cli`)

Repository-neutral engineering workflow CLI for quality gates, conventional commits, releases, and versioning.

## Overview

Project Forge standardizes common Python repository engineering workflows into a single standalone CLI without copying scripts from repository to repository:

- **Multi-engine Quality Gate**: Fast (<2s) and Full diagnostic checks across Ruff (lint & format), Mypy, Pyright, Pylint, and Pytest.
- **Native Standard-Version Replacement**: Pure Python SemVer bumper (`pforge bump`) calculating increments from Conventional Commits, updating project files, generating `CHANGELOG.md`, and tagging releases.
- **Conventional Commit Automation**: Grouped atomic commits with repository-neutral scope inference and interactive wizard (`pforge commit`).
- **Quality Hooks**: Project-neutral Git hooks (`pre-commit` and `pre-push`) calling `pforge quality`.
- **Changelog & GitHub Workflows**: Single-source changelog parsing, pull request creation with embedded quality tables, and GitHub release publication.
- **Publishing & Diagnostics**: Clean `uv build` and `uv publish` orchestration, and non-destructive `doctor` and `status` commands.

## Installation

```bash
# Using uv (recommended)
uv add --dev pforge-cli

# Using pip
pip install pforge-cli
```

## CLI Usage

### Diagnostics & Status
```bash
pforge status       # High-level dashboard snapshot of repository state
pforge doctor       # Diagnostic environment verification of tools and configs
```

### Quality Gate
```bash
pforge quality --fast       # Fast Tier (<2s): Ruff check, Ruff format check, Mypy
pforge quality --fast --fix # Auto-apply safe Ruff lint & format fixes
pforge quality              # Full Tier: Ruff, Mypy, Pyright, Pylint, Pytest
pforge quality --export all # Export structured audit reports to outputs/ (CSV & JSON)
```

### Version Bumping & Changelog
```bash
pforge bump --dry-run                 # Preview next version and changelog entry
pforge bump                           # Automatically detect bump type and update files
pforge bump --release-as minor        # Explicitly bump minor (or patch, major)
pforge bump --prerelease rc           # Bump with prerelease identifier
```

### Automated Conventional Commits
```bash
pforge commit --preview      # Preview grouped atomic conventional commits
pforge commit -i             # Interactive commit wizard with diff inspection
pforge commit --run          # Execute atomic commits immediately
```

### Git Quality Hooks
```bash
pforge hooks install        # Install pre-commit and pre-push quality hooks
pforge hooks status         # Check installation and core.hooksPath status
pforge hooks uninstall      # Clean hooks and unset core.hooksPath
```

### Pull Requests & Releases
```bash
pforge pr preview           # Preview PR title, notes, and Quality Gate table
pforge pr create            # Create/update PR on GitHub via gh CLI
pforge release preview      # Preview release notes for latest version
pforge release publish      # Publish release to GitHub via gh CLI
```

### PyPI Publishing
```bash
pforge publish --dry-run    # Verify quality, clean dist/, build with uv build
pforge publish              # Build packages and upload to PyPI using token
```

## Configuration (`pyproject.toml`)

Project Forge works with zero configuration for standard Python repositories. Custom settings can be optionally configured under `[tool.project-forge]`:

```toml
[tool.project-forge]
source = ["src"]
tests = ["tests"]
changelog = "CHANGELOG.md"

[tool.project-forge.git]
development_branch = "dev"
default_branch = "main"

[tool.project-forge.quality]
fast = ["ruff-check", "ruff-format", "mypy"]
full = ["ruff-check", "ruff-format", "mypy", "pyright", "pytest"]

[tool.project-forge.commits]
header_max_length = 72

[tool.project-forge.bump]
tag_prefix = "v"
files = ["pyproject.toml", "src/**/__init__.py"]

[tool.project-forge.docs]
require_module_docstrings = true
require_package_ownership = false
```

## Development & Testing

```bash
# Sync environment
uv sync

# Run test suite
uv run pytest tests/ -v

# Run linters and typecheckers
uv run ruff check .
uv run ruff format --check src/ tests/
uv run mypy src
uv run pyright
```

## License

GPL-3.0-or-later

