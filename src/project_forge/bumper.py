"""Native Python standard-version replacement for version bumping and changelog generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import tomlkit
from packaging.version import InvalidVersion, Version

from project_forge.process import run_process


@dataclass
class ParsedCommit:
    """Structured representation of a conventional commit."""

    commit_hash: str
    subject: str
    body: str
    commit_type: str = "chore"
    scope: str = ""
    description: str = ""
    is_breaking: bool = False


# Map conventional commit types to section titles and icons
CATEGORY_MAP: dict[str, str] = {
    "feat": "Features 🔥",
    "fix": "Bug Fixes 🛠",
    "perf": "Performance Improvements 🏎",
    "refactor": "Code Refactoring 🖌",
    "docs": "Documentation 📃",
    "test": "Tests 🧪",
    "build": "Build System 🏗",
    "ci": "CI / Tooling 🛠",
    "style": "Styling 🎨",
    "revert": "Reverts ◀",
    "chore": "Others 🔧",
}


def parse_conventional_commit(commit_hash: str, subject: str, body: str) -> ParsedCommit:
    """Parse conventional commit header and body for type, scope, breaking changes.

    Parameters
    ----------
    commit_hash : str
        Git commit hash (short or full).
    subject : str
        First line of commit message.
    body : str
        Remaining lines of commit message.

    Returns
    -------
    ParsedCommit
        Parsed commit representation.
    """
    # Regex: ^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+(?P<desc>.+)$
    pattern = re.compile(
        r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+(?P<desc>.+)$"
    )
    match = pattern.match(subject.strip())

    is_breaking = False
    if "BREAKING CHANGE:" in body or "BREAKING-CHANGE:" in body:
        is_breaking = True

    if match:
        c_type = match.group("type").lower()
        scope = match.group("scope") or ""
        breaking_mark = match.group("breaking")
        if breaking_mark:
            is_breaking = True
        desc = match.group("desc").strip()
        return ParsedCommit(
            commit_hash=commit_hash,
            subject=subject.strip(),
            body=body.strip(),
            commit_type=c_type,
            scope=scope,
            description=desc,
            is_breaking=is_breaking,
        )

    # Fallback non-conventional commit
    return ParsedCommit(
        commit_hash=commit_hash,
        subject=subject.strip(),
        body=body.strip(),
        commit_type="chore",
        scope="",
        description=subject.strip(),
        is_breaking=is_breaking,
    )


def get_commits_since_last_tag(
    root_dir: Path,
    tag_prefix: str = "v",
    first_release: bool = False,
) -> tuple[str | None, list[ParsedCommit]]:
    """Get all commits since the last release tag.

    Parameters
    ----------
    root_dir : Path
        Repository root directory.
    tag_prefix : str, optional
        Tag prefix, by default "v".
    first_release : bool, optional
        If True, returns all commits from repository beginning.

    Returns
    -------
    tuple[str | None, list[ParsedCommit]]
        (latest_tag, list_of_parsed_commits)
    """
    latest_tag: str | None = None
    if not first_release:
        # Find latest tag matching pattern
        tag_proc = run_process(
            ["git", "describe", "--tags", "--abbrev=0", f"--match={tag_prefix}*"],
            cwd=root_dir,
        )
        if tag_proc.passed and tag_proc.stdout.strip():
            latest_tag = tag_proc.stdout.strip()
        else:
            # Try without prefix
            tag_proc2 = run_process(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=root_dir,
            )
            if tag_proc2.passed and tag_proc2.stdout.strip():
                latest_tag = tag_proc2.stdout.strip()

    # Log command with field separator (%x1f) and record separator (%x1e)
    # %h: short hash, %s: subject, %b: body
    log_range = f"{latest_tag}..HEAD" if latest_tag else "HEAD"
    cmd = [
        "git",
        "log",
        log_range,
        "--format=%h%x1f%s%x1f%b%x1e",
    ]
    log_proc = run_process(cmd, cwd=root_dir)
    if not log_proc.passed or not log_proc.stdout.strip():
        return latest_tag, []

    commits: list[ParsedCommit] = []
    records = log_proc.stdout.split("\x1e")
    for rec in records:
        rec = rec.strip()
        if not rec:
            continue
        parts = rec.split("\x1f")
        h = parts[0].strip() if len(parts) > 0 else ""
        s = parts[1].strip() if len(parts) > 1 else ""
        b = parts[2].strip() if len(parts) > 2 else ""
        if not s:
            continue
        # Skip release commits from appearing in changelog
        if s.startswith("chore(release):") or s.startswith("release:"):
            continue
        commits.append(parse_conventional_commit(h, s, b))

    return latest_tag, commits


def detect_semver_bump(commits: list[ParsedCommit]) -> str:
    """Analyze conventional commits to determine SemVer increment.

    Parameters
    ----------
    commits : list[ParsedCommit]
        List of parsed commits since last release.

    Returns
    -------
    str
        'major', 'minor', or 'patch'
    """
    if not commits:
        return "patch"

    has_breaking = any(c.is_breaking for c in commits)
    if has_breaking:
        return "major"

    has_feat = any(c.commit_type == "feat" for c in commits)
    if has_feat:
        return "minor"

    return "patch"


def calculate_next_version(
    current_version: str,
    bump_type: str,
    prerelease: str | None = None,
) -> str:
    """Calculate the next SemVer version string.

    Parameters
    ----------
    current_version : str
        Current version (e.g. '0.1.0' or '1.2.3-beta.1').
    bump_type : str
        'major', 'minor', 'patch', or an explicit version string ('1.0.0').
    prerelease : str | None, optional
        Optional prerelease tag (e.g. 'alpha', 'beta', 'rc').

    Returns
    -------
    str
        New incremented version string.
    """
    clean_curr = current_version.lstrip("v").strip()

    # Check if bump_type is directly an explicit version string
    try:
        explicit_v = Version(bump_type)
        return str(explicit_v)
    except InvalidVersion:
        pass

    try:
        v = Version(clean_curr)
        major = v.major
        minor = v.minor
        micro = v.micro
    except InvalidVersion:
        # Fallback regex parsing
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)", clean_curr)
        if m:
            major, minor, micro = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            major, minor, micro = 0, 1, 0

    bump = bump_type.lower()
    if bump == "major":
        major += 1
        minor = 0
        micro = 0
    elif bump == "minor":
        minor += 1
        micro = 0
    elif bump == "patch":
        micro += 1

    base_ver = f"{major}.{minor}.{micro}"
    if prerelease:
        return f"{base_ver}-{prerelease}.0"
    return base_ver


def update_file_version(
    filepath: Path,
    new_version: str,
) -> bool:
    """Update version string in target file based on file type.

    Parameters
    ----------
    filepath : Path
        Path to file to update.
    new_version : str
        New SemVer version string.

    Returns
    -------
    bool
        True if updated successfully.
    """
    if not filepath.is_file():
        return False

    name = filepath.name.lower()

    if name == "pyproject.toml":
        content = filepath.read_text(encoding="utf-8")
        doc = tomlkit.parse(content)
        if "project" in doc and "version" in doc["project"]:
            doc["project"]["version"] = new_version
            filepath.write_text(tomlkit.dumps(doc), encoding="utf-8")
            return True
        # Fallback regex if tomlkit structure differs
        subbed, count = re.subn(
            r'^(version\s*=\s*")[^"]+(")',
            rf"\g<1>{new_version}\g<2>",
            content,
            flags=re.MULTILINE,
        )
        if count > 0:
            filepath.write_text(subbed, encoding="utf-8")
            return True
        return False

    if name == "package.json":
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            data["version"] = new_version
            filepath.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            return True
        except Exception:
            return False

    if name == "version_info.txt":
        content = filepath.read_text(encoding="utf-8")
        # Convert SemVer '12.1.1' to '12, 1, 1, 0' for Windows fixed info
        parts = new_version.split("-")[0].split(".")
        while len(parts) < 4:
            parts.append("0")
        tuple_str = ", ".join(parts[:4])

        content = re.sub(
            r"filevers=\(\d+,\s*\d+,\s*\d+,\s*\d+\)",
            f"filevers=({tuple_str})",
            content,
        )
        content = re.sub(
            r"prodvers=\(\d+,\s*\d+,\s*\d+,\s*\d+\)",
            f"prodvers=({tuple_str})",
            content,
        )
        content = re.sub(
            r"StringStruct\('FileVersion',\s*'[^']+'\)",
            f"StringStruct('FileVersion', '{new_version}')",
            content,
        )
        content = re.sub(
            r"StringStruct\('ProductVersion',\s*'[^']+'\)",
            f"StringStruct('ProductVersion', '{new_version}')",
            content,
        )
        filepath.write_text(content, encoding="utf-8")
        return True

    if name.endswith(".py"):
        content = filepath.read_text(encoding="utf-8")
        subbed, count = re.subn(
            r'(__version__\s*=\s*")[^"]+(")',
            rf"\g<1>{new_version}\g<2>",
            content,
        )
        if count > 0:
            filepath.write_text(subbed, encoding="utf-8")
            return True
        return False

    return False


def generate_changelog_section(
    version: str,
    date_str: str,
    commits: list[ParsedCommit],
    tag_prefix: str = "v",
) -> str:
    """Generate Markdown release notes section grouped by category.

    Parameters
    ----------
    version : str
        New release version (e.g. '0.2.0').
    date_str : str
        Date string (e.g. '2026-11-24').
    commits : list[ParsedCommit]
        List of parsed commits included in release.
    tag_prefix : str, optional
        Prefix for release tag.

    Returns
    -------
    str
        Formatted Markdown text for the section.
    """
    clean_ver = version.lstrip("v")
    lines: list[str] = [
        f"## [{clean_ver}] - {date_str}",
        "",
    ]

    # Group commits by category
    grouped: dict[str, list[ParsedCommit]] = {}
    for c in commits:
        grouped.setdefault(c.commit_type, []).append(c)

    # Order categories according to CATEGORY_MAP
    for c_type, title in CATEGORY_MAP.items():
        type_commits = grouped.get(c_type, [])
        if not type_commits:
            continue

        lines.append(f"### {title}")
        for c in type_commits:
            scope_prefix = f"**{c.scope}**: " if c.scope else ""
            breaking_note = " **(BREAKING CHANGE)**" if c.is_breaking else ""
            hash_suffix = f" ([{c.commit_hash}](commit/{c.commit_hash}))" if c.commit_hash else ""
            lines.append(f"- {scope_prefix}{c.description}{breaking_note}{hash_suffix}")
        lines.append("")

    return "\n".join(lines).strip()


def prepend_to_changelog(changelog_path: Path, new_section: str) -> None:
    """Insert new release section at the top of CHANGELOG.md under title.

    Parameters
    ----------
    changelog_path : Path
        Path to CHANGELOG.md.
    new_section : str
        Formatted markdown section to insert.
    """
    title = "# Changelog\n\nAll notable changes to this project will be documented in this file.\n"
    if not changelog_path.exists():
        changelog_path.write_text(f"{title}\n{new_section}\n", encoding="utf-8")
        return

    existing = changelog_path.read_text(encoding="utf-8")
    # Check if starts with a markdown H1 title
    title_match = re.match(r"^(#\s+[^\n]+\n+)", existing)
    if title_match:
        header = title_match.group(1)
        rest = existing[title_match.end() :].lstrip()
        updated = f"{header}\n{new_section}\n\n{rest}"
    else:
        updated = f"{title}\n{new_section}\n\n{existing.lstrip()}"

    changelog_path.write_text(updated, encoding="utf-8")


def run_bump(
    root_dir: Path,
    release_as: str | None = None,
    prerelease: str | None = None,
    first_release: bool = False,
    dry_run: bool = False,
    no_commit: bool = False,
    no_tag: bool = False,
    tag_prefix: str = "v",
    pipeline: bool = False,
) -> tuple[int, str]:
    """Execute complete native SemVer bump and changelog generation.

    Parameters
    ----------
    root_dir : Path
        Project root directory.
    release_as : str | None, optional
        'patch', 'minor', 'major', or specific version ('1.2.0').
    prerelease : str | None, optional
        Prerelease identifier ('alpha', 'beta', 'rc').
    first_release : bool, optional
        Whether this is the first release.
    dry_run : bool, optional
        Preview without writing files or making Git commits.
    no_commit : bool, optional
        Skip creating Git release commit.
    no_tag : bool, optional
        Skip creating Git release tag.
    tag_prefix : str, optional
        Tag prefix, by default 'v'.
    pipeline : bool, optional
        Whether to execute post-release pipeline after bumping, by default False.

    Returns
    -------
    tuple[int, str]
        (exit_code, new_version)
    """
    from project_forge.config import load_config
    from project_forge.project import read_project_metadata

    cfg = load_config(root_dir)
    metadata = read_project_metadata(root_dir)
    current_version = metadata.get("version", "0.1.0")

    _last_tag, commits = get_commits_since_last_tag(
        root_dir,
        tag_prefix=tag_prefix,
        first_release=first_release,
    )

    # Determine bump type
    bump_type = release_as or detect_semver_bump(commits)
    new_version = calculate_next_version(current_version, bump_type, prerelease)

    today = datetime.now().strftime("%Y-%m-%d")
    changelog_section = generate_changelog_section(
        version=new_version,
        date_str=today,
        commits=commits,
        tag_prefix=tag_prefix,
    )

    target_files: list[Path] = []
    if cfg.bump.files:
        for f_pattern in cfg.bump.files:
            if any(char in f_pattern for char in ("*", "?", "[")):
                for m in root_dir.glob(f_pattern):
                    if m.is_file():
                        if m.suffix == ".py":
                            if "__version__" in m.read_text(encoding="utf-8", errors="ignore"):
                                target_files.append(m)
                        else:
                            target_files.append(m)
            else:
                p = root_dir / f_pattern
                if p.is_file():
                    target_files.append(p)
    else:
        # Default files: pyproject.toml, package.json, and only top-level package __init__.py if __version__ is present
        if (root_dir / "pyproject.toml").is_file():
            target_files.append(root_dir / "pyproject.toml")
        if (root_dir / "package.json").is_file():
            target_files.append(root_dir / "package.json")
        for src_dir in cfg.source:
            src_path = root_dir / src_dir
            if src_path.exists():
                for pkg_dir in src_path.iterdir():
                    if pkg_dir.is_dir():
                        init_f = pkg_dir / "__init__.py"
                        if init_f.is_file() and "__version__" in init_f.read_text(
                            encoding="utf-8", errors="ignore"
                        ):
                            target_files.append(init_f)

    changelog_path = root_dir / cfg.bump.changelog_file

    if dry_run:
        return 0, new_version

    # Update files
    for f in target_files:
        update_file_version(f, new_version)

    # Prepend changelog
    prepend_to_changelog(changelog_path, changelog_section)

    # Update uv.lock if pyproject.toml was updated and sync_uv is enabled
    if cfg.bump.sync_uv and (root_dir / "pyproject.toml") in target_files:
        run_process(["uv", "sync"], cwd=root_dir)

    # Git stage and commit
    if not no_commit:
        paths_to_stage = [str(f.relative_to(root_dir)) for f in target_files if f.exists()]
        if changelog_path.exists():
            paths_to_stage.append(str(changelog_path.relative_to(root_dir)))
        if (root_dir / "uv.lock").exists():
            paths_to_stage.append("uv.lock")

        if cfg.bump.commit_all:
            run_process(["git", "add", "-u"], cwd=root_dir)
        run_process(["git", "add"] + paths_to_stage, cwd=root_dir)

        commit_msg = f"chore(release): {tag_prefix}{new_version}"
        commit_res = run_process(["git", "commit", "-m", commit_msg], cwd=root_dir)
        if not commit_res.passed:
            return 1, new_version

    # Git tag
    if not no_tag:
        tag_name = f"{tag_prefix}{new_version}"
        tag_msg = f"chore(release): {tag_name}"
        tag_res = run_process(["git", "tag", "-a", tag_name, "-m", tag_msg], cwd=root_dir)
        if not tag_res.passed:
            return 1, new_version

    # Execute release pipeline if requested
    if pipeline:
        from project_forge.releases import run_release_pipeline

        pipeline_code = run_release_pipeline(root_dir=root_dir)
        if pipeline_code != 0:
            return pipeline_code, new_version

    return 0, new_version
