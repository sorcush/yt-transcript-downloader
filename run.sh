#!/bin/bash
set -e
cd "$(dirname "$0")"
uvicorn backend.main:app --reload --port 8000 &
SERVER_PID=$!
sleep 1
echo "Server running at http://localhost:8000"
if command -v open &>/dev/null; then
    open http://localhost:8000
elif command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:8000
fi
wait $SERVER_PID
