#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$PROJECT_DIR/../../work/odoo19-env/.venv/bin/python"
exec "$VENV_PYTHON" "$PROJECT_DIR/dev.py" "$@"
