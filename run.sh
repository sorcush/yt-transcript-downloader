#!/bin/bash
cd "$(dirname "$0")"

cleanup() {
    kill -- -"$SERVER_PID" 2>/dev/null || true
    sleep 1
    kill -9 -- -"$SERVER_PID" 2>/dev/null || true
}
trap cleanup INT TERM HUP EXIT

set -m  # enable job control so uvicorn gets its own process group
uvicorn backend.main:app --reload --port 8000 &
SERVER_PID=$!
sleep 1
echo "Server running at http://localhost:8000  (Ctrl+C to stop)"
if command -v open &>/dev/null; then
    open http://localhost:8000
elif command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:8000
fi
wait $SERVER_PID
