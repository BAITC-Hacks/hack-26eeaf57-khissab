#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f offline/career-quest-images.tar ]]; then
  docker image load -i offline/career-quest-images.tar
fi
docker image inspect career-quest-backend:local career-quest-frontend:local >/dev/null
for name in employees.json events.json skills.json activity_history.csv; do
  test -f "data/$name" || { echo "Missing data/$name" >&2; exit 1; }
done
# An explicit overlay wins over .env: no model network request in offline mode.
docker compose -f docker-compose.yml -f docker-compose.offline.yml up --no-build --pull never "$@"
