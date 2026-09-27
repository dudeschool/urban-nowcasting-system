/**
 * Map Visualization Engine using Leaflet.js
 * Handles multi-layer geospatial visualization:
 * - Doppler Radar reflectivity (dBZ)
 * - 2D Surface Inundation depths (cm)
 * - 1D Drainage network with surcharge backflow pulsing markers
 * - Street risk level polylines
 * - Flood-Safe Dynamic navigation paths
 */

let map = null;
const layers = {
  radar: L.layerGroup(),
  flood: L.layerGroup(),
  drainage: L.layerGroup(),
  surcharge: L.layerGroup(),
  roads: L.layerGroup(),
  route: L.layerGroup()
};

function initMap(center = [28.4595, 77.0266], zoom = 13.5) {
  map = L.map('map', {
    center: center,
    zoom: zoom,
    zoomControl: false,
    attributionControl: false
  });

  // Position zoom controls top-left
  L.control.zoom({ position: 'topleft' }).addTo(map);

  // Google Maps Standard API Basemap
  L.tileLayer('https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {
    maxZoom: 20,
    attribution: '&copy; Google Maps'
  }).addTo(map);

  // Add layer groups to map
  Object.values(layers).forEach(layer => layer.addTo(map));

  return map;
}

// Radar dBZ Color Gradient
function getDbzColor(dbz) {
  if (dbz >= 55) return '#a855f7'; // Purple / Violent cloudburst
  if (dbz >= 48) return '#ef4444'; // Red / Extreme convective
  if (dbz >= 40) return '#f97316'; // Orange / Heavy
  if (dbz >= 32) return '#eab308'; // Yellow / Moderate
  if (dbz >= 24) return '#22c55e'; // Light green / Light rain
  return '#3b82f6';
}

// Flood Depth Color
function getFloodDepthColor(depthCm) {
  if (depthCm >= 45) return '#ec4899'; // Critical / Submerged
  if (depthCm >= 25) return '#ef4444'; // Severe
  if (depthCm >= 10) return '#f59e0b'; // Moderate
  return '#10b981'; // Safe
}

// Pipe Capacity Color
function getPipeColor(utilizationPct) {
  if (utilizationPct >= 100) return '#f43f5e'; // Choked / Surcharging
  if (utilizationPct >= 75) return '#f59e0b'; // Near capacity
  return '#06b6d4'; // Normal gravity flow
}

function renderRadarPoints(points) {
  layers.radar.clearLayers();
  if (!points) return;

  points.forEach(pt => {
    const [lat, lon, dbz, rainRate] = pt;
    const circle = L.circle([lat, lon], {
      radius: 95,
      fillColor: getDbzColor(dbz),
      fillOpacity: 0.38,
      stroke: false
    });
    circle.bindTooltip(`Radar: ${dbz} dBZ | Rain: ${rainRate} mm/h`, { sticky: true });
    layers.radar.addLayer(circle);
  });
}

function renderInundationPolygons(polygons) {
  layers.flood.clearLayers();
  if (!polygons) return;

  polygons.forEach(poly => {
    const rect = L.rectangle(poly.bounds, {
      fillColor: getFloodDepthColor(poly.depth_cm),
      fillOpacity: poly.depth_cm >= 40 ? 0.65 : 0.42,
      weight: 1,
      color: getFloodDepthColor(poly.depth_cm),
      opacity: 0.5
    });
    rect.bindTooltip(`Surface Water: ${poly.depth_cm} cm (${poly.category})`, { sticky: true });
    layers.flood.addLayer(rect);
  });
}

function renderDrainageNetwork(drainageData, onPipeClick) {
  layers.drainage.clearLayers();
  layers.surcharge.clearLayers();
  if (!drainageData) return;

  const nodeMap = {};
  // Nodes (Manholes & Outfalls)
  drainageData.nodes.forEach(node => {
    nodeMap[node.id] = node;

    if (node.is_outfall) {
      // Outfall marker
      const outfallMarker = L.circleMarker([node.lat, node.lon], {
        radius: 8,
        fillColor: '#3b82f6',
        color: '#fff',
        weight: 2,
        fillOpacity: 0.9
      });
      outfallMarker.bindPopup(`<b>${node.name}</b><br>Major Storm Discharge Outfall<br>Inflow: ${node.inflow_m3s} m³/s`);
      layers.drainage.addLayer(outfallMarker);
    } else if (node.is_surcharging) {
      // Surcharging Manhole with pulsating ring!
      const iconHtml = `<div class="pulse-marker-ring"></div>`;
      const customIcon = L.divIcon({
        html: iconHtml,
        className: 'surcharge-icon-wrap',
        iconSize: [24, 24],
        iconAnchor: [12, 12]
      });
      const surMarker = L.marker([node.lat, node.lon], { icon: customIcon });
      surMarker.bindPopup(`
        <div style="font-family: sans-serif; color: #1e293b;">
          <h4 style="color: #e11d48; margin: 0 0 4px 0;">SURCHARGE ERUPTION</h4>
          <strong>${node.name} (${node.id})</strong><br>
          Overflow Backflow Rate: <b style="color: #e11d48;">${Math.round(node.surcharge_m3s * 1000)} L/s</b><br>
          <small>HGL exceeds ground elevation; stormwater erupting onto street surface!</small>
        </div>
      `);
      layers.surcharge.addLayer(surMarker);
    } else {
      // Normal manhole
      const mhMarker = L.circleMarker([node.lat, node.lon], {
        radius: 4.5,
        fillColor: node.inferred ? '#06b6d4' : '#64748b',
        color: '#fff',
        weight: 1,
        fillOpacity: 0.8
      });
      mhMarker.bindTooltip(`${node.name} ${node.inferred ? '(Inferred)' : ''}`);
      layers.drainage.addLayer(mhMarker);
    }
  });

  // Conduits / Pipes
  drainageData.pipes.forEach(pipe => {
    const u = nodeMap[pipe.from];
    const v = nodeMap[pipe.to];
    if (!u || !v) return;

    const latlngs = [[u.lat, u.lon], [v.lat, v.lon]];
    const color = getPipeColor(pipe.utilization_pct);

    const polyline = L.polyline(latlngs, {
      color: color,
      weight: pipe.utilization_pct >= 100 ? 5 : 3.5,
      dashArray: pipe.inferred ? '5, 5' : null,
      opacity: 0.85
    });

    polyline.bindTooltip(`Pipe ${pipe.id}: Ø${pipe.diam_mm}mm | Flow: ${pipe.flow_m3s}/${pipe.capacity_m3s} m³/s (${pipe.utilization_pct}%)`);
    polyline.on('click', () => {
      if (onPipeClick) onPipeClick(pipe);
    });

    layers.drainage.addLayer(polyline);
  });
}

function renderRoads(roadsData, onRoadClick) {
  layers.roads.clearLayers();
  if (!roadsData) return;

  roadsData.forEach(road => {
    const color = getFloodDepthColor(road.max_depth_cm);
    const polyline = L.polyline(road.path, {
      color: color,
      weight: road.max_depth_cm >= 25 ? 6 : 4,
      opacity: 0.9
    });

    polyline.bindTooltip(`<b>${road.name}</b><br>Water Depth: ${road.max_depth_cm} cm (${road.risk_level})`);
    polyline.on('click', () => {
      if (onRoadClick) onRoadClick(road);
    });

    layers.roads.addLayer(polyline);
  });
}

function renderRoutePaths(routeResult) {
  layers.route.clearLayers();
  if (!routeResult) return;

  const { commuter, emergency, baseline_dry } = routeResult;

  // Render baseline path (dashed gray)
  if (baseline_dry && baseline_dry.success) {
    const baseLine = L.polyline(baseline_dry.path_coords, {
      color: '#94a3b8',
      weight: 3,
      dashArray: '4, 6',
      opacity: 0.6
    });
    baseLine.bindTooltip(`Baseline Dry Weather Route (${baseline_dry.estimated_time_min} min)`);
    layers.route.addLayer(baseLine);
  }

  // Render safe commuter or emergency path
  const activeRoute = emergency.success ? emergency : commuter;
  if (activeRoute && activeRoute.success) {
    const isEmerg = activeRoute.mode === 'emergency';
    const routeLine = L.polyline(activeRoute.path_coords, {
      color: isEmerg ? '#38bdf8' : '#eab308',
      weight: 7,
      opacity: 0.95
    });
    routeLine.bindTooltip(`<b>${activeRoute.vehicle_name} Route</b><br>ETA: ${activeRoute.estimated_time_min} min | Max Water: ${activeRoute.max_depth_encountered_cm} cm`);
    layers.route.addLayer(routeLine);

    // Start & End markers
    const startCoord = activeRoute.path_coords[0];
    const endCoord = activeRoute.path_coords[activeRoute.path_coords.length - 1];

    const startMarker = L.circleMarker(startCoord, {
      radius: 9,
      fillColor: '#10b981',
      color: '#fff',
      weight: 2,
      fillOpacity: 1
    }).bindTooltip(`Start: ${activeRoute.start_name}`);

    const endMarker = L.circleMarker(endCoord, {
      radius: 9,
      fillColor: '#ef4444',
      color: '#fff',
      weight: 2,
      fillOpacity: 1
    }).bindTooltip(`Destination: ${activeRoute.end_name}`);

    layers.route.addLayer(startMarker);
    layers.route.addLayer(endMarker);

    // Fit map to show route
    map.fitBounds(routeLine.getBounds(), { padding: [50, 50] });
  }
}

function clearRoutePaths() {
  layers.route.clearLayers();
}

function toggleMapLayer(layerName, isVisible) {
  if (!layers[layerName]) return;
  if (isVisible) {
    if (!map.hasLayer(layers[layerName])) {
      map.addLayer(layers[layerName]);
    }
  } else {
    if (map.hasLayer(layers[layerName])) {
      map.removeLayer(layers[layerName]);
    }
  }
}

window.MapEngine = {
  initMap,
  renderRadarPoints,
  renderInundationPolygons,
  renderDrainageNetwork,
  renderRoads,
  renderRoutePaths,
  clearRoutePaths,
  toggleMapLayer
};
