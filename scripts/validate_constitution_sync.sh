#!/usr/bin/env bash
# Verify that command docs, manifests, and constitution stay in sync.

set -euo pipefail

SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(CDPATH="" cd "$SCRIPT_DIR/.." && pwd)"

run_checks() {
  local output
  if output="$(
    cd "$REPO_ROOT" && \
      env UV_CACHE_DIR="${SPECKIT_UV_CACHE_DIR:-/tmp/uv-cache}" \
      uv run python scripts/validate_command_script_coverage.py --json 2>&1
  )"; then
    echo "PASS: command/script coverage validator"
  else
    echo "ERROR: command/script coverage validator failed." >&2
    echo "$output" >&2
    exit 1
  fi
}

# Usage:
#   scripts/validate_constitution_sync.sh [base_ref]
#
# Default base_ref is origin/main when available, otherwise main.
# The check enforces:
# - If files under .claude/commands/** or .specify/templates/** changed,
#   then constitution.md must also change in the same diff.
# - If constitution.md changed, then constitution-changelog.md must also change
#   in the same diff (amendment history must be recorded).

BASE_REF="${1:-}"
if [[ -z "${BASE_REF}" ]]; then
  if git -C "$REPO_ROOT" rev-parse --verify origin/main >/dev/null 2>&1; then
    BASE_REF="origin/main"
  else
    BASE_REF="main"
  fi
fi

if ! git -C "$REPO_ROOT" rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  echo "ERROR: base ref not found: $BASE_REF" >&2
  echo "Hint: pass an explicit ref, e.g. scripts/validate_constitution_sync.sh main" >&2
  exit 2
fi

run_checks

changed_files="$(
  git -C "$REPO_ROOT" diff --name-only "$BASE_REF"...HEAD
)"

if [[ -z "$changed_files" ]]; then
  echo "PASS: no changes vs $BASE_REF"
  exit 0
fi

governance_surface_changes="$(
  printf "%s\n" "$changed_files" | rg -n '^(\.claude/commands/|\.specify/templates/)' || true
)"

if [[ -z "$governance_surface_changes" ]]; then
  echo "PASS: no changes under .claude/commands/** or .specify/templates/**"
  exit 0
fi

constitution_changed="$(
  printf "%s\n" "$changed_files" | rg -n '^constitution\.md$' || true
)"

if [[ -z "$constitution_changed" ]]; then
  echo "ERROR: governance surfaces changed but constitution was not updated." >&2
  echo >&2
  echo "Changed governance-surface files:" >&2
  printf "%s\n" "$governance_surface_changes" >&2
  echo >&2
  echo "Required file missing from diff:" >&2
  echo "  constitution.md" >&2
  echo >&2
  echo "Action: update constitution (version/sync impact as appropriate) in same change." >&2
  exit 1
fi

# constitution.md changed — also require constitution-changelog.md to be updated
changelog_changed="$(
  printf "%s\n" "$changed_files" | rg -n '^constitution-changelog\.md$' || true
)"

if [[ -n "$changelog_changed" ]]; then
  echo "PASS: governance surfaces changed; constitution and changelog both updated."
  exit 0
fi

echo "ERROR: constitution.md changed but constitution-changelog.md was not updated." >&2
echo >&2
echo "Action: append a SYNC IMPACT REPORT entry to constitution-changelog.md in the same change." >&2
exit 1
