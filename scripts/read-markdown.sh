#!/bin/bash

# read-markdown.sh: Resolve markdown sections with vector-first anchoring and grep fallback.
#
# MANDATORY: All reads of markdown files >100 lines MUST use this helper.
# This script now prefers a vector markdown hit for the section anchor, then
# falls back to exact heading grep if the vector index has no usable match.
#
# Usage:
#   read_markdown_section <file_path> <section_heading>
#
# Examples:
#   read_markdown_section specs/020-app-foundation/plan.md "External Ingress"
#   read_markdown_section .claude/domains/14_security_controls.md "Core Principles"
#
# Returns: stdout contains the section content; exits 0 on success, 1 if section not found

set -e

_vector_markdown_line_num() {
    local file="$1"
    local section="$2"

    if [[ -z "$file" || -z "$section" ]]; then
        return 1
    fi

    if ! command -v uv >/dev/null 2>&1; then
        return 1
    fi

    local repo_root
    repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

    python3 - "$repo_root" "$file" "$section" <<'PYTHON_EOF'
import json
import subprocess
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).expanduser().resolve()
target_file = Path(sys.argv[2]).expanduser().resolve()
section = sys.argv[3]

cmd = [
    "uv",
    "run",
    "--no-sync",
    "python",
    "-m",
    "src.mcp_codebase.indexer",
    "--repo-root",
    str(repo_root),
    "query",
    section,
    "--scope",
    "markdown",
    "--top-k",
    "5",
]
proc = subprocess.run(cmd, capture_output=True, text=True)
if proc.returncode != 0:
    raise SystemExit(0)

try:
    payload = json.loads(proc.stdout or "[]")
except json.JSONDecodeError:
    raise SystemExit(0)

def _resolve_file(item):
    candidate = item.get("file_path")
    if candidate:
        return candidate
    content = item.get("content")
    if isinstance(content, dict):
        return content.get("file_path")
    return None

def _resolve_line(item):
    line = item.get("line_start")
    if line is not None:
        return line
    content = item.get("content")
    if isinstance(content, dict):
        return content.get("line_start")
    return None

def _resolve_heading(item):
    heading = item.get("heading")
    if heading:
        return heading
    content = item.get("content")
    if isinstance(content, dict):
        return content.get("heading")
    return None

def _resolve_breadcrumb_tail(item):
    breadcrumb = item.get("breadcrumb")
    if isinstance(breadcrumb, list) and breadcrumb:
        return breadcrumb[-1]
    content = item.get("content")
    if isinstance(content, dict):
        breadcrumb = content.get("breadcrumb")
        if isinstance(breadcrumb, list) and breadcrumb:
            return breadcrumb[-1]
    return None

for item in payload:
    candidate = _resolve_file(item)
    if not candidate:
        continue
    try:
        if Path(candidate).expanduser().resolve() != target_file:
            continue
    except Exception:
        continue

    heading = _resolve_heading(item)
    breadcrumb_tail = _resolve_breadcrumb_tail(item)
    if heading != section and breadcrumb_tail != section:
        continue

    line = _resolve_line(item)
    if line is not None:
        print(line)
        raise SystemExit(0)

raise SystemExit(0)
PYTHON_EOF
}

read_markdown_section() {
    local file="$1"
    local section="$2"

    if [[ -z "$file" || -z "$section" ]]; then
        echo "ERROR: read_markdown_section requires two arguments: <file> <section_heading>" >&2
        return 1
    fi

    if [[ ! -f "$file" ]]; then
        echo "ERROR: File not found: $file" >&2
        return 1
    fi

    # Step 1: Prefer a vector hit for the section anchor, then fall back to grep.
    local line_num
    line_num="$(_vector_markdown_line_num "$file" "$section")"

    if [[ -z "$line_num" ]]; then
        line_num=$(grep -n "^## $section" "$file" | cut -d: -f1 | head -1)
    fi

    if [[ -z "$line_num" ]]; then
        echo "ERROR: Section '## $section' not found in $file" >&2
        return 1
    fi

    # Step 2: Calculate the window size (default: 50 lines from the section start)
    # This can be tuned per-section if needed
    local window_size=50

    # Step 3: Use the Claude Code Read tool via Python to read the window
    # Since this is a bash script, we invoke Python which has access to the Read tool
    python3 - "$file" "$line_num" "$window_size" <<'PYTHON_EOF'
import sys
from pathlib import Path

file_path = sys.argv[1]
start_line = int(sys.argv[2])
window_size = int(sys.argv[3])

# Read the file
content = Path(file_path).read_text().split('\n')

# Extract the window starting from line_num (1-indexed)
# Adjust to 0-indexed
start_idx = start_line - 1
end_idx = min(start_idx + window_size, len(content))

# Print the section with line numbers for context
for i in range(start_idx, end_idx):
    print(f"{i+1}\t{content[i]}")
PYTHON_EOF

    return 0
}

# If called directly (not sourced), execute the function with provided arguments
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    read_markdown_section "$@"
fi
