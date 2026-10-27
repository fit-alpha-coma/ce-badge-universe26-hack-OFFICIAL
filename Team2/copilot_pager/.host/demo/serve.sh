#!/usr/bin/env bash
set -euo pipefail

PAGER_APP="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec "$PAGER_APP/.host/.venv/bin/copilot-pager" serve
