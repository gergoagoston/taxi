'''
    An interactive web application for visualizing taxi trip hotspots in Porto using PostGIS KMeans for clustering.
    This script launches a web server using the Panel library to display an interactive map.
    The application connects to a PostgreSQL database (`taxis_porto`) to fetch taxi trip data.
    
    It provides a user interface with controls to filter the data based on:
    - Mode: 'pickup', 'dropoff', or 'both'.
    - Year: A specific year or 'All' years.
    - Time of Day: A range of hours.
    
    Upon clicking the 'Recalculate Map' button, the script executes a SQL query against a PostGIS-enabled database. 
    The query performs K-Means clustering (ST_ClusterKMeans) on the filtered trip points.
    The resulting clusters are visualized as convex hull polygons on a Folium map. 
    The color of each polygon represents the density of trips within that cluster, providing a clear visual indication of hotspots.
    The UI controls are presented in a floating panel overlaying the map for a modern and clean user experience.
    
    Key Libraries:
    - panel: For creating the web application and interactive widgets.
    - psycopg2: For connecting to the PostgreSQL database.
    - pandas: For initial data fetching (e.g., available years).
    - folium: For rendering the interactive map.
    
    To run this application, execute the following command in your terminal:
#$  panel serve cluster_prototype_v2.py --autoreload --show
'''

import os
import panel as pn
import psycopg2
import pandas as pd
from psycopg2.extras import RealDictCursor
import folium
from branca.colormap import LinearColormap

pn.extension()

# --- GLOBAL DB CONFIG ---
DB_CONFIG = {
    "dbname": "taxis_porto",
    "user": "postgres",
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "host": "127.0.0.1",
    "port": 5433
}

# --- FETCH AVAILABLE YEARS ---
def fetch_years():
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql("SELECT DISTINCT EXTRACT(YEAR FROM time) AS y FROM trip_simple ORDER BY y;", conn)
    conn.close()
    years_list = list(df["y"].astype(int))
    return ["All"] + years_list  # prepend "All"

years = fetch_years()


# --- WIDGETS ---
year_selector = pn.widgets.Select(
    name="Year",
    options=years,
    value="All"
)

mode_selector = pn.widgets.RadioButtonGroup(
    name="Mode",
    options=["pickup", "dropoff", "both"],
    button_type="primary"
)

time_slider = pn.widgets.RangeSlider(
    name="Hour Range",
    start=0,
    end=23,
    value=(7, 11),
    step=1
)

refresh_button = pn.widgets.Button(name="Recalculate Map", button_type="success")

map_panel = pn.pane.HTML("""
<div style="display: flex; justify-content: center; align-items: center; height: 100vh;">
    <h3>Select the parameters to load the map...</h3>
</div>
""", sizing_mode="stretch_both", css_classes=["fullscreen-map"])


# --- CLUSTER QUERY BUILDER WITH trip_simple table ---
def build_query(mode, year, h1, h2):
    if mode == "both":
        geom = "unnest(ARRAY[pickup, dropoff])"
    else:
        geom = mode

    year_filter = "" if year == "All" else f"AND EXTRACT(YEAR FROM time) = {year}"

    return f"""
    WITH pts AS (
        SELECT {geom} AS geom
        FROM trip_simple
        WHERE {geom} IS NOT NULL
        {year_filter}
        AND EXTRACT(HOUR FROM time) BETWEEN {h1} AND {h2}
        -- LIMIT 100000 -- limit for performance, REMOVE AFTER TESTING
    ),
    clusters AS (
        SELECT
            ST_ClusterKMeans(geom, 600) OVER () AS cid,
            geom
        FROM pts
    ),
    polys AS (
        SELECT
            cid,
            -- ST_ConcaveHull(ST_Collect(geom), 0.8) AS hull,
            ST_ConvexHull(ST_Collect(geom)) AS hull, -- testing convex hull for performance
            ST_Centroid(ST_Collect(geom)) AS center,
            COUNT(*) AS count_points
        FROM clusters
        GROUP BY cid
        HAVING COUNT(*) > 15
    )
    SELECT
        ST_AsGeoJSON(hull)::json AS hull,
        ST_AsGeoJSON(center)::json AS center,
        count_points
    FROM polys
    ORDER BY count_points DESC;
    """

# --- NEW CLUSTER QUERY BUILDER WITH trip_points table ---
def new_build_query(mode, year, h1, h2):
    if mode == "both":
        mode_filter = "mode IN ('pickup', 'dropoff')"
    else:
        mode_filter = f"mode = '{mode}'"

    year_filter = "" if year == "All" else f"AND year = {int(year)}"

    return f"""
    WITH pts AS (
        SELECT geom
        FROM trip_points
        WHERE {mode_filter}
        {year_filter}
        AND hour BETWEEN {h1} AND {h2}
    ),
    clusters AS (
        SELECT
            ST_ClusterKMeans(geom, 800) OVER () AS cid,
            geom
        FROM pts
    ),
    polys AS (
        SELECT
            cid,
            -- ST_ConcaveHull(ST_Collect(geom), 0.85) AS hull,
            ST_ConvexHull(ST_Collect(geom)) AS hull,
            ST_Centroid(ST_Collect(geom)) AS center,
            COUNT(*) AS count_points
        FROM clusters
        GROUP BY cid
        HAVING COUNT(*) > 20
    )
    SELECT
        ST_AsGeoJSON(hull)::json AS hull,
        ST_AsGeoJSON(center)::json AS center,
        count_points
    FROM polys
    ORDER BY count_points DESC;
    """



# --- MAP UPDATE CALLBACK ---
def refresh(_):
    map_panel.object = """
    <div style="display: flex; justify-content: center; align-items: center; height: 100vh;">
        <h3>Processing...</h3>
    </div>
    """

    mode = mode_selector.value
    year = year_selector.value
    h1, h2 = time_slider.value

    query = new_build_query(mode, year, h1, h2)

    conn = psycopg2.connect(**DB_CONFIG)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        clusters = cur.fetchall()
    conn.close()

    if not clusters:
        map_panel.object = "<h3>No data found for this filter.</h3>"
        return

    counts = [c["count_points"] for c in clusters]
    colormap = LinearColormap(
        ["#0051ff", "#23af00", "#b9ad02", "#ff0000", "#490a00"],
        vmin=min(counts), vmax=max(counts)
    )

    m = folium.Map(location=[41.15, -8.6], zoom_start=12, tiles="CartoDB Positron")

    for c in clusters:
        hull = c["hull"]
        count = c["count_points"]
        color = colormap(count)

        folium.GeoJson(
            hull,
            style_function=lambda _, col=color: {"weight": 1, "color": col, "fillOpacity": 0.25},
            highlight_function=lambda _, col=color: {"weight": 2, "color": col, "fillOpacity": 0.45},
            tooltip=f"Trips: {count}"
        ).add_to(m)

    map_panel.object = m._repr_html_()


refresh_button.on_click(refresh)


# --- FLOATING UI CSS ---
pn.extension(raw_css=["""
body, html, .bk-root { margin: 0 !important; padding: 0 !important; height: 100%; width: 100%; overflow: hidden; }
.fullscreen-map iframe { height: 100% !important; width: 100% !important; }
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
"""])


# --- UI PANEL ---
controls = pn.Column(
    pn.pane.Markdown("### Controls", css_classes=["controls-title"]),
    mode_selector,
    year_selector,
    time_slider,
    refresh_button,
    css_classes=["floating-ui"]
)

ui = pn.Row(map_panel, controls, sizing_mode="stretch_both")
ui.servable()
