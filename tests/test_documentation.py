"""Unit tests for AST documentation auditor."""

from pathlib import Path
from project_forge.documentation import DocumentationAuditor


def test_documentation_auditor_compliant(tmp_path: Path):
    """Verify fully documented Python file has zero violations."""
    code = '''"""Sample module docstring."""

class Calculator:
    """A simple calculator class."""

    def add(self, a: int, b: int) -> int:
        """Add two integers.

        Parameters
        ----------
        a : int
            First number.
        b : int
            Second number.

        Returns
        -------
        int
            Sum of numbers.
        """
        return a + b
'''
    py_file = tmp_path / "calc.py"
    py_file.write_text(code, encoding="utf-8")

    auditor = DocumentationAuditor(base_dir=tmp_path)
    auditor.audit_file(py_file)
    assert len(auditor.violations) == 0


def test_documentation_auditor_missing_docs(tmp_path: Path):
    """Verify missing module, class, and method docstrings are flagged."""
    code = """
class UndocumentedClass:
    def undocumented_method(self):
        pass
"""
    py_file = tmp_path / "bad.py"
    py_file.write_text(code, encoding="utf-8")

    auditor = DocumentationAuditor(base_dir=tmp_path)
    auditor.audit_file(py_file)
    assert len(auditor.violations) >= 3

    rules = {v.rule for v in auditor.violations}
    assert "MISSING_MODULE_DOCSTRING" in rules
    assert "MISSING_CLASS_DOCSTRING" in rules
    assert "MISSING_METHOD_DOCSTRING" in rules

