# database.py
"""Handles all database connections and query building."""

import psycopg2
import pandas as pd
from config import DB_CONFIG

def fetch_data(query):
    """Connects to the DB, executes a query, and returns a DataFrame."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        print(f"Database connection error: {e}")
        return pd.DataFrame() # Return empty df on error

def build_query(mode, start_date, end_date, h1, h2, day_types):
    """Fetch raw trip points (lat, lon) between dates at a fixed hour."""

    date_filter = f"""
        AND time >= '{start_date}'
        AND time <= '{end_date}'
        AND EXTRACT(HOUR FROM time) BETWEEN {h1} AND {h2}
    """

    if "Weekday" in day_types and "Weekend" not in day_types:
        day_filter = "AND is_weekend = FALSE"
    elif "Weekend" in day_types and "Weekday" not in day_types:
        day_filter = "AND is_weekend = TRUE"
    else:
        day_filter = "" 

    bbox_filter = "AND ST_X({geom}) BETWEEN -8.75 AND -8.50 AND ST_Y({geom}) BETWEEN 41.0 AND 41.3"

    if mode == "both":
        return f"""
        SELECT ST_Y(geom) AS lat, ST_X(geom) AS lon
        FROM (
            SELECT pickup AS geom, time, is_weekend FROM trip_simple WHERE pickup IS NOT NULL {bbox_filter.format(geom='pickup')}
            UNION ALL
            SELECT dropoff AS geom, time, is_weekend FROM trip_simple WHERE dropoff IS NOT NULL {bbox_filter.format(geom='dropoff')}
        ) t
        WHERE 1=1 {date_filter} {day_filter};
        """
    else:
        geom = mode
        return f"""
        SELECT ST_Y({geom}) AS lat, ST_X({geom}) AS lon
        FROM trip_simple
        WHERE {geom} IS NOT NULL
        {bbox_filter.format(geom=geom)}
        {date_filter} {day_filter};
        """

def build_grid_query(mode, start_date, end_date, h1, h2, day_types, cell_size=0.001):
    """Aggregate trips into a lat/lon grid for faster rendering."""

    date_filter = f"""
        AND time >= '{start_date}'
        AND time <= '{end_date}'
        AND EXTRACT(HOUR FROM time) BETWEEN {h1} AND {h2}
    """

    if "Weekday" in day_types and "Weekend" not in day_types:
        day_filter = "AND is_weekend = FALSE"
    elif "Weekend" in day_types and "Weekday" not in day_types:
        day_filter = "AND is_weekend = TRUE"
    else:
        day_filter = ""

    if mode == "both":
        return f"""
        SELECT lon_snapped AS lon, lat_snapped AS lat, COUNT(*) AS trips
        FROM (
            SELECT (ROUND(ST_X(pickup)/{cell_size})*{cell_size})::double precision AS lon_snapped,
                   (ROUND(ST_Y(pickup)/{cell_size})*{cell_size})::double precision AS lat_snapped
            FROM trip_simple
            WHERE pickup IS NOT NULL
              AND ST_X(pickup) BETWEEN -8.75 AND -8.50
              AND ST_Y(pickup) BETWEEN 41.0 AND 41.3
              {date_filter} {day_filter}
            UNION ALL
            SELECT (ROUND(ST_X(dropoff)/{cell_size})*{cell_size})::double precision AS lon_snapped,
                   (ROUND(ST_Y(dropoff)/{cell_size})*{cell_size})::double precision AS lat_snapped
            FROM trip_simple
            WHERE dropoff IS NOT NULL
              AND ST_X(dropoff) BETWEEN -8.75 AND -8.50
              AND ST_Y(dropoff) BETWEEN 41.0 AND 41.3
              {date_filter} {day_filter}
        ) t
        GROUP BY lon_snapped, lat_snapped
        HAVING COUNT(*) > 1
        ORDER BY trips DESC
        """
    else:
        geom = mode
        return f"""
        SELECT (ROUND(ST_X({geom})/{cell_size})*{cell_size})::double precision AS lon,
               (ROUND(ST_Y({geom})/{cell_size})*{cell_size})::double precision AS lat,
               COUNT(*) AS trips
        FROM trip_simple
        WHERE {geom} IS NOT NULL
          AND ST_X({geom}) BETWEEN -8.75 AND -8.50
          AND ST_Y({geom}) BETWEEN 41.0 AND 41.3
          {date_filter} {day_filter}
        GROUP BY lon, lat
        HAVING COUNT(*) > 1
        ORDER BY trips DESC
        """