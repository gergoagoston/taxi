#!/usr/bin/env python3
"""
Render roads from a PostGIS table into a self-contained Bokeh HTML map (works with Bokeh 3.8).

Requirements:
    geopandas>=0.14
    shapely>=2.0
    pyproj>=3.6
    SQLAlchemy>=2.0
    psycopg2-binary>=2.9
    bokeh>=3.8
    xyzservices>=2024.1.0
"""

import os, argparse, warnings
from pathlib import Path
import geopandas as gpd
from shapely.geometry import LineString, MultiLineString
from sqlalchemy import create_engine, text

from bokeh.io import output_file, save
from bokeh.models import ColumnDataSource, HoverTool
from bokeh.plotting import figure
import xyzservices.providers as xyz


def _explode_lines(geom):
    if geom is None:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    return []


def _geos_to_xsys(geoms):
    xs, ys = [], []
    for ln in geoms:
        x, y = ln.coords.xy
        xs.append(list(x))
        ys.append(list(y))
    return xs, ys


def _class_color(hwy):
    palette = {
        "motorway": "#d73027",
        "trunk": "#fc8d59",
        "primary": "#fee08b",
        "secondary": "#d9ef8b",
        "tertiary": "#91cf60",
        "residential": "#1a9850",
    }
    return palette.get(hwy, "#555555")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", default="public")
    parser.add_argument("--table", default="oporto_roads")
    parser.add_argument("--geom", default="geometry")
    parser.add_argument("--cols", default="name,highway,maxspeed,oneway,lanes,length")
    parser.add_argument("--where", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--simplify", type=float, default=0.0)
    parser.add_argument(
        "--tiles",
        default="CartoDB Positron",
        help="Basemap: 'CartoDB Positron', 'OSM', 'Stamen Terrain', 'None'",
    )
    parser.add_argument("--out", default="roads_bokeh.html")
    args = parser.parse_args()

    db_url = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5433/taxis_porto"
    if not db_url:
        raise SystemExit(
            "Set DATABASE_URL='postgresql+psycopg2://user:pass@host:5432/dbname'"
        )

    engine = create_engine(db_url, pool_pre_ping=True)

    cols = [c.strip() for c in args.cols.split(",") if c.strip()]
    qcols = ", ".join([f'"{c}"' for c in cols])
    fqtn = f'"{args.schema}"."{args.table}"'
    gcol = f'"{args.geom}"'
    sql = f"SELECT {qcols}, {gcol} AS geom FROM {fqtn}"
    if args.where:
        sql += f" WHERE {args.where}"
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"

    # Detect SRID
    with engine.begin() as conn:
        srid = conn.execute(
            text("SELECT Find_SRID(:schema,:table,:geom)"),
            {"schema": args.schema, "table": args.table, "geom": args.geom},
        ).scalar()
        if not srid or int(srid) == 0:
            srid = (
                conn.execute(
                    text(
                        f"SELECT ST_SRID({gcol}) FROM {fqtn} WHERE {gcol} IS NOT NULL LIMIT 1"
                    )
                ).scalar()
                or 4326
            )
    srid = int(srid)

    gdf = gpd.read_postgis(sql, con=engine, geom_col="geom", crs=f"EPSG:{srid}")
    if gdf.empty:
        raise SystemExit("No rows returned; check table/filters.")

    gdf = gdf.to_crs(3857)  # Web Mercator
    if args.simplify > 0:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            gdf["geom"] = gdf.geometry.simplify(args.simplify, preserve_topology=True)

    # Build Bokeh figure
    output_file(args.out, title="Roads (Bokeh 3.8)")
    p = figure(
        title="Road Network",
        x_axis_type="mercator",
        y_axis_type="mercator",
        active_scroll="wheel_zoom",
        sizing_mode="stretch_both",
        width=1000,
        height=700,
        tools="pan,wheel_zoom,box_zoom,reset,save,hover",
    )

    if args.tiles.lower() != "none":
        if "cartodb" in args.tiles.lower():
            p.add_tile(xyz.CartoDB.Positron, retina=True)
        elif "stamen" in args.tiles.lower():
            p.add_tile(xyz.Stamen.Terrain, retina=True)
        else:
            p.add_tile(xyz.OpenStreetMap.Mapnik, retina=True)

    hover = p.select_one(HoverTool)
    hover.tooltips = [(c, f"@{c}") for c in cols if c != "geometry"]

    classes = (
        sorted(gdf["highway"].dropna().astype(str).unique())
        if "highway" in gdf.columns
        else ["other"]
    )

    for hwy in classes:
        sdf = (
            gdf[gdf["highway"].astype(str) == hwy] if "highway" in gdf.columns else gdf
        )
        all_lines = [ln for geom in sdf.geometry for ln in _explode_lines(geom)]
        xs, ys = _geos_to_xsys(all_lines)
        if not xs:
            continue

        rep = {
            c: str(sdf[c].iloc[0]) if c in sdf.columns and len(sdf) else ""
            for c in cols
        }
        data = {"xs": xs, "ys": ys}
        for c in cols:
            data[c] = [rep.get(c, "")] * len(xs)
        src = ColumnDataSource(data)

        p.multi_line(
            xs="xs",
            ys="ys",
            source=src,
            line_color=_class_color(hwy),
            line_width=2,
            line_alpha=0.9,
            legend_label=hwy,
        )

    p.legend.location = "bottom_right"
    p.legend.click_policy = "hide"
    x0, y0, x1, y1 = gdf.total_bounds
    p.x_range.start, p.x_range.end, p.y_range.start, p.y_range.end = x0, x1, y0, y1

    save(p)
    print(f"✅ Saved {args.out}")


if __name__ == "__main__":
    main()
