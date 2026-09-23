#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for name in employees.json events.json skills.json activity_history.csv; do
  test -f "data/$name" || { echo "Missing data/$name" >&2; exit 1; }
done
docker compose build
mkdir -p offline
docker image save -o offline/career-quest-images.tar career-quest-backend:local career-quest-frontend:local
echo "Offline images prepared for this machine's architecture. Keep the repository and local data/ with them."
echo "On the offline machine: bash scripts/run-offline.sh"
