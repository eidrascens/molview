#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ ! -f web/dist/index.html || ! -f web/dist/viewer.js ]]; then
  echo "Mol* frontend bundle not found; run: npm install && npm run build" >&2
  exit 1
fi
exec env PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m molview "$@"
