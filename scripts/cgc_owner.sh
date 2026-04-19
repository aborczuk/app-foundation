#!/usr/bin/env bash
set -euo pipefail

cgc_owner_pid_file() {
  printf '%s\n' "$CODEGRAPH_DB_DIR/${CGC_OWNER_DB_NAME:-kuzudb}.owner.pid"
}

cgc_owner_lock_file() {
  printf '%s\n' "$CODEGRAPH_DB_DIR/${CGC_OWNER_DB_NAME:-kuzudb}.lock"
}

cgc_owner_wait_seconds() {
  printf '%s\n' "${CGC_OWNER_WAIT_SECONDS:-15}"
}

cgc_owner_poll_seconds() {
  printf '%s\n' "${CGC_OWNER_POLL_SECONDS:-1}"
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

cgc_owner_clear_artifacts() {
  rm -f "$(cgc_owner_pid_file)" "$(cgc_owner_lock_file)"
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
  local owner_file owner_wait owner_poll waited owner_pid

  owner_file="$(cgc_owner_pid_file)"
  owner_wait="$(cgc_owner_wait_seconds)"
  owner_poll="$(cgc_owner_poll_seconds)"
  waited=0

  while [ -f "$owner_file" ]; do
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

    if [ "$waited" -ge "$owner_wait" ]; then
      echo "Existing CodeGraph owner (pid $owner_pid) is still active after ${owner_wait}s; refusing recovery yet." >&2
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
