#!/usr/bin/env python3
"""Return low-payload pull request metadata."""

from __future__ import annotations

import subprocess
import sys


def _usage() -> str:
    """Return the usage text for the safe PR info helper."""
    return (
        "Usage: scripts/gh_safe_pr_info.py <owner/repo> <pr_number>\n\n"
        "Example:\n"
        "  scripts/gh_safe_pr_info.py aborczuk/app-foundation 17\n"
    )


def main(argv: list[str]) -> int:
    """Load PR metadata with a minimal field set."""
    if len(argv) != 2:
        print(_usage(), file=sys.stderr)
        return 1

    repo, pr = argv
    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            pr,
            "--repo",
            repo,
            "--json",
            "number,title,state,isDraft,url,author,baseRefName,headRefName,changedFiles,additions,deletions,updatedAt",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        return result.returncode

    if result.stdout:
        print(result.stdout, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
