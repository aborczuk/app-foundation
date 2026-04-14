#!/usr/bin/env bash

set -euo pipefail

print_usage() {
  cat <<'EOF'
Usage:
  .specify/scripts/test-research.sh feature_id=XYZ

What it checks:
  1. The speckit.research manifest entry still points at research-template-compact.md.
  2. The speckit.research command doc still documents the compact scaffold invocation and no-subagent flow.
  3. pipeline-scaffold generates a research.md with all required section headers.
EOF
}

FEATURE_ID=""

for arg in "$@"; do
  case "$arg" in
    --help|-h)
      print_usage
      exit 0
      ;;
    feature_id=*)
      FEATURE_ID="${arg#feature_id=}"
      ;;
    *)
      print_usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$FEATURE_ID" ]]; then
  print_usage >&2
  exit 1
fi

TMP_ROOT="${TMPDIR:-/tmp}"
TEST_DIR="$(mktemp -d "${TMP_ROOT%/}/research-${FEATURE_ID:-feature}-XXXXXX")"
trap 'rm -rf "$TEST_DIR"' EXIT

export UV_CACHE_DIR="${TMP_ROOT%/}/app-foundation-uv-cache"
mkdir -p "$UV_CACHE_DIR"

uv run python - "$FEATURE_ID" <<'PY'
import sys
from pathlib import Path

import yaml

repo_root = Path.cwd()
manifest_path = repo_root / ".specify" / "command-manifest.yaml"
command_doc_path = repo_root / ".claude" / "commands" / "speckit.research.md"
expected_template = "research-template-compact.md"

manifest = yaml.safe_load(manifest_path.read_text())
template = manifest["commands"]["speckit.research"]["artifacts"][0]["template"]
if template != expected_template:
    raise SystemExit(f"Manifest template mismatch: expected {expected_template}, found {template}")

command_doc = command_doc_path.read_text()
required_snippets = [
    "research-template-compact.md",
    "UV_CACHE_DIR=\"${TMPDIR:-/tmp}/app-foundation-uv-cache\" uv run python .specify/scripts/pipeline-scaffold.py speckit.research",
    "Do not spawn sub-agents",
    "top 3-5 matches",
    "feature_id=XYZ",
]
missing = [snippet for snippet in required_snippets if snippet not in command_doc]
if missing:
    raise SystemExit(f"Command doc missing required snippets: {', '.join(missing)}")
PY

uv run python .specify/scripts/pipeline-scaffold.py speckit.research --feature-dir "$TEST_DIR" FEATURE_NAME="Compact Research Test" >/dev/null

python3 - "$TEST_DIR/research.md" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
required = [
    "## Zero-Custom-Server Assessment",
    "## Repo Assembly Map",
    "## Package Adoption Options",
    "## Conceptual Patterns",
    "## Search Tools Used",
    "## Unanswered Questions",
]
missing = [section for section in required if section not in text]
if missing:
    raise SystemExit(f"Missing sections: {', '.join(missing)}")
PY

printf '%s\n' "$TEST_DIR/research.md"
