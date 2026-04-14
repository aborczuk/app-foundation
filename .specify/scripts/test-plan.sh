#!/usr/bin/env bash

set -euo pipefail

print_usage() {
  cat <<'EOF'
Usage:
  .specify/scripts/test-plan.sh feature_id=XYZ

What it checks:
  1. The speckit.plan manifest entry still points at plan-template.md, data-model-template.md, and quickstart-template.md.
  2. The speckit.plan command doc still documents the compact, deterministic, driver-backed flow.
  3. pipeline-scaffold generates plan.md, data-model.md, and quickstart.md with the expected section headers.
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
TEST_DIR="$(mktemp -d "${TMP_ROOT%/}/plan-${FEATURE_ID:-feature}-XXXXXX")"
trap 'rm -rf "$TEST_DIR"' EXIT

export UV_CACHE_DIR="${TMP_ROOT%/}/app-foundation-uv-cache"
mkdir -p "$UV_CACHE_DIR"

uv run python - "$FEATURE_ID" <<'PY'
from pathlib import Path
import yaml

repo_root = Path.cwd()
manifest_path = repo_root / ".specify" / "command-manifest.yaml"
command_doc_path = repo_root / ".claude" / "commands" / "speckit.plan.md"

manifest = yaml.safe_load(manifest_path.read_text())
artifacts = manifest["commands"]["speckit.plan"]["artifacts"]
templates = [artifact["template"] for artifact in artifacts]
expected_templates = ["plan-template.md", "data-model-template.md", "quickstart-template.md"]
if templates != expected_templates:
    raise SystemExit(
        "Manifest template mismatch: expected "
        f"{expected_templates}, found {templates}"
    )

command_doc = command_doc_path.read_text()
required_snippets = [
    "Compact Contract (Load First)",
    "setup-plan.sh --json",
    "speckit_gate_status.py --mode plan",
    "speckit_plan_gate.py spec-core-action",
    "speckit_plan_gate.py research-prereq",
    "speckit_plan_gate.py plan-sections",
    "speckit_plan_gate.py design-artifacts",
    "pipeline-scaffold.py speckit.plan",
    "driver already owns",
    "planreview",
    "feasibilityspike",
]
missing = [snippet for snippet in required_snippets if snippet not in command_doc]
if missing:
    raise SystemExit(f"Command doc missing required snippets: {', '.join(missing)}")

forbidden_snippets = [
    "--artifact",
    "--fr-ids",
    "FR_PHRASE",
    "gh workflow search",
    "echo '{\"event\": \"plan_started\"}'",
    "echo '{\"event\": \"plan_approved\"}'",
]
present = [snippet for snippet in forbidden_snippets if snippet in command_doc]
if present:
    raise SystemExit(f"Command doc still contains forbidden snippets: {', '.join(present)}")
PY

uv run python .specify/scripts/pipeline-scaffold.py speckit.plan --feature-dir "$TEST_DIR" FEATURE_NAME="Compact Plan Test" >/dev/null

python3 - "$TEST_DIR" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
required_files = [
    root / "plan.md",
    root / "data-model.md",
    root / "quickstart.md",
]
missing = [str(path) for path in required_files if not path.exists()]
if missing:
    raise SystemExit(f"Missing scaffolded artifacts: {', '.join(missing)}")

plan_text = (root / "plan.md").read_text()
required_sections = [
    "## Summary",
    "## Technical Context",
    "## Repeated Architectural Unit Recognition",
    "## Reuse-First Architecture Decision",
    "## Pipeline Architecture Model",
    "## Artifact / Event Contract Architecture",
    "## Architecture Flow",
    "## External Ingress + Runtime Readiness Gate",
    "## State / Storage / Reliability Model",
    "## Open Feasibility Questions",
    "## Handoff Contract to Sketch",
]
missing_sections = [section for section in required_sections if section not in plan_text]
if missing_sections:
    raise SystemExit(f"Missing plan sections: {', '.join(missing_sections)}")
PY

printf '%s\n' "$TEST_DIR/plan.md"
