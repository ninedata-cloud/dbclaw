import ast
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HAN_RANGE_START = "\u4e00"
HAN_RANGE_END = "\u9fff"
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}


def _contains_han(text: str) -> bool:
    return any(HAN_RANGE_START <= char <= HAN_RANGE_END for char in text)


def _string_literals(node: ast.AST):
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            yield child.value


def _production_python_files():
    yield PROJECT_ROOT / "run.py"
    yield from (PROJECT_ROOT / "backend").rglob("*.py")


@pytest.mark.unit
def test_application_log_templates_are_english():
    violations = []

    for path in _production_python_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            is_print = isinstance(node.func, ast.Name) and node.func.id == "print"
            is_log = isinstance(node.func, ast.Attribute) and node.func.attr in LOG_METHODS
            if not (is_print or is_log):
                continue

            if any(_contains_han(value) for arg in node.args for value in _string_literals(arg)):
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")

    assert violations == [], "Chinese text found in application log/console templates: " + ", ".join(violations)


@pytest.mark.unit
def test_startup_self_check_output_is_english():
    path = PROJECT_ROOT / "backend/services/startup_self_check.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str) and _contains_han(node.value)]

    assert violations == [], f"Chinese text found in startup self-check output at lines: {violations}"


@pytest.mark.unit
def test_embedded_integration_logs_and_errors_are_english():
    path = PROJECT_ROOT / "backend/utils/integration_templates.py"
    outer_tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = []

    for node in ast.walk(outer_tree):
        if not isinstance(node, ast.Dict):
            continue

        integration_id = "unknown"
        code = None
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "integration_id" and isinstance(value, ast.Constant):
                integration_id = str(value.value)
            elif isinstance(key, ast.Constant) and key.value == "code" and isinstance(value, ast.Constant):
                code = value.value

        if not isinstance(code, str):
            continue

        embedded_tree = ast.parse(code, filename=f"{path}:{integration_id}")
        for embedded_node in ast.walk(embedded_tree):
            is_log = (
                isinstance(embedded_node, ast.Call)
                and isinstance(embedded_node.func, ast.Attribute)
                and embedded_node.func.attr in LOG_METHODS
            )
            if not (isinstance(embedded_node, ast.Raise) or is_log):
                continue
            if any(_contains_han(value) for value in _string_literals(embedded_node)):
                violations.append(f"{integration_id}:{embedded_node.lineno}")

    assert violations == [], "Chinese text found in embedded integration logs/errors: " + ", ".join(violations)
