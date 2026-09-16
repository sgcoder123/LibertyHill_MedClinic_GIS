# Key Sources

This file is the human-readable source register for the GIS application.
Update it every time a new phase, layer, dataset, or externally sourced feature is added.

## How To Maintain This File

- Add each new phase or feature under its own heading.
- List the authoritative source URLs that feed the map, dashboard, popups, or derived metrics.
- If a phase relies on many facility-level pages, summarize the source family here and keep the row-level detail in a companion CSV.
- Note important limitations so the application remains evidence-based and neutral.

## Phase 1: Study Context And Base Map

### Liberty Hill context statistics

- Source: U.S. Census Bureau QuickFacts
- URL: https://www.census.gov/quickfacts/fact/table/libertyhillcitytexas/PST045225
- Used for: City-level context cards in the dashboard
- Limitations: QuickFacts values are contextual city estimates and are not merged directly with ACS block-group spatial analysis.

### Basemap tiles

- Source: OpenStreetMap contributors
- URL: https://www.openstreetmap.org/copyright
- Used for: Leaflet basemap tile background
- Limitations: Basemap is reference context, not an authoritative analytical layer for this study.

## Phase 2: ACS Demographic Layer

### ACS 2024 5-Year Estimates

- Source: U.S. Census Bureau
- URL: https://api.census.gov/data/2024/acs/acs5
- Used for: Block-group demographic fields, percentages, and the healthcare need score inputs
- Limitations: Survey-based estimates with margins of error; the 2024 ACS 5-Year release reflects the 2020-2024 collection period.

### ACS variable catalog

- Source: U.S. Census Bureau
- URL: https://api.census.gov/data/2024/acs/acs5/variables.json
- Used for: Metadata descriptions in the ACS variable catalog export
- Limitations: Documentation support only; not a spatial layer.

### TIGER/Line 2024 Block Groups

- Source: U.S. Census Bureau
- URL: https://www2.census.gov/geo/tiger/TIGER2024/BG/tl_2024_48_bg.zip
- Used for: Block-group geometries joined to ACS attributes
- Limitations: Boundary vintage and ACS survey period differ conceptually and should be interpreted together with care.

### TIGER/Line 2024 Places

- Source: U.S. Census Bureau
- URL: https://www2.census.gov/geo/tiger/TIGER2024/PLACE/tl_2024_48_place.zip
- Used for: Liberty Hill city boundary intersection context
- Limitations: Used for contextual city-boundary overlap, not as a utility or service-area boundary.

### Detailed ACS metadata export

- Supporting file: [metadata/acs_block_group_metadata.csv](/Users/saig/LibertyHill_MedClinic_GIS/metadata/acs_block_group_metadata.csv)
- Used for: Field-level provenance and estimate or margin-of-error documentation

## Phase 3: Healthcare Facilities And Accessibility

### Facility verification register

- Supporting file: [metadata/healthcare_facility_sources.csv](/Users/saig/LibertyHill_MedClinic_GIS/metadata/healthcare_facility_sources.csv)
- Used for: Facility-by-facility official source URLs, organizations, statuses, dates, and notes
- Limitations: Facility branding, hours, and service offerings can change and require ongoing verification.

### Official provider and hospital pages currently used in the GIS

- Care First Clinic: https://www.carefirstclinic.com/
- Austin Regional Clinic Liberty Hill: https://www.austinregionalclinic.com/clinics/liberty-hill
- Austin Regional Clinic Leander: https://www.austinregionalclinic.com/clinics/leander
- Baylor Scott & White Clinic - Leander: https://www.bswhealth.com/locations/clinic/leander
- CareNow Urgent Care - Liberty Hill: https://www.carenow.com/locations/austin/liberty-hill
- CareNow Urgent Care - Leander: https://www.carenow.com/locations/austin/leander
- St. David's Emergency Center - Leander: https://www.stdavids.com/locations/st-davids-emergency-center-leander
- Baylor Scott & White Clinic - Georgetown: https://www.bswhealth.com/locations/clinic/georgetown
- Additional provider URLs may appear in the supporting register as more verified facilities are added.

### Healthcare geocoding and validation

- U.S. Census Geocoder: https://geocoding.geo.census.gov/geocoder/
- Nominatim OpenStreetMap search: https://nominatim.openstreetmap.org/
- Used for: Filling or validating facility coordinates when official source pages do not expose usable coordinates directly
- Limitations: Geocoding validates location, not whether a facility currently operates at that address.

### Healthcare accessibility layer

- Derived from: [data/processed/liberty_hill_healthcare_facilities.geojson](/Users/saig/LibertyHill_MedClinic_GIS/data/processed/liberty_hill_healthcare_facilities.geojson) and [data/processed/liberty_hill_acs_block_groups.geojson](/Users/saig/LibertyHill_MedClinic_GIS/data/processed/liberty_hill_acs_block_groups.geojson)
- Used for: Block-group nearest-facility distance fields shown in the healthcare accessibility layer
- Limitations: Current access values are straight-line distances, not drive-time or network-travel measures.

## Phase 4: Transportation Network

### TIGER/Line 2024 Roads

- Source: U.S. Census Bureau
- URL: https://www2.census.gov/geo/tiger/TIGER2024/ROADS/tl_2024_48491_roads.zip
- Used for: Transportation network centerlines within the 10-mile study area and major-corridor classification
- Limitations: Road centerlines support access context only; they do not represent traffic counts, speed, congestion, or turn restrictions.

### Transportation summary output

- Supporting file: [metadata/road_network_summary.json](/Users/saig/LibertyHill_MedClinic_GIS/metadata/road_network_summary.json)
- Used for: Summary counts of road segments, major corridors, and centerline mileage in the study area

## Phase 5: Utilities

### City of Liberty Hill Utilities

- Source: City of Liberty Hill
- URL: https://www.libertyhilltx.gov/380/Utilities
- Used for: Utility billing contact point, water and wastewater service responsibilities, and customer-service context
- Limitations: The page documents utility administration and customer service, not parcel-level service boundaries.

### City of Liberty Hill New Customers utility guidance

- Source: City of Liberty Hill
- URL: https://www.libertyhilltx.gov/500/New-Customers
- Used for: Study-area provider relationships showing where City of Liberty Hill, City of Georgetown, and City of Leander serve water or wastewater customers near Liberty Hill
- Limitations: Provider guidance is subdivision-oriented and should not be treated as a formal GIS service-area polygon layer.

### City of Georgetown Customer Care

- Source: City of Georgetown
- URL: https://georgetowntexas.gov/utilities/customer_care/
- Used for: Georgetown utility customer care address, phone, and supported utility services for provider-point mapping
- Limitations: The mapped point is a customer-care office, not a service-area boundary.

### City of Leander Utilities

- Source: City of Leander
- URL: https://www.leandertx.gov/514/Utilities
- Used for: Leander utility office address, water utility contact details, and documented PEC and Atmos context
- Limitations: The mapped point is a utility office location, not a service-area boundary.

### Utility provider supporting files

- Supporting file: [metadata/utility_provider_sources.csv](/Users/saig/LibertyHill_MedClinic_GIS/metadata/utility_provider_sources.csv)
- Supporting file: [metadata/utility_provider_summary.json](/Users/saig/LibertyHill_MedClinic_GIS/metadata/utility_provider_summary.json)
- Derived layer: [data/processed/liberty_hill_utilities.geojson](/Users/saig/LibertyHill_MedClinic_GIS/data/processed/liberty_hill_utilities.geojson)
- Used for: The utilities point layer shown in the GIS

## Machine-Readable Companion Register

- Structured source catalog: [metadata/data_sources.csv](/Users/saig/LibertyHill_MedClinic_GIS/metadata/data_sources.csv)
- This Markdown file is the readable overview.
- The CSV file is the structured companion register for scripts and tabular review.