from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from flask import Flask, jsonify, render_template


@dataclass(frozen=True)
class StudyConfig:
    study_name: str
    city_name: str
    county_name: str
    state_name: str
    latitude: float
    longitude: float
    default_zoom: int
    five_mile_radius_miles: float
    ten_mile_radius_miles: float


STUDY_CONFIG = StudyConfig(
    study_name="SH 29 / 183A Medical Clinic Study Area",
    city_name="Liberty Hill",
    county_name="Williamson County",
    state_name="Texas",
    latitude=30.6521666667,
    longitude=-97.8797222222,
    default_zoom=11,
    five_mile_radius_miles=5.0,
    ten_mile_radius_miles=10.0,
)

QUICKFACTS_CONTEXT = {
    "source": "U.S. Census Bureau QuickFacts",
    "profile_year": 2025,
    "population_2025": 13317,
    "population_2020": 3646,
    "population_2010": 967,
    "growth_2020_2025_pct": 276.6,
    "under_5_pct": 11.5,
    "under_18_pct": 32.6,
    "age_65_plus_pct": 5.5,
    "uninsured_under_65_pct": 24.6,
    "disability_under_65_pct": 10.4,
    "median_household_income": 115096,
    "per_capita_income": 37567,
    "poverty_pct": 7.2,
}

PHASE_STATUS = {
    "phase_1": "complete",
    "phase_2": "complete",
    "phase_3": "complete",
    "phase_4": "complete",
    "phase_5": "pending_data",
    "phase_6": "pending_data",
    "phase_7": "pending_data",
    "phase_8": "pending_data",
    "phase_9": "pending_data",
    "phase_10": "pending_data",
}

BASE_DIR = Path(__file__).resolve().parent
ACS_BLOCK_GROUPS_PATH = BASE_DIR / "data" / "processed" / "liberty_hill_acs_block_groups.geojson"
HEALTHCARE_FACILITIES_PATH = BASE_DIR / "data" / "processed" / "liberty_hill_healthcare_facilities.geojson"
HEALTHCARE_ACCESSIBILITY_PATH = BASE_DIR / "data" / "processed" / "liberty_hill_healthcare_accessibility.geojson"
ROAD_NETWORK_PATH = BASE_DIR / "data" / "processed" / "liberty_hill_roads.geojson"


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/bootstrap")
    def bootstrap() -> tuple[dict, int]:
        return (
            jsonify(
                {
                    "study_config": asdict(STUDY_CONFIG),
                    "quickfacts": QUICKFACTS_CONTEXT,
                    "phase_status": PHASE_STATUS,
                    "layers": {
                        "acs_block_groups": {
                            "available": ACS_BLOCK_GROUPS_PATH.exists(),
                            "endpoint": "/api/layers/acs-block-groups",
                        },
                        "healthcare_facilities": {
                            "available": HEALTHCARE_FACILITIES_PATH.exists(),
                            "endpoint": "/api/layers/healthcare-facilities",
                        },
                        "healthcare_accessibility": {
                            "available": HEALTHCARE_ACCESSIBILITY_PATH.exists(),
                            "endpoint": "/api/layers/healthcare-accessibility",
                        },
                        "road_network": {
                            "available": ROAD_NETWORK_PATH.exists(),
                            "endpoint": "/api/layers/road-network",
                        }
                    },
                }
            ),
            200,
        )

    @app.get("/api/layers/acs-block-groups")
    def acs_block_groups() -> tuple[dict, int]:
        if not ACS_BLOCK_GROUPS_PATH.exists():
            return (
                jsonify(
                    {
                        "error": "ACS block-group layer is not available yet.",
                        "expected_path": str(ACS_BLOCK_GROUPS_PATH),
                    }
                ),
                404,
            )

        return (jsonify(json.loads(ACS_BLOCK_GROUPS_PATH.read_text(encoding="utf-8"))), 200)

    @app.get("/api/layers/healthcare-facilities")
    def healthcare_facilities() -> tuple[dict, int]:
        if not HEALTHCARE_FACILITIES_PATH.exists():
            return (
                jsonify(
                    {
                        "error": "Healthcare facility layer is not available yet.",
                        "expected_path": str(HEALTHCARE_FACILITIES_PATH),
                    }
                ),
                404,
            )

        return (jsonify(json.loads(HEALTHCARE_FACILITIES_PATH.read_text(encoding="utf-8"))), 200)

    @app.get("/api/layers/healthcare-accessibility")
    def healthcare_accessibility() -> tuple[dict, int]:
        if not HEALTHCARE_ACCESSIBILITY_PATH.exists():
            return (
                jsonify(
                    {
                        "error": "Healthcare accessibility layer is not available yet.",
                        "expected_path": str(HEALTHCARE_ACCESSIBILITY_PATH),
                    }
                ),
                404,
            )

        return (jsonify(json.loads(HEALTHCARE_ACCESSIBILITY_PATH.read_text(encoding="utf-8"))), 200)

    @app.get("/api/layers/road-network")
    def road_network() -> tuple[dict, int]:
        if not ROAD_NETWORK_PATH.exists():
            return (
                jsonify(
                    {
                        "error": "Road network layer is not available yet.",
                        "expected_path": str(ROAD_NETWORK_PATH),
                    }
                ),
                404,
            )

        return (jsonify(json.loads(ROAD_NETWORK_PATH.read_text(encoding="utf-8"))), 200)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)