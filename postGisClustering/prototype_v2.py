import panel as pn
import psycopg2
import pandas as pd
from psycopg2.extras import RealDictCursor
import folium
from branca.colormap import LinearColormap

pn.extension()

DB_CONFIG = {
    "dbname": "taxis_porto",
    "user": "postgres",
    "password": "postgres",
    "host": "127.0.0.1",
    "port": 5433
}

def fetch_years():
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql("SELECT DISTINCT EXTRACT(YEAR FROM time) AS y FROM trip_simple ORDER BY y;", conn)
    conn.close()
    return list(df["y"].astype(int))

years = fetch_years()

mode_selector = pn.widgets.RadioButtonGroup(
    name="Mode",
    options=["pickup", "dropoff", "both"],
    button_type="primary"
)

year_selector = pn.widgets.Select(
    name="Year",
    options=years,
    value=years[0]
)

time_slider = pn.widgets.RangeSlider(
    name="Hour Range",
    start=0,
    end=23,
    value=(7, 11),
    step=1
)

refresh_button = pn.widgets.Button(name="Update Map", button_type="success")

map_panel = pn.pane.HTML("<h3>Choose filters and press Update Map</h3>", height=800, sizing_mode="stretch_width")

def build_query(mode, year, h1, h2):
    geom = {
        "pickup": "pickup",
        "dropoff": "dropoff",
        "both": "unnest(ARRAY[pickup, dropoff])"
    }[mode]

    return f"""
    WITH pts AS (
        SELECT {geom} AS geom
        FROM trip_simple
        WHERE {geom} IS NOT NULL
        AND EXTRACT(YEAR FROM time) = {year}
        AND EXTRACT(HOUR FROM time) BETWEEN {h1} AND {h2}
        ORDER BY random()
        LIMIT 30000
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
            ST_ConcaveHull(ST_Collect(geom), 0.85) AS hull,
            ST_Centroid(ST_Collect(geom)) AS center,
            COUNT(*) AS count_points
        FROM clusters
        GROUP BY cid
    )
    SELECT
        ST_AsGeoJSON(hull)::json AS hull,
        ST_AsGeoJSON(center)::json AS center,
        count_points
    FROM polys
    ORDER BY count_points DESC;
    """

def refresh(event):
    mode = mode_selector.value
    year = year_selector.value
    h1, h2 = time_slider.value

    conn = psycopg2.connect(**DB_CONFIG)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(build_query(mode, year, h1, h2))
        clusters = cur.fetchall()
    conn.close()

    if not clusters:
        map_panel.object = "<h3>No data</h3>"
        return

    counts = [c["count_points"] for c in clusters]
    colormap = LinearColormap(
        colors=["#66c2ff", "#3399ff", "#0077ff", "#ff8800", "#ff5500", "#ff0000"],
        vmin=min(counts), vmax=max(counts)
    )

    m = folium.Map(location=[41.15, -8.6], zoom_start=13, tiles="CartoDB Positron")

    for c in clusters:
        hull = c["hull"]
        count = c["count_points"]
        color = colormap(count)

        folium.GeoJson(
            hull,
            style_function=lambda x, col=color: {
                "weight": 1,
                "color": col,
                "fillColor": col,
                "fillOpacity": 0.20,   # ✅ most átlátszó!
            },
            highlight_function=lambda x, col=color: {
                "weight": 2,
                "color": col,
                "fillColor": col,
                "fillOpacity": 0.50,   # ✅ hoverkor kiemeli
            },
            tooltip=f"🔥 Hotspot — {count} trips"
        ).add_to(m)

    map_panel.object = m._repr_html_()

refresh_button.on_click(refresh)

ui = pn.Column(
    pn.pane.Markdown("## 🚖 Porto Taxi Hotspot Explorer — TRUE Hotspots (No Density Blur)"),
    pn.Row(mode_selector, year_selector),
    time_slider,
    refresh_button,
    map_panel
)

ui.servable()
