"""Unit tests for repository-neutral Conventional Commit automation."""

from project_forge.commits import (
    ChangedFile,
    build_commit_groups,
    format_commit_header,
    infer_commit_message,
    infer_scope,
)


def test_format_commit_header_length():
    """Verify commit header formatting strictly adheres to maximum character limit."""
    header = format_commit_header("feat(auth)", "a" * 100, max_length=72)
    assert len(header) <= 72
    assert header.startswith("feat(auth): ")


def test_infer_scope():
    """Verify repository-neutral scope inference across sources, tests, configs."""
    # Source file in src/project_forge/cli.py -> cli
    assert infer_scope("src/project_forge/cli.py", source_roots=["src"]) == "cli"

    # Deep source file src/project_forge/domain/entity.py -> domain
    assert infer_scope("src/project_forge/domain/entity.py", source_roots=["src"]) == "domain"

    # Test file
    assert infer_scope("tests/test_quality.py") == "quality"

    # CI & configs
    assert infer_scope(".githooks/pre-commit") == "hooks"
    assert infer_scope(".github/workflows/ci.yml") == "ci"
    assert infer_scope(".plan/README.md") == "planning"


def test_infer_commit_message():
    """Verify inferring conventional commit types and scopes."""
    # Modified source
    f_src = ChangedFile(status="M", filepath="src/project_forge/process.py")
    msg_src = infer_commit_message(f_src, source_roots=["src"])
    assert msg_src == "refactor(process): update process"

    # Added test
    f_test = ChangedFile(status="A", filepath="tests/test_auth.py")
    msg_test = infer_commit_message(f_test)
    assert msg_test == "test(auth): update test suite"

    # Config file
    f_cfg = ChangedFile(status="M", filepath="ruff.toml")
    msg_cfg = infer_commit_message(f_cfg)
    assert msg_cfg == "ci(ruff): update tool configuration"

    # Deleted file
    f_del = ChangedFile(status="D", filepath="src/project_forge/old_helper.py")
    msg_del = infer_commit_message(f_del, source_roots=["src"])
    assert "remove deprecated" in msg_del


def test_build_commit_groups():
    """Verify grouping changed files by message and handling overrides."""
    files = [
        ChangedFile(status="M", filepath="src/project_forge/cli.py"),
        ChangedFile(status="M", filepath="src/project_forge/doctor.py"),
        ChangedFile(status="M", filepath="tests/test_cli.py"),
    ]
    overrides = {
        "feat(cli): enhance cli with doctor command": [
            "src/project_forge/cli.py",
            "src/project_forge/doctor.py",
        ]
    }
    groups = build_commit_groups(files, overrides, source_roots=["src"])
    assert len(groups) == 2
    assert groups[0].message == "feat(cli): enhance cli with doctor command"
    assert len(groups[0].files) == 2

    # Remaining file inferred
    assert groups[1].message == "test(cli): update test suite"
    assert len(groups[1].files) == 1

