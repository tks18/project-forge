"""Unit tests for Project Forge configuration schema and loading."""

from pathlib import Path
from project_forge.config import ProjectForgeConfig, load_config


def test_default_config():
    """Verify default configuration has expected values."""
    cfg = ProjectForgeConfig()
    assert cfg.source == ["src"]
    assert cfg.tests == ["tests"]
    assert cfg.changelog == "CHANGELOG.md"
    assert cfg.git.development_branch == "dev"
    assert cfg.git.default_branch == "main"
    assert "ruff-check" in cfg.quality.fast
    assert cfg.commits.header_max_length == 72
    assert cfg.bump.tag_prefix == "v"


def test_load_config_non_existent(tmp_path: Path):
    """Verify loading config from empty dir returns defaults."""
    cfg = load_config(tmp_path)
    assert cfg.source == ["src"]
    assert cfg.git.development_branch == "dev"


def test_load_config_custom_toml(tmp_path: Path):
    """Verify loading custom [tool.project-forge] settings."""
    toml_content = """
[project]
name = "custom-project"
version = "1.0.0"

[tool.project-forge]
source = ["lib"]
tests = ["unit_tests"]
changelog = "RELEASES.md"

[tool.project-forge.git]
development_branch = "develop"
default_branch = "master"

[tool.project-forge.quality]
fast = ["ruff-check"]
full = ["ruff-check", "pytest"]

[tool.project-forge.commits]
header_max_length = 80
"""
    (tmp_path / "pyproject.toml").write_text(toml_content, encoding="utf-8")
    cfg = load_config(tmp_path)

    assert cfg.source == ["lib"]
    assert cfg.tests == ["unit_tests"]
    assert cfg.changelog == "RELEASES.md"
    assert cfg.git.development_branch == "develop"
    assert cfg.git.default_branch == "master"
    assert cfg.quality.fast == ["ruff-check"]
    assert cfg.commits.header_max_length == 80

