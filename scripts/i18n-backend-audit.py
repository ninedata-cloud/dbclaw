#!/usr/bin/env python3
"""AST based guard against unsafe or fixed-language API response strings."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def call_name(node: ast.Call) -> str:
    function = node.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return ""


def contains_dynamic_exception(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Call)
        and call_name(child) == "str"
        and child.args
        and isinstance(child.args[0], ast.Name)
        and child.args[0].id.lower() in {"e", "err", "error", "exc", "exception"}
        for child in ast.walk(node)
    )


def fixed_string(node: ast.AST) -> bool:
    return isinstance(node, (ast.Constant, ast.JoinedStr, ast.BinOp)) and not (
        isinstance(node, ast.Constant) and not isinstance(node.value, str)
    )


class AuditVisitor(ast.NodeVisitor):
    def __init__(self, relative: str) -> None:
        self.relative = relative
        self.violations: list[tuple[str, int, str]] = []

    def add(self, node: ast.AST, rule: str) -> None:
        self.violations.append((rule, getattr(node, "lineno", 1), self.relative))

    def visit_Call(self, node: ast.Call) -> None:
        name = call_name(node)
        if name == "HTTPException":
            for keyword in node.keywords:
                if keyword.arg == "detail" and fixed_string(keyword.value):
                    self.add(keyword.value, "raw-http-detail")

        if name in {"JSONResponse", "send_json", "send_text"} and contains_dynamic_exception(node):
            self.add(node, "exception-in-client-response")

        if name == "JSONResponse":
            content = next((kw.value for kw in node.keywords if kw.arg == "content"), None)
            if isinstance(content, ast.Dict):
                for key, value in zip(content.keys, content.values):
                    if isinstance(key, ast.Constant) and key.value in {"message", "detail"} and fixed_string(value):
                        self.add(value, "fixed-response-message")
        if name.endswith("Response"):
            for keyword in node.keywords:
                if keyword.arg in {"error", "message", "detail"} and contains_dynamic_exception(keyword.value):
                    self.add(keyword.value, "exception-in-response-model")
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant)
                and key.value in {"error", "message", "detail"}
                and contains_dynamic_exception(value)
            ):
                self.add(value, "exception-in-response-payload")
        self.generic_visit(node)


def collect() -> tuple[Counter[str], dict[str, str]]:
    counts: Counter[str] = Counter()
    samples: dict[str, str] = {}
    for file in sorted(BACKEND.rglob("*.py")):
        relative = str(file.relative_to(ROOT))
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=relative)
        visitor = AuditVisitor(relative)
        visitor.visit(tree)
        for rule, line, source in visitor.violations:
            key = f"{rule}\0{source}"
            counts[key] += 1
            samples.setdefault(key, f"{source}:{line} [{rule}]")
    return counts, samples


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.parse_args()
    counts, samples = collect()
    violations = list(counts.items())
    if violations:
        print("Unsafe or fixed-language backend response strings detected:")
        for key, count in violations[:50]:
            print(f"  {samples[key]} ({count})")
        if len(violations) > 50:
            print(f"  ... and {len(violations) - 50} more")
        return 1
    print("Backend i18n AST audit passed (0 violations).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
