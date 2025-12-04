# app.py
"""
--- Porto Taxi Heatmap ---

== ONE-TIME SETUP ==
Ensure 'config.py' has your PostgreSQL credentials.
Run the 'setup.sql' script in pgAdmin or psql to create the 'trip_simple' table

== TO RUN THIS APP ==
Open your terminal in this directory.
Run: panel serve app.py --show --autoreload
"""

import panel as pn
import folium
from folium.plugins import HeatMap

# Local imports from our new files
from widgets import (
    map_style_selector, mode_selector, start_date, end_date,
    hour_selector, day_type_selector, refresh_button,
)
from database import fetch_data, build_query, build_grid_query

# --- APP CONFIG & STYLING ---
with open("styles.css") as f:
    css_content = f.read()

pn.extension(raw_css=[css_content])
pn.config.theme = 'dark'

map_panel = pn.pane.HTML(
    """
    <div style="display: flex; justify-content: center; align-items: center; 
                 height: 100vh; color: white; background-color: #181818;">
        <h3>Processing...</h3>
    </div>
    """,
    sizing_mode="stretch_both",
    height=800
)

# --- MAP UPDATE CALLBACK (The "Controller") ---
def refresh(event=None):
    map_style = map_style_selector.value
    bg_color = "#181818" if map_style == "CartoDB dark_matter" else "#f0f0f0"
    
    # This script correctly sets the background for the 
    # main page (parent) AND the map iframe (document).
    js_script = f"""
    <script>
        try {{
            document.body.style.backgroundColor = '{bg_color}';
            document.documentElement.style.backgroundColor = '{bg_color}';
            parent.document.body.style.backgroundColor = '{bg_color}';
            parent.document.documentElement.style.backgroundColor = '{bg_color}';
        }} catch(e) {{
            console.error('Failed to set parent background:', e);
        }}
    </script>
    """
    
    text_color = "white" if bg_color == "#181818" else "black"
    
    # Show loading
    loading_html = f"""
        {js_script}
        <div style="display: flex; justify-content: center; align-items: center; 
                     height: 100vh; color: {text_color};">
            <h3>Processing...</h3>
        </div>
    """
    map_panel.object = loading_html
    print("Loading message set")

    # --- Get values from widgets ---
    mode = mode_selector.value
    start = start_date.value
    end = end_date.value
    h1, h2 = hour_selector.value
    day_types = day_type_selector.value
    print(f"Mode={mode}, Dates={start} to {end}, Hours={h1}-{h2}, Days={day_types}")

    # --- Fetch Data ---
    query = build_query(mode, start, end, h1, h2, day_types)
    df = fetch_data(query)
    print(f"Got {len(df)} rows")

    if df.empty:
        map_panel.object = f"""
            {js_script}
            <div style="display: flex; justify-content: center; align-items: center; 
                         height: 100vh; color: {text_color};">
                <h3>No data found for this filter.</h3>
            </div>
        """
        return

    # --- Base map ---
    m = folium.Map(
        location=[41.15, -8.6],
        zoom_start=12,
        tiles=map_style,
        zoom_control=False,
    )
    
    # --- Grid layer ---
    grid_query = build_grid_query(mode, start, end, h1, h2, day_types, cell_size=0.003)
    grid_df = fetch_data(grid_query)

    max_trips = 0
    if not grid_df.empty:
        max_trips = int(grid_df["trips"].max())
        features = []
        half = 0.0015
        for _, row in grid_df.iterrows():
            lon, lat, trips = float(row["lon"]), float(row["lat"]), int(row["trips"])
            coords = [
                [lon - half, lat - half], [lon + half, lat - half],
                [lon + half, lat + half], [lon - half, lat + half],
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
                "fillColor": "transparent", "color": "transparent", "weight": 0, "fillOpacity": 0.0,
            },
            highlight_function=lambda x: {
                "fillColor": "#ffff00", "color": "#ffcc00", "weight": 1, "fillOpacity": 0.3,
            },
            tooltip=folium.GeoJsonTooltip(fields=["trips"], aliases=["Trips:"]),
        ).add_to(m)

    # --- Heatmap ---
    heat_data = df[["lat", "lon"]].values.tolist()
    colormap = {0.1: 'pink', 0.3: 'blue', 0.4: 'green', 0.55: 'yellow', 0.75: 'orange', 1.0: 'red'}
    HeatMap(heat_data, radius=20, min_opacity=0.1, max_opacity=0.9, gradient=colormap).add_to(m)
    print("Rendering HTML...")

    # --- Render Map ---
    map_html = m._repr_html_()
    map_with_bg = f"""
    {js_script}
    {map_html}
    """
    map_panel.object = map_with_bg
    print("Map object set!\n")

# --- Bind Callbacks ---
refresh_button.on_click(refresh)
map_style_selector.param.watch(refresh, 'value')
mode_selector.param.watch(refresh, 'value')

# --- UI LAYOUT ---
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

# Load the map when the app first starts
pn.state.onload(refresh) 

# Combine the map and controls into the final UI
ui = pn.Row(map_panel, controls, sizing_mode="stretch_both")
ui.servable()