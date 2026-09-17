# Methodology

## Current implementation status

The current application is a Phase 1 scaffold. It establishes the study location, configurable 5-mile and 10-mile analysis extents, a base web map, and a dashboard for contextual QuickFacts values.

## Planned analysis framework

The analysis should remain transparent and configurable.

Suggested initial comparison themes:

- Population density
- Healthcare accessibility gap
- Healthcare need and demographics
- Transportation accessibility
- Utility accessibility

## Planned normalization

Derived indicators can be normalized to comparable scales when needed, but they do not need to be collapsed into one weighted score.

## Interpretation guardrails

- Comparative findings should be described as relative, not absolute.
- ACS values are estimates and should be shown with caution.
- Facility inventories must be runtime-verified before final use.
- Utility service availability is a feasibility indicator, not proof of service.
- Parcel suitability does not imply parcel availability.
- Travel-time outputs depend on the routing source and traffic assumptions.