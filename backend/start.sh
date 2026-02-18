#!/usr/bin/env sh
set -eu

cd /app/backend

uvicorn main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

cleanup() {
  kill "$API_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

exec streamlit run leaderboard/main.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true

