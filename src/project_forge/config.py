"""Configuration schema and loader for Project Forge."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class GitConfig(BaseModel):
    """Git branch configuration."""

    development_branch: str = "dev"
    default_branch: str = "main"


class QualityConfig(BaseModel):
    """Quality gate engines and tiers configuration."""

    fast: list[str] = Field(default_factory=lambda: ["ruff-check", "ruff-format", "mypy"])
    full: list[str] = Field(
        default_factory=lambda: ["ruff-check", "ruff-format", "mypy", "pyright", "pytest"]
    )
    extra_paths: list[str] = Field(default_factory=list)


class CommitsConfig(BaseModel):
    """Conventional commit behavior configuration."""

    header_max_length: int = 72
    overrides_file: str = ".commit_overrides.json"
    scope_overrides: dict[str, str] = Field(default_factory=dict)


class DocsConfig(BaseModel):
    """Documentation auditor policies."""

    require_module_docstrings: bool = True
    require_package_ownership: bool = False
    require_init_docs: bool = False
    include_private: bool = False


class BumpConfig(BaseModel):
    """Version bumper and changelog generator configuration."""

    tag_prefix: str = "v"
    files: list[str] = Field(default_factory=lambda: ["pyproject.toml", "package.json"])
    commit_all: bool = True
    changelog_file: str = "CHANGELOG.md"
    sync_uv: bool = True


class ProjectForgeConfig(BaseModel):
    """Top-level configuration loaded from [tool.project-forge]."""

    source: list[str] = Field(default_factory=lambda: ["src"])
    tests: list[str] = Field(default_factory=lambda: ["tests"])
    changelog: str = "CHANGELOG.md"
    git: GitConfig = Field(default_factory=GitConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)
    commits: CommitsConfig = Field(default_factory=CommitsConfig)
    docs: DocsConfig = Field(default_factory=DocsConfig)
    bump: BumpConfig = Field(default_factory=BumpConfig)


def load_config(root_dir: Path | None = None) -> ProjectForgeConfig:
    """Load configuration from pyproject.toml [tool.project-forge] section.

    If pyproject.toml does not exist or has no [tool.project-forge] section,
    safe defaults are returned.

    Parameters
    ----------
    root_dir : Path | None, optional
        Project root directory, by default None (searched from cwd).

    Returns
    -------
    ProjectForgeConfig
        Loaded and validated configuration model.
    """
    if root_dir is None:
        from project_forge.project import find_project_root

        root_dir = find_project_root()

    pyproject_file = root_dir / "pyproject.toml"
    if not pyproject_file.is_file():
        return ProjectForgeConfig()

    try:
        content = pyproject_file.read_bytes()
        data: dict[str, Any] = tomllib.loads(content.decode("utf-8"))
        tool_section = data.get("tool", {}).get("project-forge", {})
        return ProjectForgeConfig.model_validate(tool_section)
    except Exception as exc:
        raise ValueError(
            f"Failed to parse [tool.project-forge] in {pyproject_file}: {exc}"
        ) from exc
