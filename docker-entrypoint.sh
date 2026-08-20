#!/bin/sh
set -e

echo "waiting for postgres..."
until python -c "
import sys, psycopg
from app.config import get_settings
url = get_settings().database_url.replace('postgresql+psycopg://', 'postgresql://')
try:
    psycopg.connect(url, connect_timeout=3).close()
except Exception as exc:
    print(exc, file=sys.stderr); sys.exit(1)
" 2>/dev/null; do
  sleep 1
done

echo "applying migrations..."
alembic upgrade head

exec "$@"
