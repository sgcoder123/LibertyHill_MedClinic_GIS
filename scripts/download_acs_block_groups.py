from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point

ACS_BASE_URL = "https://api.census.gov/data/2024/acs/acs5"
VARIABLES_URL = f"{ACS_BASE_URL}/variables.json"
TEXAS_BLOCK_GROUPS_URL = "https://www2.census.gov/geo/tiger/TIGER2024/BG/tl_2024_48_bg.zip"
TEXAS_PLACES_URL = "https://www2.census.gov/geo/tiger/TIGER2024/PLACE/tl_2024_48_place.zip"
STATE_FIPS = "48"
COUNTY_FIPS = "491"
LIBERTY_HILL_STUDY_POINT = (-97.8797222222, 30.6521666667)
STUDY_RADIUS_MILES = 10.0
METERS_PER_MILE = 1609.344
OUTPUT_GEOJSON = Path("data/processed/liberty_hill_acs_block_groups.geojson")
OUTPUT_CSV = Path("data/processed/liberty_hill_acs_block_groups.csv")
CITY_BOUNDARY_GEOJSON = Path("data/processed/liberty_hill_city_boundary.geojson")
METADATA_CSV = Path("metadata/acs_block_group_metadata.csv")
HTTP_TIMEOUT = 60

SUPPRESSED_VALUES = {
    "",
    "null",
    "None",
    "-666666666",
    "-333333333",
    "-222222222",
    "-999999999",
}


@dataclass(frozen=True)
class VariableSpec:
    table: str
    variable: str
    description: str


DIRECT_VARIABLES = [
    VariableSpec("B01003", "B01003_001", "Total population"),
    VariableSpec("B27010", "B27010_001", "Civilian noninstitutionalized population for health insurance calculation"),
    VariableSpec("C18108", "C18108_001", "Civilian noninstitutionalized population for disability calculation"),
    VariableSpec("C17002", "C17002_001", "Population for whom poverty status is determined"),
    VariableSpec("B19013", "B19013_001", "Median household income in the past 12 months"),
    VariableSpec("B19301", "B19301_001", "Per capita income in the past 12 months"),
    VariableSpec("B08201", "B08201_001", "Total households"),
    VariableSpec("B08201", "B08201_002", "Households with no vehicle available"),
]

AGE_COMPONENTS = {
    "under5": ["B01001_003", "B01001_027"],
    "under18": ["B01001_003", "B01001_004", "B01001_005", "B01001_006", "B01001_027", "B01001_028", "B01001_029", "B01001_030"],
    "age18_64": [
        "B01001_007", "B01001_008", "B01001_009", "B01001_010", "B01001_011", "B01001_012", "B01001_013", "B01001_014",
        "B01001_015", "B01001_016", "B01001_017", "B01001_018", "B01001_019", "B01001_031", "B01001_032", "B01001_033",
        "B01001_034", "B01001_035", "B01001_036", "B01001_037", "B01001_038", "B01001_039", "B01001_040", "B01001_041",
        "B01001_042", "B01001_043",
    ],
    "age65plus": ["B01001_020", "B01001_021", "B01001_022", "B01001_023", "B01001_024", "B01001_025", "B01001_044", "B01001_045", "B01001_046", "B01001_047", "B01001_048", "B01001_049"],
}

UNINSURED_COMPONENTS = ["B27010_017", "B27010_033", "B27010_050", "B27010_066"]
DISABILITY_COMPONENTS = ["C18108_003", "C18108_004", "C18108_007", "C18108_008", "C18108_011", "C18108_012"]
POVERTY_COMPONENTS = ["C17002_002", "C17002_003"]

USED_VARIABLES = (
    DIRECT_VARIABLES
    + [VariableSpec("B01001", code, f"Age component for {alias}") for alias, codes in AGE_COMPONENTS.items() for code in codes]
    + [VariableSpec("B27010", code, "Uninsured population component") for code in UNINSURED_COMPONENTS]
    + [VariableSpec("C18108", code, "Population with disability component") for code in DISABILITY_COMPONENTS]
    + [VariableSpec("C17002", code, "Population below poverty component") for code in POVERTY_COMPONENTS]
)


def require_api_key() -> str:
    api_key = os.environ.get("CENSUS_API_KEY")
    if not api_key:
        raise SystemExit("CENSUS_API_KEY is not set. Export the Census API key before running this script.")
    return api_key


def fetch_census_group(session: requests.Session, api_key: str, group_name: str) -> pd.DataFrame:
    params = {
        "get": f"NAME,group({group_name})",
        "for": "block group:*",
        "in": f"state:{STATE_FIPS} county:{COUNTY_FIPS}",
        "key": api_key,
    }
    response = session.get(ACS_BASE_URL, params=params, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    try:
        payload = response.json()
    except json.JSONDecodeError as error:
        snippet = response.text[:400].strip().replace("\n", " ")
        raise RuntimeError(
            f"Census API returned a non-JSON response for group {group_name}. "
            f"Check that CENSUS_API_KEY is valid. Response snippet: {snippet}"
        ) from error
    frame = pd.DataFrame(payload[1:], columns=payload[0])

    columns_to_drop = [column for column in frame.columns if column.endswith(("EA", "MA", "M", "E")) and column.startswith("GEO")]
    if columns_to_drop:
        frame = frame.drop(columns=columns_to_drop)

    duplicate_name_columns = [column for column in frame.columns if column == "NAME"]
    if len(duplicate_name_columns) > 1:
        frame = frame.loc[:, ~frame.columns.duplicated()]

    return frame


def load_variable_catalog(session: requests.Session) -> dict[str, dict[str, str]]:
    response = session.get(VARIABLES_URL, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    try:
        return response.json()["variables"]
    except json.JSONDecodeError as error:
        snippet = response.text[:400].strip().replace("\n", " ")
        raise RuntimeError(
            "Census variables endpoint returned a non-JSON response. "
            f"Response snippet: {snippet}"
        ) from error


def normalize_suppressed(value: object) -> object:
    if value is None:
        return pd.NA
    if isinstance(value, str) and value in SUPPRESSED_VALUES:
        return pd.NA
    try:
        return float(value)
    except (TypeError, ValueError):
        return pd.NA


def convert_numeric_columns(frame: pd.DataFrame) -> pd.DataFrame:
    for column in frame.columns:
        if column in {"NAME", "state", "county", "tract", "block group"}:
            continue
        frame[column] = frame[column].map(normalize_suppressed)
    return frame


def rss_moe(values: Iterable[object]) -> object:
    cleaned = [float(value) for value in values if pd.notna(value)]
    if not cleaned:
        return pd.NA
    return math.sqrt(sum(value * value for value in cleaned))


def sum_columns(frame: pd.DataFrame, variables: list[str], alias: str) -> None:
    estimate_columns = [f"{variable}E" for variable in variables]
    moe_columns = [f"{variable}M" for variable in variables]
    frame[alias] = frame[estimate_columns].sum(axis=1, min_count=1)
    frame[f"{alias}_moe"] = frame[moe_columns].apply(rss_moe, axis=1)


def calculate_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    numerator_values = pd.to_numeric(numerator, errors="coerce")
    denominator_values = pd.to_numeric(denominator, errors="coerce")
    valid = denominator_values.notna() & denominator_values.ne(0) & numerator_values.notna()
    ratios = numerator_values.divide(denominator_values).mul(100.0)
    return ratios.where(valid, np.nan).astype("float64")


def min_max_normalize(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
      return pd.Series(np.nan, index=series.index, dtype="float64")
    minimum = valid.min()
    maximum = valid.max()
    if minimum == maximum:
      return pd.Series(50.0, index=series.index, dtype="float64")
    return ((series - minimum) / (maximum - minimum)) * 100.0


def build_geoid(frame: pd.DataFrame) -> pd.DataFrame:
    frame["GEOID"] = frame["state"] + frame["county"] + frame["tract"] + frame["block group"]
    return frame


def fetch_acs_data(session: requests.Session, api_key: str) -> pd.DataFrame:
    group_names = ["B01001", "B01003", "B27010", "C18108", "C17002", "B19013", "B19301", "B08201"]
    merged: pd.DataFrame | None = None
    join_columns = ["state", "county", "tract", "block group", "NAME"]

    for group_name in group_names:
        group_frame = fetch_census_group(session, api_key, group_name)
        group_frame = convert_numeric_columns(group_frame)
        extra_identifier_columns = [column for column in ["GEO_ID"] if column in group_frame.columns and column not in join_columns]
        if extra_identifier_columns:
            group_frame = group_frame.drop(columns=extra_identifier_columns)
        merged = group_frame if merged is None else merged.merge(group_frame, on=join_columns, how="inner")

    if merged is None:
        raise RuntimeError("No ACS data could be retrieved from the Census API.")

    return build_geoid(merged)


def download_tiger_block_groups() -> gpd.GeoDataFrame:
    tiger_frame = gpd.read_file(TEXAS_BLOCK_GROUPS_URL)
    tiger_frame = tiger_frame.loc[tiger_frame["COUNTYFP"] == COUNTY_FIPS].copy()
    return tiger_frame[["GEOID", "geometry"]]


def download_liberty_hill_place() -> gpd.GeoDataFrame:
    places = gpd.read_file(TEXAS_PLACES_URL)
    matches = places.loc[places["NAME"].str.casefold() == "liberty hill"].copy()
    if matches.empty:
        raise RuntimeError("Liberty Hill place boundary was not found in the 2024 TIGER/Line place file.")
    return matches[["GEOID", "NAME", "NAMELSAD", "geometry"]]


def create_study_area() -> gpd.GeoDataFrame:
    point = gpd.GeoDataFrame(
        {"name": ["study_point"]},
        geometry=[Point(LIBERTY_HILL_STUDY_POINT)],
        crs="EPSG:4326",
    )
    projected = point.to_crs("EPSG:5070")
    buffered = projected.buffer(STUDY_RADIUS_MILES * METERS_PER_MILE)
    return gpd.GeoDataFrame({"name": ["study_area"]}, geometry=buffered, crs="EPSG:5070").to_crs("EPSG:4326")


def process_acs_data(acs_frame: pd.DataFrame, block_groups: gpd.GeoDataFrame, liberty_hill_place: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    merged = block_groups.merge(acs_frame, on="GEOID", how="inner")
    geodata = gpd.GeoDataFrame(merged, geometry="geometry", crs="EPSG:4269").to_crs("EPSG:4326")

    study_area = create_study_area()
    liberty_hill_place = liberty_hill_place.to_crs("EPSG:4326")
    retained = geodata.loc[geodata.geometry.intersects(study_area.iloc[0].geometry)].copy()
    retained["intersects_liberty_hill_city"] = retained.geometry.intersects(liberty_hill_place.unary_union)

    projected = retained.to_crs("EPSG:5070")
    retained["area_sq_miles"] = projected.geometry.area / (METERS_PER_MILE ** 2)

    retained["population"] = retained["B01003_001E"]
    retained["population_moe"] = retained["B01003_001M"]
    sum_columns(retained, AGE_COMPONENTS["under5"], "under5")
    sum_columns(retained, AGE_COMPONENTS["under18"], "under18")
    sum_columns(retained, AGE_COMPONENTS["age18_64"], "age18_64")
    sum_columns(retained, AGE_COMPONENTS["age65plus"], "age65plus")
    sum_columns(retained, UNINSURED_COMPONENTS, "uninsured")
    sum_columns(retained, DISABILITY_COMPONENTS, "disability")
    sum_columns(retained, POVERTY_COMPONENTS, "poverty")

    retained["civilian_noninstitutionalized_population"] = retained["B27010_001E"]
    retained["civilian_noninstitutionalized_population_moe"] = retained["B27010_001M"]
    retained["disability_population_base"] = retained["C18108_001E"]
    retained["disability_population_base_moe"] = retained["C18108_001M"]
    retained["poverty_population_base"] = retained["C17002_001E"]
    retained["poverty_population_base_moe"] = retained["C17002_001M"]
    retained["households"] = retained["B08201_001E"]
    retained["households_moe"] = retained["B08201_001M"]
    retained["no_vehicle_households"] = retained["B08201_002E"]
    retained["no_vehicle_households_moe"] = retained["B08201_002M"]
    retained["median_household_income"] = retained["B19013_001E"]
    retained["median_household_income_moe"] = retained["B19013_001M"]
    retained["per_capita_income"] = retained["B19301_001E"]
    retained["per_capita_income_moe"] = retained["B19301_001M"]

    retained["population_density"] = retained["population"] / retained["area_sq_miles"]
    retained["youth_population_pct"] = calculate_ratio(retained["under18"], retained["population"])
    retained["senior_population_pct"] = calculate_ratio(retained["age65plus"], retained["population"])
    retained["uninsured_pct"] = calculate_ratio(retained["uninsured"], retained["civilian_noninstitutionalized_population"])
    retained["disability_pct"] = calculate_ratio(retained["disability"], retained["disability_population_base"])
    retained["poverty_pct"] = calculate_ratio(retained["poverty"], retained["poverty_population_base"])
    retained["no_vehicle_pct"] = calculate_ratio(retained["no_vehicle_households"], retained["households"])

    retained["uninsured_pct_numerator"] = "uninsured"
    retained["uninsured_pct_denominator"] = "civilian_noninstitutionalized_population"
    retained["disability_pct_numerator"] = "disability"
    retained["disability_pct_denominator"] = "disability_population_base"
    retained["poverty_pct_numerator"] = "poverty"
    retained["poverty_pct_denominator"] = "poverty_population_base"
    retained["no_vehicle_pct_numerator"] = "no_vehicle_households"
    retained["no_vehicle_pct_denominator"] = "households"
    retained["youth_population_pct_numerator"] = "under18"
    retained["youth_population_pct_denominator"] = "population"
    retained["senior_population_pct_numerator"] = "age65plus"
    retained["senior_population_pct_denominator"] = "population"

    normalized_components = pd.concat(
        [
            min_max_normalize(retained["uninsured_pct"]).rename("uninsured_component"),
            min_max_normalize(retained["disability_pct"]).rename("disability_component"),
            min_max_normalize(retained["poverty_pct"]).rename("poverty_component"),
            min_max_normalize(retained["no_vehicle_pct"]).rename("no_vehicle_component"),
            min_max_normalize(retained["youth_population_pct"]).rename("youth_component"),
            min_max_normalize(retained["senior_population_pct"]).rename("senior_component"),
        ],
        axis=1,
    )
    retained = retained.join(normalized_components)
    retained["healthcare_need_score"] = normalized_components.mean(axis=1, skipna=True)
    retained["healthcare_need_notes"] = (
        "Relative index averaging min-max normalized uninsured_pct, disability_pct, poverty_pct, no_vehicle_pct, "
        "youth_population_pct, and senior_population_pct within the retained Liberty Hill study-area block groups."
    )

    final_columns = [
        "GEOID",
        "NAME",
        "state",
        "county",
        "tract",
        "block group",
        "population",
        "population_moe",
        "area_sq_miles",
        "population_density",
        "under5",
        "under5_moe",
        "under18",
        "under18_moe",
        "age18_64",
        "age18_64_moe",
        "age65plus",
        "age65plus_moe",
        "civilian_noninstitutionalized_population",
        "civilian_noninstitutionalized_population_moe",
        "uninsured",
        "uninsured_moe",
        "uninsured_pct",
        "disability_population_base",
        "disability_population_base_moe",
        "disability",
        "disability_moe",
        "disability_pct",
        "poverty_population_base",
        "poverty_population_base_moe",
        "poverty",
        "poverty_moe",
        "poverty_pct",
        "median_household_income",
        "median_household_income_moe",
        "per_capita_income",
        "per_capita_income_moe",
        "households",
        "households_moe",
        "no_vehicle_households",
        "no_vehicle_households_moe",
        "no_vehicle_pct",
        "youth_population_pct",
        "senior_population_pct",
        "healthcare_need_score",
        "healthcare_need_notes",
        "uninsured_pct_numerator",
        "uninsured_pct_denominator",
        "disability_pct_numerator",
        "disability_pct_denominator",
        "poverty_pct_numerator",
        "poverty_pct_denominator",
        "no_vehicle_pct_numerator",
        "no_vehicle_pct_denominator",
        "youth_population_pct_numerator",
        "youth_population_pct_denominator",
        "senior_population_pct_numerator",
        "senior_population_pct_denominator",
        "intersects_liberty_hill_city",
        "geometry",
    ]
    return retained[final_columns]


def write_outputs(frame: gpd.GeoDataFrame) -> None:
    OUTPUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(OUTPUT_GEOJSON, driver="GeoJSON")
    csv_frame = frame.drop(columns="geometry").copy()
    csv_frame.to_csv(OUTPUT_CSV, index=False)


def write_city_boundary(place_frame: gpd.GeoDataFrame) -> None:
    CITY_BOUNDARY_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    boundary = place_frame.to_crs("EPSG:4326").copy()
    boundary["boundary_name"] = boundary["NAMELSAD"].fillna(boundary["NAME"])
    boundary["source"] = "TIGER/Line 2024 Texas places"
    boundary[["GEOID", "NAME", "NAMELSAD", "boundary_name", "source", "geometry"]].to_file(
        CITY_BOUNDARY_GEOJSON,
        driver="GeoJSON",
    )


def write_metadata(variable_catalog: dict[str, dict[str, str]]) -> None:
    METADATA_CSV.parent.mkdir(parents=True, exist_ok=True)
    with METADATA_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "Dataset",
            "Year",
            "Source",
            "API endpoint",
            "Geography",
            "Variable",
            "Variable description",
            "Estimate/MOE",
            "Date downloaded",
            "Notes/limitations",
        ])
        for spec in USED_VARIABLES:
            estimate_meta = variable_catalog.get(f"{spec.variable}E", {})
            moe_meta = variable_catalog.get(f"{spec.variable}M", {})
            writer.writerow([
                "ACS 5-Year Estimates",
                "2024",
                "U.S. Census Bureau",
                ACS_BASE_URL,
                "Williamson County, Texas block groups filtered to the Liberty Hill study area",
                f"{spec.variable}E",
                estimate_meta.get("label", spec.description),
                "Estimate",
                date.today().isoformat(),
                spec.description,
            ])
            if moe_meta:
                writer.writerow([
                    "ACS 5-Year Estimates",
                    "2024",
                    "U.S. Census Bureau",
                    ACS_BASE_URL,
                    "Williamson County, Texas block groups filtered to the Liberty Hill study area",
                    f"{spec.variable}M",
                    moe_meta.get("label", f"Margin of error for {spec.variable}"),
                    "MOE",
                    date.today().isoformat(),
                    "Margin of error accompanies the paired estimate and should be considered in small-area interpretation.",
                ])


def main() -> None:
    api_key = require_api_key()
    session = requests.Session()
    session.headers.update({"User-Agent": "LibertyHillMedicalClinicGIS/1.0"})

    variable_catalog = load_variable_catalog(session)
    acs_frame = fetch_acs_data(session, api_key)
    block_groups = download_tiger_block_groups()
    liberty_hill_place = download_liberty_hill_place()
    processed = process_acs_data(acs_frame, block_groups, liberty_hill_place)

    write_outputs(processed)
    write_city_boundary(liberty_hill_place)
    write_metadata(variable_catalog)

    total_downloaded = len(acs_frame)
    retained = len(processed)
    city_intersections = int(processed["intersects_liberty_hill_city"].sum()) if not processed.empty else 0
    print(f"Downloaded {total_downloaded} Williamson County block groups from the 2024 ACS 5-Year API.")
    print(f"Retained {retained} block groups intersecting the Liberty Hill 10-mile study area.")
    print(f"{city_intersections} retained block groups intersect the Liberty Hill city boundary.")
    print(f"Wrote {OUTPUT_GEOJSON} and {OUTPUT_CSV}.")
    print(f"Wrote city boundary layer to {CITY_BOUNDARY_GEOJSON}.")
    print(f"Wrote metadata catalog to {METADATA_CSV}.")


if __name__ == "__main__":
    main()