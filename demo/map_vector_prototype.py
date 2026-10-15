import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, Response, render_template_string
from flask_cors import CORS

# --- 1. Configuration ---

app = Flask(__name__)
CORS(app) # Allow our frontend to talk to this backend

DB_CONFIG = {
    "dbname": "taxis_porto",
    "user": "postgres",
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "host": "127.0.0.1",
    "port": 5433
}

# --- IMPORTANT ---
# We are switching to MapLibre, so no Mapbox token is needed.
# MAPBOX_ACCESS_TOKEN = "PASTE_YOUR_MAPBOX_TOKEN_HERE" # This line is no longer needed


# --- 2. The Vector Tile SQL Query (The "Magic") ---

# This SQL query is executed by PostGIS. It's the heart of the MVT server.
# It filters by date and BBOX, then converts the data to a binary tile.
MVT_SQL_QUERY = """
WITH
    -- 1. Get the BBOX of the requested tile in Web Mercator (3857)
    tile_env AS (
        SELECT ST_TileEnvelope(%s, %s, %s) AS bbox_merc
    ),
    
    -- 2. Select the correct point (start or end)
    trip_points AS (
        SELECT 
            -- This CASE statement dynamically selects the start or end point
            CASE 
                WHEN %s = 'end' THEN ST_EndPoint(t.geom_line)
                ELSE ST_StartPoint(t.geom_line)
            END AS geom_wgs84, -- Geometry in WGS84 (lat/lon)
            t.trip_id,
            t.timestamp
        FROM trip t, tile_env
        WHERE 
            -- 3. Filter by our date/time parameters
            t.timestamp BETWEEN %s AND %s
            
            -- 4. CRITICAL: Filter by the tile's BBOX.
            -- This uses the GIST index. We must transform the tile's Mercator
            -- BBOX back to WGS84 (4326) for the index to work.
            AND t.geom_line && ST_Transform(tile_env.bbox_merc, 4326)
    ),
    
    -- 5. Transform our data to Mercator and clip to the tile boundaries
    mvt_geom AS (
        SELECT
            -- ST_AsMVTGeom clips the geometry to the tile boundary
            -- and converts its coordinates to the MVT's internal 0-4096 grid.
            ST_AsMVTGeom(
                ST_Transform(tp.geom_wgs84, 3857), -- Project to Mercator
                tile_env.bbox_merc,
                4096, -- Tile extent (default)
                256,  -- Buffer to prevent clipping artifacts
                true  -- Clip geometries
            ) AS geom,
            tp.trip_id,
            tp.timestamp
        FROM trip_points tp, tile_env
        -- We do a more precise intersection test here
        WHERE ST_Intersects(ST_Transform(tp.geom_wgs84, 3857), tile_env.bbox_merc)
    )

-- 6. Finally, aggregate all geometries into a single MVT binary
-- 'trips' is the name of the layer inside the tile.
SELECT ST_AsMVT(mvt_geom.*, 'trips') AS mvt
FROM mvt_geom;
"""

# --- 3. The Backend API Endpoints ---

@app.route('/')
def index():
    """Serves the main HTML page."""
    # We no longer need to check for the Mapbox token
    # Renders the HTML file string from disk
    with open('index.html', 'r') as f:
        html_content = f.read()
    # We no longer need to pass the token to the template
    return render_template_string(html_content)


@app.route('/api/tiles/<int:z>/<int:x>/<int:y>')
def get_tile(z, x, y):
    """
    This is the "simulated" tile server endpoint.
    It responds to requests like /api/tiles/12/1020/1530
    """
    
    # Get filters from query parameters
    # Set defaults if they are missing
    start_time = request.args.get('start_time', '1372636800')
    end_time = request.args.get('end_time', '1372723200')
    point_type = request.args.get('type', 'start')

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            # SQL parameters for the query
            params = (z, x, y, point_type, start_time, end_time)
            
            cur.execute(MVT_SQL_QUERY, params)
            
            row = cur.fetchone()
            if row and row[0]:
                mvt_data = row[0] # This is a binary `memoryview`
                
                # Return the binary data with the correct MVT MIME type
                return Response(
                    mvt_data,
                    mimetype='application/vnd.mapbox-vector-tile'
                )
            else:
                # Return an empty tile
                return Response(b'', mimetype='application/vnd.mapbox-vector-tile')

    except Exception as e:
        print(f"Error fetching tile: {e}")
        return Response(f"Error processing tile: {e}", status=500)
    finally:
        if 'conn' in locals() and conn:
            conn.close()


# --- 4. Run the Server ---
if __name__ == '__main__':
    print("MVT Prototype Server running on http://127.0.0.1:5001")
    # print("Make sure you have set your MAPBOX_ACCESS_TOKEN in app.py") # No longer needed
    app.run(port=5001, debug=True)

