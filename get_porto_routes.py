#!/usr/bin/env python3
"""
Pull drivable road segments for Porto, Portugal from OpenStreetMap
and load them into a PostGIS table.

Requirements (pip):
    osmnx>=1.9.3
    geopandas>=0.14
    shapely>=2.0
    pyproj>=3.6
    psycopg2-binary>=2.9
    SQLAlchemy>=2.0
    geoalchemy2>=0.14

Environment:
    DATABASE_URL='postgresql+psycopg2://user:password@host:5432/dbname'

Usage:
    python porto_roads_to_postgis.py \
        --table oporto_roads \
        --schema public \
        --replace
"""

import os
import argparse
import osmnx as ox
import geopandas as gpd
from sqlalchemy import create_engine, text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--place",
        default="Porto, Portugal",
        help="Geocoding string for the boundary (default: Porto, Portugal)",
    )
    parser.add_argument(
        "--table", default="oporto_roads", help="Target PostGIS table name"
    )
    parser.add_argument("--schema", default="public", help="Target schema (must exist)")
    parser.add_argument(
        "--srid",
        type=int,
        default=4326,
        help="SRID to store geometry in (default: 4326)",
    )
    parser.add_argument(
        "--network_type",
        default="drive",
        choices=["drive", "drive_service"],
        help="OSMnx network type (default: drive)",
    )
    parser.add_argument(
        "--replace", action="store_true", help="Replace table if it exists"
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append if table exists (mutually exclusive with --replace)",
    )
    args = parser.parse_args()

    db_url = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5433/taxis_porto"
    if not db_url:
        raise SystemExit(
            "Set DATABASE_URL env var: postgresql+psycopg2://user:pass@host:5432/dbname"
        )

    if args.replace and args.append:
        raise SystemExit("Use either --replace or --append, not both.")

    print("1) Geocoding boundary…")
    boundary_gdf = ox.geocode_to_gdf(args.place).to_crs(4326)
    boundary_poly = boundary_gdf.geometry.iloc[0]

    print("2) Downloading OSM drivable network… (this can take a minute)")
    G = ox.graph_from_polygon(
        boundary_poly, network_type=args.network_type, simplify=True
    )

    print("3) Converting to GeoDataFrames…")
    # Edges = road segments; Nodes = intersections
    nodes, edges = ox.graph_to_gdfs(G, nodes=True, edges=True, fill_edge_geometry=True)

    # Keep useful attributes if they exist
    keep_cols = [
        "osmid",
        "name",
        "highway",
        "oneway",
        "maxspeed",
        "lanes",
        "length",
        "access",
        "bridge",
        "tunnel",
        "surface",
    ]
    for c in keep_cols:
        if c not in edges.columns:
            edges[c] = None

    # Normalize data types and explode lists to strings where needed
    def _maybe_str(x):
        if isinstance(x, (list, tuple, set)):
            return ",".join(map(str, x))
        return x

    for c in keep_cols:
        edges[c] = edges[c].map(_maybe_str)

    # Ensure CRS & clip (safety)
    edges = edges.set_crs(4326, allow_override=True)
    edges = gpd.clip(edges, boundary_poly)

    # Rename geometry to the usual name (geopandas already uses 'geometry')
    # and keep only what we need
    edges = edges[keep_cols + ["geometry"]]

    # Optionally reproject (defaults to 4326)
    if args.srid != 4326:
        print(f"Reprojecting to EPSG:{args.srid}…")
        edges = edges.to_crs(epsg=args.srid)

    print(f"4) Connecting to PostGIS at {db_url} …")
    engine = create_engine(db_url, pool_pre_ping=True)

    # Ensure PostGIS extension exists and schema is present
    with engine.begin() as conn:
        print("Ensuring PostGIS extension is enabled…")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        # Schema: we assume it exists; create if you want:
        # conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {args.schema};"))

    # Write to PostGIS
    if_exists = "replace" if args.replace else ("append" if args.append else "fail")
    print(
        f"5) Writing {len(edges):,} road segments to {args.schema}.{args.table} (if_exists='{if_exists}')…"
    )
    edges.to_postgis(
        name=args.table,
        con=engine,
        schema=args.schema,
        if_exists=if_exists,
        index=False,
    )

    # Add spatial index + a few helpful indexes
    geom_col = "geometry"
    fqtn = f"{args.schema}.{args.table}"
    with engine.begin() as conn:
        print("6) Creating indexes…")
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {args.table}_geom_gix ON {fqtn} USING GIST ({geom_col});"
            )
        )
        conn.execute(
            text(f"CREATE INDEX IF NOT EXISTS {args.table}_name_idx ON {fqtn} (name);")
        )
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {args.table}_highway_idx ON {fqtn} (highway);"
            )
        )

    print("Done ✅")
    print(f"Table ready: {fqtn}")


if __name__ == "__main__":
    main()
