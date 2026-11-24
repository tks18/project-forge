"""Top-level Typer CLI command router for Project Forge (pforge)."""

from __future__ import annotations

import typer

from project_forge.bumper import run_bump
from project_forge.changelog import (
    get_latest_release,
    get_release_by_version,
    validate_changelog,
)
from project_forge.commits import execute_commit_flow
from project_forge.config import load_config
from project_forge.doctor import run_doctor
from project_forge.documentation import run_documentation_audit
from project_forge.hooks import get_hooks_status, install_hooks, uninstall_hooks
from project_forge.project import find_project_root
from project_forge.publishing import run_publish_flow
from project_forge.pull_requests import run_pr_workflow
from project_forge.quality import run_quality_gate
from project_forge.releases import run_release_pipeline, run_release_workflow
from project_forge.status import show_status

app = typer.Typer(
    name="pforge",
    help="Repository-neutral engineering workflow CLI for quality gates, commits, releases, and versioning.",
    no_args_is_help=True,
)

hooks_app = typer.Typer(
    name="hooks", help="Manage git pre-commit and pre-push quality hooks.", no_args_is_help=True
)
changelog_app = typer.Typer(
    name="changelog", help="Inspect and validate CHANGELOG.md.", no_args_is_help=True
)
pr_app = typer.Typer(
    name="pr", help="Preview and create GitHub pull requests.", no_args_is_help=True
)
release_app = typer.Typer(
    name="release", help="Preview and publish GitHub releases.", no_args_is_help=True
)
docs_app = typer.Typer(name="docs", help="AST-level documentation auditor.", no_args_is_help=True)

app.add_typer(hooks_app)
app.add_typer(changelog_app)
app.add_typer(pr_app)
app.add_typer(release_app)
app.add_typer(docs_app)


@app.command()
def doctor() -> None:
    """Run diagnostic checks on repository configuration and external toolchains."""
    code = run_doctor()
    raise typer.Exit(code)


@app.command()
def status() -> None:
    """Display high-level snapshot dashboard of project status."""
    code = show_status()
    raise typer.Exit(code)


@app.command()
def bump(
    release_as: str | None = typer.Option(
        None,
        "--release-as",
        "-r",
        help="Explicit release increment ('patch', 'minor', 'major', or version like '1.2.0').",
    ),
    patch: bool = typer.Option(
        False,
        "--patch",
        help="Bump patch version (e.g. 1.0.0 -> 1.0.1).",
    ),
    minor: bool = typer.Option(
        False,
        "--minor",
        help="Bump minor version (e.g. 1.0.0 -> 1.1.0).",
    ),
    major: bool = typer.Option(
        False,
        "--major",
        help="Bump major version (e.g. 1.0.0 -> 2.0.0).",
    ),
    prerelease: str | None = typer.Option(
        None,
        "--prerelease",
        "-p",
        help="Prerelease tag identifier ('alpha', 'beta', 'rc').",
    ),
    first_release: bool = typer.Option(
        False,
        "--first-release",
        help="Generate first release from repository inception.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-d",
        help="Preview version calculation and changelog without writing files or making Git commits.",
    ),
    no_commit: bool = typer.Option(
        False,
        "--no-commit",
        help="Do not create release commit.",
    ),
    no_tag: bool = typer.Option(
        False,
        "--no-tag",
        help="Do not create annotated release tag.",
    ),
    pipeline: bool = typer.Option(
        False,
        "--pipeline",
        help="Execute complete post-release pipeline after bumping (push, PR, draft release).",
    ),
) -> None:
    """Native Python SemVer version bumper and changelog generator."""
    target_release_as = release_as
    if patch:
        target_release_as = "patch"
    elif minor:
        target_release_as = "minor"
    elif major:
        target_release_as = "major"

    root_dir = find_project_root()
    cfg = load_config(root_dir)
    code, new_version = run_bump(
        root_dir=root_dir,
        release_as=target_release_as,
        prerelease=prerelease,
        first_release=first_release,
        dry_run=dry_run,
        no_commit=no_commit,
        no_tag=no_tag,
        tag_prefix=cfg.bump.tag_prefix,
        pipeline=pipeline,
    )
    if dry_run:
        typer.echo(f"[DRY-RUN] Next calculated version: {new_version}")
    else:
        typer.echo(f"Successfully bumped version to v{new_version}")
    raise typer.Exit(code)


@app.command()
def quality(
    fast: bool = typer.Option(
        False, "--fast", help="Run Tier 1 fast checks (<2s: Ruff Lint, Format, Mypy)."
    ),
    fix: bool = typer.Option(
        False, "--fix", help="Automatically apply safe formatting and lint fixes."
    ),
    tier: str = typer.Option("full", "--tier", help="Quality tier: 'fast' or 'full'."),
    export: str = typer.Option(
        "cli", "--export", help="Output format: 'cli', 'csv', 'json', or 'all'."
    ),
    output_path: str | None = typer.Option(
        None, "--output-path", help="Destination path for exported report file."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress logs."),
) -> None:
    """Run unified multi-engine quality gate and diagnostics."""
    chosen_tier = "fast" if fast else tier
    code = run_quality_gate(
        tier=chosen_tier,
        export=export,
        output_path=output_path,
        auto_fix=fix,
        quiet=quiet,
    )
    raise typer.Exit(code)


@app.command()
def commit(
    preview: bool = typer.Option(
        False, "--preview", "--dry-run", help="Preview atomic commit groups without committing."
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Interactive file/group commit wizard."
    ),
    run: bool = typer.Option(False, "--run", help="Execute commits immediately."),
    map_path: str | None = typer.Option(
        None, "--map", help="Path to custom Message-to-Paths overrides JSON."
    ),
    only_mapped: bool = typer.Option(
        False, "--only-mapped", help="Only commit files explicitly mapped in overrides."
    ),
    no_verify: bool = typer.Option(
        False, "--no-verify", "-n", help="Bypass git hooks during commit execution."
    ),
    skip_audit: bool = typer.Option(False, "--skip-audit", help="Skip upfront quality gate check."),
) -> None:
    """Automated conventional commits with scope inference and grouping."""
    code = execute_commit_flow(
        dry_run=preview,
        interactive=interactive,
        run=run,
        map_path=map_path,
        only_mapped=only_mapped,
        no_verify=no_verify,
        skip_audit=skip_audit,
    )
    raise typer.Exit(code)


@app.command()
def publish(
    skip_quality: bool = typer.Option(
        False, "--skip-quality", help="Skip pre-publish quality gate check."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-d", help="Build and check packages without uploading to PyPI."
    ),
) -> None:
    """Build distribution packages and publish to PyPI using token from .env or environment."""
    code = run_publish_flow(skip_quality=skip_quality, dry_run=dry_run)
    raise typer.Exit(code)


# -----------------------------------------------------------------------------
# Hooks Subcommands
# -----------------------------------------------------------------------------


@hooks_app.command("install")
def hooks_install() -> None:
    """Install git pre-commit and pre-push quality hooks."""
    code = install_hooks()
    if code == 0:
        typer.echo("Git quality hooks installed successfully.")
    raise typer.Exit(code)


@hooks_app.command("status")
def hooks_status_cmd() -> None:
    """Check git hooks installation and configuration status."""
    st = get_hooks_status()
    typer.echo(f"Hooks Installed    : {st['installed']}")
    typer.echo(f"Git core.hooksPath : {st['core_hooks_path']}")
    typer.echo(f"Tracked pre-commit : {st['tracked_pre_commit']}")
    typer.echo(f"Tracked pre-push   : {st['tracked_pre_push']}")


@hooks_app.command("uninstall")
def hooks_uninstall() -> None:
    """Uninstall git hooks and unset git core.hooksPath."""
    code = uninstall_hooks()
    typer.echo("Git hooks uninstalled.")
    raise typer.Exit(code)


# -----------------------------------------------------------------------------
# Changelog Subcommands
# -----------------------------------------------------------------------------


@changelog_app.command("validate")
def changelog_validate() -> None:
    """Validate CHANGELOG.md file existence and formatting."""
    root_dir = find_project_root()
    cfg = load_config(root_dir)
    valid, errors = validate_changelog(root_dir / cfg.changelog)
    if valid:
        typer.echo(f"Changelog '{cfg.changelog}' is valid.")
        raise typer.Exit(0)
    for err in errors:
        typer.echo(f"Error: {err}", err=True)
    raise typer.Exit(1)


@changelog_app.command("latest")
def changelog_latest() -> None:
    """Display the latest release notes from CHANGELOG.md."""
    root_dir = find_project_root()
    cfg = load_config(root_dir)
    rel = get_latest_release(root_dir / cfg.changelog)
    if rel:
        typer.echo(rel.body)
        raise typer.Exit(0)
    typer.echo("No releases found in changelog.", err=True)
    raise typer.Exit(1)


@changelog_app.command("show")
def changelog_show(version: str = typer.Argument(..., help="Release version to display.")) -> None:
    """Display release notes for a specific version."""
    root_dir = find_project_root()
    cfg = load_config(root_dir)
    rel = get_release_by_version(root_dir / cfg.changelog, version)
    if rel:
        typer.echo(rel.body)
        raise typer.Exit(0)
    typer.echo(f"Version '{version}' not found in changelog.", err=True)
    raise typer.Exit(1)


# -----------------------------------------------------------------------------
# PR Subcommands
# -----------------------------------------------------------------------------


@pr_app.command("preview")
def pr_preview(
    head: str | None = typer.Option(None, "--head", help="Source branch."),
    base: str | None = typer.Option(None, "--base", help="Target branch."),
    version: str | None = typer.Option(
        None, "--version", help="Version to extract from changelog."
    ),
    title: str | None = typer.Option(None, "--title", help="Custom PR title."),
    draft: bool = typer.Option(False, "--draft", help="Preview as draft PR."),
    re_audit: bool = typer.Option(False, "--re-audit", help="Force fresh quality gate execution."),
) -> None:
    """Preview PR title, changelog body, and Quality Gate certification table."""
    code = run_pr_workflow(
        head=head,
        base=base,
        version=version,
        title=title,
        draft=draft,
        re_audit=re_audit,
        dry_run=True,
    )
    raise typer.Exit(code)


@pr_app.command("create")
def pr_create(
    head: str | None = typer.Option(None, "--head", help="Source branch."),
    base: str | None = typer.Option(None, "--base", help="Target branch."),
    version: str | None = typer.Option(
        None, "--version", help="Version to extract from changelog."
    ),
    title: str | None = typer.Option(None, "--title", help="Custom PR title."),
    draft: bool = typer.Option(False, "--draft", help="Open as draft PR."),
    re_audit: bool = typer.Option(False, "--re-audit", help="Force fresh quality gate execution."),
) -> None:
    """Create or update GitHub PR with embedded Quality Gate certification."""
    code = run_pr_workflow(
        head=head,
        base=base,
        version=version,
        title=title,
        draft=draft,
        re_audit=re_audit,
        dry_run=False,
    )
    raise typer.Exit(code)


# -----------------------------------------------------------------------------
# Release Subcommands
# -----------------------------------------------------------------------------


@release_app.command("preview")
def release_preview(
    latest: bool = typer.Option(True, "--latest", help="Preview latest changelog entry."),
    version: str | None = typer.Option(None, "--version", help="Target specific version."),
    all_releases: bool = typer.Option(False, "--all", help="Preview all changelog entries."),
) -> None:
    """Preview release notes from changelog."""
    code = run_release_workflow(
        publish=False,
        latest=latest,
        single_version=version,
        preview_all=all_releases,
    )
    raise typer.Exit(code)


@release_app.command("publish")
def release_publish(
    latest: bool = typer.Option(True, "--latest", help="Publish latest version."),
    version: str | None = typer.Option(None, "--version", help="Target specific version."),
    draft: bool = typer.Option(False, "--draft", help="Publish as draft release on GitHub."),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Prompt before publishing."
    ),
) -> None:
    """Publish release to GitHub using gh CLI."""
    code = run_release_workflow(
        publish=True,
        latest=latest,
        single_version=version,
        draft=draft,
        interactive=interactive,
    )
    raise typer.Exit(code)


@release_app.command("pipeline")
def release_pipeline_cmd(
    push: bool = typer.Option(
        True, "--push/--no-push", help="Push commits and tags to remote origin."
    ),
    create_pr: bool = typer.Option(
        True, "--create-pr/--no-create-pr", help="Create or update pull request."
    ),
    draft: bool = typer.Option(True, "--draft/--no-draft", help="Create draft release on GitHub."),
) -> None:
    """Execute complete post-release pipeline: git push -> create PR -> draft release."""
    root_dir = find_project_root()
    code = run_release_pipeline(
        root_dir=root_dir,
        push=push,
        create_pr=create_pr,
        draft_release=draft,
    )
    raise typer.Exit(code)


@release_app.command("flow")
def release_flow_cmd(
    patch: bool = typer.Option(False, "--patch", help="Bump patch version and execute pipeline."),
    minor: bool = typer.Option(False, "--minor", help="Bump minor version and execute pipeline."),
    major: bool = typer.Option(False, "--major", help="Bump major version and execute pipeline."),
    release_as: str | None = typer.Option(
        None, "--release-as", "--as", help="Explicit version to bump to."
    ),
) -> None:
    """Execute complete release flow: bump version -> push -> create PR -> draft release."""
    target_release_as = release_as
    if patch:
        target_release_as = "patch"
    elif minor:
        target_release_as = "minor"
    elif major:
        target_release_as = "major"

    root_dir = find_project_root()
    cfg = load_config(root_dir)
    code, new_version = run_bump(
        root_dir=root_dir,
        release_as=target_release_as,
        tag_prefix=cfg.bump.tag_prefix,
        pipeline=True,
    )
    if code == 0:
        typer.echo(f"Successfully completed release flow for {cfg.bump.tag_prefix}{new_version}")
    raise typer.Exit(code)


# -----------------------------------------------------------------------------
# Docs Subcommands
# -----------------------------------------------------------------------------


@docs_app.command("audit")
def docs_audit(
    strict: bool = typer.Option(
        False, "--strict", help="Include private methods and internal helpers."
    ),
    require_init: bool = typer.Option(
        False, "--require-init", help="Require explicit __init__ docstring."
    ),
    as_json: bool = typer.Option(False, "--json", help="Output structured JSON instead of table."),
) -> None:
    """Run AST documentation auditor across configured source roots."""
    code = run_documentation_audit(strict=strict, require_init=require_init, as_json=as_json)
    raise typer.Exit(code)
