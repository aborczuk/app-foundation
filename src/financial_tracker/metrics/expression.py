"""Restricted, non-executable metric expression validation."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_MAX_EXPRESSION_LENGTH = 4096
_MAX_AST_NODES = 256
_MAX_AST_DEPTH = 64
_MAX_DEPENDENCY_NODES = 1024


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
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        return ValidationReport(False, "", (), ("unsafe_syntax",))
    try:
        tree = ast.parse(expression, mode="eval")
    except (RecursionError, SyntaxError):
        return ValidationReport(False, "", (), ("unsafe_syntax",))

    nodes = _bounded_ast_nodes(tree)
    if nodes is None:
        return ValidationReport(False, "", (), ("unsafe_syntax",))
    dependencies = tuple(sorted({node.id for node in nodes if isinstance(node, ast.Name)}))
    for dependency in dependencies:
        if dependency not in approved_inputs:
            errors.add(f"unknown_symbol:{dependency}")
    allowed_nodes = (ast.Expression, ast.BinOp, ast.Name, ast.Load, ast.Constant, ast.operator)
    if any(not isinstance(node, allowed_nodes) for node in nodes):
        errors.add("unsafe_syntax")
    inferred_unit = _infer_unit(tree.body, approved_inputs, errors)
    if inferred_unit != output_unit and inferred_unit != "unknown":
        errors.add("unit_mismatch")
    if dependency_graph is not None:
        cycle_state = _has_cycle(metric_id, dependency_graph)
        if cycle_state is True:
            errors.add("dependency_cycle")
        elif cycle_state is None:
            errors.add("dependency_graph_too_large")
    canonical = ast.unparse(tree.body)
    return ValidationReport(not errors, canonical, dependencies, tuple(sorted(errors)))


def _bounded_ast_nodes(tree: ast.AST) -> tuple[ast.AST, ...] | None:
    """Collect AST nodes while enforcing parser resource limits."""
    nodes: list[ast.AST] = []
    pending: list[tuple[ast.AST, int]] = [(tree, 0)]
    while pending:
        node, depth = pending.pop()
        if len(nodes) >= _MAX_AST_NODES or depth > _MAX_AST_DEPTH:
            return None
        nodes.append(node)
        pending.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
    return tuple(nodes)


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
            if isinstance(node.right, ast.Constant) and node.right.value == 0:
                errors.add("division_by_zero")
                return "unknown"
            return left
        if left == right:
            return "ratio"
        return f"{left}/{right}"
    errors.add("unsafe_syntax")
    return "unknown"


def _has_cycle(root: str, graph: Mapping[str, Sequence[str]]) -> bool | None:
    """Detect a reachable cycle without recursing through an unbounded graph."""
    visiting: set[str] = set()
    visited: set[str] = set()
    pending: list[tuple[str, bool]] = [(root, False)]
    inspected = 0
    while pending:
        node, exiting = pending.pop()
        if exiting:
            visiting.remove(node)
            visited.add(node)
            continue
        if node in visiting:
            return True
        if node in visited:
            continue
        inspected += 1
        if inspected > _MAX_DEPENDENCY_NODES:
            return None
        visiting.add(node)
        pending.append((node, True))
        pending.extend((dependency, False) for dependency in graph.get(node, ()))
    return False
