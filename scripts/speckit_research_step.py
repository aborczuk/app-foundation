#!/usr/bin/env python3
"""Generate and persist research triage and discovery notes for speckit.research."""

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

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DISCOVERY_MAX_TERMS = 5
FILE_PATH_RE = re.compile(r"^file_path:\s*(?P<path>.+)$", re.MULTILINE)
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
    """Return the repo-local environment for research workflows."""
    from uv_env import repo_uv_env

    os.environ.update(repo_uv_env())
    return os.environ.copy()


def _load_spec_description(spec_file: Path) -> str:
    """Extract the stored user description from the generated spec scaffold."""
    if not spec_file.is_file():
        return ""
    text = spec_file.read_text(encoding="utf-8")
    if "User description:" in text:
        return text.split("User description:", 1)[1].strip().strip('"')
    return text.strip()


def _extract_terms(description: str) -> list[str]:
    """Derive a compact set of research discovery terms from the feature description."""
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


def _classify_tshirt_size(match_count: int, duplicate: bool) -> str:
    """Map research signal breadth to a t-shirt size."""
    if duplicate:
        return "xs"
    if match_count == 0:
        return "xl"
    if match_count == 1:
        return "l"
    if match_count <= 3:
        return "m"
    return "s"


def _extract_file_paths(output: str) -> list[str]:
    """Pull file paths out of read_code context output."""
    return [match.group("path").strip() for match in FILE_PATH_RE.finditer(output)]


def _build_triage(discovery: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize duplicate risk and rough LOE from discovery results."""
    matching_results = [result for result in discovery if bool(result.get("has_matches"))]
    duplicate_hits: list[dict[str, str]] = []
    for result in matching_results:
        term = str(result.get("term") or "unknown")
        output = "\n".join([str(result.get("stdout") or ""), str(result.get("stderr") or "")])
        for file_path in _extract_file_paths(output):
            if "/specs/" in file_path or file_path.endswith("spec.md"):
                duplicate_hits.append({"term": term, "file_path": file_path})

    duplicate = bool(duplicate_hits)
    tshirt_size = _classify_tshirt_size(len(matching_results), duplicate)
    return {
        "duplicate": duplicate,
        "tshirt_size": tshirt_size,
        "matching_terms": len(matching_results),
        "duplicate_hits": duplicate_hits[:5],
    }


def _run_uv_command(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run a repo-local command with the uv environment."""
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _render_discovery_result(result: dict[str, Any]) -> str:
    """Render one discovery result block for the terminal and discovery.md."""
    term = result.get("term", "unknown")
    has_matches = bool(result.get("has_matches"))
    stdout = str(result.get("stdout") or "").rstrip()
    stderr = str(result.get("stderr") or "").rstrip()
    lines = [f"- {term}", f"  has_matches: {str(has_matches).lower()}"]
    if stdout:
        lines.append("  stdout:")
        lines.extend(f"    {line}" for line in stdout.splitlines())
    if stderr:
        lines.append("  stderr:")
        lines.extend(f"    {line}" for line in stderr.splitlines())
    return "\n".join(lines)


def _render_triage_result(triage: dict[str, Any]) -> str:
    """Render the triage summary block for discovery.md."""
    lines = [
        "## Triage",
        "",
        f"- duplicate: {str(bool(triage.get('duplicate'))).lower()}",
        f"- tshirt_size: {triage.get('tshirt_size', 'unknown')}",
        f"- matching_terms: {int(triage.get('matching_terms', 0))}",
    ]
    duplicate_hits = triage.get("duplicate_hits") or []
    if duplicate_hits:
        lines.append("- duplicate_hits:")
        for hit in duplicate_hits:
            lines.append(f"  - {hit.get('term', 'unknown')}: {hit.get('file_path', 'unknown')}")
    return "\n".join(lines)


def _run_discovery(terms: Iterable[str], env: dict[str, str]) -> list[dict[str, Any]]:
    """Run semantic code discovery for each search term in parallel."""
    term_list = list(terms)
    if not term_list:
        return []

    with ThreadPoolExecutor(max_workers=min(len(term_list), 5)) as pool:
        future_map = {
            pool.submit(_run_uv_command, [sys.executable, "scripts/read_code.py", "context", term], env=env): term
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


def _write_discovery_artifact(feature_dir: Path, discovery: list[dict[str, Any]]) -> Path:
    """Write discovery.md for the feature."""
    triage = _build_triage(discovery)
    lines = ["# Discovery", "", _render_triage_result(triage), "", "## Code Discovery", ""]
    for result in discovery:
        lines.append(_render_discovery_result(result))
        lines.append("")
    discovery_path = feature_dir / "discovery.md"
    discovery_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return discovery_path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse research discovery runner arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-dir", required=True)
    parser.add_argument("--spec-file", required=True)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """Build discovery notes for the research phase."""
    args = _parse_args(argv)
    feature_dir = Path(args.feature_dir).resolve()
    spec_file = Path(args.spec_file).resolve()

    try:
        env = _build_uv_env()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not feature_dir.is_dir():
        print(f"ERROR: Missing feature dir: {feature_dir}", file=sys.stderr)
        return 1
    if not spec_file.is_file():
        print(f"ERROR: Missing spec file: {spec_file}", file=sys.stderr)
        return 1

    discovery_path = feature_dir / "discovery.md"
    description = _load_spec_description(spec_file)
    terms = _extract_terms(description or feature_dir.name)
    discovery = _run_discovery(terms, env)
    triage = _build_triage(discovery)
    _write_discovery_artifact(feature_dir, discovery)

    payload = {
        "schema_version": "1.0.0",
        "ok": True,
        "exit_code": 0,
        "feature_dir": str(feature_dir),
        "spec_file": str(spec_file),
        "discovery_file": str(discovery_path),
        "term_count": len(discovery),
        "triage": triage,
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
