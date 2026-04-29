#!/usr/bin/env python3
"""Return a bounded list of changed files for a pull request."""

from __future__ import annotations

import json
import subprocess
import sys


def _usage() -> str:
    """Return the usage text for the safe PR file helper."""
    return (
        "Usage: scripts/gh_safe_pr_files.py <owner/repo> <pr_number> [max_rows]\n\n"
        "Example:\n"
        "  scripts/gh_safe_pr_files.py aborczuk/app-foundation 17 100\n"
    )


def main(argv: list[str]) -> int:
    """Load PR file metadata with a bounded payload."""
    if len(argv) not in {2, 3}:
        print(_usage(), file=sys.stderr)
        return 1

    repo, pr = argv[0], argv[1]
    try:
        max_rows = int(argv[2]) if len(argv) == 3 else 200
    except ValueError:
        print("ERROR: max_rows must be a positive integer", file=sys.stderr)
        return 1

    if max_rows <= 0:
        print("ERROR: max_rows must be a positive integer", file=sys.stderr)
        return 1

    result = subprocess.run(
        ["gh", "pr", "view", pr, "--repo", repo, "--json", "files"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        return result.returncode

    payload = json.loads(result.stdout or "{}")
    files = payload.get("files", [])
    selected = [
        {
            "path": item.get("path"),
            "status": item.get("status"),
            "additions": item.get("additions"),
            "deletions": item.get("deletions"),
            "changes": item.get("changes"),
        }
        for item in files[:max_rows]
    ]
    print(json.dumps(selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
