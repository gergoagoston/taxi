# widgets.py
"""Defines all Panel widgets and UI components."""

import panel as pn
from datetime import date

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

refresh_button = pn.widgets.Button(name="Recalculate Map", button_type="primary")

map_panel = pn.pane.HTML(
    """
<div style="display: flex; justify-content: center; align-items: center; height: 100vh;">
    <h3>Select parameters to load the heatmap...</h3>
</div>
""",
    sizing_mode="stretch_both",
    css_classes=["fullscreen-map"],
)
