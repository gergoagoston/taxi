#!/usr/bin/env python
"""
Plot 1000 taxi trajectories from PostGIS onto an interactive map (Folium/Leaflet).

Usage (from Windows PowerShell):
  python plot_trips.py --host localhost --port 5432 --db taxi --user postgres --password YOUR_PASSWORD --limit 1000 --out trips_map.html

If you are running this inside another Docker container on the same compose network, use --host db instead of localhost.
"""

import argparse
import json
import os
import sys
from typing import List, Tuple

import folium
import psycopg2
from psycopg2.extras import RealDictCursor

DEFAULT_CENTER = (41.1496, -8.6109)  # Porto city center (lat, lon)

SQL = """
SELECT
  trip_id,
  call_type,
  day_type,
  ST_AsGeoJSON(geom_line)::json AS geojson
FROM trip
WHERE geom_line IS NOT NULL
ORDER BY random()
LIMIT %s;
"""

def fetch_features(conn, limit: int):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SQL, (limit,))
        rows = cur.fetchall()
    features = []
    for r in rows:
        gj = r["geojson"]
        if not gj or gj.get("type") != "LineString":
            continue
        features.append({
            "type": "Feature",
            "geometry": gj,
            "properties": {
                "trip_id": r["trip_id"],
                "call_type": r["call_type"],
                "day_type": r["day_type"],
            },
        })
    return features

def compute_center_from_lines(features) -> Tuple[float, float]:
    """Rough center as the average of all coordinates’ first and last points."""
    lat_sum = 0.0
    lon_sum = 0.0
    n = 0
    for f in features:
        coords = f["geometry"]["coordinates"]
        if not coords:
            continue
        # coords are [lon, lat]
        for idx in (0, -1):
            try:
                lon, lat = coords[idx]
                lat_sum += float(lat)
                lon_sum += float(lon)
                n += 1
            except Exception:
                pass
    if n == 0:
        return DEFAULT_CENTER
    return (lat_sum / n, lon_sum / n)

def call_type_color(ct: str) -> str:
    """
    Simple color coding:
      A (dispatch) -> blue
      B (stand)    -> green
      C (street)   -> red
    """
    return {"A": "blue", "B": "green", "C": "red"}.get(ct or "", "gray")

def main():
    ap = argparse.ArgumentParser(description="Draw taxi trajectories from PostGIS onto a map.")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=5432)
    ap.add_argument("--db", "--dbname", dest="dbname", default="taxi")
    ap.add_argument("--user", default="postgres")
    ap.add_argument("--password", default=os.getenv("POSTGRES_PASSWORD", ""))
    ap.add_argument("--limit", type=int, default=1000, help="Number of trips to plot")
    ap.add_argument("--out", default="trips_map.html", help="Output HTML map filename")
    args = ap.parse_args()

    # Connect
    try:
        conn = psycopg2.connect(
            host=args.host,
            port=args.port,
            dbname=args.dbname,
            user=args.user,
            password=args.password,
        )
    except Exception as e:
        print(f"❌ Failed to connect to Postgres: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        features = fetch_features(conn, args.limit)
    finally:
        conn.close()

    if not features:
        print("⚠️ No features returned. Make sure table 'trip' exists and 'geom_line' is populated.", file=sys.stderr)
        sys.exit(2)

    # Center the map around the dataset
    center_lat, center_lon = compute_center_from_lines(features)
    m = folium.Map(location=(center_lat, center_lon), zoom_start=12, tiles="cartodbpositron")

    # Group by call_type for easy toggling
    groups = {}
    for f in features:
        ct = (f["properties"].get("call_type") or "").upper()
        groups.setdefault(ct, folium.FeatureGroup(name=f"CALL_TYPE {ct or '?'}")).add_to(m)

    # Add trajectories
    for f in features:
        gj = f["geometry"]
        props = f["properties"]
        ct = (props.get("call_type") or "").upper()
        color = call_type_color(ct)

        # Popup with basics
        popup_html = f"""
        <b>TRIP_ID:</b> {props.get('trip_id')}<br/>
        <b>CALL_TYPE:</b> {ct}<br/>
        <b>DAY_TYPE:</b> {props.get('day_type')}
        """
        folium.GeoJson(
            data=f,
            name=f"trip_{props.get('trip_id')}",
            style_function=lambda _feat, color=color: {"color": color, "weight": 2, "opacity": 0.7},
            tooltip=f"Trip {props.get('trip_id')} (call {ct})",
            popup=folium.Popup(popup_html, max_width=300),
        ).add_to(groups.get(ct) or m)

    folium.LayerControl(collapsed=False).add_to(m)
    m.save(args.out)
    print(f"✅ Map written to {args.out}. Open it in your browser.")

if __name__ == "__main__":
    main()
