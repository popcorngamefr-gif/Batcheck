#!/usr/bin/env bash
# Lance batcheck et ouvre le navigateur.
cd "$(dirname "$0")" || exit 1

PY=python3
command -v $PY >/dev/null 2>&1 || PY=python

URL="http://127.0.0.1:8765"
( sleep 1.5
  if command -v open >/dev/null 2>&1; then open "$URL"          # macOS
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" # Linux
  fi ) &

exec $PY server.py
