# Liberty Hill Medical Clinic GIS

Interactive web GIS application for evaluating the relative suitability of the SH 29 / US 183 area in Liberty Hill, Texas for a proposed medical clinic.

## Current status

Phase 1 is scaffolded:

- Flask application shell
- Leaflet-based interactive study map
- Configurable proposed clinic study marker
- Configurable 5-mile and 10-mile study areas
- QuickFacts context panel for Liberty Hill
- Project metadata and methodology stubs

Phase 2 is wired and ready for data retrieval:

- 2024 ACS 5-Year block-group downloader script using the official Census API
- 2024 TIGER/Line block-group and place-boundary join workflow
- ACS metadata export for variable provenance and limitations
- Leaflet choropleth layer for ACS block groups with switchable thematic display

Phase 3 is wired and ready for verified facility inputs:

- Verified healthcare inventory build script driven by an authoritative raw-facility CSV
- Straight-line distance from the proposed site for every facility
- Duplicate screening and manual-verification reports
- Separate Leaflet healthcare layers for primary care, urgent care, hospitals, emergency departments, specialty clinics, and pharmacies
- Block-group nearest-facility distance outputs when ACS block groups are available

Phases 2 through 10 depend on downloading and validating authoritative datasets before they are added to the analysis.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

## Deploy on Vercel

This repo is configured as a single Flask app deployed through Vercel's Python runtime.

1. Connect the repository to Vercel.
2. Let Vercel use `vercel.json` as the project config.
3. Deploy the root app through `api/index.py`, which imports the Flask app from `app.py`.
4. Keep `data/processed/` in the deployment bundle, because the API reads the processed GeoJSON layers from disk at request time.

The app should work without extra runtime environment variables. The data-processing scripts still expect local tooling and are not part of the deployed runtime.

## Data policy

- Authoritative datasets should be documented in `metadata/data_sources.csv` before use.
- Maintain `metadata/key_sources.md` as the human-readable phase-by-phase source register whenever a new feature or dataset is added.
- QuickFacts city-level statistics are displayed as context only and should not be merged directly with ACS block-group estimates.
- The default study coordinate is a configurable map seed for the SH 29 / US 183 study area and should be refined as parcel- and road-level analysis is added.

## ACS notes

- ACS 5-Year estimates are survey-based estimates rather than exact population counts.
- Margins of error should be considered when comparing small-area values across block groups.
- The 2024 ACS 5-Year release represents the 2020-2024 ACS collection period.
- 2025 QuickFacts population estimates and 2024 ACS 5-Year estimates should not be treated as identical datasets.
- Block-group boundaries and ACS attributes must be joined with the full Census GEOID.
- Derived percentages in the processed ACS outputs document their numerators and denominators in the exported fields and metadata.

## Healthcare inventory notes

- Third-party directories may help discovery, but each facility should be verified against an official provider, hospital, pharmacy, or government source whenever possible.
- If a facility cannot be verified as current, mark it as `Unverified` rather than assuming it is current.
- Rebranded facilities should use the current name as the primary label and preserve the former name in `former_name`.
- Straight-line distances should remain labeled as distance-based rather than travel-time based.
- The healthcare accessibility outputs remain neutral and should be used to compare relative access patterns rather than declare adequacy by themselves.

## Next implementation targets

1. Run the ACS block-group pipeline after `CENSUS_API_KEY` is available
2. Populate `data/raw/verified_healthcare_facilities.csv` from the template and run `scripts/build_healthcare_inventory.py`
3. Add transportation and accessibility layers
4. Add environmental constraints
5. Extend the transparent suitability scoring workflow