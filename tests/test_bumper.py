"""Unit tests for native version bumper and changelog generator."""

from pathlib import Path
from project_forge.bumper import (
    ParsedCommit,
    calculate_next_version,
    detect_semver_bump,
    generate_changelog_section,
    parse_conventional_commit,
    update_file_version,
)


def test_parse_conventional_commit():
    """Verify parsing conventional commit types, scopes, and breaking changes."""
    c1 = parse_conventional_commit("abc1234", "feat(auth): add login endpoint", "")
    assert c1.commit_type == "feat"
    assert c1.scope == "auth"
    assert c1.description == "add login endpoint"
    assert not c1.is_breaking

    c2 = parse_conventional_commit("def5678", "fix!: drop legacy python support", "")
    assert c2.commit_type == "fix"
    assert c2.is_breaking

    c3 = parse_conventional_commit(
        "ghi9012", "refactor(api): change payload schema", "BREAKING CHANGE: payload renamed"
    )
    assert c3.commit_type == "refactor"
    assert c3.scope == "api"
    assert c3.is_breaking


def test_detect_semver_bump():
    """Verify automatic detection of major, minor, patch bumps."""
    # Breaking change -> major
    commits_major = [
        ParsedCommit("1", "fix: bug", "", "fix"),
        ParsedCommit("2", "feat: new", "", "feat", is_breaking=True),
    ]
    assert detect_semver_bump(commits_major) == "major"

    # Feature -> minor
    commits_minor = [
        ParsedCommit("1", "fix: bug", "", "fix"),
        ParsedCommit("2", "feat: new", "", "feat"),
    ]
    assert detect_semver_bump(commits_minor) == "minor"

    # Fix only -> patch
    commits_patch = [
        ParsedCommit("1", "fix: bug", "", "fix"),
        ParsedCommit("2", "docs: readme", "", "docs"),
    ]
    assert detect_semver_bump(commits_patch) == "patch"


def test_calculate_next_version():
    """Verify SemVer version incrementing."""
    assert calculate_next_version("0.1.0", "patch") == "0.1.1"
    assert calculate_next_version("0.1.0", "minor") == "0.2.0"
    assert calculate_next_version("0.1.0", "major") == "1.0.0"
    assert calculate_next_version("1.2.3", "minor", prerelease="rc") == "1.3.0-rc.0"
    assert calculate_next_version("1.2.3", "2.0.0-beta.1") == "2.0.0b1" or "2.0.0-beta.1"


def test_update_file_version_pyproject(tmp_path: Path):
    """Verify updating pyproject.toml version cleanly."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """[project]
name = "demo"
version = "0.1.0"
description = "Sample"
""",
        encoding="utf-8",
    )
    ok = update_file_version(pyproject, "0.2.0")
    assert ok
    content = pyproject.read_text(encoding="utf-8")
    assert 'version = "0.2.0"' in content


def test_update_file_version_package_json(tmp_path: Path):
    """Verify updating package.json version cleanly."""
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text('{\n  "name": "demo",\n  "version": "1.0.0"\n}\n', encoding="utf-8")
    ok = update_file_version(pkg_json, "1.1.0")
    assert ok
    content = pkg_json.read_text(encoding="utf-8")
    assert '"version": "1.1.0"' in content


def test_update_file_version_init_py(tmp_path: Path):
    """Verify updating __version__ in __init__.py."""
    init_py = tmp_path / "__init__.py"
    init_py.write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    ok = update_file_version(init_py, "0.2.0")
    assert ok
    content = init_py.read_text(encoding="utf-8")
    assert '__version__ = "0.2.0"' in content


def test_update_file_version_init_py_without_version(tmp_path: Path):
    """Verify __init__.py without __version__ is NOT modified."""
    init_py = tmp_path / "__init__.py"
    init_py.write_text('from .sub import something\n', encoding="utf-8")
    ok = update_file_version(init_py, "0.2.0")
    assert not ok
    assert '__version__' not in init_py.read_text(encoding="utf-8")


def test_update_file_version_version_info(tmp_path: Path):
    """Verify version_info.txt tuple and string struct updates."""
    ver_info = tmp_path / "version_info.txt"
    ver_info.write_text(
        """filevers=(12, 1, 0, 0)
prodvers=(12, 1, 0, 0)
StringStruct('FileVersion', '12.1.0')
StringStruct('ProductVersion', '12.1.0')
""",
        encoding="utf-8",
    )
    ok = update_file_version(ver_info, "12.1.1")
    assert ok
    content = ver_info.read_text(encoding="utf-8")
    assert "filevers=(12, 1, 1, 0)" in content
    assert "prodvers=(12, 1, 1, 0)" in content
    assert "StringStruct('FileVersion', '12.1.1')" in content
    assert "StringStruct('ProductVersion', '12.1.1')" in content


def test_generate_changelog_section():
    """Verify generating Markdown release notes section with conventional categories."""
    commits = [
        ParsedCommit("abc1234", "feat(auth): login", "", "feat", "auth", "login"),
        ParsedCommit(
            "def5678", "fix(db): connection timeout", "", "fix", "db", "connection timeout"
        ),
    ]
    section = generate_changelog_section("0.2.0", "2026-11-24", commits)
    assert "## [0.2.0] - 2026-11-24" in section
    assert "### Features 🔥" in section
    assert "- **auth**: login ([abc1234](commit/abc1234))" in section
    assert "### Bug Fixes 🛠" in section
    assert "- **db**: connection timeout ([def5678](commit/def5678))" in section
