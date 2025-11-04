import psycopg2
from psycopg2.extras import RealDictCursor
import folium
from folium.features import DivIcon

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
# SQL query (DBSCAN + CONVEX HULL)
# --------------------------
# This query does all the work in PostGIS:
# 1. Filters for a specific day (Jul 1, 2013).
# 2. Runs ST_ClusterDBSCAN to find natural clusters.
# 3. Calculates the shape (ST_ConvexHull) and center (ST_Centroid) of each cluster.
#
# --- You MUST tune these parameters ---
# eps := 0.001: The max distance (in degrees) between points to be in the
#              same cluster. 0.001 is ~111 meters. Try 0.0005 for tighter clusters.
# minpoints := 10: The minimum number of points required to form a cluster.
#
SQL_DBSCAN_POLYGONS = """
WITH
-- 1. Get base points for the target day
filtered_trips AS (
    SELECT geom_line
    FROM trip
    -- WHERE 
        -- Filter for Jul 01 2013 (UTC timestamps)
        -- "timestamp" BETWEEN 1372636800 AND 1372723199
        -- geom_line IS NOT NULL
    LIMIT 50000
),
-- 2. Extract the start points
points AS (
    SELECT ST_StartPoint(geom_line) AS geom
    FROM filtered_trips
    WHERE ST_StartPoint(geom_line) IS NOT NULL
),
-- 3. Run DBSCAN clustering
clusters AS (
    SELECT
        geom,
        ST_ClusterDBSCAN(geom, eps := 0.001, minpoints := 10) OVER() AS cluster_id
    FROM points
)
-- 4. Group by cluster_id and get the shape, center, and count
SELECT
    cluster_id,
    COUNT(*) AS trip_count,
    -- Get the polygon area
    ST_AsGeoJSON(ST_ConvexHull(ST_Collect(geom))) AS area_geojson,
    -- Get the center point
    ST_AsGeoJSON(ST_Centroid(ST_Collect(geom))) AS center_geojson
FROM clusters
WHERE
    cluster_id IS NOT NULL -- Filter out "noise" points
GROUP BY
    cluster_id
HAVING
    -- ST_ConvexHull needs at least 3 points to make a valid polygon
    COUNT(*) > 2;
"""

# --------------------------
# Fetch data from Postgres
# --------------------------
def fetch_clusters(conn):
    """
    Fetches the pre-clustered hotspot polygons and counts from the database.
    """
    clusters = []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SQL_DBSCAN_POLYGONS)
        rows = cur.fetchall()
        
    for r in rows:
        if not r["area_geojson"] or not r["center_geojson"]:
            continue
        
        # GeoJSON is [lon, lat]
        center_coords = r["center_geojson"]["coordinates"]
        
        clusters.append({
            "count": r["trip_count"],
            "area": r["area_geojson"],
            "center": [center_coords[1], center_coords[0]] # Folium wants [lat, lon]
        })
    return clusters

# --------------------------
# Create Folium map
# --------------------------
def create_map(clusters):
    """
    Creates the map and plots the cluster areas and count markers.
    """
    fmap = folium.Map(
        location=[41.15, -8.6], 
        zoom_start=12, 
        tiles="Cartodb Positron",
    )
    
    # --- Add Custom CSS for our circular count markers ---
    css_styles = """
    <style>
    .cluster-count-marker {
        display: flex;
        justify-content: center;
        align-items: center;
        border-radius: 50%;
        color: white;
        font-family: Arial, sans-serif;
        font-weight: bold;
        font-size: 14px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        border: 2px solid rgba(255,255,255,0.5);
        text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
        background-color: rgba(255, 0, 0, 0.7); /* Red */
    }
    </style>
    """
    fmap.get_root().html.add_child(folium.Element(css_styles))

    # --- Add each cluster to the map ---
    for c in clusters:
        count = c['count']
        
        # 1. Add the Cluster Area (Polygon)
        folium.GeoJson(
            c['area'],
            style_function=lambda x: {
                'fillColor': '#ff0000',
                'color': '#ff0000',
                'weight': 2,
                'fillOpacity': 0.1
            },
            tooltip=f"Cluster<br><b>{count}</b> trips"
        ).add_to(fmap)
        
        # 2. Add the Count Marker at the center
        # (Slightly larger marker for bigger clusters)
        radius = 16 + min(count // 100, 14) # Base 16px, grows with count
        
        icon = DivIcon(
            icon_size=(radius*2, radius*2),
            icon_anchor=(radius, radius),
            html=f"""<div class="cluster-count-marker">{count}</div>""",
        )

        folium.Marker(
            location=c['center'],
            icon=icon,
            tooltip=f"Cluster<br><b>{count}</b> trips"
        ).add_to(fmap)

    return fmap

# --------------------------
# Main
# --------------------------
if __name__ == "__main__":
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        
        print("Fetching and clustering data from PostGIS...")
        print("(This may take a moment, ST_ClusterDBSCAN is a heavy query...)")
        
        clusters = fetch_clusters(conn) 
        
        conn.close()

        print(f"Found {len(clusters)} distinct clusters.")

        if len(clusters) == 0:
            print("No clusters found. Try adjusting 'eps' or 'minpoints' in the SQL query.")
            exit()
            
        print("Building map...")
        fmap = create_map(clusters)
        
        output_file = "postgis_cluster_areas.html"
        fmap.save(output_file)
        
        print(f"Map saved to {output_file}")

    except psycopg2.OperationalError as e:
        print("\n--- DATABASE CONNECTION ERROR ---")
        print(f"Could not connect to the database: {e}")
        print("Please ensure the database is running and the DB_CONFIG settings are correct.")
