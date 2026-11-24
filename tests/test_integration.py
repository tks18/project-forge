"""End-to-end integration tests using an isolated temporary Git repository."""

from pathlib import Path
from project_forge.process import run_process


def test_e2e_git_repo_workflow(tmp_path: Path):
    """Verify end-to-end Project Forge operations inside an isolated Git repository."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # 1. Initialize git repo
    run_process(["git", "init", "-b", "main"], cwd=repo_dir)
    run_process(["git", "config", "user.name", "Test User"], cwd=repo_dir)
    run_process(["git", "config", "user.email", "test@example.com"], cwd=repo_dir)

    # 2. Create minimal pyproject.toml and source
    (repo_dir / "pyproject.toml").write_text(
        """[project]
name = "test-repo"
version = "0.1.0"
description = "Integration test repository"

[tool.project-forge]
source = ["src"]
tests = ["tests"]
changelog = "CHANGELOG.md"
""",
        encoding="utf-8",
    )
    (repo_dir / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.1.0] - 2026-11-24\n\n### Features 🔥\n- initial\n",
        encoding="utf-8",
    )
    src_dir = repo_dir / "src" / "test_repo"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text('"""Init."""\n__version__ = "0.1.0"\n', encoding="utf-8")
    (src_dir / "core.py").write_text(
        '"""Core module."""\ndef run():\n    return 42\n', encoding="utf-8"
    )

    # Initial commit
    run_process(["git", "add", "."], cwd=repo_dir)
    run_process(["git", "commit", "-m", "chore: initial commit"], cwd=repo_dir)
    run_process(["git", "tag", "-a", "v0.1.0", "-m", "chore(release): v0.1.0"], cwd=repo_dir)

    # 3. Add a new feature commit
    (src_dir / "feature.py").write_text(
        '"""Feature module."""\ndef feat():\n    return True\n', encoding="utf-8"
    )

    # 4. Run pforge status via CLI in repo_dir
    res_status = run_process(["uv", "run", "pforge", "status"], cwd=repo_dir)
    assert res_status.passed
    assert "test-repo" in res_status.stdout
    assert "0.1.0" in res_status.stdout

    # 5. Run pforge commit --preview
    res_commit_preview = run_process(["uv", "run", "pforge", "commit", "--preview"], cwd=repo_dir)
    assert res_commit_preview.passed
    assert "Planned Commit Groups" in res_commit_preview.stdout

    # 6. Run pforge changelog validate
    res_cl_val = run_process(["uv", "run", "pforge", "changelog", "validate"], cwd=repo_dir)
    assert res_cl_val.passed

    # 7. Run pforge bump --dry-run with --patch, --minor, --major flags
    res_bump_patch = run_process(
        ["uv", "run", "pforge", "bump", "--dry-run", "--patch"], cwd=repo_dir
    )
    assert res_bump_patch.passed
    assert "0.1.1" in res_bump_patch.stdout

    res_bump_minor = run_process(
        ["uv", "run", "pforge", "bump", "--dry-run", "--minor"], cwd=repo_dir
    )
    assert res_bump_minor.passed
    assert "0.2.0" in res_bump_minor.stdout

    res_bump_major = run_process(
        ["uv", "run", "pforge", "bump", "--dry-run", "--major"], cwd=repo_dir
    )
    assert res_bump_major.passed
    assert "1.0.0" in res_bump_major.stdout

    # 8. Verify release pipeline command exists
    res_release_help = run_process(["uv", "run", "pforge", "release", "--help"], cwd=repo_dir)
    assert res_release_help.passed
    assert "pipeline" in res_release_help.stdout
