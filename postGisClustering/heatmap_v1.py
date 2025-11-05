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
    "password": "postgres",
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

    # --- create folium heatmap ---
    m = folium.Map(location=[41.15, -8.6], zoom_start=12, tiles="CartoDB Positron")
    heat_data = df[["lat", "lon"]].values.tolist()

    HeatMap(
        heat_data,
        radius=10,
        blur=10,
        min_opacity=0.2,
        max_opacity=0.6,
        # gradient={0.0: "blue", 0.4: "cyan", 0.65: "lime", 0.85: "yellow", 1.0: "red"},
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
