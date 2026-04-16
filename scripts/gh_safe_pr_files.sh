#!/usr/bin/env bash

# gh_safe_pr_files.sh: bounded changed-file listing for PR research and review workflows.
#
# Usage:
#   scripts/gh_safe_pr_files.sh <owner/repo> <pr_number> [max_rows]
#
# Example:
#   scripts/gh_safe_pr_files.sh aborczuk/app-foundation 17 100

set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "Usage: scripts/gh_safe_pr_files.sh <owner/repo> <pr_number> [max_rows]" >&2
    exit 1
fi

repo="$1"
pr="$2"
max_rows="${3:-200}"

if ! [[ "$max_rows" =~ ^[0-9]+$ ]] || [[ "$max_rows" -le 0 ]]; then
    echo "ERROR: max_rows must be a positive integer" >&2
    exit 1
fi

gh pr view "$pr" --repo "$repo" --json files --jq '
  .files
  | .[:'"$max_rows"']
  | map({path, status, additions, deletions, changes})
'
