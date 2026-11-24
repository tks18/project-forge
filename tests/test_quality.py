"""Unit tests for Quality Gate output parsers and diagnostics."""

from project_forge.quality import (
    parse_generic_failures,
    parse_mypy_output,
    parse_pylint_output,
    parse_pyright_output,
    parse_ruff_output,
)


def test_parse_ruff_output():
    """Verify parsing Ruff linter diagnostic messages."""
    raw = """src/project_forge/cli.py:42:5: E501 Line too long (105 > 100)
src/project_forge/process.py:10:1: F401 `sys` imported but unused
"""
    issues = parse_ruff_output(raw)
    assert len(issues) == 2
    assert issues[0].engine == "Ruff"
    assert issues[0].file == "src/project_forge/cli.py"
    assert issues[0].line == 42
    assert issues[0].column == 5
    assert issues[0].code == "E501"
    assert issues[0].severity == "Error"

    assert issues[1].code == "F401"
    assert issues[1].severity == "Error"


def test_parse_mypy_output():
    """Verify parsing Mypy typecheck diagnostic messages."""
    raw = """src/project_forge/config.py:15: error: Incompatible types in assignment (expression has type "int", variable has type "str")  [assignment]
src/project_forge/process.py:20: note: See https://mypy.readthedocs.io
"""
    issues = parse_mypy_output(raw)
    assert len(issues) == 2
    assert issues[0].engine == "Mypy"
    assert issues[0].file == "src/project_forge/config.py"
    assert issues[0].line == 15
    assert issues[0].severity == "Error"
    assert issues[0].code == "assignment"


def test_parse_pyright_output():
    """Verify parsing Pyright typecheck diagnostic messages."""
    raw = """  src/project_forge/quality.py:50:12 - error: Cannot access member "foo" for type "str" (reportGeneralTypeIssues)
"""
    issues = parse_pyright_output(raw)
    assert len(issues) == 1
    assert issues[0].engine == "Pyright"
    assert issues[0].file == "src/project_forge/quality.py"
    assert issues[0].line == 50
    assert issues[0].column == 12
    assert issues[0].code == "reportGeneralTypeIssues"
    assert issues[0].severity == "Error"


def test_parse_pylint_output():
    """Verify parsing Pylint diagnostic messages."""
    raw = """src/project_forge/commits.py:25:0: C0114: Missing module docstring (missing-module-docstring)
src/project_forge/project.py:30:4: E1101: Instance of 'X' has no 'y' member (no-member)
"""
    issues = parse_pylint_output(raw)
    assert len(issues) == 2
    assert issues[0].engine == "Pylint"
    assert issues[0].code == "missing-module-docstring"
    assert issues[0].severity == "Convention"

    assert issues[1].code == "no-member"
    assert issues[1].severity == "Error"


def test_parse_generic_failures():
    """Verify parsing generic pytest or command failures."""
    raw = """FAILED tests/test_one.py::test_fail - AssertionError
error: could not compile
"""
    issues = parse_generic_failures(raw, engine_name="Pytest")
    assert len(issues) == 2
    assert issues[0].engine == "Pytest"
    assert issues[0].code == "FAIL"

