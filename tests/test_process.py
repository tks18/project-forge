"""Unit tests for subprocess execution runner."""

import sys
from project_forge.process import run_process


def test_run_process_success():
    """Verify running a successful command."""
    res = run_process([sys.executable, "-c", "print('hello project forge')"])
    assert res.passed
    assert res.exit_code == 0
    assert "hello project forge" in res.stdout
    assert res.duration_seconds > 0


def test_run_process_failure():
    """Verify running a failing command captures exit code and output."""
    res = run_process(
        [sys.executable, "-c", "import sys; sys.stderr.write('fatal error'); sys.exit(42)"]
    )
    assert not res.passed
    assert res.exit_code == 42
    assert "fatal error" in res.stderr
    assert "fatal error" in res.combined_output


def test_run_process_non_existent():
    """Verify non-existent executable returns exit code 127."""
    res = run_process(["non_existent_binary_xyz_12345"])
    assert not res.passed
    assert res.exit_code == 127
    assert "not found" in res.stderr.lower()
