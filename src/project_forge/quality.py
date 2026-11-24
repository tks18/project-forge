"""Unified Quality Gate & Multi-Engine Diagnostics Orchestration Engine."""

from __future__ import annotations

import csv
import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from project_forge.process import run_process

console = Console()


@dataclass
class DiagnosticIssue:
    """Normalized diagnostic issue from any static analysis engine."""

    engine: str
    file: str
    line: int
    column: int
    code: str
    severity: str
    message: str


def _empty_issues() -> list[DiagnosticIssue]:
    return []


@dataclass
class EngineResult:
    """Result summary of a single diagnostic engine run."""

    name: str
    tier: str
    command: list[str]
    duration_seconds: float
    exit_code: int
    passed: bool
    issues: list[DiagnosticIssue] = field(default_factory=_empty_issues)
    raw_output: str = ""


# -----------------------------------------------------------------------------
# Diagnostic Output Parsers
# -----------------------------------------------------------------------------


def parse_ruff_output(output: str) -> list[DiagnosticIssue]:
    """Parse Ruff diagnostic output."""
    issues: list[DiagnosticIssue] = []
    # Match: path/file.py:line:col: CODE Message
    pattern = re.compile(r"^([^:]+):(\d+):(\d+):\s+([A-Z0-9]+)\s+(.*)$", re.MULTILINE)
    for match in pattern.finditer(output):
        fpath, line, col, code, msg = match.groups()
        issues.append(
            DiagnosticIssue(
                engine="Ruff",
                file=fpath.strip(),
                line=int(line),
                column=int(col),
                code=code.strip(),
                severity="Error" if code.startswith(("E", "F")) else "Warning",
                message=msg.strip(),
            )
        )
    return issues


def parse_mypy_output(output: str) -> list[DiagnosticIssue]:
    """Parse Mypy diagnostic output."""
    issues: list[DiagnosticIssue] = []
    # Match: path/file.py:line: error: Message  [code]
    pattern = re.compile(
        r"^([^:]+):(\d+):\s+(error|warning|note):\s+(.*?)(?:\s+\[([a-z-]+)\])?$", re.MULTILINE
    )
    for match in pattern.finditer(output):
        fpath, line, sev, msg, code = match.groups()
        issues.append(
            DiagnosticIssue(
                engine="Mypy",
                file=fpath.strip(),
                line=int(line),
                column=0,
                code=(code or sev).strip(),
                severity=sev.capitalize(),
                message=msg.strip(),
            )
        )
    return issues


def parse_pyright_output(output: str) -> list[DiagnosticIssue]:
    """Parse Pyright diagnostic output."""
    issues: list[DiagnosticIssue] = []
    # Match: path/file.py:line:col - error: Message (code)
    pattern = re.compile(
        r"^\s*([^:\n]+):(\d+):(\d+)\s+-\s+(error|warning|info):\s+(.*?)(?:\s+\(([a-zA-Z0-9]+)\))?$",
        re.MULTILINE,
    )
    for match in pattern.finditer(output):
        fpath, line, col, sev, msg, code = match.groups()
        issues.append(
            DiagnosticIssue(
                engine="Pyright",
                file=fpath.strip(),
                line=int(line),
                column=int(col),
                code=(code or sev).strip(),
                severity=sev.capitalize(),
                message=msg.strip(),
            )
        )
    return issues


def parse_pylint_output(output: str) -> list[DiagnosticIssue]:
    """Parse Pylint diagnostic output."""
    issues: list[DiagnosticIssue] = []
    # Match: path/file.py:line:col: C0123: Message (symbol)
    pattern = re.compile(
        r"^([^:]+):(\d+):(\d+):\s+([CRWEF]\d+):\s+(.*?)(?:\s+\(([a-z-]+)\))?$", re.MULTILINE
    )
    for match in pattern.finditer(output):
        fpath, line, col, code, msg, symbol = match.groups()
        sev_map = {"E": "Error", "F": "Fatal", "W": "Warning", "R": "Refactor", "C": "Convention"}
        sev = sev_map.get(code[0], "Warning")
        issues.append(
            DiagnosticIssue(
                engine="Pylint",
                file=fpath.strip(),
                line=int(line),
                column=int(col),
                code=symbol or code,
                severity=sev,
                message=msg.strip(),
            )
        )
    return issues


def parse_generic_failures(output: str, engine_name: str = "Generic") -> list[DiagnosticIssue]:
    """Parse generic failure messages from tool output."""
    issues: list[DiagnosticIssue] = []
    for line in output.splitlines():
        if "FAILED " in line or "error:" in line.lower():
            issues.append(
                DiagnosticIssue(
                    engine=engine_name,
                    file="general",
                    line=0,
                    column=0,
                    code="FAIL",
                    severity="Error",
                    message=line.strip(),
                )
            )
    return issues


# -----------------------------------------------------------------------------
# Engine Execution Runner
# -----------------------------------------------------------------------------


def _run_engine(
    name: str,
    tier: str,
    command: list[str],
    parser_fn: Callable[[str], list[DiagnosticIssue]] | None,
    cwd: Path,
) -> EngineResult:
    """Execute a single diagnostic engine command and capture metrics."""
    res = run_process(command, cwd=cwd)
    raw = res.combined_output

    issues: list[DiagnosticIssue] = []
    if not res.passed:
        if parser_fn:
            issues = parser_fn(raw)
        else:
            issues = parse_generic_failures(raw, engine_name=name)

    return EngineResult(
        name=name,
        tier=tier,
        command=command,
        duration_seconds=res.duration_seconds,
        exit_code=res.exit_code,
        passed=res.passed,
        issues=issues,
        raw_output=raw,
    )


# -----------------------------------------------------------------------------
# Quality Gate Orchestrator
# -----------------------------------------------------------------------------


def run_quality_gate(
    tier: str = "full",
    export: str = "cli",
    output_path: str | None = None,
    auto_fix: bool = False,
    quiet: bool = False,
    root_dir: Path | None = None,
) -> int:
    """Run all configured quality engines based on tier and report results.

    Parameters
    ----------
    tier : str, optional
        'fast' or 'full', by default 'full'.
    export : str, optional
        'cli', 'csv', 'json', or 'all', by default 'cli'.
    output_path : str | None, optional
        Explicit output file destination, by default None.
    auto_fix : bool, optional
        Whether to run ruff format and ruff check --fix before testing, by default False.
    quiet : bool, optional
        Suppress progress logs, by default False.
    root_dir : Path | None, optional
        Project root directory, by default None (auto-discovered).

    Returns
    -------
    int
        0 if all engines passed, 1 on failure.
    """
    if root_dir is None:
        from project_forge.project import find_project_root

        root_dir = find_project_root()

    from project_forge.config import load_config
    from project_forge.project import read_project_metadata

    cfg = load_config(root_dir)
    metadata = read_project_metadata(root_dir)
    project_name = metadata.get("name", root_dir.name)

    if not quiet:
        console.print(
            Panel(
                f"[bold cyan]Local-First Quality Gate & Diagnostics[/bold cyan]\n"
                f"[dim]Project:[/dim] {project_name} | [dim]Tier:[/dim] [bold]{tier.upper()}[/bold] | "
                f"[dim]Export:[/dim] [bold]{export.upper()}[/bold]",
                border_style="cyan",
            )
        )

    if auto_fix:
        if not quiet:
            console.print("[yellow]>> Running auto-fix (Ruff lint & format)...[/yellow]")
        run_process(["uv", "run", "ruff", "check", "--fix", "."], cwd=root_dir)
        run_process(["uv", "run", "ruff", "format", "."], cwd=root_dir)

    # Engine specifications catalog
    # Map engine IDs to (Display Name, Default Tier, Command, Parser)
    engine_catalog: dict[str, tuple[str, str, list[str], Any]] = {
        "ruff-check": (
            "Ruff Check",
            "Fast",
            ["uv", "run", "ruff", "check", "."],
            parse_ruff_output,
        ),
        "ruff-format": (
            "Ruff Format",
            "Fast",
            ["uv", "run", "ruff", "format", "--check", "."],
            parse_generic_failures,
        ),
        "mypy": (
            "Mypy Typecheck",
            "Fast",
            ["uv", "run", "mypy", "src"],
            parse_mypy_output,
        ),
        "pyright": (
            "Pyright Typecheck",
            "Full",
            ["uv", "run", "pyright"],
            parse_pyright_output,
        ),
        "pylint": (
            "Pylint Deep Analysis",
            "Full",
            ["uv", "run", "pylint", "src"],
            parse_pylint_output,
        ),
        "pytest": (
            "Pytest Suite",
            "Full",
            ["uv", "run", "pytest", "tests/", "-q"],
            parse_generic_failures,
        ),
    }

    # Resolve configured engine list for requested tier
    selected_engine_ids = cfg.quality.fast if tier == "fast" else cfg.quality.full

    # Filter catalog
    engine_specs: list[tuple[str, str, list[str], Any]] = []
    for eng_id in selected_engine_ids:
        if eng_id in engine_catalog:
            disp_name, eng_tier, cmd, parser_fn = engine_catalog[eng_id]
            engine_specs.append((disp_name, eng_tier, cmd, parser_fn))

    results: list[EngineResult] = []
    total_start = time.perf_counter()

    for name, eng_tier, cmd, parser_fn in engine_specs:
        if not quiet:
            console.print(f"[dim]Running {name}...[/dim]", end="\r")
        res = _run_engine(name, eng_tier, cmd, parser_fn, cwd=root_dir)
        results.append(res)
        status_label = (
            "[bold green]✓ PASS[/bold green]" if res.passed else "[bold red]✗ FAIL[/bold red]"
        )
        if not quiet:
            console.print(f"  {status_label} {name:<24} ({res.duration_seconds:.2f}s)")

    total_duration = time.perf_counter() - total_start
    all_passed = all(r.passed for r in results)

    # 1. Render CLI Table
    table = Table(title="\nQuality Gate Audit Summary", header_style="bold magenta")
    table.add_column("Engine", style="bold")
    table.add_column("Tier", justify="center")
    table.add_column("Duration", justify="right")
    table.add_column("Issues", justify="right")
    table.add_column("Status", justify="center")

    total_issues = 0
    all_issues_list: list[DiagnosticIssue] = []

    for r in results:
        total_issues += len(r.issues)
        all_issues_list.extend(r.issues)
        status_str = "[bold green]PASS[/bold green]" if r.passed else "[bold red]FAIL[/bold red]"
        issues_str = "[green]0[/green]" if len(r.issues) == 0 else f"[red]{len(r.issues)}[/red]"
        table.add_row(r.name, r.tier, f"{r.duration_seconds:.2f}s", issues_str, status_str)

    if not quiet:
        console.print(table)

    # 2. Render Failure Diagnostics if any
    if not all_passed and not quiet:
        console.print("\n[bold red]── Diagnostics / Failures Detected ──[/bold red]")
        for r in results:
            if not r.passed:
                console.print(f"\n[bold yellow]Engine:[/bold yellow] [bold red]{r.name}[/bold red]")
                if r.issues:
                    for iss in r.issues[:15]:
                        console.print(
                            f"  [cyan]{iss.file}:{iss.line}[/cyan] [bold]{iss.code}[/bold] ({iss.severity}): {iss.message}"
                        )
                    if len(r.issues) > 15:
                        console.print(f"  [dim]... and {len(r.issues) - 15} more issues[/dim]")
                else:
                    lines = r.raw_output.splitlines()[-10:]
                    console.print("  " + "\n  ".join(lines))

    # 3. Handle CSV / JSON Exports
    outputs_dir = root_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now().isoformat()

    if export in ("csv", "all"):
        csv_file = (
            Path(output_path)
            if output_path and export == "csv"
            else outputs_dir / "audit_report.csv"
        )
        with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Timestamp",
                    "Engine",
                    "Tier",
                    "File",
                    "Line",
                    "Column",
                    "Code",
                    "Severity",
                    "Message",
                ]
            )
            if all_issues_list:
                for iss in all_issues_list:
                    writer.writerow(
                        [
                            timestamp_str,
                            iss.engine,
                            tier,
                            iss.file,
                            iss.line,
                            iss.column,
                            iss.code,
                            iss.severity,
                            iss.message,
                        ]
                    )
            else:
                writer.writerow(
                    [
                        timestamp_str,
                        "ALL_ENGINES",
                        tier,
                        "None",
                        0,
                        0,
                        "CLEAN",
                        "Info",
                        "All checks passed cleanly",
                    ]
                )
        if not quiet:
            console.print(
                f"\n[bold green]✓ Structured CSV audit report written to:[/bold green] {csv_file}"
            )

    if export in ("json", "all"):
        json_file = (
            Path(output_path)
            if output_path and export == "json"
            else outputs_dir / "audit_report.json"
        )
        payload = {
            "timestamp": timestamp_str,
            "project": project_name,
            "tier": tier,
            "all_passed": all_passed,
            "total_duration_seconds": round(total_duration, 2),
            "total_issues": total_issues,
            "engines": [
                {
                    "name": r.name,
                    "tier": r.tier,
                    "passed": r.passed,
                    "duration_seconds": round(r.duration_seconds, 2),
                    "exit_code": r.exit_code,
                    "issue_count": len(r.issues),
                    "issues": [asdict(iss) for iss in r.issues],
                }
                for r in results
            ],
        }
        with open(json_file, mode="w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        if not quiet:
            console.print(
                f"[bold green]✓ Structured JSON audit report written to:[/bold green] {json_file}"
            )

    # Summary Footer
    if not quiet:
        summary_color = "bold green" if all_passed else "bold red"
        status_text = "ALL QUALITY ENGINES PASSED" if all_passed else "QUALITY GATE FAILED"
        console.print(
            f"\n[{summary_color}]══ {status_text} (Total: {total_duration:.2f}s) ══[/{summary_color}]\n"
        )

    return 0 if all_passed else 1
