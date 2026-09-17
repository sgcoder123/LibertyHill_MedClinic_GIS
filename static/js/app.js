const layerRegistry = {};
let acsLayer = null;
let healthcareAccessibilityLayer = null;
let roadNetworkLayer = null;
let acsLegendControl = null;
let currentAcsMetric = "population_density";
let currentHealthcareAccessibilityMetric = "nearest_urgent_care_miles";
const healthcareTypeLayers = {};

const HEALTHCARE_LAYER_NAMES = [
  "healthcare-primary",
  "healthcare-urgent",
  "healthcare-hospital",
  "healthcare-emergency",
  "healthcare-specialty",
  "healthcare-pharmacy",
];

const HEALTHCARE_TYPES = {
  primary_care: { layerName: "healthcare-primary", label: "Primary Care", color: "#215a6d" },
  urgent_care: { layerName: "healthcare-urgent", label: "Urgent Care", color: "#bb4d00" },
  hospital: { layerName: "healthcare-hospital", label: "Hospital", color: "#6b5b95" },
  emergency_department: { layerName: "healthcare-emergency", label: "Emergency Department", color: "#a61c3c" },
  specialty_clinic: { layerName: "healthcare-specialty", label: "Specialty Clinic", color: "#447055" },
  pharmacy: { layerName: "healthcare-pharmacy", label: "Pharmacy", color: "#8b7a2f" },
};

const ACS_METRICS = {
  population_density: {
    label: "Population density",
    valueSuffix: " people/sq mi",
    bins: [0, 500, 1500, 3000, 5000],
    colors: ["#fff4e8", "#f6d3a9", "#e5a36c", "#cd6e34", "#8e3d06"],
  },
  uninsured_pct: {
    label: "Uninsured percentage",
    valueSuffix: "%",
    bins: [0, 8, 12, 18, 25],
    colors: ["#f4f6fb", "#d6dfef", "#a8bddb", "#678ab5", "#264c73"],
  },
  poverty_pct: {
    label: "Poverty percentage",
    valueSuffix: "%",
    bins: [0, 4, 8, 12, 20],
    colors: ["#f7efe7", "#e7ceb6", "#d59d77", "#ba6943", "#7c3417"],
  },
  disability_pct: {
    label: "Disability percentage",
    valueSuffix: "%",
    bins: [0, 8, 12, 16, 22],
    colors: ["#eff3e7", "#d2dfbe", "#a9c187", "#709456", "#3e5926"],
  },
  healthcare_need_score: {
    label: "Healthcare need score",
    valueSuffix: "",
    bins: [0, 20, 40, 60, 80],
    colors: ["#fff1db", "#ffd199", "#ffab5c", "#de7430", "#8e3d06"],
  },
};

const HEALTHCARE_ACCESSIBILITY_METRICS = {
  nearest_urgent_care_miles: {
    label: "Nearest urgent care",
    valueSuffix: " miles",
    bins: [0, 1, 3, 5, 10],
    colors: ["#2a4b3f", "#4f7c5e", "#88b27d", "#d7c868", "#b9663d"],
  },
  nearest_hospital_miles: {
    label: "Nearest hospital",
    valueSuffix: " miles",
    bins: [0, 1, 3, 5, 10],
    colors: ["#25334f", "#4e648d", "#8d9fc5", "#d4c09a", "#aa5a4c"],
  },
};

function milesToMeters(miles) {
  return miles * 1609.344;
}

function formatInteger(value) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function formatPercent(value) {
  return `${value.toFixed(1)}%`;
}

function formatNullableNumber(value, formatter, fallback = "N/A") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return fallback;
  }
  return formatter(Number(value));
}

function addDashboardCard(container, label, value, subtitle) {
  const card = document.createElement("article");
  card.className = "dashboard-card";
  card.innerHTML = `
    <div class="metric-label">${label}</div>
    <div class="metric-value">${value}</div>
    <div class="metric-subtitle">${subtitle}</div>
  `;
  container.appendChild(card);
}

function upsertDashboardCard(cardId, label, value, subtitle) {
  const container = document.getElementById("dashboard");
  const existing = document.getElementById(cardId);
  if (existing) {
    existing.querySelector(".metric-label").textContent = label;
    existing.querySelector(".metric-value").textContent = value;
    existing.querySelector(".metric-subtitle").textContent = subtitle;
    return;
  }

  const card = document.createElement("article");
  card.className = "dashboard-card";
  card.id = cardId;
  card.innerHTML = `
    <div class="metric-label">${label}</div>
    <div class="metric-value">${value}</div>
    <div class="metric-subtitle">${subtitle}</div>
  `;
  container.appendChild(card);
}

function buildDashboard(quickfacts) {
  const container = document.getElementById("dashboard");
  container.innerHTML = "";
  addDashboardCard(container, "Liberty Hill 2025 Population", formatInteger(quickfacts.population_2025), "QuickFacts contextual city estimate");
  addDashboardCard(container, "Growth Since 2020", formatPercent(quickfacts.growth_2020_2025_pct), `2020 Census base: ${formatInteger(quickfacts.population_2020)}`);
  addDashboardCard(container, "Under 18", formatPercent(quickfacts.under_18_pct), "Indicates pediatric and family care demand");
  addDashboardCard(container, "Uninsured Under 65", formatPercent(quickfacts.uninsured_under_65_pct), "Highlights healthcare access pressure");
  addDashboardCard(container, "Median Household Income", `$${formatInteger(quickfacts.median_household_income)}`, "City-level context only");
}

function registerLayer(name, layer) {
  layerRegistry[name] = layer;
}

function setLayerVisibility(map, layerName, visible) {
  const layer = layerRegistry[layerName];
  if (!layer) {
    return;
  }
  if (visible) {
    layer.addTo(map);
  } else if (map.hasLayer(layer)) {
    map.removeLayer(layer);
  }
}

function setHealthcareToggleState(enabled) {
  [
    "healthcare-all-toggle",
    "healthcare-primary-toggle",
    "healthcare-urgent-toggle",
    "healthcare-hospital-toggle",
    "healthcare-emergency-toggle",
    "healthcare-specialty-toggle",
    "healthcare-pharmacy-toggle",
  ].forEach((id) => {
    const toggle = document.getElementById(id);
    if (toggle) {
      toggle.disabled = !enabled;
    }
  });
}

function setHealthcareAccessibilityToggleState(enabled) {
  ["healthcare-accessibility-toggle", "healthcare-accessibility-select"].forEach((id) => {
    const control = document.getElementById(id);
    if (control) {
      control.disabled = !enabled;
    }
  });
}

function setRoadNetworkToggleState(enabled) {
  const toggle = document.getElementById("road-network-toggle");
  if (toggle) {
    toggle.disabled = !enabled;
  }
}

function syncHealthcareMasterToggleState() {
  const masterToggle = document.getElementById("healthcare-all-toggle");
  if (!masterToggle || masterToggle.disabled) {
    return;
  }
  const allChecked = HEALTHCARE_LAYER_NAMES.every((layerName) => {
    const toggle = document.querySelector(`[data-layer="${layerName}"]`);
    return toggle && toggle.checked;
  });
  masterToggle.checked = allChecked;
}

function getMetricColor(metricName, rawValue) {
  const metric = ACS_METRICS[metricName];
  const value = Number(rawValue);
  if (rawValue === null || rawValue === undefined || Number.isNaN(value)) {
    return "#d8d4ca";
  }
  for (let index = metric.bins.length - 1; index >= 0; index -= 1) {
    if (value >= metric.bins[index]) {
      return metric.colors[index];
    }
  }
  return metric.colors[0];
}

function getAccessibilityMetricColor(metricName, rawValue) {
  const metric = HEALTHCARE_ACCESSIBILITY_METRICS[metricName];
  const value = Number(rawValue);
  if (rawValue === null || rawValue === undefined || Number.isNaN(value)) {
    return "#d8d4ca";
  }
  for (let index = metric.bins.length - 1; index >= 0; index -= 1) {
    if (value >= metric.bins[index]) {
      return metric.colors[index];
    }
  }
  return metric.colors[0];
}

function buildLegendRows(metricName) {
  const metric = ACS_METRICS[metricName];
  return metric.bins
    .map((lowerBound, index) => {
      const upperBound = metric.bins[index + 1];
      const label = upperBound === undefined ? `${lowerBound}+${metric.valueSuffix}` : `${lowerBound}-${upperBound}${metric.valueSuffix}`;
      return `<div class="legend-row"><span class="legend-swatch" style="background:${metric.colors[index]}"></span><span>${label}</span></div>`;
    })
    .join("");
}

function renderAcsLegend(map) {
  if (acsLegendControl) {
    map.removeControl(acsLegendControl);
  }
  acsLegendControl = L.control({ position: "bottomright" });
  acsLegendControl.onAdd = () => {
    const container = L.DomUtil.create("div", "legend");
    container.innerHTML = `<div class="legend-title">${ACS_METRICS[currentAcsMetric].label}</div>${buildLegendRows(currentAcsMetric)}`;
    return container;
  };
  acsLegendControl.addTo(map);
}

function renderHealthcareAccessibilityLegend(map) {
  if (acsLegendControl) {
    map.removeControl(acsLegendControl);
  }
  acsLegendControl = L.control({ position: "bottomright" });
  acsLegendControl.onAdd = () => {
    const metric = HEALTHCARE_ACCESSIBILITY_METRICS[currentHealthcareAccessibilityMetric];
    const container = L.DomUtil.create("div", "legend");
    container.innerHTML = `<div class="legend-title">${metric.label}</div>${metric.bins
      .map((lowerBound, index) => {
        const upperBound = metric.bins[index + 1];
        const label = upperBound === undefined ? `${lowerBound}+${metric.valueSuffix}` : `${lowerBound}-${upperBound}${metric.valueSuffix}`;
        return `<div class="legend-row"><span class="legend-swatch" style="background:${metric.colors[index]}"></span><span>${label}</span></div>`;
      })
      .join("")}`;
    return container;
  };
  acsLegendControl.addTo(map);
}

function refreshThematicLegend(map) {
  const accessibilityToggle = document.getElementById("healthcare-accessibility-toggle");
  const acsToggle = document.getElementById("acs-layer-toggle");
  if (accessibilityToggle?.checked && healthcareAccessibilityLayer) {
    renderHealthcareAccessibilityLegend(map);
    return;
  }
  if (acsToggle?.checked && acsLayer) {
    renderAcsLegend(map);
    return;
  }
  if (acsLegendControl) {
    map.removeControl(acsLegendControl);
  }
}

function buildAcsPopup(properties) {
  return `
    <div>
      <strong>${properties.NAME ?? "ACS Block Group"}</strong><br>
      GEOID: ${properties.GEOID ?? "N/A"}<br>
      Population: ${formatNullableNumber(properties.population, formatInteger)} (MOE: ${formatNullableNumber(properties.population_moe, formatInteger)})<br>
      Population density: ${formatNullableNumber(properties.population_density, (value) => `${formatInteger(value)} people/sq mi`)}<br>
      Under 18 %: ${formatNullableNumber(properties.youth_population_pct, formatPercent)}<br>
      Age 65+ %: ${formatNullableNumber(properties.senior_population_pct, formatPercent)}<br>
      Uninsured %: ${formatNullableNumber(properties.uninsured_pct, formatPercent)} (Estimate MOE: ${formatNullableNumber(properties.uninsured_moe, formatInteger)})<br>
      Disability %: ${formatNullableNumber(properties.disability_pct, formatPercent)} (Estimate MOE: ${formatNullableNumber(properties.disability_moe, formatInteger)})<br>
      Poverty %: ${formatNullableNumber(properties.poverty_pct, formatPercent)} (Estimate MOE: ${formatNullableNumber(properties.poverty_moe, formatInteger)})<br>
      Median household income: ${formatNullableNumber(properties.median_household_income, (value) => `$${formatInteger(value)}`)}<br>
      No-vehicle households: ${formatNullableNumber(properties.no_vehicle_households, formatInteger)} (MOE: ${formatNullableNumber(properties.no_vehicle_households_moe, formatInteger)})<br>
      Healthcare need score: ${formatNullableNumber(properties.healthcare_need_score, (value) => value.toFixed(1))}
    </div>
  `;
}

function buildHealthcarePopup(properties) {
  const sourceLink = properties.source_url ? `<a href="${properties.source_url}" target="_blank" rel="noopener noreferrer">Official source</a>` : "N/A";
  const websiteLink = properties.website ? `<a href="${properties.website}" target="_blank" rel="noopener noreferrer">Website</a>` : "N/A";
  return `
    <div>
      <strong>${properties.facility_name ?? "Healthcare facility"}</strong><br>
      Facility type: ${properties.facility_type_label ?? properties.facility_type ?? "N/A"}<br>
      Address: ${properties.full_address ?? "N/A"}<br>
      Organization: ${properties.organization ?? "N/A"}<br>
      Services: ${properties.services ?? "N/A"}<br>
      Straight-line distance from proposed clinic: ${formatNullableNumber(properties.distance_from_proposed_site_miles, (value) => `${value.toFixed(2)} miles`)}<br>
      Drive time: ${formatNullableNumber(properties.drive_time_minutes, (value) => `${value.toFixed(1)} minutes`)}<br>
      Current status: ${properties.current_status ?? "N/A"}<br>
      Verification date: ${properties.verification_date ?? "N/A"}<br>
      Source: ${sourceLink}<br>
      Website: ${websiteLink}
    </div>
  `;
}

function buildHealthcareAccessibilityPopup(properties) {
  return `
    <div>
      <strong>${properties.NAME ?? "ACS Block Group"}</strong><br>
      Healthcare access measure: ${properties.healthcare_access_measure ?? "N/A"}<br>
      Access distance band: ${properties.healthcare_access_distance_band ?? "N/A"}<br>
      Nearest urgent care: ${formatNullableNumber(properties.nearest_urgent_care_miles, (value) => `${value.toFixed(2)} miles`)}<br>
      Nearest hospital: ${formatNullableNumber(properties.nearest_hospital_miles, (value) => `${value.toFixed(2)} miles`)}<br>
      Healthcare need score: ${formatNullableNumber(properties.healthcare_need_score, (value) => value.toFixed(1))}
    </div>
  `;
}

function buildRoadPopup(properties) {
  return `
    <div>
      <strong>${properties.road_name ?? "Road segment"}</strong><br>
      Road class: ${properties.road_class ?? "N/A"}<br>
      Route type: ${properties.route_type ?? "N/A"}<br>
      Major corridor: ${properties.is_major_corridor ? "Yes" : "No"}<br>
      Segment length: ${formatNullableNumber(properties.segment_length_miles, (value) => `${value.toFixed(2)} miles`)}<br>
      Source: TIGER/Line 2024 Williamson County roads
    </div>
  `;
}

function styleAcsFeature(feature) {
  return {
    color: "#5e6776",
    weight: 1,
    opacity: 0.75,
    fillOpacity: 0.72,
    fillColor: getMetricColor(currentAcsMetric, feature.properties[currentAcsMetric]),
  };
}

function refreshAcsStyles(map) {
  if (!acsLayer) {
    return;
  }
  acsLayer.setStyle((feature) => styleAcsFeature(feature));
  refreshThematicLegend(map);
}

function styleHealthcareAccessibilityFeature(feature) {
  return {
    color: "#5e6776",
    weight: 1,
    opacity: 0.75,
    fillOpacity: 0.72,
    fillColor: getAccessibilityMetricColor(currentHealthcareAccessibilityMetric, feature.properties[currentHealthcareAccessibilityMetric]),
  };
}

function refreshHealthcareAccessibilityStyles(map) {
  if (!healthcareAccessibilityLayer) {
    return;
  }
  healthcareAccessibilityLayer.setStyle((feature) => styleHealthcareAccessibilityFeature(feature));
  refreshThematicLegend(map);
}

function styleRoadFeature(feature) {
  const isMajorCorridor = Boolean(feature.properties.is_major_corridor);
  return {
    color: isMajorCorridor ? "#8e3d06" : "#596275",
    weight: isMajorCorridor ? 3.2 : 1.5,
    opacity: isMajorCorridor ? 0.95 : 0.6,
  };
}

function summarizeHealthcareFacilities(features) {
  const total = features.length;
  const withinFiveMiles = features.filter((feature) => Number(feature.properties.distance_from_proposed_site_miles) <= 5).length;
  const countsByType = Object.keys(HEALTHCARE_TYPES).reduce((accumulator, key) => {
    accumulator[key] = 0;
    return accumulator;
  }, {});
  features.forEach((feature) => {
    const type = feature.properties.facility_type;
    if (countsByType[type] !== undefined) {
      countsByType[type] += 1;
    }
  });
  return { total, withinFiveMiles, countsByType };
}

async function loadHealthcareLayers(map, layerConfig) {
  const statusElement = document.getElementById("healthcare-status");
  setHealthcareToggleState(false);

  HEALTHCARE_LAYER_NAMES.forEach((layerName) => {
    const layerGroup = L.layerGroup();
    healthcareTypeLayers[layerName] = layerGroup;
    registerLayer(layerName, layerGroup);
  });

  if (!layerConfig?.available) {
    if (statusElement) {
      statusElement.textContent = "Awaiting verified healthcare facility inventory.";
    }
    return;
  }

  const response = await fetch(layerConfig.endpoint);
  if (!response.ok) {
    throw new Error("Healthcare facility layer could not be loaded");
  }

  const geojson = await response.json();
  const features = geojson.features ?? [];
  features.forEach((feature) => {
    const typeConfig = HEALTHCARE_TYPES[feature.properties.facility_type];
    if (!typeConfig) {
      return;
    }
    const marker = L.circleMarker([feature.geometry.coordinates[1], feature.geometry.coordinates[0]], {
      radius: 6,
      color: "#ffffff",
      weight: 1,
      fillOpacity: 0.9,
      fillColor: typeConfig.color,
    }).bindPopup(buildHealthcarePopup(feature.properties));
    healthcareTypeLayers[typeConfig.layerName].addLayer(marker);
  });

  setHealthcareToggleState(true);
  const summary = summarizeHealthcareFacilities(features);
  if (statusElement) {
    statusElement.textContent = `Loaded ${summary.total} healthcare facilities; ${summary.withinFiveMiles} are within 5 straight-line miles of the proposed site.`;
  }
  upsertDashboardCard("healthcare-facilities-card", "Healthcare Facilities", formatInteger(summary.total), `${formatInteger(summary.withinFiveMiles)} within 5 straight-line miles`);
}

function summarizeHealthcareAccessibility(features) {
  const distances = features
    .map((feature) => Number(feature.properties.nearest_any_medical_miles))
    .filter((value) => !Number.isNaN(value));
  const averageDistance = distances.length ? distances.reduce((sum, value) => sum + value, 0) / distances.length : null;
  const fartherThanFiveMiles = distances.filter((value) => value > 5).length;
  return { averageDistance, fartherThanFiveMiles, total: features.length };
}

async function loadHealthcareAccessibilityLayer(map, layerConfig) {
  const statusElement = document.getElementById("healthcare-accessibility-status");
  const toggle = document.getElementById("healthcare-accessibility-toggle");
  const metricSelect = document.getElementById("healthcare-accessibility-select");
  setHealthcareAccessibilityToggleState(false);

  if (!layerConfig?.available) {
    if (statusElement) {
      statusElement.textContent = "Awaiting healthcare accessibility output.";
    }
    return;
  }

  const response = await fetch(layerConfig.endpoint);
  if (!response.ok) {
    throw new Error("Healthcare accessibility layer could not be loaded");
  }

  const geojson = await response.json();
  healthcareAccessibilityLayer = L.geoJSON(geojson, {
    style: styleHealthcareAccessibilityFeature,
    onEachFeature: (feature, layer) => {
      layer.bindPopup(buildHealthcareAccessibilityPopup(feature.properties));
      layer.on({
        mouseover: () => layer.setStyle({ weight: 2, color: "#14213d" }),
        mouseout: () => refreshHealthcareAccessibilityStyles(map),
      });
    },
  });

  registerLayer("healthcare-accessibility", healthcareAccessibilityLayer);
  setHealthcareAccessibilityToggleState(true);
  if (statusElement) {
    statusElement.textContent = `Loaded ${geojson.features.length} healthcare accessibility block groups.`;
  }
  const summary = summarizeHealthcareAccessibility(geojson.features ?? []);
  upsertDashboardCard(
    "healthcare-access-card",
    "Healthcare Access",
    summary.averageDistance === null ? "N/A" : `${summary.averageDistance.toFixed(2)} mi`,
    `${formatInteger(summary.fartherThanFiveMiles)} block groups are more than 5 miles from the nearest medical facility`
  );
  metricSelect.addEventListener("change", (event) => {
    currentHealthcareAccessibilityMetric = event.target.value;
    refreshHealthcareAccessibilityStyles(map);
  });
  if (toggle.checked) {
    healthcareAccessibilityLayer.addTo(map);
    refreshThematicLegend(map);
  }
}

function summarizeRoadNetwork(features) {
  const majorSegments = features.filter((feature) => Boolean(feature.properties.is_major_corridor)).length;
  const totalMiles = features.reduce((sum, feature) => sum + (Number(feature.properties.segment_length_miles) || 0), 0);
  const majorMiles = features.reduce(
    (sum, feature) => sum + (Boolean(feature.properties.is_major_corridor) ? Number(feature.properties.segment_length_miles) || 0 : 0),
    0
  );
  return { totalSegments: features.length, majorSegments, totalMiles, majorMiles };
}

async function loadRoadNetworkLayer(map, layerConfig) {
  const statusElement = document.getElementById("road-network-status");
  const toggle = document.getElementById("road-network-toggle");
  setRoadNetworkToggleState(false);

  if (!layerConfig?.available) {
    if (statusElement) {
      statusElement.textContent = "Awaiting transportation network output.";
    }
    return;
  }

  const response = await fetch(layerConfig.endpoint);
  if (!response.ok) {
    throw new Error("Road network layer could not be loaded");
  }

  const geojson = await response.json();
  roadNetworkLayer = L.geoJSON(geojson, {
    style: styleRoadFeature,
    onEachFeature: (feature, layer) => {
      layer.bindPopup(buildRoadPopup(feature.properties));
      layer.on({
        mouseover: () => layer.setStyle({ weight: 4, opacity: 1 }),
        mouseout: () => roadNetworkLayer.resetStyle(layer),
      });
    },
  });

  registerLayer("road-network", roadNetworkLayer);
  setRoadNetworkToggleState(true);
  const summary = summarizeRoadNetwork(geojson.features ?? []);
  if (statusElement) {
    statusElement.textContent = `Loaded ${formatInteger(summary.totalSegments)} road segments, including ${formatInteger(summary.majorSegments)} major-corridor segments.`;
  }
  upsertDashboardCard(
    "road-network-card",
    "Transportation Network",
    `${summary.totalMiles.toFixed(1)} mi`,
    `${summary.majorMiles.toFixed(1)} miles are classified as major corridors`
  );
  if (toggle.checked) {
    roadNetworkLayer.addTo(map);
  }
}

async function loadAcsLayer(map, layerConfig) {
  const statusElement = document.getElementById("acs-status");
  const toggle = document.getElementById("acs-layer-toggle");
  const metricSelect = document.getElementById("acs-metric-select");
  if (!layerConfig?.available) {
    toggle.disabled = true;
    metricSelect.disabled = true;
    if (statusElement) {
      statusElement.textContent = "Awaiting ACS download and processing.";
    }
    return;
  }

  const response = await fetch(layerConfig.endpoint);
  if (!response.ok) {
    throw new Error("ACS block-group layer could not be loaded");
  }

  const acsGeoJson = await response.json();
  acsLayer = L.geoJSON(acsGeoJson, {
    style: styleAcsFeature,
    onEachFeature: (feature, layer) => {
      layer.bindPopup(buildAcsPopup(feature.properties));
      layer.on({
        mouseover: () => layer.setStyle({ weight: 2, color: "#14213d" }),
        mouseout: () => refreshAcsStyles(map),
      });
    },
  });

  registerLayer("acs-block-groups", acsLayer);
  toggle.disabled = false;
  metricSelect.disabled = false;
  if (statusElement) {
    statusElement.textContent = `Loaded ${acsGeoJson.features.length} ACS block groups for the Liberty Hill study area.`;
  }
  metricSelect.addEventListener("change", (event) => {
    currentAcsMetric = event.target.value;
    refreshAcsStyles(map);
  });
  if (toggle.checked) {
    acsLayer.addTo(map);
    refreshThematicLegend(map);
  }
}

function syncLayerToggles(map) {
  document.querySelectorAll("[data-layer]").forEach((input) => {
    input.addEventListener("change", (event) => {
      const { layer } = event.target.dataset;
      if (layer === "healthcare-all") {
        HEALTHCARE_LAYER_NAMES.forEach((layerName) => {
          const toggle = document.querySelector(`[data-layer="${layerName}"]`);
          if (toggle && !toggle.disabled) {
            toggle.checked = event.target.checked;
            setLayerVisibility(map, layerName, event.target.checked);
          }
        });
        syncHealthcareMasterToggleState();
        return;
      }

      const mapLayer = layerRegistry[layer];
      if (!mapLayer) {
        return;
      }

      if (event.target.checked) {
        mapLayer.addTo(map);
        if (layer === "acs-block-groups" || layer === "healthcare-accessibility") {
          refreshThematicLegend(map);
        }
      } else {
        map.removeLayer(mapLayer);
        if (layer === "acs-block-groups" || layer === "healthcare-accessibility") {
          refreshThematicLegend(map);
        }
      }

      if (HEALTHCARE_LAYER_NAMES.includes(layer)) {
        syncHealthcareMasterToggleState();
      }
    });
  });
}

function buildMap(studyConfig) {
  const map = L.map("map", { zoomControl: true, minZoom: 9 }).setView([studyConfig.latitude, studyConfig.longitude], studyConfig.default_zoom);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  const proposedClinic = L.marker([studyConfig.latitude, studyConfig.longitude]).bindPopup(`
    <strong>Proposed Medical Clinic Study Location</strong><br>
    SH 29 / 183A intersection area<br>
    Population, healthcare, utilities, and suitability metrics will populate as datasets are processed.
  `);
  const fiveMileCircle = L.circle([studyConfig.latitude, studyConfig.longitude], {
    radius: milesToMeters(studyConfig.five_mile_radius_miles),
    color: "#bb4d00",
    weight: 2,
    fillColor: "#e3a06c",
    fillOpacity: 0.14,
  }).bindPopup("5-mile study area");
  const tenMileCircle = L.circle([studyConfig.latitude, studyConfig.longitude], {
    radius: milesToMeters(studyConfig.ten_mile_radius_miles),
    color: "#14213d",
    weight: 2,
    dashArray: "8 8",
    fillColor: "#4c678f",
    fillOpacity: 0.08,
  }).bindPopup("10-mile study area");

  registerLayer("study-location", proposedClinic.addTo(map));
  registerLayer("study-5", fiveMileCircle.addTo(map));
  registerLayer("study-10", tenMileCircle.addTo(map));
  L.control.scale({ imperial: true, metric: true }).addTo(map);
  syncLayerToggles(map);
  return map;
}

async function bootstrapApp() {
  const response = await fetch("/api/bootstrap");
  if (!response.ok) {
    throw new Error("Failed to load application bootstrap data");
  }

  const payload = await response.json();
  buildDashboard(payload.quickfacts);
  const map = buildMap(payload.study_config);
  await loadRoadNetworkLayer(map, payload.layers?.road_network);
  await loadHealthcareLayers(map, payload.layers?.healthcare_facilities);
  await loadAcsLayer(map, payload.layers?.acs_block_groups);
  await loadHealthcareAccessibilityLayer(map, payload.layers?.healthcare_accessibility);
}

bootstrapApp().catch((error) => {
  console.error(error);
  const container = document.getElementById("dashboard");
  container.innerHTML = `<article class="dashboard-card"><div class="metric-label">Application error</div><div class="metric-subtitle">${error.message}</div></article>`;
});