#!/bin/sh
set -eu

echo "payback: running database migrations"
alembic upgrade head

echo "payback: starting application"
exec python -m payback
