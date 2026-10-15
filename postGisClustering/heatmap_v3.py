import os
import panel as pn
import psycopg2
import pandas as pd
from psycopg2.extras import RealDictCursor
import folium
from folium.plugins import HeatMap
from datetime import date

pn.extension()

# --- GLOBAL DB CONFIG ---
DB_CONFIG = {
    "dbname": "taxis_porto",
    "user": "postgres",
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "host": "127.0.0.1",
    "port": 5433,
}

# --- WIDGETS ---
map_style_selector = pn.widgets.RadioButtonGroup(
    name="Map Style",
    options={"Light": "CartoDB Positron", "Dark": "CartoDB dark_matter"},
    value="CartoDB dark_matter",
    button_type="primary",
)

mode_selector = pn.widgets.RadioButtonGroup(
    name="Mode", options=["Pickup", "Dropoff", "Both"], button_type="primary"
)

start_date = pn.widgets.DatePicker(
    name="Start Date", 
    value=date(2013, 11, 1), 
    start=date(2013, 7, 1), 
    end=date(2014, 7, 1),
    stylesheets=["""
        :host {
            --design-background-text-color: white;
            --design-background-color: #2c2c2c;
        }
    """]
)

end_date = pn.widgets.DatePicker(
    name="End Date", 
    value=date(2014, 7, 1), 
    start=date(2013, 7, 1), 
    end=date(2014, 7, 1),
    stylesheets=["""
        :host {
            --design-background-text-color: white;
            --design-background-color: #2c2c2c;
        }
    """]
)


hour_selector = pn.widgets.RangeSlider(
    name="Hour Range", 
    start=0, 
    end=23, 
    value=(7, 11), 
    step=1, 
    styles={"color": "white"},
    stylesheets=["""
        :host .noUi-connect {
            background: gray !important;
        }
    """]
)

# Weekday/Weekend checkboxes
day_type_selector = pn.widgets.CheckBoxGroup(
    name="Day Type", options=["Weekday", "Weekend"], value=["Weekday", "Weekend"], styles={"color": "white"}
)
# Apply dark theme styling to widgets
pn.config.theme = 'dark'
refresh_button = pn.widgets.Button(name="Recalculate Map", button_type="success")

map_panel = pn.pane.HTML(
    """
<div style="display: flex; justify-content: center; align-items: center; height: 100vh;">
    <h3>Select parameters to load the heatmap...</h3>
</div>
""",
    sizing_mode="stretch_both",
    css_classes=["fullscreen-map"],
)


# --- EVENT: Prevent both checkboxes from being deselected ---
def enforce_day_selection(event):
    if not day_type_selector.value:  # if both unchecked
        day_type_selector.value = ["Weekday"]  # recheck at least one


day_type_selector.param.watch(enforce_day_selection, "value")


# --- SQL QUERY BUILDERS ---
def build_query(mode, start_date, end_date, h1, h2, day_types):
    """Fetch raw trip points (lat, lon) between dates at a fixed hour."""

    # Date and time filters
    date_filter = f"""
        AND time >= '{start_date}'
        AND time <= '{end_date}'
        AND EXTRACT(HOUR FROM time) BETWEEN {h1} AND {h2}
    """

    # Day type filter
    if "Weekday" in day_types and "Weekend" not in day_types:
        day_filter = "AND is_weekend = FALSE"
    elif "Weekend" in day_types and "Weekday" not in day_types:
        day_filter = "AND is_weekend = TRUE"
    else:
        day_filter = ""  # both selected → no filter

    bbox_filter = "AND ST_X({geom}) BETWEEN -8.75 AND -8.50 AND ST_Y({geom}) BETWEEN 41.0 AND 41.3"

    if mode == "both":
        return f"""
        SELECT ST_Y(geom) AS lat, ST_X(geom) AS lon
        FROM (
            SELECT pickup AS geom, time, is_weekend FROM trip_simple WHERE pickup IS NOT NULL {bbox_filter.format(geom='pickup')}
            UNION ALL
            SELECT dropoff AS geom, time, is_weekend FROM trip_simple WHERE dropoff IS NOT NULL {bbox_filter.format(geom='dropoff')}
        ) t
        WHERE 1=1 {date_filter} {day_filter};
        """
    else:
        geom = mode
        return f"""
        SELECT ST_Y({geom}) AS lat, ST_X({geom}) AS lon
        FROM trip_simple
        WHERE {geom} IS NOT NULL
        {bbox_filter.format(geom=geom)}
        {date_filter} {day_filter};
        """


def build_grid_query(mode, start_date, end_date, h1, h2, day_types, cell_size=0.001):
    """Aggregate trips into a lat/lon grid for faster rendering."""

    date_filter = f"""
        AND time >= '{start_date}'
        AND time <= '{end_date}'
        AND EXTRACT(HOUR FROM time) BETWEEN {h1} AND {h2}
    """

    if "Weekday" in day_types and "Weekend" not in day_types:
        day_filter = "AND is_weekend = FALSE"
    elif "Weekend" in day_types and "Weekday" not in day_types:
        day_filter = "AND is_weekend = TRUE"
    else:
        day_filter = ""

    if mode == "both":
        return f"""
        SELECT lon_snapped AS lon, lat_snapped AS lat, COUNT(*) AS trips
        FROM (
            SELECT (ROUND(ST_X(pickup)/{cell_size})*{cell_size})::double precision AS lon_snapped,
                   (ROUND(ST_Y(pickup)/{cell_size})*{cell_size})::double precision AS lat_snapped
            FROM trip_simple
            WHERE pickup IS NOT NULL
              AND ST_X(pickup) BETWEEN -8.75 AND -8.50
              AND ST_Y(pickup) BETWEEN 41.0 AND 41.3
              {date_filter} {day_filter}
            UNION ALL
            SELECT (ROUND(ST_X(dropoff)/{cell_size})*{cell_size})::double precision AS lon_snapped,
                   (ROUND(ST_Y(dropoff)/{cell_size})*{cell_size})::double precision AS lat_snapped
            FROM trip_simple
            WHERE dropoff IS NOT NULL
              AND ST_X(dropoff) BETWEEN -8.75 AND -8.50
              AND ST_Y(dropoff) BETWEEN 41.0 AND 41.3
              {date_filter} {day_filter}
        ) t
        GROUP BY lon_snapped, lat_snapped
        HAVING COUNT(*) > 1
        ORDER BY trips DESC
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
          {date_filter} {day_filter}
        GROUP BY lon, lat
        HAVING COUNT(*) > 1
        ORDER BY trips DESC
        """


# --- MAP UPDATE CALLBACK ---
def refresh(event=None):
    map_style = map_style_selector.value
    bg_color = "#181818" if map_style == "CartoDB dark_matter" else "#f0f0f0"
    
    map_panel.object = f"""
        <script>
            document.body.style.backgroundColor = '{bg_color}';
            document.documentElement.style.backgroundColor = '{bg_color}';
        </script>
        <div style="display: flex; justify-content: center; align-items: center; height: 100vh;">
            <h3>Processing...</h3>
        </div>
    """

    mode = mode_selector.value
    start = start_date.value
    end = end_date.value
    h1, h2 = hour_selector.value
    day_types = day_type_selector.value

    query = build_query(mode, start, end, h1, h2, day_types)

    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql(query, conn)
    conn.close()

    if df.empty:
        map_panel.object = "<h3>No data found for this filter.</h3>"
        return

    # --- Base map ---
    m = folium.Map(location=[41.15, -8.6], zoom_start=12, tiles=map_style)
    
    # --- Grid layer ---
    grid_query = build_grid_query(mode, start, end, h1, h2, day_types, cell_size=0.003)
    conn = psycopg2.connect(**DB_CONFIG)
    grid_df = pd.read_sql(grid_query, conn)
    conn.close()

    if not grid_df.empty:
        features = []
        half = 0.0015
        for _, row in grid_df.iterrows():
            lon, lat, trips = float(row["lon"]), float(row["lat"]), int(row["trips"])
            coords = [
                [lon - half, lat - half],
                [lon + half, lat - half],
                [lon + half, lat + half],
                [lon - half, lat + half],
                [lon - half, lat - half],
            ]
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {"trips": trips},
            })

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
            tooltip=folium.GeoJsonTooltip(fields=["trips"], aliases=["Trips:"]),
        ).add_to(m)

    # --- Heatmap ---
    heat_data = df[["lat", "lon"]].values.tolist()
    colormap = {0.0: 'pink', 0.3: 'blue', 0.5: 'green',  0.6: 'yellow', 0.8: 'orange', 1.0: 'red'}
    HeatMap(heat_data, radius=20, min_opacity=0.1, max_opacity=0.9, gradient=colormap).add_to(m)

    bg_color = "#181818" if map_style == "CartoDB dark_matter" else "#f0f0f0"
    map_html = m._repr_html_()
    map_with_bg = f"""
    <script>
        document.body.style.backgroundColor = '{bg_color}';
        document.documentElement.style.backgroundColor = '{bg_color}';
    </script>
    {map_html}
    """
    map_panel.object = map_with_bg


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
    overflow: hidden !important;
}

.fullscreen-map iframe {
    height: 100vh !important;
    width: 100vw !important;
    border: none !important;
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
}

.theme-title {
    color: white !important;
    font-weight: 600;
    margin-top: 8px;
}

"""
    ]
)

# --- UI PANEL ---
controls = pn.Column(
    pn.pane.Markdown("### Theme", css_classes=["theme-title"]),
    map_style_selector,
    pn.pane.Markdown("### Controls", css_classes=["controls-title"]),
    mode_selector,
    start_date,
    end_date,
    hour_selector,
    day_type_selector,
    refresh_button,
    css_classes=["floating-ui"],
)

pn.state.onload(refresh)
ui = pn.Row(map_panel, controls, sizing_mode="stretch_both")
ui.servable()
