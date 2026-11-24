#!/bin/bash
# Double-click to start. First start creates a Python environment (needs internet once).
cd "$(dirname "$0")"
VENV="$HOME/.venvs/village-dg"
PY=/opt/homebrew/bin/python3.12
[ -x "$PY" ] || PY=python3
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating Python environment in $VENV ..."
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/python" -c "import numpy, matplotlib, PIL, requests, tkintermapview" 2>/dev/null \
  || "$VENV/bin/pip" install -q -r requirements.txt
exec "$VENV/bin/python" main.py
