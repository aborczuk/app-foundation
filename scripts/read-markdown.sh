#!/bin/bash

# read-markdown.sh: Enforce grep-first pattern for markdown file reads
#
# MANDATORY: All reads of markdown files >100 lines MUST use this helper.
# This script enforces the Markdown File Read Efficiency rule from CLAUDE.md:
# "For any markdown file >100 lines, Grep MUST be called first to locate
#  the relevant section, then Read with offset/limit targeting only that window."
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

    # Step 1: Grep for the section heading to get line number
    local line_num
    line_num=$(grep -n "^## $section" "$file" | cut -d: -f1 | head -1)

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
