from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point

PROPOSED_SITE_LATITUDE = 30.6521666667
PROPOSED_SITE_LONGITUDE = -97.8797222222
METERS_PER_MILE = 1609.344
HTTP_TIMEOUT = 30
RAW_INPUT_PATH = Path("data/raw/verified_utility_providers.csv")
OUTPUT_GEOJSON = Path("data/processed/liberty_hill_utilities.geojson")
OUTPUT_CSV = Path("data/processed/liberty_hill_utilities.csv")
SUMMARY_PATH = Path("metadata/utility_provider_summary.json")
SOURCE_METADATA_PATH = Path("metadata/utility_provider_sources.csv")

UTILITY_TYPE_LABELS = {
    "water": "Water",
    "wastewater": "Wastewater",
    "water_wastewater": "Water and Wastewater",
    "electricity": "Electricity",
    "natural_gas": "Natural Gas",
}

REQUIRED_COLUMNS = [
    "utility_id",
    "provider_name",
    "utility_type",
    "services",
    "study_area_context",
    "address",
    "city",
    "state",
    "zip_code",
    "phone",
    "email",
    "website",
    "source_url",
    "source_organization",
    "verification_date",
    "verification_notes",
    "latitude",
    "longitude",
]


def coerce_string(value: object) -> str | pd.NA:
    if value is None or pd.isna(value):
        return pd.NA
    text = str(value).strip()
    return text if text else pd.NA


def coerce_float(value: object) -> float | pd.NA:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return pd.NA
    try:
        return float(value)
    except (TypeError, ValueError):
        return pd.NA


def format_address(row: pd.Series) -> str:
    parts = [row.get("address"), row.get("city"), row.get("state"), row.get("zip_code")]
    return ", ".join([str(part).strip() for part in parts if pd.notna(part) and str(part).strip()])


def geocode_address(session: requests.Session, row: pd.Series) -> tuple[float | pd.NA, float | pd.NA, str | None]:
    address = format_address(row)
    if not address:
        return pd.NA, pd.NA, "Address missing; geocoder not attempted."

    response = session.get(
        "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
        params={
            "address": address,
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "format": "json",
        },
        timeout=HTTP_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    matches = payload.get("result", {}).get("addressMatches", [])
    if matches:
        coordinates = matches[0]["coordinates"]
        return float(coordinates["y"]), float(coordinates["x"]), "Coordinates populated from U.S. Census geocoder using the listed official address."

    fallback = session.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": address, "format": "jsonv2", "limit": 1},
        headers={"User-Agent": "LibertyHillMedicalClinicGIS/1.0"},
        timeout=HTTP_TIMEOUT,
    )
    fallback.raise_for_status()
    results = fallback.json()
    if results:
        return float(results[0]["lat"]), float(results[0]["lon"]), "Coordinates populated from Nominatim after the Census geocoder returned no match."

    return pd.NA, pd.NA, "Census geocoder and Nominatim did not return a coordinate match."


def load_verified_utilities() -> pd.DataFrame:
    if not RAW_INPUT_PATH.exists():
        raise SystemExit(f"Verified utility provider input not found at {RAW_INPUT_PATH}.")

    frame = pd.read_csv(RAW_INPUT_PATH, dtype="string").replace({"": pd.NA})
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise SystemExit(f"Verified utility provider input is missing required columns: {', '.join(missing)}")

    for column in REQUIRED_COLUMNS:
        if column not in {"latitude", "longitude"}:
            frame[column] = frame[column].map(coerce_string)

    frame["latitude"] = frame["latitude"].map(coerce_float)
    frame["longitude"] = frame["longitude"].map(coerce_float)
    return frame


def validate_and_geocode(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "LibertyHillMedicalClinicGIS/1.0"})
    notes: list[str] = []

    for index, row in frame.iterrows():
        issues: list[str] = []

        if pd.isna(row.get("utility_type")) or row["utility_type"] not in UTILITY_TYPE_LABELS:
            issues.append("Utility type is not one of the supported layer categories.")

        latitude = frame.at[index, "latitude"]
        longitude = frame.at[index, "longitude"]
        if pd.notna(latitude) and not (-90 <= float(latitude) <= 90):
            issues.append("Latitude is outside valid range.")
            frame.at[index, "latitude"] = pd.NA
        if pd.notna(longitude) and not (-180 <= float(longitude) <= 180):
            issues.append("Longitude is outside valid range.")
            frame.at[index, "longitude"] = pd.NA

        if pd.isna(frame.at[index, "latitude"]) or pd.isna(frame.at[index, "longitude"]):
            geocoded_latitude, geocoded_longitude, geocode_note = geocode_address(session, row)
            if pd.notna(geocoded_latitude) and pd.notna(geocoded_longitude):
                frame.at[index, "latitude"] = geocoded_latitude
                frame.at[index, "longitude"] = geocoded_longitude
                issues.append(geocode_note or "Coordinates populated from official address.")
            elif geocode_note:
                issues.append(geocode_note)

        for required_field in ["provider_name", "address", "city", "state", "zip_code", "source_url", "verification_date"]:
            if pd.isna(row.get(required_field)):
                issues.append(f"Missing required field: {required_field}.")

        existing_notes = [str(row["verification_notes"])] if pd.notna(row.get("verification_notes")) else []
        existing_notes.extend(issues)
        frame.at[index, "verification_notes"] = " | ".join(existing_notes) if existing_notes else pd.NA

        if issues:
            notes.append(f"{row.get('utility_id', index)}: {' '.join(issues)}")

    return frame, notes


def build_geodataframe(frame: pd.DataFrame) -> gpd.GeoDataFrame:
    geodata = gpd.GeoDataFrame(
        frame.copy(),
        geometry=gpd.points_from_xy(frame["longitude"], frame["latitude"], crs="EPSG:4326"),
    )
    geodata["utility_type_label"] = geodata["utility_type"].map(UTILITY_TYPE_LABELS)
    geodata["full_address"] = geodata.apply(format_address, axis=1)
    return geodata


def calculate_site_distances(geodata: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    projected = geodata.to_crs("EPSG:5070")
    proposed = gpd.GeoSeries([Point(PROPOSED_SITE_LONGITUDE, PROPOSED_SITE_LATITUDE)], crs="EPSG:4326").to_crs("EPSG:5070").iloc[0]
    geodata["distance_from_proposed_site_miles"] = projected.geometry.distance(proposed) / METERS_PER_MILE
    geodata["within_five_miles"] = geodata["distance_from_proposed_site_miles"] <= 5
    geodata["within_ten_miles"] = geodata["distance_from_proposed_site_miles"] <= 10
    return geodata


def write_outputs(geodata: gpd.GeoDataFrame) -> None:
    OUTPUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    export_columns = [
        "utility_id",
        "provider_name",
        "utility_type",
        "utility_type_label",
        "services",
        "study_area_context",
        "address",
        "city",
        "state",
        "zip_code",
        "phone",
        "email",
        "website",
        "source_url",
        "source_organization",
        "verification_date",
        "verification_notes",
        "latitude",
        "longitude",
        "full_address",
        "distance_from_proposed_site_miles",
        "within_five_miles",
        "within_ten_miles",
        "geometry",
    ]
    geodata[export_columns].to_file(OUTPUT_GEOJSON, driver="GeoJSON")
    geodata[export_columns[:-1]].to_csv(OUTPUT_CSV, index=False)


def write_source_metadata(geodata: gpd.GeoDataFrame) -> None:
    SOURCE_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    source_metadata = geodata[
        [
            "provider_name",
            "utility_type",
            "source_url",
            "source_organization",
            "verification_date",
            "verification_notes",
        ]
    ].rename(columns={"verification_notes": "notes"})
    source_metadata.to_csv(SOURCE_METADATA_PATH, index=False)


def build_summary(geodata: gpd.GeoDataFrame) -> dict[str, object]:
    return {
        "date_built": date.today().isoformat(),
        "total_utility_providers": int(len(geodata)),
        "providers_within_five_miles": int(geodata["within_five_miles"].sum()),
        "providers_within_ten_miles": int(geodata["within_ten_miles"].sum()),
        "counts_by_utility_type": {
            utility_type: int((geodata["utility_type"] == utility_type).sum())
            for utility_type in UTILITY_TYPE_LABELS
            if int((geodata["utility_type"] == utility_type).sum()) > 0
        },
        "provider_names": geodata["provider_name"].dropna().tolist(),
    }


def main() -> None:
    utilities = load_verified_utilities()
    utilities, validation_notes = validate_and_geocode(utilities)
    valid_rows = utilities.loc[
        utilities["latitude"].notna()
        & utilities["longitude"].notna()
        & utilities["utility_type"].isin(UTILITY_TYPE_LABELS)
    ].copy()
    geodata = build_geodataframe(valid_rows)
    geodata = calculate_site_distances(geodata)

    write_outputs(geodata)
    write_source_metadata(geodata)
    SUMMARY_PATH.write_text(json.dumps(build_summary(geodata), indent=2), encoding="utf-8")

    print(f"Processed {len(utilities)} verified utility provider records.")
    print(f"Exported {len(geodata)} utility providers to {OUTPUT_GEOJSON} and {OUTPUT_CSV}.")
    print(f"Providers within 5 miles of the proposed site: {int(geodata['within_five_miles'].sum())}.")
    print(f"Wrote utility source metadata to {SOURCE_METADATA_PATH}.")
    print(f"Wrote utility summary to {SUMMARY_PATH}.")
    if validation_notes:
        print(f"Validation appended notes to {len(validation_notes)} utility records.")


if __name__ == "__main__":
    main()