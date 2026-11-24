"""Fast project status dashboard display."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from project_forge.changelog import get_latest_release
from project_forge.config import load_config
from project_forge.hooks import get_hooks_status
from project_forge.process import run_process
from project_forge.project import (
    find_project_root,
    get_dirty_files,
    get_git_branch,
    read_project_metadata,
)

console = Console()


def show_status(root_dir: Path | None = None) -> int:
    """Print a clean dashboard overview of repository status."""
    if root_dir is None:
        root_dir = find_project_root()

    cfg = load_config(root_dir)
    metadata = read_project_metadata(root_dir)
    branch = get_git_branch(root_dir)
    dirty = get_dirty_files(root_dir)
    hooks = get_hooks_status(root_dir)
    latest_rel = get_latest_release(root_dir / cfg.changelog)

    gh_res = run_process(["gh", "auth", "status"], cwd=root_dir)
    gh_status = (
        "[green]Authenticated[/green]"
        if gh_res.passed
        else "[yellow]Unauthenticated/Missing[/yellow]"
    )

    table = Table(title="Project Forge Status", show_header=True, header_style="bold magenta")
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("Project Name", metadata.get("name", root_dir.name))
    table.add_row("Project Version", f"[bold green]{metadata.get('version')}[/bold green]")
    table.add_row("Repository Root", str(root_dir))
    table.add_row("Git Branch", f"[cyan]{branch}[/cyan]")
    dirty_color = "green" if len(dirty) == 0 else "yellow"
    table.add_row("Working Tree", f"[{dirty_color}]{len(dirty)} dirty files[/{dirty_color}]")
    table.add_row("Quality Fast Tier", ", ".join(cfg.quality.fast))
    table.add_row("Quality Full Tier", ", ".join(cfg.quality.full))
    hooks_color = "green" if hooks["installed"] else "yellow"
    table.add_row(
        "Git Hooks",
        f"[{hooks_color}]{'Installed' if hooks['installed'] else 'Not Installed'}[/{hooks_color}]",
    )
    table.add_row("GitHub CLI", gh_status)
    latest_ver_str = latest_rel.version if latest_rel else "(none)"
    table.add_row("Changelog Latest", f"[bold cyan]{latest_ver_str}[/bold cyan]")

    console.print(table)
    return 0
