#!/usr/bin/env bash
# Shared graphify sync helpers. Stdout reserved for JSON callers.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

graphify_root() {
  cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  pwd
}

graphify_fingerprint() {
  local root="$1"
  {
    find "$root" -maxdepth 2 -type d -name .git 2>/dev/null | sort | while read -r gitdir; do
      local repo
      repo="$(dirname "$gitdir")"
      echo "REPO:$repo"
      git -C "$repo" rev-parse HEAD 2>/dev/null || echo none
      git -C "$repo" status --porcelain 2>/dev/null || true
    done
    find "$root" -maxdepth 1 -type f \( -name '*.py' -o -name '*.toml' -o -name '*.txt' \) \
      -printf '%p %T@ %s\n' 2>/dev/null | sort
  } | sha256sum | awk '{print $1}'
}

# Returns 0 if grafo al día o update ok; 1 si update falló.
# Args: none. Usa cwd = project root.
graphify_ensure_fresh() {
  local root state_dir state_file desired
  root="$(pwd)"
  state_dir="$root/graphify-out"
  state_file="$state_dir/.cursor-graphify-sync-state"
  mkdir -p "$state_dir"

  desired="$(graphify_fingerprint "$root")"

  if [[ -f "$state_file" ]] && [[ "$(cat "$state_file")" == "$desired" ]]; then
    return 0
  fi

  if graphify update . >&2; then
    echo "$desired" > "$state_file"
    return 0
  fi
  return 1
}
