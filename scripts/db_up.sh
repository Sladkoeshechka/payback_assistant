#!/usr/bin/env bash
set -euo pipefail

service="${1:-db}"
main_db="${2:-payback}"
test_db="${3:-payback_test}"
user="${4:-payback}"

docker compose up "${service}" -d

echo "Waiting for Postgres..."
for i in $(seq 1 30); do
  if docker compose exec -T "${service}" pg_isready -U "${user}" -d "${main_db}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
  if [[ "${i}" == "30" ]]; then
    echo "Postgres did not become ready in time." >&2
    exit 1
  fi
done

if ! docker compose exec -T "${service}" psql -U "${user}" -d "${main_db}" -tc \
  "SELECT 1 FROM pg_database WHERE datname='${test_db}'" | grep -q 1; then
  docker compose exec -T "${service}" psql -U "${user}" -d "${main_db}" \
    -c "CREATE DATABASE ${test_db};"
fi

echo "Postgres ready (${main_db} + ${test_db})."
