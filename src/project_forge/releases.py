"""GitHub Release preview and publication manager."""

from __future__ import annotations

import tempfile
from pathlib import Path

from rich.console import Console

from project_forge.changelog import ReleaseNotes, parse_changelog, resolve_git_tag
from project_forge.process import run_process

console = Console()


def print_release_preview(tag: str, title: str, body: str, index: int, total: int) -> None:
    """Print formatted release preview to terminal."""
    separator = "=" * 80
    console.print(f"\n{separator}")
    console.print(f"[{index}/{total}] PREVIEW: {tag}")
    console.print(separator)
    console.print(f"• Target Git Tag   : [cyan]{tag}[/cyan]")
    console.print(f"• Release Title    : [bold]{title}[/bold]")
    console.print("• Release Content  :\n")
    console.print(body)
    console.print(f"{separator}\n")


def publish_github_release(
    root_dir: Path,
    tag: str,
    title: str,
    body: str,
    is_draft: bool = False,
) -> bool:
    """Publish a release to GitHub using gh CLI."""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".md") as f:
        f.write(body)
        temp_notes = f.name

    cmd = [
        "gh",
        "release",
        "create",
        tag,
        "--title",
        title,
        "--notes-file",
        temp_notes,
    ]
    if is_draft:
        cmd.append("--draft")

    try:
        res = run_process(cmd, cwd=root_dir)
        if res.passed:
            console.print(
                f"[bold green]✔ Successfully released {tag}{' (as draft)' if is_draft else ''}[/bold green]"
            )
            return True
        console.print(f"[bold red]✘ Failed to create release for {tag}:[/bold red] {res.stderr}")
        return False
    finally:
        Path(temp_notes).unlink(missing_ok=True)


def run_release_workflow(
    root_dir: Path | None = None,
    publish: bool = False,
    latest: bool = False,
    single_version: str | None = None,
    draft: bool = False,
    preview_all: bool = False,
    interactive: bool = False,
) -> int:
    """Execute GitHub release preview or publishing workflow."""
    if root_dir is None:
        from project_forge.project import find_project_root

        root_dir = find_project_root()

    from project_forge.config import load_config
    from project_forge.project import get_git_tags

    cfg = load_config(root_dir)
    changelog_path = root_dir / cfg.changelog

    if not changelog_path.exists():
        console.print(f"[bold red]Error: Changelog not found at {changelog_path}[/bold red]")
        return 1

    releases = parse_changelog(changelog_path)
    if not releases:
        console.print("[bold red]Error: No releases parsed from changelog.[/bold red]")
        return 1

    existing_tags = get_git_tags(root_dir)

    # 1. Preview All
    if preview_all:
        for idx, rel in enumerate(releases, 1):
            tag = resolve_git_tag(rel.version, existing_tags) or f"{rel.version} (TAG NOT IN GIT)"
            print_release_preview(tag, rel.title, rel.body, idx, len(releases))
        return 0

    # 2. Preview Latest / Single
    if not publish:
        target_entry = releases[0]
        if single_version:
            clean_ver = single_version.lstrip("v")
            found = next((r for r in releases if r.clean_version == clean_ver), None)
            if not found:
                console.print(
                    f"[bold red]Error: Version '{single_version}' not found in changelog.[/bold red]"
                )
                return 1
            target_entry = found

        tag = (
            resolve_git_tag(target_entry.version, existing_tags)
            or f"{target_entry.version} (TAG NOT IN GIT)"
        )
        print_release_preview(tag, target_entry.title, target_entry.body, 1, 1)
        console.print("[dim]Use 'pforge release publish' to publish this release to GitHub.[/dim]")
        return 0

    # 3. Target determination for publishing
    target_releases = releases
    if latest:
        target_releases = [releases[0]]
    elif single_version:
        clean_ver = single_version.lstrip("v")
        target_releases = [r for r in releases if r.clean_version == clean_ver]
        if not target_releases:
            console.print(
                f"[bold red]Error: Version '{single_version}' not found in changelog.[/bold red]"
            )
            return 1

    valid_releases: list[tuple[str, ReleaseNotes]] = []
    for rel in target_releases:
        matched_tag = resolve_git_tag(rel.version, existing_tags)
        if matched_tag is not None:
            valid_releases.append((matched_tag, rel))
        else:
            console.print(
                f"[yellow]Warning: Git tag for version '{rel.version}' not found. Skipping.[/yellow]"
            )

    if not valid_releases:
        console.print("[yellow]No matching Git tags found to release.[/yellow]")
        return 0

    # Publication Execution
    for idx, (tag, rel_item) in enumerate(valid_releases, 1):
        if interactive:
            print_release_preview(tag, rel_item.title, rel_item.body, idx, len(valid_releases))
            choice = input(f"Publish release for tag '{tag}'? [y/n/q/all]: ").strip().lower()
            if choice == "q":
                break
            if choice == "n":
                continue
            if choice == "all":
                interactive = False

        console.print(
            f"Publishing release [{idx}/{len(valid_releases)}] -> Tag '{tag}', Title '{rel_item.title}'..."
        )
        ok = publish_github_release(root_dir, tag, rel_item.title, rel_item.body, is_draft=draft)
        if not ok:
            return 1

    return 0


def run_release_pipeline(
    root_dir: Path | None = None,
    push: bool = True,
    create_pr: bool = True,
    draft_release: bool = True,
) -> int:
    """Execute complete post-tag release pipeline: git push -> create PR -> draft release.

    Parameters
    ----------
    root_dir : Path | None, optional
        Project root directory.
    push : bool, optional
        Whether to push branch and follow-tags, by default True.
    create_pr : bool, optional
        Whether to create/update pull request, by default True.
    draft_release : bool, optional
        Whether to draft GitHub release, by default True.

    Returns
    -------
    int
        0 on success, non-zero on failure.
    """
    if root_dir is None:
        from project_forge.project import find_project_root

        root_dir = find_project_root()

    from project_forge.config import load_config
    from project_forge.pull_requests import run_pr_workflow

    cfg = load_config(root_dir)
    dev_branch = cfg.git.development_branch
    base_branch = cfg.git.default_branch

    console.print("\n[bold cyan]═════ Starting Automated Post-Release Pipeline ═════[/bold cyan]\n")

    # Step 1: Push commits and tags to remote
    if push:
        console.print(
            f"[bold yellow]Step 1: Pushing commits and release tags to origin {dev_branch}...[/bold yellow]"
        )
        push_res = run_process(["git", "push", "--follow-tags", "origin", dev_branch], cwd=root_dir)
        if not push_res.passed:
            console.print(
                f"[bold red]Pipeline aborted: git push failed.[/bold red]\n{push_res.stderr}"
            )
            return push_res.exit_code
        console.print("[bold green]✔ Git push completed successfully.[/bold green]")

    # Step 2: Create/update PR
    if create_pr:
        console.print(
            f"\n[bold yellow]Step 2: Creating/updating Pull Request into {base_branch} with Quality Gate certification...[/bold yellow]"
        )
        pr_code = run_pr_workflow(
            root_dir=root_dir,
            head=dev_branch,
            base=base_branch,
            dry_run=False,
        )
        if pr_code != 0:
            console.print("[bold red]Pipeline warning: PR creation had errors.[/bold red]")

    # Step 3: Publish release (draft by default)
    if draft_release:
        console.print(
            "\n[bold yellow]Step 3: Creating GitHub Draft Release for latest version...[/bold yellow]"
        )
        rel_code = run_release_workflow(
            root_dir=root_dir,
            publish=True,
            latest=True,
            draft=True,
        )
        if rel_code != 0:
            console.print(
                "[bold red]Pipeline warning: Draft release creation had errors.[/bold red]"
            )

    console.print(
        "\n[bold green]═════ Automated Post-Release Pipeline Completed ═════[/bold green]\n"
    )
    return 0
