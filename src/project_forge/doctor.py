"""Diagnostic environment inspector validating repository tooling and state."""

from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Console
from rich.table import Table

from project_forge.changelog import validate_changelog
from project_forge.config import load_config
from project_forge.hooks import get_hooks_status
from project_forge.process import run_process
from project_forge.project import find_project_root, get_git_branch, read_project_metadata

console = Console()


def run_doctor(root_dir: Path | None = None) -> int:
    """Perform read-only diagnostic checks across the repository and tools."""
    if root_dir is None:
        root_dir = find_project_root()

    cfg = load_config(root_dir)
    metadata = read_project_metadata(root_dir)

    table = Table(title="Project Forge Doctor Diagnostics", header_style="bold magenta")
    table.add_column("Category", style="cyan")
    table.add_column("Component", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Details")

    all_ok = True

    # 1. Project & Repository
    has_git = (root_dir / ".git").is_dir()
    table.add_row(
        "Repository",
        "Git Repository",
        "[bold green]PASS[/bold green]" if has_git else "[bold red]FAIL[/bold red]",
        f"Root: {root_dir}",
    )
    if not has_git:
        all_ok = False

    branch = get_git_branch(root_dir)
    table.add_row(
        "Repository",
        "Current Branch",
        "[bold green]PASS[/bold green]"
        if branch != "unknown"
        else "[bold yellow]WARN[/bold yellow]",
        branch,
    )

    pyproject_exists = (root_dir / "pyproject.toml").is_file()
    table.add_row(
        "Configuration",
        "pyproject.toml",
        "[bold green]PASS[/bold green]" if pyproject_exists else "[bold red]FAIL[/bold red]",
        f"{metadata.get('name')} v{metadata.get('version')}",
    )
    if not pyproject_exists:
        all_ok = False

    # Configured paths
    for p_str in cfg.source:
        exists = (root_dir / p_str).exists()
        table.add_row(
            "Configuration",
            f"Source path: {p_str}",
            "[bold green]PASS[/bold green]" if exists else "[bold red]FAIL[/bold red]",
            str((root_dir / p_str).resolve()),
        )
        if not exists:
            all_ok = False

    for p_str in cfg.tests:
        exists = (root_dir / p_str).exists()
        table.add_row(
            "Configuration",
            f"Test path: {p_str}",
            "[bold green]PASS[/bold green]" if exists else "[bold yellow]WARN[/bold yellow]",
            str((root_dir / p_str).resolve()),
        )

    # 2. External Executables
    tools_to_check = ["git", "uv", "gh", "ruff", "mypy", "pyright", "pytest"]
    for tool in tools_to_check:
        found = shutil.which(tool) is not None
        if not found:
            # Check if available via uv run
            proc = run_process(["uv", "run", tool, "--version"], cwd=root_dir)
            found = proc.passed

        status_str = "[bold green]PASS[/bold green]" if found else "[bold yellow]WARN[/bold yellow]"
        details_str = "Available" if found else "Not found in PATH or venv"
        table.add_row("External Tools", tool, status_str, details_str)

    # GitHub CLI Auth Check
    gh_auth = run_process(["gh", "auth", "status"], cwd=root_dir)
    table.add_row(
        "GitHub CLI",
        "gh auth status",
        "[bold green]PASS[/bold green]" if gh_auth.passed else "[bold yellow]WARN[/bold yellow]",
        "Authenticated" if gh_auth.passed else "Not logged in (run 'gh auth login')",
    )

    # Changelog check
    changelog_file = root_dir / cfg.changelog
    cl_valid, cl_errs = validate_changelog(changelog_file)
    table.add_row(
        "Changelog",
        cfg.changelog,
        "[bold green]PASS[/bold green]" if cl_valid else "[bold yellow]WARN[/bold yellow]",
        "Valid release format" if cl_valid else (cl_errs[0] if cl_errs else "Missing"),
    )

    # Hooks check
    hooks_status = get_hooks_status(root_dir)
    table.add_row(
        "Git Hooks",
        "Quality Hooks",
        "[bold green]PASS[/bold green]"
        if hooks_status["installed"]
        else "[bold yellow]WARN[/bold yellow]",
        f"core.hooksPath: {hooks_status['core_hooks_path']}",
    )

    console.print(table)
    return 0 if all_ok else 1
