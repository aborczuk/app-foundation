#!/usr/bin/env python3
"""Generate a progressive-load route-tree artifact for a source file or symbol.

This scaffolds the "route -> load -> verify" note that keeps new scripts,
functions, and tools discoverable without forcing ad-hoc documentation.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template


def _repo_root() -> Path:
    """Return the repository root for the route-tree generator."""
    return Path(__file__).resolve().parents[3]


def _load_template(repo_root: Path) -> str:
    """Load the route-tree markdown template from the specifier templates."""
    template_path = repo_root / ".specify" / "templates" / "route-tree-template.md"
    if not template_path.is_file():
        raise FileNotFoundError(f"Template not found: {template_path}")
    return template_path.read_text(encoding="utf-8")


def _derive_tools(source_kind: str, source_path: Path, source_symbol: str | None) -> tuple[str, str, str]:
    """Infer the user-facing tool, implementation, and problem class."""
    source_name = source_path.name.lower()
    if "read_markdown" in source_name or "read-markdown" in source_name:
        return ("scripts/read-markdown.sh", "scripts/read_markdown.py", "documentation navigation and workflow routing")
    if "read_code" in source_name or "read-code" in source_name:
        return ("scripts/read-code.sh", "scripts/read_code.py", "code navigation and implementation")
    if source_kind == "markdown":
        return ("scripts/read-markdown.sh", "catalog.yaml / codegraph", "documentation navigation and workflow routing")
    if source_kind == "topology":
        return ("catalog.yaml", "codegraph", "system topology and dependency mapping")
    if source_kind in {"function", "script", "module"}:
        return ("scripts/read-code.sh", "codegraph / codebase-lsp", "code navigation and implementation")
    return ("scripts/read-code.sh", "codegraph", "progressive routing")


def _derive_title(source_path: Path, source_kind: str, source_symbol: str | None) -> str:
    """Build a human-readable title for the generated route tree."""
    base = source_path.stem if source_path.suffix else source_path.name
    if source_symbol:
        return f"{base}.{source_symbol} ({source_kind})"
    return f"{base} ({source_kind})"


def _derive_output_path(repo_root: Path, source_path: Path, source_symbol: str | None) -> Path:
    """Compute the default output path for a route-tree artifact."""
    route_root = repo_root / ".specify" / "route-trees"
    relative = source_path
    if source_path.is_absolute():
        try:
            relative = source_path.relative_to(repo_root)
        except ValueError:
            relative = Path(source_path.name)
    if source_symbol:
        relative = relative.with_name(f"{relative.stem}__{source_symbol}{relative.suffix}")
    return route_root / relative.with_suffix(".md")


def main(argv: list[str] | None = None) -> int:
    """Generate a route-tree artifact from the route-tree template."""
    parser = argparse.ArgumentParser(
        description="Generate a route-tree artifact for a source file or symbol"
    )
    parser.add_argument("--source", required=True, help="Source path the route tree describes")
    parser.add_argument(
        "--kind",
        choices=("function", "script", "module", "markdown", "topology"),
        default="script",
        help="Problem class for the route tree",
    )
    parser.add_argument(
        "--symbol",
        default="",
        help="Optional symbol name when the route tree is for a specific function",
    )
    parser.add_argument(
        "--output",
        help="Optional output path. Defaults to .specify/route-trees/<source>.md",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing route-tree artifact",
    )
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    source_path = Path(args.source)
    source_symbol = args.symbol.strip() or None

    output_path = Path(args.output) if args.output else _derive_output_path(repo_root, source_path, source_symbol)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not args.force:
        print(f"ERROR: Route-tree artifact already exists: {output_path}", file=sys.stderr)
        return 1

    template = Template(_load_template(repo_root))
    primary_tool, implementation, problem_class = _derive_tools(args.kind, source_path, source_symbol)
    title = _derive_title(source_path, args.kind, source_symbol)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rendered = template.safe_substitute(
        SOURCE_PATH=str(source_path),
        SOURCE_KIND=args.kind,
        SOURCE_SYMBOL=source_symbol or "",
        GENERATED_AT=generated_at,
        TITLE=title,
        PRIMARY_TOOL=primary_tool,
        IMPLEMENTATION=implementation,
        PROBLEM_CLASS=problem_class,
        WHY_THIS_ROUTE=(
            "The source is best understood by anchoring the exact file or symbol first, "
            "then expanding only when the question needs broader relationships."
        ),
        HOW_TO_STEP_1=f"Run `{primary_tool}` against the source path to anchor the exact location.",
        HOW_TO_STEP_2=f"Use `{implementation}` if you need to inspect or modify the underlying logic.",
        HOW_TO_STEP_3="Read only the smallest bounded window or section needed to complete the change.",
        VALIDATION_1="Confirm the selected anchor is in the expected file, section, or symbol span.",
        VALIDATION_2="Run the repo's exact verifier before marking the task complete.",
        NOTES_1="Keep the route tree small and task-specific.",
        NOTES_2="Treat this artifact as the progressive-load companion to the source file or command.",
    )

    output_path.write_text(rendered, encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
