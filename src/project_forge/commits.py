"""Automated Conventional Commit tooling with repository-neutral scope inference."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table

from project_forge.process import run_process

console = Console()


@dataclass
class ChangedFile:
    """Represents an uncommitted file change in the repository."""

    status: str
    filepath: str
    orig_path: str | None = None

    @property
    def display_path(self) -> str:
        """Formatted path for user presentation and logs."""
        if self.orig_path:
            return f"{self.orig_path} -> {self.filepath}"
        return self.filepath


@dataclass
class CommitGroup:
    """Represents a cohesive group of files committed atomically together."""

    message: str
    files: list[ChangedFile] = field(default_factory=lambda: cast(list[ChangedFile], []))

    @property
    def display_summary(self) -> str:
        """Formatted summary of files in this commit group."""
        if not self.files:
            return "(no files)"
        if len(self.files) == 1:
            return self.files[0].display_path
        paths = [f.filepath.replace("\\", "/") for f in self.files]
        sample = ", ".join(Path(p).name for p in paths[:3])
        suffix = f", ... (+{len(paths) - 3} more)" if len(paths) > 3 else ""
        return f"{len(self.files)} files ({sample}{suffix})"


def format_commit_header(type_scope: str, desc: str, max_length: int = 72) -> str:
    """Format and guarantee commit header is strictly within max_length characters."""
    prefix = f"{type_scope}: "
    max_desc_len = max_length - len(prefix)
    if len(desc) > max_desc_len:
        desc = desc[:max_desc_len].rstrip()
    return f"{prefix}{desc}"


def infer_scope(
    filepath: str,
    source_roots: list[str] | None = None,
    scope_overrides: dict[str, str] | None = None,
) -> str:
    """Infer a conventional commit scope based on directory path and configured source roots.

    Parameters
    ----------
    filepath : str
        Relative file path.
    source_roots : list[str] | None, optional
        Configured source root directories (e.g. ['src']).
    scope_overrides : dict[str, str] | None, optional
        Custom scope overrides mapping.

    Returns
    -------
    str
        Inferred scope string.
    """
    norm = filepath.replace("\\", "/")
    if scope_overrides and norm in scope_overrides:
        return scope_overrides[norm]

    roots = source_roots or ["src"]
    for src_root in roots:
        norm_src = src_root.rstrip("/") + "/"
        if norm.startswith(norm_src):
            rel = norm[len(norm_src) :]
            parts = rel.split("/")
            if len(parts) >= 2:
                # e.g. project_forge/cli.py -> cli
                # or project_forge/domain/entity.py -> domain
                second_part = parts[1]
                stem = Path(second_part).stem
                return stem[:15].rstrip("_")
            return Path(parts[0]).stem[:15].rstrip("_")

    if norm.startswith("tests/"):
        stem = Path(norm).stem.replace("test_", "").rstrip("_")
        return stem[:15].rstrip("_")
    if norm.startswith(".githooks/"):
        return "hooks"
    if norm.startswith(".github/"):
        return "ci"
    if norm.startswith(".plan/"):
        return "planning"
    if norm.endswith(".md"):
        return Path(norm).stem[:15].rstrip("_")

    return Path(norm).stem[:15].rstrip("_")


def infer_commit_message(
    file_item: ChangedFile,
    source_roots: list[str] | None = None,
    scope_overrides: dict[str, str] | None = None,
    max_length: int = 72,
) -> str:
    """Infer a Conventional Commit message based on path heuristics."""
    norm = file_item.filepath.replace("\\", "/")
    scope = infer_scope(norm, source_roots, scope_overrides)

    # Deletions
    if file_item.status == "D":
        if norm.endswith("__init__.py"):
            pkg_parts = norm.split("/")
            pkg_name = pkg_parts[-2] if len(pkg_parts) >= 2 else "root"
            return format_commit_header(
                f"refactor({pkg_name[:15].rstrip('_')})", "remove package facade", max_length
            )
        stem = Path(norm).stem
        return format_commit_header(f"refactor({scope})", f"remove deprecated {stem}", max_length)

    # Renames
    if file_item.status == "R" and file_item.orig_path:
        norm_orig = file_item.orig_path.replace("\\", "/")
        stem = Path(norm).stem
        orig_stem = Path(norm_orig).stem
        if orig_stem == stem:
            dest_parts = norm.split("/")
            dest_folder = dest_parts[-2] if len(dest_parts) >= 2 else "root"
            return format_commit_header(
                f"refactor({scope})", f"relocate {stem} to {dest_folder}", max_length
            )
        return format_commit_header(
            f"refactor({scope})", f"rename {orig_stem} to {stem}", max_length
        )

    # Package __init__.py exports
    if norm.endswith("__init__.py"):
        pkg_parts = norm.split("/")
        pkg_name = pkg_parts[-2] if len(pkg_parts) >= 2 else "root"
        return format_commit_header(
            f"refactor({pkg_name[:15].rstrip('_')})", "update package exports", max_length
        )

    # Tests
    if norm.startswith("tests/"):
        return format_commit_header(f"test({scope})", "update test suite", max_length)

    # CI & Tooling
    if norm.startswith(".github/"):
        return format_commit_header("ci(github)", "update workflow configuration", max_length)
    if norm.startswith(".githooks/"):
        return format_commit_header("ci(hooks)", "update git hook", max_length)
    if norm in {
        "ruff.toml",
        "mypy.ini",
        "pyrightconfig.json",
        "pyrefly.toml",
        "uv.toml",
        ".pylintrc",
        "poe_tasks.toml",
    }:
        tool_name = Path(norm).stem.lstrip(".").split(".")[0].rstrip("_")
        return format_commit_header(f"ci({tool_name})", "update tool configuration", max_length)
    if norm in {"pyproject.toml", "package.json", "uv.lock"}:
        tool_name = Path(norm).stem.rstrip("_")
        return format_commit_header(
            f"chore({tool_name})", "update project configuration", max_length
        )

    # Source code
    roots = source_roots or ["src"]
    for src_root in roots:
        if norm.startswith(src_root.rstrip("/") + "/"):
            stem = Path(norm).stem
            action = "add" if file_item.status in ("?", "??", "A") else "update"
            return format_commit_header(f"refactor({scope})", f"{action} {stem}", max_length)

    # Documentation
    if norm.startswith(".plan/") or norm.startswith(".planning/"):
        return format_commit_header("docs(planning)", "update plan and progress", max_length)
    if norm.endswith(".md"):
        stem = Path(norm).stem[:15].rstrip("_")
        return format_commit_header(f"docs({stem})", "update documentation", max_length)

    # Generic fallback
    stem = Path(norm).stem.rstrip("_")
    action = "add" if file_item.status in ("?", "??", "A") else "update"
    return format_commit_header("chore", f"{action} {stem}", max_length)


def load_custom_overrides(root_dir: Path, cli_map_path: str | None = None) -> dict[str, list[str]]:
    """Load Message-to-Paths commit override mappings from JSON."""
    candidates: list[Path] = []
    if cli_map_path:
        candidates.append(Path(cli_map_path))
    candidates.append(root_dir / ".commit_overrides.json")
    candidates.append(root_dir / ".commit_map.json")

    for p in candidates:
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8")
                raw_data: object = json.loads(content)
                if isinstance(raw_data, dict):
                    raw_dict = cast(dict[object, object], raw_data)
                    result: dict[str, list[str]] = {}
                    for k, v in raw_dict.items():
                        msg_or_path = str(k).strip()
                        if isinstance(v, list):
                            raw_list = cast(list[object], v)
                            result[msg_or_path] = [
                                str(item).replace("\\", "/").strip() for item in raw_list
                            ]
                        elif isinstance(v, str):
                            path = msg_or_path.replace("\\", "/").strip()
                            result.setdefault(str(v).strip(), []).append(path)
                    return result
            except Exception:
                pass
    return {}


def get_changed_files(root_dir: Path) -> list[ChangedFile]:
    """Query git status for all uncommitted changes using temporary staging for renames."""
    # 1. Temporarily stage everything to trigger git rename heuristics
    run_process(["git", "add", "-A"], cwd=root_dir)

    # 2. Query porcelain status with renames
    proc = run_process(["git", "status", "-s", "-uall", "--find-renames"], cwd=root_dir)

    # 3. Immediately unstage everything so index is clean
    run_process(["git", "restore", "--staged", "."], cwd=root_dir)

    if not proc.passed or not proc.stdout.strip():
        return []

    results: list[ChangedFile] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        status_part = line[:2].strip()
        file_part = line[2:].strip().strip('"')

        if " -> " in file_part:
            orig, target = file_part.split(" -> ", 1)
            results.append(
                ChangedFile(
                    status="R",
                    filepath=target.strip().strip('"'),
                    orig_path=orig.strip().strip('"'),
                )
            )
        else:
            results.append(
                ChangedFile(
                    status=status_part,
                    filepath=file_part,
                )
            )
    return results


def build_commit_groups(
    files: list[ChangedFile],
    overrides: dict[str, list[str]],
    source_roots: list[str] | None = None,
    scope_overrides: dict[str, str] | None = None,
    only_mapped: bool = False,
    max_length: int = 72,
) -> list[CommitGroup]:
    """Group uncommitted files into atomic CommitGroup objects."""
    file_by_path: dict[str, ChangedFile] = {}
    for f in files:
        norm_target = f.filepath.replace("\\", "/")
        file_by_path[norm_target] = f
        if f.orig_path:
            norm_orig = f.orig_path.replace("\\", "/")
            file_by_path[norm_orig] = f

    groups: list[CommitGroup] = []
    accounted_filepaths: set[str] = set()

    # 1. Groups explicitly defined in overrides
    for msg, path_list in overrides.items():
        group_files: list[ChangedFile] = []
        for p in path_list:
            norm_p = p.replace("\\", "/")
            if norm_p in file_by_path:
                f_obj = file_by_path[norm_p]
                if f_obj.filepath not in accounted_filepaths:
                    group_files.append(f_obj)
                    accounted_filepaths.add(f_obj.filepath)

        if group_files:
            groups.append(CommitGroup(message=msg, files=group_files))

    # 2. Inferred groups for remaining files
    inferred_groups: dict[str, list[ChangedFile]] = {}
    for f in files:
        if f.filepath not in accounted_filepaths:
            if only_mapped:
                continue
            inf_msg = infer_commit_message(
                f, source_roots=source_roots, scope_overrides=scope_overrides, max_length=max_length
            )
            inferred_groups.setdefault(inf_msg, []).append(f)

    for inf_msg, inf_files in inferred_groups.items():
        groups.append(CommitGroup(message=inf_msg, files=inf_files))

    return groups


def show_group_diff(group: CommitGroup, root_dir: Path) -> None:
    """Display diff summary for all files in a commit group."""
    paths_to_diff: list[str] = []
    for f in group.files:
        if f.status == "R" and f.orig_path:
            paths_to_diff.append(f.orig_path.replace("\\", "/"))
        paths_to_diff.append(f.filepath.replace("\\", "/"))

    proc = run_process(["git", "diff", "HEAD", "--"] + paths_to_diff, cwd=root_dir)
    diff_text = proc.stdout
    if not diff_text.strip():
        diff_text = "(No diff detected or binary content)"

    syntax = Syntax(diff_text[:4000], "diff", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"Group Diff: {group.message}", border_style="cyan"))


def prompt_interactive_group(
    group: CommitGroup, index: int, total: int, root_dir: Path
) -> str | None:
    """Interactive wizard to approve, customize, or skip a commit group."""
    while True:
        file_lines = "\n".join(f"  • [{f.status}] {f.display_path}" for f in group.files[:8])
        if len(group.files) > 8:
            file_lines += f"\n  • ... (+{len(group.files) - 8} more files)"

        console.print(
            Panel(
                f"[bold cyan]Commit Group [{index}/{total}]:[/bold cyan]\n"
                f"[dim]Files ({len(group.files)}):[/dim]\n{file_lines}\n\n"
                f"[dim]Proposed Message:[/dim] [bold green]{group.message}[/bold green] [dim]({len(group.message)}/72 chars)[/dim]",
                title="[bold yellow]Commitlint Group Wizard[/bold yellow]",
                border_style="yellow",
            )
        )

        console.print("[bold]Choices:[/bold]")
        console.print("  [bold cyan]1[/bold cyan] -> Accept proposed message")
        console.print("  [bold cyan]2[/bold cyan] -> Enter custom commit message")
        console.print("  [bold cyan]3[/bold cyan] -> View group diff")
        console.print("  [bold cyan]4[/bold cyan] -> Skip this group")
        console.print("  [bold red]q[/bold red] -> Quit / Abort\n")

        choice = Prompt.ask(
            "[bold]Select option[/bold]", choices=["1", "2", "3", "4", "q"], default="1"
        )

        if choice == "1":
            return group.message

        if choice == "2":
            while True:
                custom_msg = Prompt.ask("Enter full commit message").strip()
                if not custom_msg:
                    console.print("[red]Commit message cannot be empty.[/red]")
                    continue
                if len(custom_msg) > 72:
                    console.print(
                        f"[red]Message exceeds 72 characters ({len(custom_msg)} chars).[/red]"
                    )
                    continue
                return custom_msg

        if choice == "3":
            show_group_diff(group, root_dir=root_dir)
            continue

        if choice == "4":
            console.print(f"[dim]Skipped group '{group.message}'[/dim]")
            return None

        if choice.lower() == "q":
            console.print("[red]Aborted by user.[/red]")
            return "__ABORT__"


def run_git_commit_group(
    group: CommitGroup,
    root_dir: Path,
    dry_run: bool = False,
    no_verify: bool = False,
) -> bool:
    """Stage all files in a group and create a single atomic git commit."""
    if len(group.message) > 72:
        console.print(
            f"[bold red]ERROR:[/bold red] Commit message exceeds 72 characters: '{group.message}'"
        )
        return False

    paths_to_stage: list[str] = []
    for f in group.files:
        if f.status == "R" and f.orig_path:
            paths_to_stage.append(f.orig_path.replace("\\", "/"))
        paths_to_stage.append(f.filepath.replace("\\", "/"))

    if dry_run:
        verify_flag = " --no-verify" if no_verify else ""
        console.print(
            f"[dim][DRY-RUN][/dim] git add -A -- {' '.join(paths_to_stage[:3])}{' ...' if len(paths_to_stage) > 3 else ''}"
        )
        console.print(
            f'[dim][DRY-RUN][/dim] git commit -m "{group.message}"{verify_flag} [dim]({len(group.files)} files)[/dim]'
        )
        return True

    # 1. Clean staging index
    run_process(["git", "restore", "--staged", "."], cwd=root_dir)

    # 2. Stage files
    add_proc = run_process(["git", "add", "-A", "--"] + paths_to_stage, cwd=root_dir)
    if not add_proc.passed:
        console.print(
            Panel(
                add_proc.combined_output,
                title="[bold red]git add FAILED[/bold red]",
                border_style="red",
            )
        )
        return False

    # 3. Check staged changes
    staged_proc = run_process(["git", "diff", "--cached", "--name-only"], cwd=root_dir)
    if not staged_proc.stdout.strip():
        console.print(
            f"[yellow]Skipping group '{group.message}': no staged changes detected.[/yellow]"
        )
        return True

    # 4. Commit
    cmd = ["git", "commit", "-m", group.message]
    if no_verify:
        cmd.append("--no-verify")

    commit_proc = run_process(cmd, cwd=root_dir)
    if not commit_proc.passed:
        console.print(
            Panel(
                commit_proc.combined_output,
                title=f"[bold red]FAILED commit: {group.message}[/bold red]",
                border_style="red",
            )
        )
        run_process(["git", "restore", "--staged", "."], cwd=root_dir)
        return False

    console.print(
        f'[bold green][OK][/bold green] Committed ({len(group.files)} files): "[cyan]{group.message}[/cyan]"'
    )
    return True


def execute_commit_flow(
    root_dir: Path | None = None,
    dry_run: bool = False,
    interactive: bool = False,
    run: bool = False,
    map_path: str | None = None,
    only_mapped: bool = False,
    no_verify: bool = False,
    skip_audit: bool = False,
) -> int:
    """Execute complete automated grouped Conventional Commits flow."""
    if root_dir is None:
        from project_forge.project import find_project_root

        root_dir = find_project_root()

    from project_forge.config import load_config

    cfg = load_config(root_dir)
    custom_overrides = load_custom_overrides(root_dir, map_path)

    is_dry_run = dry_run or (not interactive and not run)

    files = get_changed_files(root_dir)
    if not files:
        console.print("[green]Working tree is completely clean. Nothing to commit.[/green]")
        return 0

    groups = build_commit_groups(
        files,
        custom_overrides,
        source_roots=cfg.source,
        scope_overrides=cfg.commits.scope_overrides,
        only_mapped=only_mapped,
        max_length=cfg.commits.header_max_length,
    )
    if not groups:
        console.print("[yellow]No changed files match the requested commit criteria.[/yellow]")
        return 0

    mode_label = (
        "INTERACTIVE COMMIT WIZARD"
        if interactive
        else ("DRY-RUN PREVIEW" if is_dry_run else "EXECUTING GROUPED COMMITS")
    )
    total_files_in_groups = sum(len(g.files) for g in groups)
    console.print(
        f"\n--- [bold cyan]{mode_label}[/bold cyan] ({len(groups)} groups, {total_files_in_groups} files) ---\n"
    )

    table = Table(title="Planned Commit Groups", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Files", justify="right", style="cyan", width=6)
    table.add_column("Commit Message", style="bold green")
    table.add_column("Scope Summary", style="white")

    for i, g in enumerate(groups, 1):
        table.add_row(str(i), str(len(g.files)), g.message, g.display_summary)
    console.print(table)
    console.print("")

    if is_dry_run:
        console.print("[dim]To execute commits, run: pforge commit --run[/dim]")
        console.print("[dim]Or run interactively:   pforge commit -i[/dim]")
        return 0

    # Upfront quality gate
    bypass_hooks = no_verify
    if not skip_audit and not no_verify:
        from project_forge.quality import run_quality_gate

        console.print("\n[bold cyan]Running Upfront Fast Quality Gate Verification...[/bold cyan]")
        exit_code = run_quality_gate(tier="fast", export="cli", root_dir=root_dir)
        if exit_code != 0:
            console.print("[bold red]Upfront Quality Gate Failed — Commits Aborted.[/bold red]")
            return 1
        console.print("[bold green]✓ Upfront Quality Gate Passed Cleanly![/bold green]\n")
        bypass_hooks = True

    success_count = 0
    fail_count = 0
    skipped_count = 0

    try:
        for idx, group in enumerate(groups, 1):
            if interactive:
                chosen_msg = prompt_interactive_group(group, idx, len(groups), root_dir=root_dir)
                if chosen_msg == "__ABORT__":
                    break
                if chosen_msg is None:
                    skipped_count += 1
                    continue
                group.message = chosen_msg

            ok = run_git_commit_group(
                group, root_dir=root_dir, dry_run=False, no_verify=bypass_hooks
            )
            if ok:
                success_count += 1
            else:
                fail_count += 1
                break
    finally:
        run_process(["git", "restore", "--staged", "."], cwd=root_dir)

    console.print(
        f"\n[bold]Summary:[/bold] {success_count} groups committed, {fail_count} failed, {skipped_count} skipped."
    )
    return 0 if fail_count == 0 else 1
