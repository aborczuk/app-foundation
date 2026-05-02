#!/usr/bin/env python3
"""Fast-path bootstrap for speckit.specify specs."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_MAX_TERMS = 5

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "build",
    "app",
    "browser",
    "feature",
    "for",
    "from",
    "game",
    "in",
    "into",
    "make",
    "of",
    "on",
    "or",
    "playable",
    "the",
    "to",
    "up",
    "with",
}


def _build_uv_env() -> dict[str, str]:
    """Return the repo-local environment for spec workflows."""
    from uv_env import repo_uv_env

    os.environ.update(repo_uv_env())
    return os.environ.copy()


def _extract_terms(description: str) -> list[str]:
    """Extract a compact set of discovery terms from the feature description."""
    terms: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]*", description):
        normalized = token.strip("-").lower()
        if len(normalized) < 3 or normalized in STOP_WORDS:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        terms.append(normalized)
        if len(terms) >= DISCOVERY_MAX_TERMS:
            break
    return terms or ["feature"]


def _run_uv_command(args: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run a repo command through uv with the repo-local cache enabled."""
    return subprocess.run(
        ["uv", "run", "--no-sync", *args],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_discovery(terms: Iterable[str], env: dict[str, str]) -> list[dict[str, Any]]:
    """Run semantic code discovery for each search term in parallel."""
    term_list = list(terms)
    if not term_list:
        return []

    with ThreadPoolExecutor(max_workers=min(len(term_list), 5)) as pool:
        future_map = {
            pool.submit(_run_uv_command, ["python3", "scripts/read_code.py", "context", term], env=env): term
            for term in term_list
        }
        results: list[dict[str, Any]] = []
        for future, term in future_map.items():
            proc = future.result()
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            results.append(
                {
                    "term": term,
                    "returncode": proc.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "has_matches": proc.returncode == 0 and "ERROR: No match found" not in stdout + stderr,
                }
            )

    results.sort(key=lambda item: term_list.index(item["term"]))
    return results


def _create_feature(description: str, short_name: str, env: dict[str, str]) -> dict[str, Any]:
    """Create the feature scaffold and return the parsed JSON payload."""
    cmd = [
        "python3",
        ".specify/scripts/python/create_new_feature.py",
        "--json",
    ]
    if short_name:
        cmd.extend(["--short-name", short_name])
    cmd.append(description)
    proc = _run_uv_command(cmd, env=env)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "feature creation failed").strip())

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"feature creation returned invalid JSON: {exc}") from exc


def _render_discovery_result(result: dict[str, Any]) -> str:
    """Return a human-readable discovery block for a single search term."""
    lines = [f"- Term: {result['term']}"]
    body = (result["stdout"] or result["stderr"] or "").rstrip()
    if body:
        lines.extend(f"  {line}" for line in body.splitlines())
    else:
        lines.append("  No discovery output")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """Run the fast-path spec bootstrap for a new feature description."""
    parser = argparse.ArgumentParser(description="Fast-path bootstrap for speckit.specify")
    parser.add_argument("--json", action="store_true", help="Emit a JSON summary")
    parser.add_argument("--short-name", default="", help="Optional short name for the feature")
    parser.add_argument("feature_description", help="Feature description to bootstrap")
    args = parser.parse_args(argv)

    try:
        env = _build_uv_env()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    terms = _extract_terms(args.feature_description)
    discovery = _run_discovery(terms, env)

    feature = _create_feature(args.feature_description, args.short_name, env)
    feature_dir = Path(feature["SPEC_FILE"]).resolve().parent

    summary = {
        "BRANCH_NAME": feature["BRANCH_NAME"],
        "FEATURE_NUM": feature["FEATURE_NUM"],
        "FEATURE_DIR": str(feature_dir),
        "SPEC_FILE": feature["SPEC_FILE"],
        "DISCOVERY_TERMS": terms,
        "DISCOVERY": discovery,
    }

    if args.json:
        print(json.dumps(summary, separators=(",", ":")))
        return 0

    print("Discovery")
    for result in discovery:
        print(_render_discovery_result(result))
        print()
    print()
    print("Scaffolded")
    print(f"- spec: {summary['SPEC_FILE']}")
    print(f"- branch: {summary['BRANCH_NAME']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
