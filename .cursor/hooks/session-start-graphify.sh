#!/usr/bin/env bash
# sessionStart: actualiza nodos graphify. Stdout = solo JSON.
set -euo pipefail
cat >/dev/null

# shellcheck source=graphify-sync-lib.sh
source "$(cd "$(dirname "$0")" && pwd)/graphify-sync-lib.sh"
cd "$(graphify_root)"

if graphify_ensure_fresh; then
  echo '{"additional_context":"graphify: grafo sincronizado al inicio de sesión (graphify-out/). Usar graphify query|path|explain antes de explorar."}'
  exit 0
fi

echo '{"additional_context":"graphify: update falló al inicio de sesión; el grafo puede estar desactualizado. Ejecutar: graphify update ."}'
exit 0
