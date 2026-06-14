"""Regression tests for config exports used by runtime modules."""
# ruff: noqa: S101

from __future__ import annotations

import ast
from pathlib import Path

import config


def _config_import_names(py_file: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "config":
            for alias in node.names:
                if alias.name != "*":
                    names.append(alias.name)
    return names


def test_is_cloud_runtime_exported_from_config() -> None:
    assert hasattr(config, "is_cloud_runtime")
    assert callable(config.is_cloud_runtime)
    assert isinstance(config.is_cloud_runtime(), bool)


def test_app_config_imports_are_available() -> None:
    app_file = Path(__file__).resolve().parents[1] / "app.py"
    imported = _config_import_names(app_file)
    missing = [name for name in imported if not hasattr(config, name)]
    assert missing == []
