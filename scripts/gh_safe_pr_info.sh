#!/usr/bin/env bash

# gh_safe_pr_info.sh: low-payload PR metadata view for research workflows.
#
# Usage:
#   scripts/gh_safe_pr_info.sh <owner/repo> <pr_number>
#
# Example:
#   scripts/gh_safe_pr_info.sh aborczuk/app-foundation 17

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: scripts/gh_safe_pr_info.sh <owner/repo> <pr_number>" >&2
    exit 1
fi

repo="$1"
pr="$2"

gh pr view "$pr" \
    --repo "$repo" \
    --json number,title,state,isDraft,url,author,baseRefName,headRefName,changedFiles,additions,deletions,updatedAt
