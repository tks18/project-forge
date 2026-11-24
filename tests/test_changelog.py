"""Unit tests for changelog parsing, validation, and extraction."""

from pathlib import Path
from project_forge.changelog import (
    get_latest_release,
    get_release_by_version,
    parse_changelog,
    resolve_git_tag,
    validate_changelog,
)

SAMPLE_CHANGELOG = """# Changelog

All notable changes are documented here.

## [1.2.0] - 2026-11-20

### Features 🔥
- **auth**: add oauth2 support

### Bug Fixes 🛠
- **session**: resolve timeout leak

## [1.1.0] - 2026-10-15

### Features 🔥
- **cli**: add doctor command

## 1.0.0 (2026-09-01)

### Features 🔥
- initial release
"""


def test_parse_changelog(tmp_path: Path):
    """Verify parsing multiple release sections with various header formats."""
    cl_file = tmp_path / "CHANGELOG.md"
    cl_file.write_text(SAMPLE_CHANGELOG, encoding="utf-8")

    releases = parse_changelog(cl_file)
    assert len(releases) == 3
    assert releases[0].version == "1.2.0"
    assert releases[0].date == "2026-11-20"
    assert "oauth2 support" in releases[0].body

    assert releases[1].version == "1.1.0"
    assert releases[2].version == "1.0.0"


def test_get_latest_release(tmp_path: Path):
    """Verify extracting latest release."""
    cl_file = tmp_path / "CHANGELOG.md"
    cl_file.write_text(SAMPLE_CHANGELOG, encoding="utf-8")

    latest = get_latest_release(cl_file)
    assert latest is not None
    assert latest.version == "1.2.0"


def test_get_release_by_version(tmp_path: Path):
    """Verify looking up release by version string."""
    cl_file = tmp_path / "CHANGELOG.md"
    cl_file.write_text(SAMPLE_CHANGELOG, encoding="utf-8")

    rel1 = get_release_by_version(cl_file, "1.1.0")
    assert rel1 is not None
    assert rel1.version == "1.1.0"

    rel2 = get_release_by_version(cl_file, "v1.2.0")
    assert rel2 is not None
    assert rel2.version == "1.2.0"

    assert get_release_by_version(cl_file, "9.9.9") is None


def test_validate_changelog(tmp_path: Path):
    """Verify changelog validation."""
    cl_file = tmp_path / "CHANGELOG.md"
    cl_file.write_text(SAMPLE_CHANGELOG, encoding="utf-8")
    valid, errors = validate_changelog(cl_file)
    assert valid
    assert len(errors) == 0

    empty_file = tmp_path / "EMPTY.md"
    empty_file.write_text("# Empty\nNo releases here", encoding="utf-8")
    valid2, errors2 = validate_changelog(empty_file)
    assert not valid2
    assert len(errors2) > 0


def test_resolve_git_tag():
    """Verify matching changelog version to Git tags."""
    tags = {"v1.2.0", "1.1.0", "v1.0.0"}
    assert resolve_git_tag("1.2.0", tags) == "v1.2.0"
    assert resolve_git_tag("v1.1.0", tags) == "1.1.0"
    assert resolve_git_tag("2.0.0", tags) is None

