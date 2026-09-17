from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point

RAW_INPUT_PATH = Path("data/raw/verified_healthcare_facilities.csv")
RAW_TEMPLATE_PATH = Path("data/raw/verified_healthcare_facilities_template.csv")
OUTPUT_GEOJSON = Path("data/processed/liberty_hill_healthcare_facilities.geojson")
OUTPUT_CSV = Path("data/processed/liberty_hill_healthcare_facilities.csv")
ACCESSIBILITY_GEOJSON = Path("data/processed/liberty_hill_healthcare_accessibility.geojson")
ACCESSIBILITY_CSV = Path("data/processed/liberty_hill_healthcare_accessibility.csv")
ACS_BLOCK_GROUPS_PATH = Path("data/processed/liberty_hill_acs_block_groups.geojson")
SOURCE_METADATA_PATH = Path("metadata/healthcare_facility_sources.csv")
POSSIBLE_DUPLICATES_PATH = Path("metadata/healthcare_possible_duplicates.csv")
MANUAL_VERIFICATION_PATH = Path("metadata/healthcare_manual_verification.csv")
SUMMARY_PATH = Path("metadata/healthcare_inventory_summary.json")

ALWAYS_INCLUDE_FACILITY_IDS = {
    "ascension-seton-cedarpark-hospital",
    "stdavids-georgetown-hospital",
}

PROPOSED_SITE_LATITUDE = 30.6521666667
PROPOSED_SITE_LONGITUDE = -97.8797222222
STUDY_RADIUS_MILES = 10.0
METERS_PER_MILE = 1609.344
HTTP_TIMEOUT = 30
OSRM_TABLE_URL = "https://router.project-osrm.org/table/v1/driving/"

STANDARD_TYPES = {
    "primary_care": "primary_care",
    "family_medicine": "primary_care",
    "internal_medicine": "primary_care",
    "general_primary_care": "primary_care",
    "community_health_center": "primary_care",
    "urgent_care": "urgent_care",
    "walk_in_clinic": "urgent_care",
    "express_care": "urgent_care",
    "hospital": "hospital",
    "medical_center": "hospital",
    "emergency_department": "emergency_department",
    "hospital_emergency_department": "emergency_department",
    "freestanding_emergency_department": "emergency_department",
    "emergency_center": "emergency_department",
    "specialty_clinic": "specialty_clinic",
    "pharmacy": "pharmacy",
}

TYPE_LABELS = {
    "primary_care": "Primary Care",
    "urgent_care": "Urgent Care",
    "hospital": "Hospital",
    "emergency_department": "Emergency Department",
    "specialty_clinic": "Specialty Clinic",
    "pharmacy": "Pharmacy",
}

STANDARD_STATUSES = {
    "verified current": "Verified Current",
    "probably current": "Probably Current",
    "unverified": "Unverified",
    "closed": "Closed",
    "moved": "Moved",
    "rebranded": "Rebranded",
}

REQUIRED_COLUMNS = [
    "facility_id",
    "facility_name",
    "facility_type",
    "organization",
    "address",
    "city",
    "state",
    "zip_code",
    "phone",
    "website",
    "source_url",
    "source_type",
    "current_status",
    "verification_date",
    "verification_notes",
    "former_name",
    "services",
    "latitude",
    "longitude",
]


@dataclass(frozen=True)
class DuplicateCandidate:
    left_facility_id: str
    right_facility_id: str
    left_facility_name: str
    right_facility_name: str
    reason: str


def normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    cleaned = re.sub(r"[^a-z0-9]+", " ", str(value).casefold())
    return re.sub(r"\s+", " ", cleaned).strip()


def standardize_facility_type(value: object) -> str | pd.NA:
    normalized = normalize_text(value).replace(" ", "_")
    if not normalized:
        return pd.NA
    return STANDARD_TYPES.get(normalized, pd.NA)


def standardize_status(value: object) -> str | pd.NA:
    normalized = normalize_text(value)
    if not normalized:
        return pd.NA
    return STANDARD_STATUSES.get(normalized, pd.NA)


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
        return pd.NA, pd.NA, "Address missing; Census geocoder not attempted."

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
        return float(coordinates["y"]), float(coordinates["x"]), None

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


def load_verified_inventory() -> pd.DataFrame:
    if not RAW_INPUT_PATH.exists():
        raise SystemExit(
            f"Verified healthcare inventory not found at {RAW_INPUT_PATH}. Populate it from {RAW_TEMPLATE_PATH}."
        )

    frame = pd.read_csv(RAW_INPUT_PATH, dtype="string").replace({"": pd.NA})
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise SystemExit(f"Verified healthcare inventory is missing required columns: {', '.join(missing)}")

    for column in REQUIRED_COLUMNS:
        if column not in {"latitude", "longitude"}:
            frame[column] = frame[column].map(coerce_string)

    frame["facility_type"] = frame["facility_type"].map(standardize_facility_type)
    frame["current_status"] = frame["current_status"].map(standardize_status)
    frame["latitude"] = frame["latitude"].map(coerce_float)
    frame["longitude"] = frame["longitude"].map(coerce_float)
    return frame


def validate_and_geocode(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "LibertyHillMedicalClinicGIS/1.0"})
    notes: list[str] = []

    for index, row in frame.iterrows():
        issues: list[str] = []

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
                issues.append(geocode_note or "Coordinates populated from U.S. Census geocoder using the listed official address.")
            elif geocode_note:
                issues.append(geocode_note)

        if pd.isna(row.get("source_url")):
            issues.append("Missing source URL for verification.")
        if pd.isna(row.get("verification_date")):
            issues.append("Missing verification date.")
        if pd.isna(row.get("facility_type")):
            issues.append("Facility type is not standardized to an allowed value.")
        if pd.isna(row.get("current_status")):
            issues.append("Current status is not standardized to an allowed value.")

        existing_notes = [str(row["verification_notes"])] if pd.notna(row.get("verification_notes")) else []
        existing_notes.extend(issues)
        frame.at[index, "verification_notes"] = " | ".join(existing_notes) if existing_notes else pd.NA

        if issues:
            notes.append(f"{row.get('facility_id', index)}: {' '.join(issues)}")

    return frame, notes


def drop_exact_duplicates(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    latitude_series = pd.to_numeric(frame["latitude"], errors="coerce")
    longitude_series = pd.to_numeric(frame["longitude"], errors="coerce")
    comparable = frame.assign(
        normalized_name=frame["facility_name"].map(normalize_text),
        normalized_address=frame["address"].map(normalize_text),
        normalized_org=frame["organization"].map(normalize_text),
        latitude_round=latitude_series.round(6),
        longitude_round=longitude_series.round(6),
    )
    exact_mask = comparable.duplicated(
        subset=["normalized_name", "normalized_address", "facility_type", "normalized_org", "latitude_round", "longitude_round"],
        keep="first",
    )
    removed = comparable.loc[exact_mask].drop(columns=["normalized_name", "normalized_address", "normalized_org", "latitude_round", "longitude_round"])
    cleaned = comparable.loc[~exact_mask].drop(columns=["normalized_name", "normalized_address", "normalized_org", "latitude_round", "longitude_round"])
    return cleaned, removed


def detect_possible_duplicates(frame: pd.DataFrame) -> pd.DataFrame:
    latitude_series = pd.to_numeric(frame["latitude"], errors="coerce")
    longitude_series = pd.to_numeric(frame["longitude"], errors="coerce")
    comparable = frame.assign(
        normalized_name=frame["facility_name"].map(normalize_text),
        normalized_address=frame["address"].map(normalize_text),
        normalized_org=frame["organization"].map(normalize_text),
        latitude_round=latitude_series.round(5),
        longitude_round=longitude_series.round(5),
    )
    candidates: list[DuplicateCandidate] = []

    for left_index in range(len(comparable)):
        left = comparable.iloc[left_index]
        for right_index in range(left_index + 1, len(comparable)):
            right = comparable.iloc[right_index]
            reason = None
            if left["normalized_address"] and left["normalized_address"] == right["normalized_address"]:
                reason = "Same normalized street address"
            elif (
                pd.notna(left["latitude_round"]) and pd.notna(right["latitude_round"]) and pd.notna(left["longitude_round"]) and pd.notna(right["longitude_round"])
                and left["latitude_round"] == right["latitude_round"] and left["longitude_round"] == right["longitude_round"]
            ):
                reason = "Same rounded coordinates"
            elif left["normalized_org"] and left["normalized_org"] == right["normalized_org"]:
                similarity = SequenceMatcher(None, left["normalized_name"], right["normalized_name"]).ratio()
                if similarity >= 0.84:
                    reason = f"Similar name within same organization ({similarity:.2f})"

            if reason:
                candidates.append(
                    DuplicateCandidate(
                        left_facility_id=str(left["facility_id"]),
                        right_facility_id=str(right["facility_id"]),
                        left_facility_name=str(left["facility_name"]),
                        right_facility_name=str(right["facility_name"]),
                        reason=reason,
                    )
                )

    return pd.DataFrame([candidate.__dict__ for candidate in candidates])


def build_geodataframe(frame: pd.DataFrame) -> gpd.GeoDataFrame:
    geodata = gpd.GeoDataFrame(
        frame.copy(),
        geometry=gpd.points_from_xy(frame["longitude"], frame["latitude"], crs="EPSG:4326"),
    )
    geodata["facility_type_label"] = geodata["facility_type"].map(TYPE_LABELS)
    geodata["full_address"] = geodata.apply(format_address, axis=1)
    return geodata


def build_osrm_coordinate_string(coordinates: list[tuple[float, float]]) -> str:
    return ";".join(f"{longitude:.6f},{latitude:.6f}" for longitude, latitude in coordinates)


def fetch_route_matrix(
    session: requests.Session,
    sources: list[tuple[float, float]],
    destinations: list[tuple[float, float]],
) -> tuple[np.ndarray | None, np.ndarray | None]:
    if not sources or not destinations:
        return None, None

    coordinates = [*sources, *destinations]
    source_indexes = ";".join(str(index) for index in range(len(sources)))
    destination_indexes = ";".join(str(index) for index in range(len(sources), len(coordinates)))
    response = session.get(
        f"{OSRM_TABLE_URL}{build_osrm_coordinate_string(coordinates)}",
        params={
            "annotations": "distance,duration",
            "sources": source_indexes,
            "destinations": destination_indexes,
        },
        timeout=HTTP_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    distances = payload.get("distances")
    durations = payload.get("durations")
    if distances is None or durations is None:
        return None, None

    distance_matrix = np.array(distances, dtype="float64") / METERS_PER_MILE
    duration_matrix = np.array(durations, dtype="float64") / 60.0
    distance_matrix[~np.isfinite(distance_matrix)] = np.nan
    duration_matrix[~np.isfinite(duration_matrix)] = np.nan
    return distance_matrix, duration_matrix


def assign_route_metrics(geodata: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, bool]:
    if geodata.empty:
        geodata["drive_distance_miles"] = pd.Series(dtype="float64")
        geodata["drive_time_minutes"] = pd.Series(dtype="float64")
        return geodata, False

    session = requests.Session()
    session.headers.update({"User-Agent": "LibertyHillMedicalClinicGIS/1.0"})
    source = [(PROPOSED_SITE_LONGITUDE, PROPOSED_SITE_LATITUDE)]
    destinations = list(zip(geodata.geometry.x, geodata.geometry.y, strict=False))

    try:
        distance_matrix, duration_matrix = fetch_route_matrix(session, source, destinations)
    except requests.RequestException:
        geodata["drive_distance_miles"] = geodata["distance_from_proposed_site_miles"]
        geodata["drive_time_minutes"] = np.nan
        return geodata, False

    if distance_matrix is None or duration_matrix is None:
        geodata["drive_distance_miles"] = geodata["distance_from_proposed_site_miles"]
        geodata["drive_time_minutes"] = np.nan
        return geodata, False

    geodata["drive_distance_miles"] = distance_matrix[0]
    geodata["drive_time_minutes"] = duration_matrix[0]
    geodata["drive_distance_miles"] = geodata["drive_distance_miles"].fillna(geodata["distance_from_proposed_site_miles"])
    return geodata, True


def calculate_site_distances(geodata: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    projected = geodata.to_crs("EPSG:5070")
    proposed = gpd.GeoSeries([Point(PROPOSED_SITE_LONGITUDE, PROPOSED_SITE_LATITUDE)], crs="EPSG:4326").to_crs("EPSG:5070").iloc[0]
    geodata["distance_from_proposed_site_miles"] = projected.geometry.distance(proposed) / METERS_PER_MILE
    geodata["drive_time_minutes"] = np.nan
    geodata["drive_distance_miles"] = np.nan
    return geodata


def filter_to_study_radius(geodata: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    comparison_distance = geodata["drive_distance_miles"].fillna(geodata["distance_from_proposed_site_miles"])
    include_mask = comparison_distance <= STUDY_RADIUS_MILES
    include_mask = include_mask | geodata["facility_id"].isin(ALWAYS_INCLUDE_FACILITY_IDS)
    within_radius = geodata.loc[include_mask].copy()
    excluded = geodata.loc[~include_mask].copy()
    return within_radius, excluded


def write_facility_outputs(geodata: gpd.GeoDataFrame) -> None:
    OUTPUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    export_columns = [
        "facility_id",
        "facility_name",
        "facility_type",
        "facility_type_label",
        "organization",
        "address",
        "city",
        "state",
        "zip_code",
        "phone",
        "latitude",
        "longitude",
        "website",
        "source_url",
        "source_type",
        "current_status",
        "verification_date",
        "verification_notes",
        "former_name",
        "services",
        "full_address",
        "distance_from_proposed_site_miles",
        "drive_time_minutes",
        "drive_distance_miles",
        "geometry",
    ]
    geodata[export_columns].to_file(OUTPUT_GEOJSON, driver="GeoJSON")
    geodata[export_columns[:-1]].to_csv(OUTPUT_CSV, index=False)


def write_source_metadata(geodata: gpd.GeoDataFrame) -> None:
    source_metadata = geodata[
        [
            "facility_name",
            "facility_type",
            "source_url",
            "organization",
            "verification_date",
            "current_status",
            "former_name",
            "verification_notes",
        ]
    ].rename(columns={"organization": "source_organization", "verification_notes": "notes"})
    source_metadata.to_csv(SOURCE_METADATA_PATH, index=False)


def distance_to_nearest(points: gpd.GeoSeries, facilities: gpd.GeoDataFrame) -> pd.Series:
    if facilities.empty:
        return pd.Series(np.nan, index=points.index, dtype="float64")
    projected = facilities.to_crs("EPSG:5070")
    return points.apply(lambda geometry: projected.geometry.distance(geometry).min() / METERS_PER_MILE)


def route_distance_to_nearest(
    origins: list[tuple[float, float]],
    facilities: gpd.GeoDataFrame,
) -> tuple[pd.Series, pd.Series, bool]:
    origin_index = pd.RangeIndex(len(origins))
    if not origins or facilities.empty:
        nan_series = pd.Series(np.nan, index=origin_index, dtype="float64")
        return nan_series, nan_series, False

    session = requests.Session()
    session.headers.update({"User-Agent": "LibertyHillMedicalClinicGIS/1.0"})
    destinations = list(zip(facilities.geometry.x, facilities.geometry.y, strict=False))

    try:
        distance_matrix, duration_matrix = fetch_route_matrix(session, origins, destinations)
    except requests.RequestException:
        nan_series = pd.Series(np.nan, index=origin_index, dtype="float64")
        return nan_series, nan_series, False

    if distance_matrix is None or duration_matrix is None:
        nan_series = pd.Series(np.nan, index=origin_index, dtype="float64")
        return nan_series, nan_series, False

    nearest_distances = np.nanmin(distance_matrix, axis=1)
    nearest_durations = np.nanmin(duration_matrix, axis=1)
    return (
        pd.Series(nearest_distances, index=origin_index, dtype="float64"),
        pd.Series(nearest_durations, index=origin_index, dtype="float64"),
        True,
    )


def build_accessibility_outputs(geodata: gpd.GeoDataFrame) -> dict[str, int | bool] | None:
    if not ACS_BLOCK_GROUPS_PATH.exists():
        return None

    access = gpd.read_file(ACS_BLOCK_GROUPS_PATH).to_crs("EPSG:4326")
    projected_points = access.to_crs("EPSG:5070").representative_point()
    origin_points = access.representative_point()
    origin_coordinates = list(zip(origin_points.x, origin_points.y, strict=False))

    medical = geodata.loc[geodata["facility_type"] != "pharmacy"].copy()
    primary = geodata.loc[geodata["facility_type"] == "primary_care"].copy()
    urgent = geodata.loc[geodata["facility_type"] == "urgent_care"].copy()
    hospital = geodata.loc[geodata["facility_type"] == "hospital"].copy()
    emergency = geodata.loc[geodata["facility_type"] == "emergency_department"].copy()

    access["nearest_any_medical_miles"] = distance_to_nearest(projected_points, medical)
    route_primary_miles, route_primary_minutes, primary_routed = route_distance_to_nearest(origin_coordinates, primary)
    route_urgent_miles, route_urgent_minutes, urgent_routed = route_distance_to_nearest(origin_coordinates, urgent)
    route_hospital_miles, route_hospital_minutes, hospital_routed = route_distance_to_nearest(origin_coordinates, hospital)
    route_emergency_miles, route_emergency_minutes, emergency_routed = route_distance_to_nearest(origin_coordinates, emergency)
    route_any_miles, route_any_minutes, any_routed = route_distance_to_nearest(origin_coordinates, medical)

    access["nearest_primary_care_miles"] = route_primary_miles.fillna(distance_to_nearest(projected_points, primary))
    access["nearest_urgent_care_miles"] = route_urgent_miles.fillna(distance_to_nearest(projected_points, urgent))
    access["nearest_hospital_miles"] = route_hospital_miles.fillna(distance_to_nearest(projected_points, hospital))
    access["nearest_emergency_miles"] = route_emergency_miles.fillna(distance_to_nearest(projected_points, emergency))
    access["nearest_any_medical_miles"] = route_any_miles.fillna(access["nearest_any_medical_miles"])
    access["nearest_primary_care_minutes"] = route_primary_minutes
    access["nearest_urgent_care_minutes"] = route_urgent_minutes
    access["nearest_hospital_minutes"] = route_hospital_minutes
    access["nearest_emergency_minutes"] = route_emergency_minutes
    access["healthcare_access_measure"] = "Driving route distance" if any_routed else "Straight-line distance"
    access["healthcare_access_distance_band"] = pd.cut(
        access["nearest_any_medical_miles"],
        bins=[-np.inf, 1, 3, 5, 10, np.inf],
        labels=["0-1 miles", "1-3 miles", "3-5 miles", "5-10 miles", "10+ miles"],
    ).astype("string")

    ACCESSIBILITY_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    access.to_file(ACCESSIBILITY_GEOJSON, driver="GeoJSON")
    access.drop(columns="geometry").to_csv(ACCESSIBILITY_CSV, index=False)
    return {
        "block_groups": len(access),
        "route_distance_available": bool(any_routed or primary_routed or urgent_routed or hospital_routed or emergency_routed),
        "route_time_available": bool(any_routed or primary_routed or urgent_routed or hospital_routed or emergency_routed),
    }


def build_summary(raw_count: int, geodata: gpd.GeoDataFrame, excluded_by_radius: pd.DataFrame, removed_duplicates: pd.DataFrame, possible_duplicates: pd.DataFrame, manual_verification: pd.DataFrame, accessibility_summary: dict[str, int] | None) -> dict[str, object]:
    distances = geodata["drive_distance_miles"].fillna(geodata["distance_from_proposed_site_miles"])
    return {
        "date_built": date.today().isoformat(),
        "study_radius_miles": STUDY_RADIUS_MILES,
        "raw_facility_records": int(raw_count),
        "total_facilities": int(len(geodata)),
        "excluded_beyond_study_radius": int(len(excluded_by_radius)),
        "counts_by_type": {facility_type: int((geodata["facility_type"] == facility_type).sum()) for facility_type in TYPE_LABELS},
        "counts_within_distance_bands": {
            "within_1_mile": int((distances <= 1).sum()),
            "within_3_miles": int((distances <= 3).sum()),
            "within_5_miles": int((distances <= 5).sum()),
            "within_10_miles": int((distances <= 10).sum()),
        },
        "counts_by_status": geodata["current_status"].fillna("Missing").value_counts(dropna=False).to_dict(),
        "removed_exact_duplicates": int(len(removed_duplicates)),
        "possible_duplicates_flagged": int(len(possible_duplicates)),
        "manual_verification_required": int(len(manual_verification)),
        "drive_time_available": bool(geodata["drive_time_minutes"].notna().any()),
        "drive_distance_available": bool(geodata["drive_distance_miles"].notna().any()),
        "accessibility_summary": accessibility_summary,
    }


def main() -> None:
    inventory = load_verified_inventory()
    inventory, validation_notes = validate_and_geocode(inventory)
    cleaned, removed_duplicates = drop_exact_duplicates(inventory)
    possible_duplicates = detect_possible_duplicates(cleaned)

    manual_verification = cleaned.loc[
        cleaned["current_status"].ne("Verified Current")
        | cleaned["latitude"].isna()
        | cleaned["longitude"].isna()
        | cleaned["source_url"].isna()
        | cleaned["verification_date"].isna()
        | cleaned["facility_type"].isna()
    ].copy()

    valid_rows = cleaned.loc[cleaned["latitude"].notna() & cleaned["longitude"].notna() & cleaned["facility_type"].notna()].copy()
    geodata = build_geodataframe(valid_rows)
    geodata = calculate_site_distances(geodata)
    geodata, _ = assign_route_metrics(geodata)
    geodata, excluded_by_radius = filter_to_study_radius(geodata)

    write_facility_outputs(geodata)
    write_source_metadata(geodata)
    possible_duplicates.to_csv(POSSIBLE_DUPLICATES_PATH, index=False)
    manual_verification.to_csv(MANUAL_VERIFICATION_PATH, index=False)

    accessibility_summary = build_accessibility_outputs(geodata)
    summary = build_summary(len(inventory), geodata, excluded_by_radius, removed_duplicates, possible_duplicates, manual_verification, accessibility_summary)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Processed {len(inventory)} raw healthcare facility records.")
    print(f"Exported {len(geodata)} facilities to {OUTPUT_GEOJSON} and {OUTPUT_CSV}.")
    print(f"Excluded {len(excluded_by_radius)} facilities beyond {STUDY_RADIUS_MILES} route miles from the proposed site.")
    print(f"Flagged {len(possible_duplicates)} possible duplicates in {POSSIBLE_DUPLICATES_PATH}.")
    print(f"Logged {len(manual_verification)} facilities requiring manual verification in {MANUAL_VERIFICATION_PATH}.")
    if validation_notes:
        print(f"Validation appended notes to {len(validation_notes)} facilities.")
    if accessibility_summary is None:
        print("ACS block-group layer not found; skipped healthcare accessibility export.")
    else:
        print(f"Exported healthcare accessibility fields for {accessibility_summary['block_groups']} block groups.")


if __name__ == "__main__":
    main()