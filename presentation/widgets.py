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
    name='Mode',
    options=['Pickup', 'Dropoff', 'Both'],
    value='Pickup',
    button_type='primary'
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

# --- Legend Components ---
# //////////////////////
legend_title = pn.pane.Markdown(
    "### Legend",
    styles={"color": "white"},
    css_classes=["legend-title"]
)

def _default_legend_html():
    return """
    <div style="width: 200px; height: 20px; background: linear-gradient(to right, pink, blue, green, yellow, orange, red); border: 1px solid black;"></div>
    <div style="display: flex; justify-content: space-between;">
        <span>10+</span>
        <span>10,000+</span>
    </div>
    """

legend_content = pn.pane.HTML(
    _default_legend_html(),
    styles={"color": "white"},
    css_classes=["legend-content"],
)

legend = pn.Column(
    legend_title,
    legend_content,
    css_classes=["floating-legend", "floating-legend-dark"],
)

def reset_legend():
    legend_content.object = _default_legend_html()
    # Force a repaint in Panel
    try:
        legend_content.param.trigger('object')
    except Exception:
        pass

def update_legend(max_trips):
    rounded_max = 10
    if max_trips > 0:
        if max_trips >= 1000:
            rounded_max = (max_trips // 1000) * 1000
        elif max_trips >= 100:
            rounded_max = (max_trips // 100) * 100
        else:
            rounded_max = (max_trips // 10) * 10

    legend_content.object = f"""
    <div style="width: 200px; height: 20px; background: linear-gradient(to right, pink, blue, green, yellow, orange, red); border: 1px solid black;"></div>
    <div style="display: flex; justify-content: space-between;">
        <span>10+</span>
        <span>{rounded_max:,}+</span>
    </div>
    """
    # Force a repaint in Panel
    try:
        legend_content.param.trigger('object')
    except Exception:
        pass