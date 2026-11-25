#!/bin/sh
set -e
# Apply migrations as the owner role, then serve as the least-privilege app role.
python - <<'PY'
import time, sqlalchemy as sa
from termscheck.settings import settings
url = settings.migration_database_url or settings.database_url
for i in range(60):
    try:
        sa.create_engine(url).connect().close(); break
    except Exception:
        time.sleep(1)
PY
alembic upgrade head
exec "$@"
