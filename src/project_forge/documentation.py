"""AST-level documentation auditor and compliance verification gate."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


@dataclass
class DocViolation:
    """Documenting a specific missing or non-compliant docstring."""

    file: str
    line: int
    entity_type: str
    entity_name: str
    rule: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Convert violation to dictionary."""
        return {
            "file": self.file,
            "line": self.line,
            "entity_type": self.entity_type,
            "entity_name": self.entity_name,
            "rule": self.rule,
            "message": self.message,
        }


def _is_property(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if function node is decorated as property."""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "property":
            return True
        if isinstance(dec, ast.Attribute) and dec.attr in ("setter", "deleter"):
            return True
    return False


class DocumentationAuditor:
    """AST inspector checking docstrings across Python files."""

    def __init__(
        self,
        base_dir: Path,
        include_private: bool = False,
        require_init_docs: bool = False,
        require_package_ownership: bool = False,
    ) -> None:
        self.base_dir = base_dir
        self.include_private = include_private
        self.require_init_docs = require_init_docs
        self.require_package_ownership = require_package_ownership
        self.violations: list[DocViolation] = []

    def audit_file(self, file_path: Path) -> None:
        """Audit single Python file AST for docstring compliance."""
        try:
            rel_path = str(file_path.relative_to(self.base_dir))
        except ValueError:
            rel_path = str(file_path)

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))
        except Exception as exc:
            self.violations.append(
                DocViolation(
                    file=rel_path,
                    line=1,
                    entity_type="Module",
                    entity_name=file_path.name,
                    rule="PARSE_ERROR",
                    message=f"Failed to parse AST: {exc}",
                )
            )
            return

        # 1. Module Docstring Check
        module_doc = ast.get_docstring(tree)
        if not module_doc or not module_doc.strip():
            self.violations.append(
                DocViolation(
                    file=rel_path,
                    line=1,
                    entity_type="Module",
                    entity_name=file_path.name,
                    rule="MISSING_MODULE_DOCSTRING",
                    message="Module is missing a top-level docstring.",
                )
            )
        elif file_path.name == "__init__.py" and self.require_package_ownership:
            if "Owns" not in module_doc or "Does not own" not in module_doc:
                self.violations.append(
                    DocViolation(
                        file=rel_path,
                        line=1,
                        entity_type="Package",
                        entity_name=file_path.parent.name,
                        rule="MISSING_OWNERSHIP_CONTRACT",
                        message="__init__.py missing 'Owns' and/or 'Does not own' boundary contract.",
                    )
                )

        # 2. Walk AST for Classes, Functions, Methods, Properties
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                self._audit_class(node, rel_path)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._audit_function(node, rel_path, is_method=False)

    def _audit_class(self, node: ast.ClassDef, file_path: str) -> None:
        if (
            not self.include_private
            and node.name.startswith("_")
            and not node.name.startswith("__")
        ):
            return

        cls_doc = ast.get_docstring(node)
        if not cls_doc or not cls_doc.strip():
            self.violations.append(
                DocViolation(
                    file=file_path,
                    line=node.lineno,
                    entity_type="Class",
                    entity_name=node.name,
                    rule="MISSING_CLASS_DOCSTRING",
                    message=f"Class '{node.name}' is missing a docstring.",
                )
            )

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_prop = _is_property(item)
                self._audit_function(
                    item,
                    file_path,
                    is_method=True,
                    is_property=is_prop,
                    parent_class=node.name,
                    parent_class_doc=cls_doc,
                )
            elif isinstance(item, ast.ClassDef):
                self._audit_class(item, file_path)

    def _audit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
        is_method: bool = False,
        is_property: bool = False,
        parent_class: str = "",
        parent_class_doc: str | None = None,
    ) -> None:
        entity_type = "Property" if is_property else ("Method" if is_method else "Function")
        full_name = f"{parent_class}.{node.name}" if parent_class else node.name

        is_private = node.name.startswith("_") and not (
            node.name.startswith("__") and node.name.endswith("__")
        )
        if not self.include_private and is_private:
            return

        doc = ast.get_docstring(node)

        # Special handling for __init__
        if is_method and node.name == "__init__":
            if doc and doc.strip():
                return
            if not self.require_init_docs and parent_class_doc and parent_class_doc.strip():
                return
            self.violations.append(
                DocViolation(
                    file=file_path,
                    line=node.lineno,
                    entity_type="Method",
                    entity_name=full_name,
                    rule="MISSING_INIT_DOCSTRING",
                    message=f"Constructor '{full_name}' lacks docstring and parent class lacks parameters documentation.",
                )
            )
            return

        if not doc or not doc.strip():
            self.violations.append(
                DocViolation(
                    file=file_path,
                    line=node.lineno,
                    entity_type=entity_type,
                    entity_name=full_name,
                    rule=f"MISSING_{entity_type.upper()}_DOCSTRING",
                    message=f"{entity_type} '{full_name}' is missing a docstring.",
                )
            )


def run_documentation_audit(
    root_dir: Path | None = None,
    strict: bool = False,
    require_init: bool = False,
    as_json: bool = False,
) -> int:
    """Run AST documentation auditor across configured source roots."""
    if root_dir is None:
        from project_forge.project import find_project_root

        root_dir = find_project_root()

    from project_forge.config import load_config

    cfg = load_config(root_dir)

    auditor = DocumentationAuditor(
        base_dir=root_dir,
        include_private=strict or cfg.docs.include_private,
        require_init_docs=require_init or cfg.docs.require_init_docs,
        require_package_ownership=cfg.docs.require_package_ownership,
    )

    for src_path_str in cfg.source:
        src_path = root_dir / src_path_str
        if src_path.is_dir():
            for py_file in sorted(src_path.rglob("*.py")):
                auditor.audit_file(py_file)
        elif src_path.is_file() and src_path.suffix == ".py":
            auditor.audit_file(src_path)

    violations = auditor.violations

    if as_json:
        print(json.dumps([v.to_dict() for v in violations], indent=2))
        return 1 if violations else 0

    mode_label: list[str] = []
    if strict:
        mode_label.append("STRICT")
    else:
        mode_label.append("PUBLIC INTERFACES")
    if require_init:
        mode_label.append("REQUIRE __INIT__")

    console.print("=" * 80)
    console.print(
        f"AST Documentation Auditor | Scope: {cfg.source} | Mode: {', '.join(mode_label)}"
    )
    console.print("=" * 80)

    if not violations:
        console.print(
            "[bold green][PASS] ALL ENTITIES 100% DOCUMENTED! Zero violations found.[/bold green]"
        )
        console.print("=" * 80)
        return 0

    console.print(f"[bold yellow]Found {len(violations)} documentation violations:[/bold yellow]\n")
    by_type: dict[str, int] = {}
    for v in violations:
        by_type[v.entity_type] = by_type.get(v.entity_type, 0) + 1
        console.print(
            f"  [{v.entity_type:8s}] [cyan]{v.file}:{v.line}[/cyan] -> [bold]{v.entity_name}[/bold]"
        )
        console.print(f"             [dim]Rule: {v.rule} | {v.message}[/dim]")

    console.print("\nSummary by Entity Type:")
    for etype, count in sorted(by_type.items()):
        console.print(f"  - {etype}: {count}")

    console.print(f"\n[bold red]Total violations: {len(violations)}[/bold red]")
    console.print("=" * 80)
    return 1
