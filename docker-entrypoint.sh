#!/bin/bash
set -e

# Run database migrations
echo "Running alembic migrations..."
alembic upgrade head

# Run data ingestion (Idempotent)
echo "Running data ingestion..."
python scripts/ingest_data.py

# Run Neo4j bootstrap (Idempotent)
echo "Running Neo4j bootstrap..."
python scripts/neo4j_bootstrap.py

# Start the uvicorn server
echo "Starting GraphIQ server on port $PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
