from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

TIGER_WILLIAMSON_ROADS_URL = "https://www2.census.gov/geo/tiger/TIGER2024/ROADS/tl_2024_48491_roads.zip"
LIBERTY_HILL_STUDY_POINT = (-97.8797222222, 30.6521666667)
STUDY_RADIUS_MILES = 10.0
METERS_PER_MILE = 1609.344
OUTPUT_GEOJSON = Path("data/processed/liberty_hill_roads.geojson")
OUTPUT_CSV = Path("data/processed/liberty_hill_roads.csv")
SUMMARY_JSON = Path("metadata/road_network_summary.json")

ROAD_CLASS_LABELS = {
    "S1100": "Primary Road",
    "S1200": "Secondary Road",
    "S1400": "Local Neighborhood Road",
    "S1500": "Vehicular Trail",
    "S1630": "Ramp",
    "S1640": "Service Drive",
    "S1710": "Walkway",
    "S1730": "Alley",
    "S1740": "Private Road",
    "S1750": "Internal Through Road",
    "S1780": "Parking Lot Road",
}

MAJOR_ROAD_CODES = {"S1100", "S1200"}
MAJOR_ROUTE_TYPES = {"I", "S", "U"}


def create_study_area() -> gpd.GeoDataFrame:
    point = gpd.GeoDataFrame(
        {"name": ["study_point"]},
        geometry=[Point(LIBERTY_HILL_STUDY_POINT)],
        crs="EPSG:4326",
    )
    projected = point.to_crs("EPSG:5070")
    buffered = projected.buffer(STUDY_RADIUS_MILES * METERS_PER_MILE)
    return gpd.GeoDataFrame({"name": ["study_area"]}, geometry=buffered, crs="EPSG:5070").to_crs("EPSG:4326")


def classify_route_type(value: object) -> str:
    mapping = {
        "I": "Interstate",
        "S": "State Highway",
        "U": "U.S. Highway",
        "C": "County Road",
        "M": "Local or Municipal Road",
        "O": "Other Route",
    }
    if pd.isna(value):
        return "Unspecified"
    return mapping.get(str(value), "Unspecified")


def is_major_corridor(frame: gpd.GeoDataFrame) -> pd.Series:
    route_type = frame["RTTYP"].fillna("").astype(str)
    fullname = frame["FULLNAME"].fillna("").astype(str)
    return frame["MTFCC"].isin(MAJOR_ROAD_CODES) | route_type.isin(MAJOR_ROUTE_TYPES) | fullname.str.contains(r"\b(?:US|SH|FM)\b", regex=True)


def load_and_process_roads() -> gpd.GeoDataFrame:
    roads = gpd.read_file(TIGER_WILLIAMSON_ROADS_URL).to_crs("EPSG:4326")
    study_area = create_study_area()
    retained = roads.loc[roads.geometry.intersects(study_area.iloc[0].geometry)].copy()
    retained["road_name"] = retained["FULLNAME"].fillna("Unnamed road")
    retained["road_class"] = retained["MTFCC"].map(ROAD_CLASS_LABELS).fillna("Other Road")
    retained["route_type"] = retained["RTTYP"].map(classify_route_type)
    retained["is_major_corridor"] = is_major_corridor(retained)
    projected = retained.to_crs("EPSG:5070")
    retained["segment_length_miles"] = projected.geometry.length / METERS_PER_MILE
    retained["study_radius_miles"] = STUDY_RADIUS_MILES
    return retained[[
        "LINEARID",
        "road_name",
        "FULLNAME",
        "MTFCC",
        "road_class",
        "RTTYP",
        "route_type",
        "is_major_corridor",
        "segment_length_miles",
        "study_radius_miles",
        "geometry",
    ]]


def write_outputs(frame: gpd.GeoDataFrame) -> None:
    OUTPUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(OUTPUT_GEOJSON, driver="GeoJSON")
    frame.drop(columns="geometry").to_csv(OUTPUT_CSV, index=False)


def write_summary(frame: gpd.GeoDataFrame) -> None:
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "date_built": date.today().isoformat(),
        "study_radius_miles": STUDY_RADIUS_MILES,
        "total_segments": int(len(frame)),
        "major_corridor_segments": int(frame["is_major_corridor"].sum()),
        "total_centerline_miles": round(float(frame["segment_length_miles"].sum()), 2),
        "major_corridor_miles": round(float(frame.loc[frame["is_major_corridor"], "segment_length_miles"].sum()), 2),
        "counts_by_road_class": {key: int(value) for key, value in frame["road_class"].value_counts().to_dict().items()},
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> None:
    roads = load_and_process_roads()
    write_outputs(roads)
    write_summary(roads)
    print(f"Exported {len(roads)} road segments to {OUTPUT_GEOJSON} and {OUTPUT_CSV}.")
    print(f"Flagged {int(roads['is_major_corridor'].sum())} segments as major transportation corridors.")
    print(f"Wrote road summary to {SUMMARY_JSON}.")


if __name__ == "__main__":
    main()