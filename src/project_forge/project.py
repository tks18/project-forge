"""Project and Git repository discovery helpers."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from project_forge.process import run_process


def find_project_root(start_dir: Path | None = None) -> Path:
    """Find the root directory of the project by checking parent directories.

    Checks for pyproject.toml, .git, or CHANGELOG.md.

    Parameters
    ----------
    start_dir : Path | None, optional
        Starting path, by default current working directory.

    Returns
    -------
    Path
        Resolved project root path.
    """
    current = (start_dir or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate
    return current


def read_project_metadata(root_dir: Path) -> dict[str, str]:
    """Read project name, version, and description from pyproject.toml.

    Parameters
    ----------
    root_dir : Path
        Project root directory containing pyproject.toml.

    Returns
    -------
    dict[str, str]
        Metadata dictionary containing name, version, description.
    """
    pyproject_path = root_dir / "pyproject.toml"
    metadata = {
        "name": root_dir.name,
        "version": "0.1.0",
        "description": "",
    }
    if not pyproject_path.exists():
        return metadata

    try:
        content = pyproject_path.read_bytes()
        data: dict[str, Any] = tomllib.loads(content.decode("utf-8"))
        project_dict = data.get("project", {})
        metadata["name"] = project_dict.get("name", root_dir.name)
        metadata["version"] = project_dict.get("version", "0.1.0")
        metadata["description"] = project_dict.get("description", "")
    except Exception:
        pass

    return metadata


def get_git_branch(root_dir: Path) -> str:
    """Get the current git branch name.

    Parameters
    ----------
    root_dir : Path
        Project root directory.

    Returns
    -------
    str
        Current branch name or 'HEAD' if detached/unknown.
    """
    res = run_process(["git", "branch", "--show-current"], cwd=root_dir)
    branch = res.stdout.strip()
    if not branch:
        res_head = run_process(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root_dir)
        branch = res_head.stdout.strip()
    return branch or "unknown"


def get_git_tags(root_dir: Path) -> set[str]:
    """Get all git tags in the repository.

    Parameters
    ----------
    root_dir : Path
        Project root directory.

    Returns
    -------
    set[str]
        Set of tag strings.
    """
    res = run_process(["git", "tag"], cwd=root_dir)
    if res.passed and res.stdout.strip():
        return set(res.stdout.strip().splitlines())
    return set()


def get_dirty_files(root_dir: Path) -> list[str]:
    """Get list of uncommitted changed files from git status porcelain.

    Parameters
    ----------
    root_dir : Path
        Project root directory.

    Returns
    -------
    list[str]
        List of changed file paths.
    """
    res = run_process(["git", "status", "--porcelain"], cwd=root_dir)
    if not res.passed or not res.stdout.strip():
        return []
    files: list[str] = []
    for line in res.stdout.splitlines():
        if len(line) > 3:
            raw_path = line[3:].strip().strip('"')
            if " -> " in raw_path:
                _, raw_path = raw_path.split(" -> ", 1)
            files.append(raw_path.strip().strip('"'))
    return files


def is_git_clean(root_dir: Path) -> bool:
    """Check if git working tree has no uncommitted changes.

    Parameters
    ----------
    root_dir : Path
        Project root directory.

    Returns
    -------
    bool
        True if clean, False otherwise.
    """
    return len(get_dirty_files(root_dir)) == 0

