#!/usr/bin/env bash
# preToolUse: bloquea exploración hasta sync. Stdout = solo JSON.
set -euo pipefail
cat >/dev/null

# shellcheck source=graphify-sync-lib.sh
source "$(cd "$(dirname "$0")" && pwd)/graphify-sync-lib.sh"
cd "$(graphify_root)"

if graphify_ensure_fresh; then
  echo '{"permission":"allow"}'
  exit 0
fi

echo '{"permission":"deny","user_message":"graphify update falló. Revisá el PATH (~/.local/bin) o corré: graphify update .","agent_message":"graphify update failed; explore tools blocked until sync succeeds."}'
exit 2
