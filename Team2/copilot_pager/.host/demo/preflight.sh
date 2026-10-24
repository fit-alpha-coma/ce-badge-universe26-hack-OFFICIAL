#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
PAGER_APP="$PROJECT_ROOT/Team2/copilot_pager"
PAGER="$PAGER_APP/.host/.venv/bin/copilot-pager"
PAGER_PYTHON="$PAGER_APP/.host/.venv/bin/python"
HOOK_ROOT="${COPILOT_HOME:-$HOME/.copilot}"

cd "$PROJECT_ROOT"

test -x "$PAGER"
test -f "$HOOK_ROOT/hooks/copilot-pager.json"
test -f "$PAGER_APP/.demo/copilot-pager-poc/demo.py"

"$PAGER_PYTHON" --version
copilot --version

bluetoothctl show | grep -q 'Powered: yes'
echo "Bluetooth: PASS"

PYTHONPATH="$PAGER_APP/.host/src" \
  "$PAGER_PYTHON" -m unittest discover "$PAGER_APP/.host/tests" -q
python3 .github/skills/badge-app-builder/scripts/validate_app.py "$PAGER_APP"

if "$PAGER" doctor; then
  :
else
  echo "Pairing is expected to remain pending until the badge is mounted."
fi
