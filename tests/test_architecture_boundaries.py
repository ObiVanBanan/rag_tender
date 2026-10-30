from __future__ import annotations

import ast
from pathlib import Path


DOMAIN_PACKAGE = Path(__file__).parents[1] / "src" / "nomenclature_matcher" / "domain"
APPLICATION_PACKAGE = DOMAIN_PACKAGE.parent / "application"
FORBIDDEN_IMPORTS = {
    "fastapi",
    "openai",
    "psycopg",
    "qdrant_client",
    "nomenclature_matcher.application",
    "nomenclature_matcher.infrastructure",
    "nomenclature_matcher.models",
}


def test_domain_has_no_dependencies_on_application_infrastructure_or_transport():
    for source_path in DOMAIN_PACKAGE.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level > 1:
                    raise AssertionError(
                        f"{source_path.name} imports outside the domain package: {node.module}"
                    )
                imported_modules = [node.module or ""]
            elif isinstance(node, ast.Import):
                imported_modules = [alias.name for alias in node.names]
            else:
                continue

            for imported in imported_modules:
                if any(
                    imported == forbidden or imported.startswith(f"{forbidden}.")
                    for forbidden in FORBIDDEN_IMPORTS
                ):
                    raise AssertionError(
                        f"{source_path.name} has forbidden dependency: {imported}"
                    )


def test_application_does_not_import_infrastructure_adapters():
    for source_path in APPLICATION_PACKAGE.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                is_infrastructure = module == "infrastructure" or module.startswith(
                    "infrastructure."
                )
                if is_infrastructure and node.level:
                    raise AssertionError(
                        f"{source_path.name} imports an infrastructure adapter"
                    )
                if any(
                    alias.name == "nomenclature_matcher.infrastructure"
                    or alias.name.startswith("nomenclature_matcher.infrastructure.")
                    for alias in node.names
                ):
                    raise AssertionError(
                        f"{source_path.name} imports an infrastructure adapter"
                    )
            elif isinstance(node, ast.Import):
                if any(
                    alias.name == "nomenclature_matcher.infrastructure"
                    or alias.name.startswith("nomenclature_matcher.infrastructure.")
                    for alias in node.names
                ):
                    raise AssertionError(
                        f"{source_path.name} imports an infrastructure adapter"
                    )
