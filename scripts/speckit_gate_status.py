#!/usr/bin/env python3
"""Deterministic gate checks for speckit plan/implement entry conditions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

CHECKBOX_RE = re.compile(r"^\s*-\s*\[(?P<state>[ xX])\]")


@dataclass(frozen=True)
class ChecklistStatus:
    """Summary of checklist completion state for one file."""

    name: str
    path: str
    total: int
    completed: int
    incomplete: int

    @property
    def status(self) -> str:
        """Return PASS when no items are incomplete, otherwise FAIL."""
        return "PASS" if self.incomplete == 0 else "FAIL"


def _resolve_manifest_path(repo_root: Path) -> Path:
    """Resolve canonical command manifest path at repository root."""
    return repo_root / "command-manifest.yaml"


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("plan", "implement"),
        required=True,
        help="Gate mode to evaluate.",
    )
    parser.add_argument(
        "--feature-dir",
        required=True,
        help="Absolute or relative path to the feature directory under specs/.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    return parser.parse_args(argv)


def _count_checklist(path: Path) -> ChecklistStatus:
    """Count total/completed/incomplete checklist items for one markdown file."""
    total = 0
    completed = 0
    incomplete = 0

    for line in path.read_text(encoding="utf-8").splitlines():
        match = CHECKBOX_RE.match(line)
        if not match:
            continue
        total += 1
        if match.group("state").lower() == "x":
            completed += 1
        else:
            incomplete += 1

    return ChecklistStatus(
        name=path.name,
        path=str(path),
        total=total,
        completed=completed,
        incomplete=incomplete,
    )


def _scan_checklists(feature_dir: Path) -> tuple[bool, list[ChecklistStatus]]:
    """Return checklist status entries for markdown files in checklists/."""
    checklists_dir = feature_dir / "checklists"
    if not checklists_dir.is_dir():
        return (False, [])

    statuses: list[ChecklistStatus] = []
    for checklist in sorted(checklists_dir.glob("*.md")):
        statuses.append(_count_checklist(checklist))
    return (True, statuses)


def _plan_report(feature_dir: Path) -> tuple[dict[str, Any], int]:
    """Evaluate plan entry gates."""
    requirements_path = feature_dir / "checklists" / "requirements.md"
    checklists_dir_exists, checklist_entries = _scan_checklists(feature_dir)
    incomplete_total = sum(entry.incomplete for entry in checklist_entries)
    hard_block_reasons: list[str] = []

    if not requirements_path.exists():
        hard_block_reasons.append("missing_requirements_checklist")
    if incomplete_total > 0:
        hard_block_reasons.append("incomplete_checklist_items")

    report: dict[str, Any] = {
        "mode": "plan",
        "feature_dir": str(feature_dir),
        "requirements_checklist": {
            "path": str(requirements_path),
            "exists": requirements_path.exists(),
        },
        "checklists": {
            "directory_exists": checklists_dir_exists,
            "incomplete_total": incomplete_total,
            "entries": [
                {**asdict(entry), "status": entry.status} for entry in checklist_entries
            ],
        },
        "hard_block_reasons": hard_block_reasons,
        "ok": not hard_block_reasons,
    }
    exit_code = 0 if report["ok"] else 2
    return (report, exit_code)


def _implement_report(feature_dir: Path, repo_root: Path) -> tuple[dict[str, Any], int]:
    """Evaluate implement entry gates using task and checklist availability."""
    estimates_doc = feature_dir / "estimates.md"
    checklists_dir_exists, checklist_entries = _scan_checklists(feature_dir)
    incomplete_total = sum(entry.incomplete for entry in checklist_entries)
    hard_block_reasons: list[str] = []

    report: dict[str, Any] = {
        "mode": "implement",
        "feature_dir": str(feature_dir),
        "estimates": {
            "path": str(estimates_doc),
            "exists": estimates_doc.exists(),
        },
        "checklists": {
            "directory_exists": checklists_dir_exists,
            "incomplete_total": incomplete_total,
            "all_complete": incomplete_total == 0,
            "entries": [
                {**asdict(entry), "status": entry.status} for entry in checklist_entries
            ],
        },
        "hard_block_reasons": hard_block_reasons,
        "ok": not hard_block_reasons,
    }
    exit_code = 0 if report["ok"] else 2
    return (report, exit_code)


def validate_command_coverage(feature_dir: Path) -> dict[str, Any]:
    """Check for uncovered command mappings in the feature's manifest.

    Called as a solution/tasking gate check to ensure all commanded commands
    have explicit driver mode or legacy-fallback definition.

    Returns dict with:
        ok (bool): True if no uncovered commands
        uncovered_count (int): Number of uncovered commands
        uncovered (list): List of command IDs that are uncovered
        reasons (list): Details on coverage gaps
    """
    manifest_path = _resolve_manifest_path(Path(__file__).resolve().parent.parent)

    if not manifest_path.exists():
        return {
            "ok": False,
            "uncovered_count": 0,
            "uncovered": [],
            "reasons": [f"manifest not found: {manifest_path}"],
        }

    try:
        from pipeline_driver_contracts import load_driver_routes
        routes = load_driver_routes(manifest_path)
    except Exception as e:
        return {
            "ok": False,
            "uncovered_count": 0,
            "uncovered": [],
            "reasons": [f"failed to load manifest routes: {e}"],
        }

    # Check for uncovered commands (not in driver manifest with no explicit legacy mode)
    uncovered = []
    for cmd_id, route_meta in routes.items():
        driver_managed = route_meta.get("driver_managed", False)
        mode = route_meta.get("mode", "legacy")

        # Commands that are truly uncovered: no driver metadata AND not explicitly legacy
        if not driver_managed and mode == "legacy":
            # This is acceptable (explicitly legacy)
            continue
        elif driver_managed:
            # This is acceptable (driver-managed)
            continue
        else:
            # Ambiguous state - uncovered
            uncovered.append(cmd_id)

    return {
        "ok": len(uncovered) == 0,
        "uncovered_count": len(uncovered),
        "uncovered": sorted(uncovered),
        "reasons": ["uncovered_command_mappings"] if uncovered else [],
    }


def _print_human(report: dict[str, Any]) -> None:
    """Emit a concise human-readable report."""
    mode = str(report.get("mode", "unknown"))
    print(f"mode={mode} ok={report.get('ok')}")

    if mode == "plan":
        req = report["requirements_checklist"]
        checks = report["checklists"]
        print(
            "requirements_checklist="
            f"{'present' if req['exists'] else 'missing'} "
            f"incomplete_total={checks['incomplete_total']}"
        )

    reasons = report.get("hard_block_reasons", [])
    if reasons:
        print("hard_block_reasons=" + ",".join(str(reason) for reason in reasons))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected gate checks and emit a report."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    feature_dir = Path(args.feature_dir).resolve()
    repo_root = Path(__file__).resolve().parent.parent

    if args.mode == "plan":
        report, exit_code = _plan_report(feature_dir)
    else:
        report, exit_code = _implement_report(feature_dir, repo_root)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
