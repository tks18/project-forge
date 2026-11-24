"""Unit tests for project and repository discovery helpers."""

from pathlib import Path
from project_forge.project import find_project_root, read_project_metadata


def test_find_project_root(tmp_path: Path):
    """Verify finding project root traversing upwards."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    sub_dir = repo_root / "src" / "pkg"
    sub_dir.mkdir(parents=True)

    found = find_project_root(sub_dir)
    assert found == repo_root


def test_read_project_metadata(tmp_path: Path):
    """Verify reading name and version from pyproject.toml."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "my-awesome-tool"
version = "2.3.4"
description = "A powerful CLI utility"
""",
        encoding="utf-8",
    )
    metadata = read_project_metadata(tmp_path)
    assert metadata["name"] == "my-awesome-tool"
    assert metadata["version"] == "2.3.4"
    assert metadata["description"] == "A powerful CLI utility"

