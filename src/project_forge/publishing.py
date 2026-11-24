"""PyPI package build and publishing orchestration."""

from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console

from project_forge.process import run_process

console = Console()


def load_pypi_token(root_dir: Path) -> str | None:
    """Safely load PyPI upload token from environment or .env file."""
    token = os.environ.get("UV_PUBLISH_TOKEN") or os.environ.get("PYPI_TOKEN")
    if token:
        return token.strip()

    env_path = root_dir / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" in stripped:
                    key, val = stripped.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key in ("UV_PUBLISH_TOKEN", "PYPI_TOKEN", "POETRY_PYPI_TOKEN_PYPI"):
                        return val
        except OSError:
            pass

    return None


def run_publish_flow(
    root_dir: Path | None = None,
    skip_quality: bool = False,
    dry_run: bool = False,
) -> int:
    """Build distributions with uv build and publish them to PyPI.

    Parameters
    ----------
    root_dir : Path | None, optional
        Project root directory, by default None.
    skip_quality : bool, optional
        Skip pre-publish quality gate check, by default False.
    dry_run : bool, optional
        Build and check artifacts without uploading to PyPI, by default False.

    Returns
    -------
    int
        0 on success, 1 on failure.
    """
    if root_dir is None:
        from project_forge.project import find_project_root

        root_dir = find_project_root()

    # 1. Quality gate verification
    if not skip_quality:
        from project_forge.quality import run_quality_gate

        console.print(
            "[bold cyan]Step 1: Running Pre-Publish Quality Gate Verification...[/bold cyan]"
        )
        exit_code = run_quality_gate(tier="full", export="cli", root_dir=root_dir)
        if exit_code != 0:
            console.print("[bold red]Publish aborted: Quality Gate checks failed.[/bold red]")
            return exit_code

    # 2. Clean existing artifacts in dist/
    dist_dir = root_dir / "dist"
    if dist_dir.exists():
        console.print("[dim]Cleaning existing distribution packages from dist/...[/dim]")
        for pkg in list(dist_dir.glob("*.whl")) + list(dist_dir.glob("*.tar.gz")):
            try:
                pkg.unlink()
            except OSError:
                pass

    # 3. Build distribution packages using uv build
    console.print(
        "\n[bold cyan]Step 2: Building distribution packages with 'uv build'...[/bold cyan]"
    )
    build_proc = run_process(["uv", "build"], cwd=root_dir)
    if not build_proc.passed:
        console.print(f"[bold red]✘ uv build failed:[/bold red] {build_proc.stderr}")
        return build_proc.exit_code

    built_packages = [str(p) for p in dist_dir.glob("*.whl")] + [
        str(p) for p in dist_dir.glob("*.tar.gz")
    ]
    if not built_packages:
        console.print("[bold red]✘ Error: No packages found in dist/ after uv build.[/bold red]")
        return 1

    console.print(f"[bold green]✔ Built {len(built_packages)} package artifact(s):[/bold green]")
    for pkg_path in built_packages:
        console.print(f"  • {Path(pkg_path).name}")

    if dry_run:
        console.print(
            "\n[yellow]DRY-RUN Mode: Packages built successfully. Skipping PyPI upload.[/yellow]"
        )
        return 0

    # 4. Publish packages with uv publish
    token = load_pypi_token(root_dir)
    if not token:
        console.print(
            "\n[bold red]✘ PyPI Publish Error: No UV_PUBLISH_TOKEN or PYPI_TOKEN found in .env or environment.[/bold red]\n"
            "[dim]Please add UV_PUBLISH_TOKEN=pypi-... to your .env file or environment.[/dim]"
        )
        return 1

    console.print(
        "\n[bold cyan]Step 3: Publishing distribution packages to PyPI with 'uv publish'...[/bold cyan]"
    )
    publish_env = {"UV_PUBLISH_TOKEN": token}
    publish_cmd = ["uv", "publish"] + built_packages
    pub_proc = run_process(publish_cmd, cwd=root_dir, env=publish_env)
    if not pub_proc.passed:
        console.print(f"[bold red]✘ uv publish failed:[/bold red] {pub_proc.stderr}")
        return pub_proc.exit_code

    console.print("[bold green]✔ Successfully published release packages to PyPI![/bold green]")
    return 0
