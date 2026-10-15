import os
import panel as pn
import psycopg2
import pandas as pd
from psycopg2.extras import RealDictCursor
import folium
from folium.plugins import HeatMap

pn.extension()

# --- GLOBAL DB CONFIG ---
DB_CONFIG = {
    "dbname": "taxis_porto",
    "user": "postgres",
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "host": "127.0.0.1",
    "port": 5433,
}


# --- FETCH AVAILABLE YEARS ---
def fetch_years():
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql(
        "SELECT DISTINCT EXTRACT(YEAR FROM time) AS y FROM trip_simple ORDER BY y;",
        conn,
    )
    conn.close()
    years_list = list(df["y"].astype(int))
    return ["All"] + years_list


years = fetch_years()

# --- WIDGETS ---
mode_selector = pn.widgets.RadioButtonGroup(
    name="Mode", options=["pickup", "dropoff", "both"], button_type="primary"
)

year_selector = pn.widgets.Select(name="Year", options=years, value="All")

time_slider = pn.widgets.RangeSlider(
    name="Hour Range", start=0, end=23, value=(7, 11), step=1
)

refresh_button = pn.widgets.Button(name="Recalculate Map", button_type="success")

map_panel = pn.pane.HTML(
    """
<div style="display: flex; justify-content: center; align-items: center; height: 100vh;">
    <h3>Select the parameters to load the heatmap...</h3>
</div>
""",
    sizing_mode="stretch_both",
    css_classes=["fullscreen-map"],
)


# --- HEATMAP QUERY BUILDER ---
def build_query(mode, year, h1, h2):
    if mode == "both":
        # We first unnest both pickup and dropoff points in a CTE
        geom_cte = """
        WITH pts AS (
            SELECT unnest(ARRAY[pickup, dropoff]) AS geom, time
            FROM trip_simple
        )
        SELECT ST_Y(geom) AS lat, ST_X(geom) AS lon
        FROM pts
        WHERE geom IS NOT NULL
        """
    else:
        # Single geometry field
        geom_cte = f"""
        SELECT ST_Y({mode}) AS lat, ST_X({mode}) AS lon
        FROM trip_simple
        WHERE {mode} IS NOT NULL
        """

    # Add filters
    year_filter = "" if year == "All" else f"AND EXTRACT(YEAR FROM time) = {year}"

    return f"""
        {geom_cte}
        {year_filter}
        AND EXTRACT(HOUR FROM time) BETWEEN {h1} AND {h2};
    """


def build_grid_query(mode, year, h1, h2, cell_size=0.01, max_cells=3000):
    """Return an SQL query that aggregates trips into a regular latitude/longitude
    grid. cell_size is in decimal degrees (approx ~111km per degree latitude).
    Only returns the top max_cells busiest cells for performance.

    PERFORMANCE OPTIMIZATION: Limits results to top N cells and adds spatial bounds.
    """
    # build hour condition (support wrap-around)
    if h1 <= h2:
        hour_cond = f"EXTRACT(HOUR FROM time) BETWEEN {h1} AND {h2}"
    else:
        hour_cond = (
            f"(EXTRACT(HOUR FROM time) >= {h1} OR EXTRACT(HOUR FROM time) <= {h2})"
        )

    year_filter = "" if year == "All" else f"AND EXTRACT(YEAR FROM time) = {year}"

    # Spatial bounding box for Porto area (speeds up queries by filtering early)
    bbox = "AND ST_X({geom}) BETWEEN -8.75 AND -8.50 AND ST_Y({geom}) BETWEEN 41.0 AND 41.3"

    # helper to snap coordinates to a grid cell center using ROUND
    # We compute snapped lon/lat by rounding ST_X/ST_Y divided by cell_size then * cell_size
    if mode == "both":
        return f"""
        SELECT lon_snapped AS lon, lat_snapped AS lat, COUNT(*) AS trips FROM (
            SELECT (ROUND(ST_X(pickup)/{cell_size})*{cell_size})::double precision AS lon_snapped,
                   (ROUND(ST_Y(pickup)/{cell_size})*{cell_size})::double precision AS lat_snapped
            FROM trip_simple
            WHERE pickup IS NOT NULL
              AND ST_X(pickup) BETWEEN -8.75 AND -8.50
              AND ST_Y(pickup) BETWEEN 41.0 AND 41.3
              {year_filter}
              AND {hour_cond}

            UNION ALL

            SELECT (ROUND(ST_X(dropoff)/{cell_size})*{cell_size})::double precision AS lon_snapped,
                   (ROUND(ST_Y(dropoff)/{cell_size})*{cell_size})::double precision AS lat_snapped
            FROM trip_simple
            WHERE dropoff IS NOT NULL
              AND ST_X(dropoff) BETWEEN -8.75 AND -8.50
              AND ST_Y(dropoff) BETWEEN 41.0 AND 41.3
              {year_filter}
              AND {hour_cond}
        ) t
        GROUP BY lon_snapped, lat_snapped
        HAVING COUNT(*) > 1
        ORDER BY trips DESC
        LIMIT {max_cells};
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
          {year_filter}
          AND {hour_cond}
        GROUP BY lon, lat
        HAVING COUNT(*) > 1
        ORDER BY trips DESC
        LIMIT {max_cells};
        """


# --- MAP UPDATE CALLBACK ---
def refresh(event=None):
    map_panel.object = """
    <div style="display: flex; justify-content: center; align-items: center; height: 100vh;">
        <h3>Processing...</h3>
    </div>
    """

    mode = mode_selector.value
    year = year_selector.value
    h1, h2 = time_slider.value

    query = build_query(mode, year, h1, h2)

    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql(query, conn)
    conn.close()

    if df.empty:
        map_panel.object = "<h3>No data found for this filter.</h3>"
        return

    # --- create folium map ---
    m = folium.Map(location=[41.15, -8.6], zoom_start=12, tiles="CartoDB Positron")

    # OPTIMIZATION: Create grid layer using FeatureGroup for batch rendering
    # cell_size=0.003 creates ~330m × 330m cells, limited to top 3000 busiest
    grid_query = build_grid_query(mode, year, h1, h2, cell_size=0.003, max_cells=3000)
    conn = psycopg2.connect(**DB_CONFIG)
    grid_df = pd.read_sql(grid_query, conn)
    conn.close()

    # Use FeatureGroup for much faster rendering than individual GeoJson layers
    grid_layer = folium.FeatureGroup(name="Grid", show=True)

    # Build all features in a GeoJSON FeatureCollection for batch processing
    features = []
    for _, row in grid_df.iterrows():
        lon = float(row["lon"])
        lat = float(row["lat"])
        trips = int(row["trips"])

        # Create a square polygon around the grid cell center
        half = 0.0015  # half of cell_size (0.003/2)
        coords = [
            [lon - half, lat - half],
            [lon + half, lat - half],
            [lon + half, lat + half],
            [lon - half, lat + half],
            [lon - half, lat - half],
        ]

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {"trips": trips},
            }
        )

    # Create a single GeoJson layer from all features (much faster than loop)
    if features:
        geojson_collection = {"type": "FeatureCollection", "features": features}

        folium.GeoJson(
            geojson_collection,
            style_function=lambda x: {
                "fillColor": "#000000",
                "color": "transparent",
                "weight": 0,
                "fillOpacity": 0.0,
            },
            highlight_function=lambda x: {
                "fillColor": "#ffff00",
                "color": "#ffcc00",
                "weight": 1,
                "fillOpacity": 0.3,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["trips"], aliases=["Trips:"], localize=True
            ),
        ).add_to(m)

    # Then overlay the heatmap on top
    heat_data = df[["lat", "lon"]].values.tolist()
    HeatMap(
        heat_data,
        radius=10,
        blur=10,
        min_opacity=0.2,
        max_opacity=0.6,
    ).add_to(m)

    map_panel.object = m._repr_html_()


refresh_button.on_click(refresh)

# --- FLOATING UI CSS ---
pn.extension(
    raw_css=[
        """
html, body, .bk-root {
    margin: 0 !important;
    padding: 0 !important;
    height: 100vh !important;
    width: 100vw !important;
    overflow: hidden !important; /* remove scrollbars */
}

.fullscreen-map {
    height: 100vh !important;
    width: 100vw !important;
    overflow: hidden !important;
}

.fullscreen-map iframe {
    height: 100vh !important;
    width: 100vw !important;
    border: none !important;
    overflow: hidden !important;
}

.floating-ui {
    position: absolute;
    top: 15px;
    left: 15px;
    z-index: 9999;
    background: rgba(20, 20, 20, 0.75);
    padding: 12px 14px;
    border-radius: 10px;
    color: white;
    backdrop-filter: blur(6px);
}

.controls-title {
    color: white !important;
    font-weight: 600;
    margin-bottom: 8px;
}
"""
    ]
)

# --- UI PANEL ---
controls = pn.Column(
    pn.pane.Markdown("### Controls", css_classes=["controls-title"]),
    mode_selector,
    year_selector,
    time_slider,
    refresh_button,
    css_classes=["floating-ui"],
)

ui = pn.Row(map_panel, controls, sizing_mode="stretch_both")
ui.servable()
