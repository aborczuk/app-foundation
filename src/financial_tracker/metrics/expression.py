"""Restricted, non-executable metric expression validation."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Bounded validation result suitable for API responses and activation gates."""

    valid: bool
    canonical_expression: str
    dependencies: tuple[str, ...]
    errors: tuple[str, ...]


def validate_expression(
    expression: str,
    *,
    metric_id: str,
    approved_inputs: Mapping[str, str],
    output_unit: str,
    dependency_graph: Mapping[str, Sequence[str]] | None = None,
) -> ValidationReport:
    """Parse and validate one bounded expression without evaluating user input."""
    errors: set[str] = set()
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return ValidationReport(False, "", (), ("unsafe_syntax",))

    dependencies = tuple(sorted({node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}))
    for dependency in dependencies:
        if dependency not in approved_inputs:
            errors.add(f"unknown_symbol:{dependency}")
    allowed_nodes = (ast.Expression, ast.BinOp, ast.Name, ast.Load, ast.Constant, ast.operator)
    if any(not isinstance(node, allowed_nodes) for node in ast.walk(tree)):
        errors.add("unsafe_syntax")
    inferred_unit = _infer_unit(tree.body, approved_inputs, errors)
    if inferred_unit != output_unit and inferred_unit != "unknown":
        errors.add("unit_mismatch")
    if dependency_graph is not None and _has_cycle(metric_id, dependency_graph):
        errors.add("dependency_cycle")
    canonical = ast.unparse(tree.body)
    return ValidationReport(not errors, canonical, dependencies, tuple(sorted(errors)))


def _infer_unit(node: ast.AST, approved_inputs: Mapping[str, str], errors: set[str]) -> str:
    """Infer units through the allowlisted arithmetic operators."""
    if isinstance(node, ast.Name):
        return approved_inputs.get(node.id, "unknown")
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return "scalar"
    if not isinstance(node, ast.BinOp):
        errors.add("unsafe_syntax")
        return "unknown"
    left = _infer_unit(node.left, approved_inputs, errors)
    right = _infer_unit(node.right, approved_inputs, errors)
    if isinstance(node.op, (ast.Add, ast.Sub)):
        if left != "unknown" and right != "unknown" and left != right:
            errors.add("unit_mismatch")
        return left if left == right else "unknown"
    if isinstance(node.op, ast.Mult):
        if left == "scalar":
            return right
        if right == "scalar":
            return left
        return f"{left}*{right}"
    if isinstance(node.op, ast.Div):
        if right == "scalar":
            return left
        if left == right:
            return "ratio"
        return f"{left}/{right}"
    errors.add("unsafe_syntax")
    return "unknown"


def _has_cycle(root: str, graph: Mapping[str, Sequence[str]]) -> bool:
    """Detect a dependency cycle reachable from one metric identifier."""
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(dependency) for dependency in graph.get(node, ())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return visit(root)
