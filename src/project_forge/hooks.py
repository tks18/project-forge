"""Git quality hooks installer, uninstaller, and status inspector."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

from project_forge.process import run_process


def _make_executable(target: Path) -> None:
    """Set executable permission on POSIX systems."""
    try:
        current_mode = os.stat(target).st_mode
        os.chmod(target, current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass


def generate_pre_commit_script(project_name: str) -> str:
    """Generate project-neutral pre-commit shell script."""
    return f"""#!/usr/bin/env sh
# {project_name} - Pre-Commit Quality Gate (Fast Tier)
# Managed by Project Forge (pforge)
echo "[Quality Gate] Running Pre-Commit Fast Verification..."

uv run pforge quality --fast
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[Quality Gate] [FAIL] Pre-commit checks failed."
    echo "[Quality Gate] Fix issues or run 'uv run pforge quality --fast --fix' to auto-fix formatting."
    exit $EXIT_CODE
fi

echo "[Quality Gate] [PASS] Pre-commit checks passed cleanly."
exit 0
"""


def generate_pre_push_script(project_name: str) -> str:
    """Generate project-neutral pre-push shell script."""
    return f"""#!/usr/bin/env sh
# {project_name} - Pre-Push Quality Gate (Full Tier)
# Managed by Project Forge (pforge)
echo "[Quality Gate] Running Pre-Push Full Verification Suite..."

uv run pforge quality
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[Quality Gate] [FAIL] Pre-push verification failed."
    echo "[Quality Gate] Push aborted. Ensure all quality checks pass before pushing."
    exit $EXIT_CODE
fi

echo "[Quality Gate] [PASS] Full verification suite passed cleanly. Proceeding with push."
exit 0
"""


def install_hooks(root_dir: Path | None = None) -> int:
    """Install git pre-commit and pre-push hooks.

    Configures Git's core.hooksPath to point to .githooks, and installs fallbacks into .git/hooks.

    Parameters
    ----------
    root_dir : Path | None, optional
        Project root directory, by default None.

    Returns
    -------
    int
        0 on success, 1 on failure.
    """
    if root_dir is None:
        from project_forge.project import find_project_root

        root_dir = find_project_root()

    from project_forge.project import read_project_metadata

    metadata = read_project_metadata(root_dir)
    project_name = metadata.get("name", root_dir.name)

    tracked_dir = root_dir / ".githooks"
    tracked_dir.mkdir(parents=True, exist_ok=True)

    pre_commit_content = generate_pre_commit_script(project_name)
    pre_push_content = generate_pre_push_script(project_name)

    # 1. Write tracked hooks
    tracked_pre_commit = tracked_dir / "pre-commit"
    tracked_pre_push = tracked_dir / "pre-push"

    tracked_pre_commit.write_text(pre_commit_content, encoding="utf-8", newline="\n")
    _make_executable(tracked_pre_commit)

    tracked_pre_push.write_text(pre_push_content, encoding="utf-8", newline="\n")
    _make_executable(tracked_pre_push)

    # 2. Configure git core.hooksPath
    git_dir = root_dir / ".git"
    if git_dir.exists():
        proc = run_process(["git", "config", "core.hooksPath", ".githooks"], cwd=root_dir)
        if not proc.passed:
            print(f"Warning: Failed to configure git core.hooksPath: {proc.stderr}")

        # 3. Fallback write directly to .git/hooks if folder exists
        git_hooks_dir = git_dir / "hooks"
        if git_hooks_dir.is_dir():
            git_pre_commit = git_hooks_dir / "pre-commit"
            git_pre_push = git_hooks_dir / "pre-push"
            git_pre_commit.write_text(pre_commit_content, encoding="utf-8", newline="\n")
            _make_executable(git_pre_commit)
            git_pre_push.write_text(pre_push_content, encoding="utf-8", newline="\n")
            _make_executable(git_pre_push)

    return 0


def uninstall_hooks(root_dir: Path | None = None) -> int:
    """Uninstall git hooks and reset git core.hooksPath.

    Parameters
    ----------
    root_dir : Path | None, optional
        Project root directory, by default None.

    Returns
    -------
    int
        0 on success.
    """
    if root_dir is None:
        from project_forge.project import find_project_root

        root_dir = find_project_root()

    # Reset core.hooksPath
    run_process(["git", "config", "--unset", "core.hooksPath"], cwd=root_dir)

    # Remove files from .githooks if present
    tracked_dir = root_dir / ".githooks"
    if tracked_dir.is_dir():
        for hook_file in tracked_dir.glob("*"):
            if hook_file.is_file():
                hook_file.unlink(missing_ok=True)

    return 0


def get_hooks_status(root_dir: Path | None = None) -> dict[str, Any]:
    """Inspect Git hooks installation and configuration state.

    Parameters
    ----------
    root_dir : Path | None, optional
        Project root directory, by default None.

    Returns
    -------
    dict[str, Any]
        Dictionary with hooks configuration status.
    """
    if root_dir is None:
        from project_forge.project import find_project_root

        root_dir = find_project_root()

    proc = run_process(["git", "config", "--get", "core.hooksPath"], cwd=root_dir)
    hooks_path = proc.stdout.strip() if proc.passed else ""

    tracked_dir = root_dir / ".githooks"
    pre_commit_tracked = (tracked_dir / "pre-commit").exists()
    pre_push_tracked = (tracked_dir / "pre-push").exists()

    git_hooks_dir = root_dir / ".git" / "hooks"
    pre_commit_git = (git_hooks_dir / "pre-commit").exists()
    pre_push_git = (git_hooks_dir / "pre-push").exists()

    installed = bool(hooks_path == ".githooks" and pre_commit_tracked and pre_push_tracked) or bool(
        pre_commit_git and pre_push_git
    )

    return {
        "installed": installed,
        "core_hooks_path": hooks_path or "(not set)",
        "tracked_pre_commit": pre_commit_tracked,
        "tracked_pre_push": pre_push_tracked,
        "git_hooks_pre_commit": pre_commit_git,
        "git_hooks_pre_push": pre_push_git,
    }
