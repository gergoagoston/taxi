import panel as pn
import psycopg2
import pandas as pd
from psycopg2.extras import RealDictCursor
import folium
from folium import features
from branca.colormap import LinearColormap
from folium.plugins import HeatMap

#! run this command: panel serve prototype_v1.py --autoreload --show

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

refresh_button = pn.widgets.Button(name="Recalculate Map", button_type="success")

map_panel = pn.pane.HTML("<h3>Térkép készül...</h3>")

def build_query(mode, year, h1, h2):
    if mode == "both":
        geom = "unnest(ARRAY[pickup, dropoff])"
    else:
        geom = mode

    return f"""
    WITH pts AS (
        SELECT {geom} AS geom
        FROM trip_simple
        WHERE {geom} IS NOT NULL
        AND EXTRACT(YEAR FROM time) = {year}
        AND EXTRACT(HOUR FROM time) BETWEEN {h1} AND {h2}
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
            ST_ConcaveHull(ST_Collect(geom), 0.8) AS hull,
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
    ORDER BY count_points DESC
    -- LIMIT 25;
    """


def refresh(event):
    map_panel.object = "<h3>Processing...</h3>"

    mode = mode_selector.value
    year = year_selector.value
    h1, h2 = time_slider.value

    query = build_query(mode, year, h1, h2)

    conn = psycopg2.connect(**DB_CONFIG)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        clusters = cur.fetchall()
    conn.close()

    counts = [c["count_points"] for c in clusters]
    vmin, vmax = min(counts), max(counts)

    colormap = LinearColormap(
        ["#0051ff", "#33ff00", "#e5ff00", "#ff0000", "#5c0c00"],
        vmin=vmin, vmax=vmax
    )

    m = folium.Map(location=[41.15, -8.6], zoom_start=12, tiles="CartoDB Positron", width="100%", height="900px")

    for c in clusters:
        center = c["center"]["coordinates"]
        hull = c["hull"]
        count = c["count_points"]
        color = colormap(count)
        # folium.CircleMarker(
        #     location=[center[1], center[0]],
        #     radius=12,
        #     fill=True,
        #     fill_color=color,
        #     color=color,
        #     fill_opacity=0.9,
        #     tooltip=f"{count} trips"
        # ).add_to(m)

        folium.GeoJson(
            hull,
            style_function=lambda x, col=color: {"weight": 1, "color": col},
            highlight_function=lambda x, col=color: {"weight": 2, "color": col},
            tooltip=f"Cluster → {count} trips"
        ).add_to(m)

    map_panel.sizing_mode = 'stretch_width'
    map_panel.object = m._repr_html_()

def refresh_heatmap(event):
    map_panel.object = "<h3>Processing...</h3>"

    mode = mode_selector.value
    year = year_selector.value
    h1, h2 = time_slider.value

    geom = "unnest(ARRAY[pickup, dropoff])" if mode == "both" else mode

    query = f"""
        SELECT ST_X({geom}) AS lon, ST_Y({geom}) AS lat
        FROM trip_simple 
        WHERE {geom} IS NOT NULL
        AND EXTRACT(YEAR FROM time) = {year}
        AND EXTRACT(HOUR FROM time) BETWEEN {h1} AND {h2}
    """

    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql(query, conn)
    conn.close()

    m = folium.Map(location=[41.15, -8.6], zoom_start=13, tiles="CartoDB Positron", width="100%")
    HeatMap(
    df[['lat','lon']].values.tolist(),
    radius=18,
    blur=14,
    min_opacity=0.15,   # <-- lower base opacity
    max_opacity=0.65,   # <-- reduce peak brightness
)

    map_panel.sizing_mode = 'stretch_width'
    map_panel.object = m._repr_html_()


refresh_button.on_click(refresh)

ui = pn.Column(
    pn.pane.Markdown("## 🚖 Porto Taxi Hotspot Explorer"),
    pn.Row(mode_selector, year_selector),
    time_slider,
    refresh_button,
    map_panel,
    sizing_mode="stretch_width"
)


ui.servable()
