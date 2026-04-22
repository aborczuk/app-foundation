#!/usr/bin/env bash
set -euo pipefail

cgc_owner_pid_file() {
  printf '%s\n' "$CODEGRAPH_DB_DIR/${CGC_OWNER_DB_NAME:-kuzudb}.owner.pid"
}

cgc_owner_lock_file() {
  printf '%s\n' "$CODEGRAPH_DB_DIR/${CGC_OWNER_DB_NAME:-kuzudb}.lock"
}

cgc_owner_last_error_file() {
  printf '%s\n' "$CODEGRAPH_CONTEXT_DIR/last-index-error.txt"
}

cgc_owner_last_edit_signature_file() {
  printf '%s\n' "$CODEGRAPH_CONTEXT_DIR/last-edit-signature.txt"
}

cgc_owner_wait_seconds() {
  printf '%s\n' "${CGC_OWNER_WAIT_SECONDS:-15}"
}

cgc_owner_poll_seconds() {
  printf '%s\n' "${CGC_OWNER_POLL_SECONDS:-1}"
}

cgc_owner_lock_stale_seconds() {
  printf '%s\n' "${CGC_OWNER_LOCK_STALE_SECONDS:-300}"
}

cgc_owner_file_mtime_epoch() {
  local path mtime
  path="${1:-}"
  if [ -z "$path" ] || [ ! -e "$path" ]; then
    return 1
  fi

  mtime="$(stat -f '%m' "$path" 2>/dev/null || true)"
  if cgc_owner_is_valid_pid "$mtime"; then
    printf '%s\n' "$mtime"
    return 0
  fi

  mtime="$(stat -c '%Y' "$path" 2>/dev/null || true)"
  if cgc_owner_is_valid_pid "$mtime"; then
    printf '%s\n' "$mtime"
    return 0
  fi

  return 1
}

cgc_owner_is_valid_pid() {
  case "${1:-}" in
    ""|*[!0-9]*)
      return 1
      ;;
    *)
      return 0
      ;;
  esac
}

cgc_owner_pid_is_alive() {
  local owner_state

  if ! kill -0 "$1" 2>/dev/null; then
    return 1
  fi

  owner_state="$(ps -p "$1" -o stat= 2>/dev/null || true)"
  case "$owner_state" in
    *Z*)
      return 1
      ;;
  esac

  return 0
}

cgc_owner_lock_is_stale_without_owner() {
  local owner_file lock_file stale_after now mtime age

  owner_file="$(cgc_owner_pid_file)"
  lock_file="$(cgc_owner_lock_file)"
  stale_after="$(cgc_owner_lock_stale_seconds)"
  if ! cgc_owner_is_valid_pid "$stale_after"; then
    stale_after=300
  fi

  if [ -f "$owner_file" ] || [ ! -f "$lock_file" ]; then
    return 1
  fi

  mtime="$(cgc_owner_file_mtime_epoch "$lock_file" || true)"
  now="$(date +%s 2>/dev/null || true)"
  if ! cgc_owner_is_valid_pid "$mtime" || ! cgc_owner_is_valid_pid "$now"; then
    return 1
  fi

  age=$((now - mtime))
  if [ "$age" -lt 0 ]; then
    age=0
  fi
  [ "$age" -ge "$stale_after" ]
}

cgc_owner_clear_artifacts() {
  rm -f "$(cgc_owner_pid_file)" "$(cgc_owner_lock_file)"
}

cgc_owner_clear_last_error() {
  rm -f "$(cgc_owner_last_error_file)"
}

cgc_owner_clear_last_edit_signature() {
  rm -f "$(cgc_owner_last_edit_signature_file)"
}

cgc_owner_release() {
  local owner_pid current_pid
  owner_pid="$(sed -n '1p' "$(cgc_owner_pid_file)" 2>/dev/null || true)"
  current_pid="$$"
  if [ "$owner_pid" = "$current_pid" ]; then
    cgc_owner_clear_artifacts
  fi
}

cgc_owner_wait_for_release() {
  local owner_file lock_file owner_wait owner_poll waited owner_pid

  owner_file="$(cgc_owner_pid_file)"
  lock_file="$(cgc_owner_lock_file)"
  owner_wait="$(cgc_owner_wait_seconds)"
  owner_poll="$(cgc_owner_poll_seconds)"
  waited=0

  while [ -f "$owner_file" ] || [ -f "$lock_file" ]; do
    if [ -f "$owner_file" ]; then
      owner_pid="$(sed -n '1p' "$owner_file" 2>/dev/null || true)"

      if ! cgc_owner_is_valid_pid "$owner_pid"; then
        echo "Removing invalid CodeGraph owner marker: $owner_file"
        cgc_owner_clear_artifacts
        return 0
      fi

      if ! cgc_owner_pid_is_alive "$owner_pid"; then
        echo "Removing stale CodeGraph owner marker (pid $owner_pid): $owner_file"
        cgc_owner_clear_artifacts
        return 0
      fi
    elif cgc_owner_lock_is_stale_without_owner; then
      echo "Removing stale CodeGraph lock marker without owner: $lock_file"
      rm -f "$lock_file"
      return 0
    fi

    if [ "$waited" -ge "$owner_wait" ]; then
      if [ -f "$owner_file" ]; then
        echo "Existing CodeGraph owner (pid $owner_pid) is still active after ${owner_wait}s; refusing recovery yet." >&2
      else
        echo "CodeGraph lock marker persists without owner after ${owner_wait}s; refusing recovery yet." >&2
      fi
      return 75
    fi

    sleep "$owner_poll"
    waited=$((waited + owner_poll))
  done

  return 0
}

cgc_owner_claim() {
  local owner_file lock_file

  owner_file="$(cgc_owner_pid_file)"
  lock_file="$(cgc_owner_lock_file)"
  printf '%s\n' "$$" > "$owner_file"
  printf '%s\n' "pid=$$ command=$0" > "$lock_file"
  trap cgc_owner_release EXIT INT TERM
}

cgc_owner_error_is_memory_pressure() {
  local normalized_error

  normalized_error="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  case "$normalized_error" in
    *"buffer pool"*exhaust*|*"out of memory"*|*"memory pressure"*|*"memory exhausted"*|*"cannot allocate"*|*"allocation failed"*)
      return 0
      ;;
  esac

  return 1
}

cgc_owner_record_last_error() {
  local error_type exit_code error_detail error_file normalized_detail

  error_type="${1:-unknown}"
  exit_code="${2:-1}"
  error_detail="${3:-}"
  error_file="$(cgc_owner_last_error_file)"
  normalized_detail="$(printf '%s' "$error_detail" | tr '\n' ' ' | tr -s ' ')"

  {
    printf 'type=%s\n' "$error_type"
    printf 'exit_code=%s\n' "$exit_code"
    printf 'detail=%s\n' "$normalized_detail"
  } > "$error_file"
}

cgc_owner_current_edit_signature() {
  local status_file marker_file current_signature

  marker_file="$(cgc_owner_last_edit_signature_file)"
  status_file="$(mktemp "${TMPDIR:-/tmp}/cgc-edit-status-XXXXXX")"

  if ! git -C "$REPO_ROOT" status --porcelain --untracked-files=normal >"$status_file" 2>/dev/null; then
    rm -f "$status_file"
    return 0
  fi

  current_signature="$(
    python3 - "$status_file" <<'PY'
from pathlib import Path
import sys

ignored_prefixes = (
    ".codegraphcontext/",
    ".speckit/",
    ".uv-cache/",
    "logs/",
    "shadow-runs/",
)

status_path = Path(sys.argv[1])
lines = []
for raw in status_path.read_text(encoding="utf-8").splitlines():
    if not raw.strip():
        continue
    line = raw.rstrip("\n")
    path = line[3:] if len(line) > 3 else ""
    if " -> " in path:
        candidates = [part.strip() for part in path.split(" -> ")]
    else:
        candidates = [path.strip()]
    if any(candidate.startswith(ignored_prefixes) for candidate in candidates if candidate):
        continue
    lines.append(line)

print("\n".join(sorted(dict.fromkeys(lines))))
PY
  )"

  rm -f "$status_file"
  printf '%s\n' "$current_signature"
}

cgc_owner_record_edit_signature() {
  local signature_file current_signature

  signature_file="$(cgc_owner_last_edit_signature_file)"
  current_signature="$(cgc_owner_current_edit_signature)"
  printf '%s' "$current_signature" > "$signature_file"
}
