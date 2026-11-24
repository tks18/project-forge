"""Consolidated changelog parser, validator, and release notes extractor."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ReleaseNotes:
    """Parsed release section from a CHANGELOG.md file."""

    version: str
    raw_version: str
    title: str
    date: str | None
    body: str

    @property
    def clean_version(self) -> str:
        """Version string with leading 'v' stripped."""
        return self.version.lstrip("v")


def parse_changelog(changelog_path: Path) -> list[ReleaseNotes]:
    """Parse CHANGELOG.md and extract all release sections.

    Supports Markdown headers like:
    - ## [1.2.0] - 2026-11-24
    - ## [v1.2.0] (2026-11-24)
    - ## 1.2.0
    - ### [1.2.0]

    Parameters
    ----------
    changelog_path : Path
        Path to the changelog file.

    Returns
    -------
    list[ReleaseNotes]
        Ordered list of parsed releases (latest first).
    """
    if not changelog_path.is_file():
        return []

    content = changelog_path.read_text(encoding="utf-8", errors="replace")

    # Match header line containing version
    # e.g.: ## [1.2.3] or ## v1.2.3 or ### [1.2.3] - 2026-01-01
    header_pattern = re.compile(
        r"^#{2,3}\s+(?:\[(?P<ver_bracket>v?\d+\.\d+\.\d+[^\s\]]*)\]|(?P<ver_plain>v?\d+\.\d+\.\d+[^\s\(]*))"
        r"(?:\s*[-–—]?\s*(?:\((?P<date_paren>[^)]+)\)|(?P<date_plain>\d{4}-\d{2}-\d{2})))?",
        re.MULTILINE,
    )

    matches = list(header_pattern.finditer(content))
    releases: list[ReleaseNotes] = []

    for i, match in enumerate(matches):
        raw_ver = (match.group("ver_bracket") or match.group("ver_plain") or "").strip()
        version = raw_ver.lstrip("v")
        date_str = match.group("date_paren") or match.group("date_plain")
        if date_str:
            date_str = date_str.strip()

        start_idx = match.start()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(content)

        raw_body = content[start_idx:end_idx].strip()
        # Normalize top-level header of section to ## if it was ###
        body = "## " + raw_body[4:] if raw_body.startswith("### ") else raw_body

        releases.append(
            ReleaseNotes(
                version=version,
                raw_version=raw_ver,
                title=f"Release - v{version}",
                date=date_str,
                body=body,
            )
        )

    return releases


def get_latest_release(changelog_path: Path) -> ReleaseNotes | None:
    """Return the most recent release entry in CHANGELOG.md.

    Parameters
    ----------
    changelog_path : Path
        Path to CHANGELOG.md.

    Returns
    -------
    ReleaseNotes | None
        The latest release notes, or None if changelog is empty/missing.
    """
    releases = parse_changelog(changelog_path)
    return releases[0] if releases else None


def get_release_by_version(changelog_path: Path, version: str) -> ReleaseNotes | None:
    """Retrieve specific release notes by target version.

    Parameters
    ----------
    changelog_path : Path
        Path to CHANGELOG.md.
    version : str
        Target version (e.g. '1.2.0' or 'v1.2.0').

    Returns
    -------
    ReleaseNotes | None
        Matching release notes, or None if not found.
    """
    clean_target = version.lstrip("v").strip()
    releases = parse_changelog(changelog_path)
    for rel in releases:
        if rel.clean_version == clean_target:
            return rel
    return None


def validate_changelog(changelog_path: Path) -> tuple[bool, list[str]]:
    """Validate CHANGELOG.md existence and formatting.

    Parameters
    ----------
    changelog_path : Path
        Path to CHANGELOG.md.

    Returns
    -------
    tuple[bool, list[str]]
        (is_valid, error_messages)
    """
    errors: list[str] = []
    if not changelog_path.exists():
        errors.append(f"Changelog file does not exist: {changelog_path}")
        return False, errors

    releases = parse_changelog(changelog_path)
    if not releases:
        errors.append(
            "No valid SemVer release headers found in changelog (expected '## [X.Y.Z]' or '## X.Y.Z')."
        )
        return False, errors

    return True, []


def resolve_git_tag(
    version: str,
    existing_tags: set[str],
    tag_prefix: str = "v",
) -> str | None:
    """Match a version string against existing git tags.

    Checks '{tag_prefix}{clean_ver}' first, then '{clean_ver}'.

    Parameters
    ----------
    version : str
        Version to match.
    existing_tags : set[str]
        Set of available git tags in repository.
    tag_prefix : str, optional
        Tag prefix (default 'v').

    Returns
    -------
    str | None
        The matching tag name in existing_tags, or None if not found.
    """
    clean_ver = version.lstrip("v").strip()
    candidates = [f"{tag_prefix}{clean_ver}", clean_ver]
    for cand in candidates:
        if cand in existing_tags:
            return cand
    return None
