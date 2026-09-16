# Methodology

## Current implementation status

The current application is a Phase 1 scaffold. It establishes the study location, configurable 5-mile and 10-mile analysis extents, a base web map, and a dashboard for contextual QuickFacts values.

## Planned scoring framework

The suitability model will remain transparent and configurable.

Suggested initial factors:

- Population density: 20%
- Population growth and development activity: 15%
- Healthcare accessibility gap: 25%
- Healthcare need and demographics: 15%
- Transportation accessibility: 10%
- Utility accessibility: 10%
- Environmental or site constraints: 5%

## Planned normalization

Each factor will be normalized to a 0 to 100 scale before weighting.

## Interpretation guardrails

- Suitability should be described as relative, not absolute.
- ACS values are estimates and should be shown with caution.
- Facility inventories must be runtime-verified before final use.
- Utility service availability is a feasibility indicator, not proof of service.
- Parcel suitability does not imply parcel availability.
- Travel-time outputs depend on the routing source and traffic assumptions.