#!/usr/bin/env bash

set -euo pipefail

print_usage() {
  cat <<'EOF'
Usage:
  .specify/scripts/test-specify.sh

What it checks:
  1. create-new-feature.sh still creates a branch/spec pair in a writeable temp repo.
  2. create-new-feature.sh reports a permission-specific error when git metadata is not writable.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --help|-h)
      print_usage
      exit 0
      ;;
    *)
      print_usage >&2
      exit 1
      ;;
  esac
done

REPO_ROOT="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CREATE_FEATURE_SCRIPT="$REPO_ROOT/.specify/scripts/bash/create-new-feature.sh"
TMP_ROOT="${TMPDIR:-/tmp}"
TEST_DIR="$(mktemp -d "${TMP_ROOT%/}/specify-smoke-XXXXXX")"
trap 'rm -rf "$TEST_DIR"' EXIT

mkdir -p "$TEST_DIR/.specify/templates"
cat > "$TEST_DIR/.specify/templates/spec-template.md" <<'EOF'
# [FEATURE_NAME]

## Summary

[SUMMARY]
EOF

git -C "$TEST_DIR" init -q

SUCCESS_OUTPUT="$(cd "$TEST_DIR" && bash "$CREATE_FEATURE_SCRIPT" --json --short-name "smoke test" "Feature creation smoke test")"

python3 - "$SUCCESS_OUTPUT" "$TEST_DIR" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
test_dir = Path(sys.argv[2])

branch_name = payload["BRANCH_NAME"]
spec_file = Path(payload["SPEC_FILE"]).resolve()

if not branch_name.endswith("smoke-test"):
    raise SystemExit(f"Unexpected branch name: {branch_name}")
if not spec_file.exists():
    raise SystemExit(f"Spec file was not created: {spec_file}")

expected_spec = (test_dir / "specs" / branch_name / "spec.md").resolve()
if spec_file != expected_spec:
    raise SystemExit(f"Unexpected spec path: {spec_file} != {expected_spec}")
PY

FAKE_BIN="$TEST_DIR/fake-bin"
mkdir -p "$FAKE_BIN"
REAL_GIT="$(command -v git)"
cat > "$FAKE_BIN/git" <<EOF
#!/usr/bin/env bash
set -euo pipefail

if [[ "\${1:-}" == "switch" && "\${2:-}" == "-c" ]]; then
  echo "fatal: cannot lock ref 'refs/heads/test-branch': Permission denied" >&2
  exit 1
fi

exec "$REAL_GIT" "\$@"
EOF
chmod +x "$FAKE_BIN/git"

set +e
FAIL_OUTPUT="$(cd "$TEST_DIR" && PATH="$FAKE_BIN:$PATH" bash "$CREATE_FEATURE_SCRIPT" --json --short-name "locked branch" "Feature creation failure smoke test" 2>&1)"
FAIL_EXIT=$?
set -e

if [[ $FAIL_EXIT -eq 0 ]]; then
  echo "Expected create-new-feature.sh to fail when git branch creation is denied" >&2
  exit 1
fi

case "$FAIL_OUTPUT" in
  *"repository metadata is not writable in this environment"* ) ;;
  *)
    echo "Permission-specific message missing from failure output" >&2
    printf '%s\n' "$FAIL_OUTPUT" >&2
    exit 1
    ;;
esac

case "$FAIL_OUTPUT" in
  *"fatal: cannot lock ref"* ) ;;
  *)
    echo "Underlying git stderr missing from failure output" >&2
    printf '%s\n' "$FAIL_OUTPUT" >&2
    exit 1
    ;;
esac

printf '%s\n' "$TEST_DIR"
