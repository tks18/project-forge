"""Unit tests for Git hooks script generation and status."""

from pathlib import Path
from project_forge.hooks import (
    generate_pre_commit_script,
    generate_pre_push_script,
    get_hooks_status,
)


def test_generate_hooks_neutral_branding():
    """Verify generated hooks use provided project name and call pforge."""
    pre_commit = generate_pre_commit_script("My Project")
    assert "My Project" in pre_commit
    assert "uv run pforge quality --fast" in pre_commit
    assert "Personal Finance ETL" not in pre_commit

    pre_push = generate_pre_push_script("My Project")
    assert "My Project" in pre_push
    assert "uv run pforge quality" in pre_push
    assert "Personal Finance ETL" not in pre_push


def test_get_hooks_status_uninstalled(tmp_path: Path):
    """Verify status reports uninstalled on clean dir."""
    st = get_hooks_status(tmp_path)
    assert not st["installed"]
    assert not st["tracked_pre_commit"]
    assert not st["tracked_pre_push"]

