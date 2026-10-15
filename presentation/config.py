# config.py
"""Application configuration loaded from environment variables."""

import os

DB_CONFIG = {
    "dbname": os.getenv("POSTGRES_DB", "taxis_porto"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
    "port": int(os.getenv("POSTGRES_PORT", "5433")),
}

# Optional CARTO Basemaps API key. If it is missing, the app uses OpenStreetMap.
CARTO_API_KEY = os.getenv("CARTO_API_KEY", "")
