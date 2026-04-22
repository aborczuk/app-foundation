#!/usr/bin/env bash

# Source-only helper that keeps uv's cache inside the repository.
# This avoids permission failures in sandboxed or restricted environments.

if [[ -z "${UV_CACHE_DIR:-}" ]]; then
    UV_CACHE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.codegraphcontext/.uv-cache"
    export UV_CACHE_DIR
fi

mkdir -p "$UV_CACHE_DIR"
