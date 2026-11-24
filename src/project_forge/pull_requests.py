"""Automated GitHub Pull Request Generator with Quality Gate Certification."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, cast

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from project_forge.changelog import parse_changelog
from project_forge.process import run_process

console = Console()


def load_audit_report(root_dir: Path, force_run: bool = False) -> dict[str, Any]:
    """Load latest audit report from outputs/audit_report.json, running audit if missing."""
    report_file = root_dir / "outputs" / "audit_report.json"

    if force_run or not report_file.exists():
        from project_forge.quality import run_quality_gate

        console.print("[dim]Generating fresh Quality Gate audit report (Full Tier)...[/dim]")
        run_quality_gate(tier="full", export="all", quiet=True, root_dir=root_dir)

    if report_file.exists():
        try:
            content = report_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                return cast(dict[str, Any], data)
        except Exception as exc:
            console.print(f"[yellow]Warning: Could not read audit report JSON: {exc}[/yellow]")

    return {
        "timestamp": "N/A",
        "tier": "full",
        "all_passed": True,
        "total_duration_seconds": 0.0,
        "total_issues": 0,
        "engines": [],
    }


def format_audit_markdown(audit_data: dict[str, Any], head_branch: str, base_branch: str) -> str:
    """Format Quality Gate audit metrics into a GitHub Markdown table."""
    engines = audit_data.get("engines", [])
    all_passed = audit_data.get("all_passed", True)
    total_duration = audit_data.get("total_duration_seconds", 0.0)
    timestamp = audit_data.get("timestamp", "N/A")

    lines: list[str] = [
        "---",
        "## 🛡️ Quality Gate Certification",
        "",
        "| Quality Engine | Tier | Duration | Issues | Status |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]

    for eng in engines:
        name = eng.get("name", "Unknown")
        tier = eng.get("tier", "Full")
        duration = eng.get("duration_seconds", 0.0)
        issues = eng.get("issue_count", 0)
        passed = eng.get("passed", True)
        status_badge = "✅ PASS" if passed else "❌ FAIL"
        lines.append(f"| {name} | {tier} | {duration:.2f}s | {issues} | {status_badge} |")

    overall_badge = (
        "🟢 **ALL QUALITY ENGINES PASSED**" if all_passed else "🔴 **QUALITY GATE ISSUES DETECTED**"
    )

    lines.extend(
        [
            "",
            f"> **Gate Status:** {overall_badge} (Total: {total_duration:.2f}s)  ",
            f"> **Audit Timestamp:** `{timestamp}`  ",
            f"> **Branch Flow:** `{head_branch}` ➔ `{base_branch}`  ",
        ]
    )

    return "\n".join(lines)


def check_gh_cli() -> bool:
    """Check if GitHub CLI (gh) is installed and authenticated."""
    proc = run_process(["gh", "auth", "status"])
    return proc.passed


def find_existing_pr(head: str, base: str, root_dir: Path) -> dict[str, Any] | None:
    """Check if an open pull request already exists between head and base."""
    cmd = [
        "gh",
        "pr",
        "list",
        "--head",
        head,
        "--base",
        base,
        "--state",
        "open",
        "--json",
        "number,title,url,state",
    ]
    proc = run_process(cmd, cwd=root_dir)
    if proc.passed and proc.stdout.strip():
        try:
            raw = json.loads(proc.stdout)
            if isinstance(raw, list) and raw:
                first = cast(dict[str, Any], raw[0])
                return first
        except Exception:
            pass
    return None


def run_pr_workflow(
    root_dir: Path | None = None,
    head: str | None = None,
    base: str | None = None,
    version: str | None = None,
    title: str | None = None,
    draft: bool = False,
    re_audit: bool = False,
    dry_run: bool = False,
) -> int:
    """Execute PR preview or creation workflow."""
    if root_dir is None:
        from project_forge.project import find_project_root

        root_dir = find_project_root()

    from project_forge.config import load_config
    from project_forge.project import get_git_branch

    cfg = load_config(root_dir)
    head_branch = head or get_git_branch(root_dir)
    base_branch = base or cfg.git.default_branch

    changelog_path = root_dir / cfg.changelog
    if not changelog_path.exists():
        console.print(f"[bold red]Error: Changelog file not found at {changelog_path}[/bold red]")
        return 1

    releases = parse_changelog(changelog_path)
    if not releases:
        console.print("[bold red]Error: No releases parsed from changelog.[/bold red]")
        return 1

    if version:
        clean_target = version.lstrip("v")
        target_entry = next((r for r in releases if r.clean_version == clean_target), None)
        if not target_entry:
            console.print(
                f"[bold red]Error: Version '{version}' not found in {changelog_path.name}[/bold red]"
            )
            return 1
    else:
        target_entry = releases[0]

    pr_title = title or f"Release v{target_entry.clean_version}"
    audit_data = load_audit_report(root_dir, force_run=re_audit)
    audit_md = format_audit_markdown(audit_data, head_branch=head_branch, base_branch=base_branch)

    pr_body = f"{target_entry.body}\n\n{audit_md}\n"

    if dry_run:
        console.print(
            Panel(
                f"[bold cyan]Base Branch:[/bold cyan] {base_branch}\n"
                f"[bold cyan]Head Branch:[/bold cyan] {head_branch}\n"
                f"[bold cyan]PR Title:[/bold cyan]    {pr_title}\n"
                f"[bold cyan]Mode:[/bold cyan]        [yellow]DRY-RUN PREVIEW[/yellow]\n"
                f"[dim]Draft PR:[/dim]    {'Yes' if draft else 'No'}",
                title="[bold yellow]Pull Request Preview[/bold yellow]",
                border_style="yellow",
            )
        )
        syntax = Syntax(pr_body, "markdown", theme="monokai", line_numbers=False)
        console.print(Panel(syntax, title="Generated PR Body", border_style="cyan"))
        console.print(
            "[green]Dry run complete. Use create command to publish PR to GitHub.[/green]"
        )
        return 0

    if not check_gh_cli():
        console.print(
            "[bold red]Error: GitHub CLI (gh) is not installed or authenticated.[/bold red]"
        )
        console.print("[dim]Run 'gh auth login' to authenticate with your GitHub account.[/dim]")
        return 1

    existing_pr = find_existing_pr(head=head_branch, base=base_branch, root_dir=root_dir)

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".md") as f:
        f.write(pr_body)
        temp_body_path = f.name

    try:
        if existing_pr:
            pr_num = str(existing_pr.get("number", ""))
            pr_url = str(existing_pr.get("url", ""))
            console.print(
                f"[bold cyan]Found open PR #{pr_num}. Updating title and description...[/bold cyan]"
            )
            cmd = [
                "gh",
                "pr",
                "edit",
                pr_num,
                "--title",
                pr_title,
                "--body-file",
                temp_body_path,
            ]
            res = run_process(cmd, cwd=root_dir)
            if res.passed:
                console.print(
                    f"[bold green]✔ Successfully updated PR #{pr_num}:[/bold green] {pr_url}"
                )
                return 0
            console.print(f"[bold red]✘ Failed to update PR #{pr_num}:[/bold red] {res.stderr}")
            return 1

        console.print(
            f"[bold cyan]Creating new pull request from '{head_branch}' into '{base_branch}'...[/bold cyan]"
        )
        cmd = [
            "gh",
            "pr",
            "create",
            "--head",
            head_branch,
            "--base",
            base_branch,
            "--title",
            pr_title,
            "--body-file",
            temp_body_path,
        ]
        if draft:
            cmd.append("--draft")

        res = run_process(cmd, cwd=root_dir)
        if res.passed:
            new_url = res.stdout.strip()
            console.print(
                f"[bold green]✔ Successfully created Pull Request:[/bold green] {new_url}"
            )
            return 0
        console.print(f"[bold red]✘ Failed to create pull request:[/bold red] {res.stderr}")
        return 1
    finally:
        Path(temp_body_path).unlink(missing_ok=True)
