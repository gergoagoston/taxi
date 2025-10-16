import psycopg2
from psycopg2.extras import RealDictCursor
import folium
from folium.plugins import MarkerCluster

# --------------------------
# Database connection config
# --------------------------
DB_CONFIG = {
    "dbname": "taxis_porto",
    "user": "postgres",
    "password": "postgres",
    "host": "127.0.0.1",
    "port": 5433
}

# --------------------------
# SQL query
# --------------------------
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

# --------------------------
# Fetch data from Postgres
# --------------------------
def fetch_features(conn, limit: int):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SQL, (limit,))
        rows = cur.fetchall()
    features = []
    for r in rows:
        gj = r["geojson"]
        if not gj or gj.get("type") != "LineString":
            continue
        coords = gj.get("coordinates", [])
        if not coords:
            continue
        first_coord = coords[0]  # [lon, lat]
        features.append({
            "type": "Feature",
            "geometry": gj,
            "properties": {
                "trip_id": r["trip_id"],
                "call_type": r["call_type"],
                "day_type": r["day_type"],
                "start_lon": first_coord[0],
                "start_lat": first_coord[1]
            }
        })
    return features

# --------------------------
# Create Folium map
# --------------------------
def create_map(features):
    # Center map roughly around Porto
    fmap = folium.Map(location=[41.15, -8.6], zoom_start=12)
    cluster = MarkerCluster().add_to(fmap)

    for f in features:
        lat = f["properties"]["start_lat"]
        lon = f["properties"]["start_lon"]
        popup_text = (
            f"Trip ID: {f['properties']['trip_id']}<br>"
            f"Call Type: {f['properties']['call_type']}<br>"
            f"Day Type: {f['properties']['day_type']}"
        )
        folium.Marker(
            location=[lat, lon],
            popup=popup_text,
            icon=folium.Icon(color="blue", icon="taxi", prefix="fa")
        ).add_to(cluster)

    return fmap

# --------------------------
# Main
# --------------------------
if __name__ == "__main__":
    conn = psycopg2.connect(**DB_CONFIG)
    features = fetch_features(conn, limit=10000)
    conn.close()

    print(f"Fetched {len(features)} features.")

    fmap = create_map(features)
    fmap.save("trip_starts.html")
    print("Map saved to trip_starts.html")
