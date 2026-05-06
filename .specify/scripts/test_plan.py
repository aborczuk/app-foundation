#!/usr/bin/env python3
"""Smoke-test the plan workflow contracts and scaffold output."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


def _usage() -> str:
    """Return the usage text for the plan smoke test."""
    return (
        "Usage:\n"
        "  .specify/scripts/test_plan.py feature_id=XYZ\n\n"
        "What it checks:\n"
        "  1. The speckit.plan manifest entry points at the combined plan step and plan-template.md.\n"
        "  2. The speckit.plan command doc documents triage-first combined planning.\n"
        "  3. pipeline-scaffold generates plan.md with the expected combined section headers.\n"
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
    """Verify the manifest and command-doc snippets for speckit.plan."""
    manifest_path = repo_root / ".specify" / "command-manifest.yaml"
    command_doc_path = repo_root / ".claude" / "commands" / "speckit.plan.md"

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest["commands"]["speckit.plan"]["artifacts"]
    templates = [artifact["template"] for artifact in artifacts]
    expected_templates = ["plan-template.md"]
    if templates != expected_templates:
        raise SystemExit(
            "Manifest template mismatch: expected "
            f"{expected_templates}, found {templates}"
        )
    script_path = manifest["commands"]["speckit.plan"]["driver"].get("script_path")
    if script_path != "scripts/speckit_plan_step.py":
        raise SystemExit(f"Plan script mismatch: expected scripts/speckit_plan_step.py, found {script_path}")

    command_doc = command_doc_path.read_text(encoding="utf-8")
    required_snippets = [
        "Compact Contract",
        "speckit_plan_step.py",
        "duplicate_marked",
        "plan_approved",
        "Do not infer t-shirt size from the number of discovery matches",
        "Do not create `discovery.md`, `research.md`, `sketch.md`",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in command_doc]
    if missing:
        raise SystemExit(f"Command doc missing required snippets: {', '.join(missing)}")

    forbidden_snippets = [
        "--artifact",
        "--fr-ids",
        "FR_PHRASE",
        "gh workflow search",
        "echo '{\"event\": \"plan_started\"}'",
        "echo '{\"event\": \"plan_approved\"}'",
    ]
    present = [snippet for snippet in forbidden_snippets if snippet in command_doc]
    if present:
        raise SystemExit(f"Command doc still contains forbidden snippets: {', '.join(present)}")


def _run_pipeline_scaffold(test_dir: Path) -> None:
    """Generate the plan scaffold in a temporary feature directory."""
    script = Path(__file__).resolve().parents[0] / "pipeline-scaffold.py"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "speckit.plan",
            "--feature-dir",
            str(test_dir),
            "FEATURE_NAME=Compact Plan Test",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _assert_scaffold_output(root: Path) -> None:
    """Verify the plan scaffolded artifacts and section coverage."""
    required_files = [root / "plan.md"]
    missing = [str(path) for path in required_files if not path.exists()]
    if missing:
        raise SystemExit(f"Missing scaffolded artifacts: {', '.join(missing)}")

    plan_text = (root / "plan.md").read_text(encoding="utf-8")
    required_sections = [
        "## Triage",
        "## Routing Contract",
        "## Internal Discovery",
        "## Plan Completion Summary",
    ]
    missing_sections = [section for section in required_sections if section not in plan_text]
    if missing_sections:
        raise SystemExit(f"Missing plan sections: {', '.join(missing_sections)}")


def main(argv: list[str]) -> int:
    """Run the plan smoke test."""
    feature_id = _parse_args(argv)
    if not feature_id:
        print(_usage(), file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[2]
    _assert_manifest_and_doc(repo_root)

    tmp_root = Path(tempfile.mkdtemp(prefix=f"plan-{feature_id}-"))
    try:
        _run_pipeline_scaffold(tmp_root)
        _assert_scaffold_output(tmp_root)
        print(tmp_root / "plan.md")
        return 0
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
