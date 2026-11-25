# Build context: repository root (see docker-compose.yml)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/termscheck ./termscheck
RUN pip install .
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/scripts ./scripts
COPY backend/docker-entrypoint.sh /usr/local/bin/
COPY data /app/data
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && useradd -m app && mkdir -p /app/storage && chown app /app/storage
USER app
ENV TERMSCHECK_STORAGE_DIR=/app/storage TERMSCHECK_RECORDED_DIR=/app/data/recorded_extractions
EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "termscheck.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
