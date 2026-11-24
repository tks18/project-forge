"""Unified subprocess execution runner for Project Forge."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcessResult:
    """Result of an executed subprocess."""

    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float

    @property
    def passed(self) -> bool:
        """Return True if command returned zero exit code."""
        return self.exit_code == 0

    @property
    def combined_output(self) -> str:
        """Return combined stdout and stderr."""
        out = self.stdout.strip()
        err = self.stderr.strip()
        if out and err:
            return f"{out}\n{err}"
        return out or err


def run_process(
    command: list[str],
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = True,
    text: bool = True,
    check: bool = False,
    timeout: float | None = None,
) -> ProcessResult:
    """Execute a subprocess command with unified error and duration handling.

    Parameters
    ----------
    command : list[str]
        Command arguments list.
    cwd : Path | str | None, optional
        Working directory for the process, by default None.
    env : dict[str, str] | None, optional
        Environment variables dictionary, by default None (inherits os.environ).
    capture_output : bool, optional
        Whether to capture stdout and stderr, by default True.
    text : bool, optional
        Whether to decode output as string, by default True.
    check : bool, optional
        Whether to raise CalledProcessError on non-zero exit code, by default False.
    timeout : float | None, optional
        Command timeout in seconds, by default None.

    Returns
    -------
    ProcessResult
        Populated result object with execution metrics.
    """
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=proc_env,
            capture_output=capture_output,
            text=text,
            encoding="utf-8" if text else None,
            errors="replace" if text else None,
            check=check,
            timeout=timeout,
        )
        duration = time.perf_counter() - t0
        return ProcessResult(
            command=command,
            exit_code=proc.returncode,
            stdout=proc.stdout or "" if text else "",
            stderr=proc.stderr or "" if text else "",
            duration_seconds=duration,
        )
    except subprocess.CalledProcessError as exc:
        duration = time.perf_counter() - t0
        return ProcessResult(
            command=command,
            exit_code=exc.returncode,
            stdout=exc.stdout or "" if text else "",
            stderr=exc.stderr or "" if text else "",
            duration_seconds=duration,
        )
    except FileNotFoundError as exc:
        duration = time.perf_counter() - t0
        return ProcessResult(
            command=command,
            exit_code=127,
            stdout="",
            stderr=f"Executable not found: {command[0]} ({exc})",
            duration_seconds=duration,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.perf_counter() - t0
        out_str = (
            exc.stdout.decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        return ProcessResult(
            command=command,
            exit_code=124,
            stdout=out_str if text else "",
            stderr=f"Command timed out after {timeout} seconds",
            duration_seconds=duration,
        )
