#!/usr/bin/env python3
"""Smoke-test the research workflow contracts and scaffold output."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


def _usage() -> str:
    """Return the usage text for the research smoke test."""
    return (
        "Usage:\n"
        "  .specify/scripts/test_research.py feature_id=XYZ\n\n"
        "What it checks:\n"
        "  1. The speckit.research manifest entry still points at research-template-compact.md.\n"
        "  2. The speckit.research command doc still documents the compact scaffold invocation and no-subagent flow.\n"
        "  3. pipeline-scaffold generates a research.md with all required section headers.\n"
    )


def _parse_args(argv: list[str]) -> str | None:
    """Return the feature identifier if it is present."""
    feature_id = ""
    for arg in argv:
        if arg in {"--help", "-h"}:
            print(_usage())
            raise SystemExit(0)
        if arg.startswith("feature_id="):
            feature_id = arg.split("=", 1)[1]
            continue
        print(_usage(), file=sys.stderr)
        raise SystemExit(1)
    return feature_id or None


def _assert_manifest_and_doc(repo_root: Path) -> None:
    """Verify the manifest and command-doc snippets for speckit.research."""
    manifest_path = repo_root / ".specify" / "command-manifest.yaml"
    command_doc_path = repo_root / ".claude" / "commands" / "speckit.research.md"
    expected_template = "research-template-compact.md"

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    template = manifest["commands"]["speckit.research"]["artifacts"][0]["template"]
    if template != expected_template:
        raise SystemExit(f"Manifest template mismatch: expected {expected_template}, found {template}")

    command_doc = command_doc_path.read_text(encoding="utf-8")
    required_snippets = [
        "research-template-compact.md",
        "UV_CACHE_DIR=\"${TMPDIR:-/tmp}/app-foundation-uv-cache\" uv run python .specify/scripts/pipeline-scaffold.py speckit.research",
        "Do not spawn sub-agents",
        "top 3-5 matches",
        "feature_id=XYZ",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in command_doc]
    if missing:
        raise SystemExit(f"Command doc missing required snippets: {', '.join(missing)}")


def _run_pipeline_scaffold(test_dir: Path) -> None:
    """Generate the research scaffold in a temporary feature directory."""
    script = Path(__file__).resolve().parents[0] / "pipeline-scaffold.py"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "speckit.research",
            "--feature-dir",
            str(test_dir),
            "FEATURE_NAME=Compact Research Test",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _assert_research_scaffold(root: Path) -> None:
    """Verify the generated research scaffold content."""
    research_path = root / "research.md"
    if not research_path.exists():
        raise SystemExit(f"Missing scaffolded artifact: {research_path}")

    text = research_path.read_text(encoding="utf-8")
    required = [
        "## Zero-Custom-Server Assessment",
        "## Repo Assembly Map",
        "## Package Adoption Options",
        "## Conceptual Patterns",
        "## Search Tools Used",
        "## Unanswered Questions",
    ]
    missing = [section for section in required if section not in text]
    if missing:
        raise SystemExit(f"Missing sections: {', '.join(missing)}")


def main(argv: list[str]) -> int:
    """Run the research smoke test."""
    feature_id = _parse_args(argv)
    if not feature_id:
        print(_usage(), file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[2]
    _assert_manifest_and_doc(repo_root)

    tmp_root = Path(tempfile.mkdtemp(prefix=f"research-{feature_id}-"))
    try:
        _run_pipeline_scaffold(tmp_root)
        _assert_research_scaffold(tmp_root)
        print(tmp_root / "research.md")
        return 0
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
