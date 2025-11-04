import psycopg2
from psycopg2.extras import RealDictCursor
import folium
from math import sin

DB_CONFIG = {
    "dbname": "taxis_porto",
    "user": "postgres",
    "password": "postgres",
    "host": "127.0.0.1",
    "port": 5433
}

SQL_DBSCAN = """
WITH pts AS (
    SELECT pickup AS geom
    FROM trip_simple
    WHERE pickup IS NOT NULL
    AND random() < 0.25       -- 25% sampling (gyorsít)
    LIMIT 300000              -- mehetünk 1M-ig is, ha kell
),
clusters AS (
    SELECT
        ST_ClusterDBSCAN(geom, eps := 0.00015, minpoints := 30) OVER () AS cid,
        geom
    FROM pts
),
cluster_polygons AS (
    SELECT
        cid,
        ST_ConcaveHull(ST_Collect(geom), 0.7) AS hull,
        ST_Centroid(ST_Collect(geom)) AS center,
        COUNT(*) AS count_points
    FROM clusters
    WHERE cid IS NOT NULL
    GROUP BY cid
)
SELECT
    cid,
    ST_AsGeoJSON(hull)::json AS hull_geojson,
    ST_AsGeoJSON(center)::json AS center_geojson,
    count_points
FROM cluster_polygons
ORDER BY count_points DESC;
"""


SQL_K_MEANS = """
WITH pickups AS (
    SELECT
        pickup AS geom
    FROM trip_simple
    WHERE pickup IS NOT NULL
    ORDER BY random()
    LIMIT 200000
),
clusters AS (
    SELECT
        ST_ClusterKMeans(geom, 800) OVER () AS cid,
        geom
    FROM pickups
),
cluster_polygons AS (
    SELECT
        cid,
        ST_ConcaveHull(ST_Collect(geom), 0.9) AS hull,
        ST_Centroid(ST_Collect(geom)) AS center,
        COUNT(*) AS count_points
    FROM clusters
    GROUP BY cid
)
SELECT
    cid,
    ST_AsGeoJSON(hull)::json AS hull_geojson,
    ST_AsGeoJSON(center)::json AS center_geojson,
    count_points
FROM cluster_polygons
WHERE count_points > 1
ORDER BY count_points DESC;
"""

def fetch_clusters():
    conn = psycopg2.connect(**DB_CONFIG)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SQL_K_MEANS)
        rows = cur.fetchall()
    conn.close()
    return rows

def make_map(clusters):
    # Black & white basemap
    m = folium.Map(
        location=[41.15, -8.6],
        zoom_start=13,
        tiles="CartoDB Positron"
    )

    counts = [c["count_points"] for c in clusters]
    vmin, vmax = min(counts), max(counts)

    def colorize(v):
    # normalized 0..1
        r = (v - vmin) / (vmax - vmin + 1e-9)

        # Vibrant Viridis style approximation
        R = int(50 + 200 * sin(3.1 * r + 0.5))
        G = int(80 + 180 * sin(3.1 * r + 2.1))
        B = int(120 + 120 * sin(3.1 * r + 4.0))

        return f"#{max(0,min(R,255)):02x}{max(0,min(G,255)):02x}{max(0,min(B,255)):02x}"

    print(f"Adding {len(clusters)} clusters to the map...")

    for c in clusters:
        center = c["center_geojson"]["coordinates"]
        hull = c["hull_geojson"]
        count = c["count_points"]
        color = colorize(count)

        # ---- CIRCLE LABEL (always visible) ----
        # folium.CircleMarker(
        #     location=[center[1], center[0]],
        #     radius=14,
        #     fill=True,
        #     fill_color=color,
        #     color=color,
        #     fill_opacity=0.9,
        #     tooltip=f"{count} trips"
        # ).add_to(m)

        # ---- HULL (visible only on hover) ----
        folium.GeoJson(
            hull,
            style_function=lambda x, col=color: {
                "weight": 1,
                "color": col,
                "fillColor": col,
                # "fillOpacity": 0.0     # invisible by default
            },
            highlight_function=lambda x, col=color: {
                "weight": 2,
                "color": col,
                "fillColor": col,
                # "fillOpacity": 0.35    # show on hover
            },
            tooltip=f"Cluster area — {count} trips"
        ).add_to(m)

    return m

if __name__ == "__main__":
    clusters = fetch_clusters()
    fmap = make_map(clusters)
    fmap.save("hotspot_bubbles.html")
    print("✅ hotspot_bubbles.html elkészült")
