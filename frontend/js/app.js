/**
 * Main Application Orchestrator
 * Coordinates state, timeline playback, Chart.js telemetry, map updates, and UI interactions.
 */

let nowcastData = null;
let currentTimestepIndex = 2; // Default to T+30 or T+45 min
let timestepsList = [0, 15, 30, 45, 60, 90, 120, 180];
let isPlaying = false;
let playInterval = null;

let hyetographChart = null;
let modalChart = null;
let drainEditorHandle = null;

document.addEventListener('DOMContentLoaded', async () => {
  // 1. Initialize Map
  window.MapEngine.initMap();

  // 2. Initialize Tab Switching
  setupTabs();

  // 3. Setup Layer Toggles
  setupLayerToggles();

  // 4. Setup Modal Close
  setupModal();

  // 5. Fetch Ward & Initial Nowcast Data
  await loadNowcastData();

  // 6. Setup Secondary Modules
  drainEditorHandle = window.DrainEditor.setupDrainEditor(onCalibrationUpdated);
  window.RoutingEngine.setupRouting(() => timestepsList[currentTimestepIndex]);
  window.BacktestEngine.setupBacktest();

  // 7. Setup Playback & Scrubber Controls
  setupPlaybackControls();

  // 8. Setup Scenario Trigger
  setupScenarioTrigger();
});

function setupTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn, .sidebar-nav-btn');
  const tabContents = document.querySelectorAll('.tab-content');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-tab');
      tabBtns.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const targetContent = document.getElementById(`tab-${target}`);
      if (targetContent) targetContent.classList.add('active');

      // Clear route if navigating away from routing tab
      if (target !== 'routing') {
        window.MapEngine.clearRoutePaths();
      }
    });
  });
}

function setupLayerToggles() {
  const toggles = [
    { id: 'layerRadar', layer: 'radar' },
    { id: 'layerFlood', layer: 'flood' },
    { id: 'layerDrainage', layer: 'drainage' },
    { id: 'layerSurcharge', layer: 'surcharge' },
    { id: 'layerRoads', layer: 'roads' }
  ];

  toggles.forEach(t => {
    const el = document.getElementById(t.id);
    if (el) {
      el.addEventListener('change', (e) => {
        window.MapEngine.toggleMapLayer(t.layer, e.target.checked);
      });
    }
  });
}

async function loadNowcastData() {
  try {
    const resp = await fetch('/api/nowcast');
    if (!resp.ok) throw new Error('Failed to load nowcast data');
    nowcastData = await resp.json();
    timestepsList = nowcastData.timesteps;

    buildStepButtons();
    renderCurrentTimestep();
    initHyetographChart();

  } catch (err) {
    console.error('Error fetching nowcast:', err);
  }
}

function onCalibrationUpdated(newNowcast) {
  nowcastData = newNowcast;
  timestepsList = nowcastData.timesteps;
  renderCurrentTimestep();
  initHyetographChart();
}

function buildStepButtons() {
  const container = document.getElementById('stepButtonsContainer');
  container.innerHTML = '';

  timestepsList.forEach((t, idx) => {
    const btn = document.createElement('button');
    btn.className = `step-btn ${idx === currentTimestepIndex ? 'active' : ''}`;
    btn.innerText = `T+${t}`;
    btn.addEventListener('click', () => {
      currentTimestepIndex = idx;
      updateStepButtonsUI();
      renderCurrentTimestep();
    });
    container.appendChild(btn);
  });
}

function updateStepButtonsUI() {
  const buttons = document.querySelectorAll('.step-btn');
  buttons.forEach((b, idx) => {
    if (idx === currentTimestepIndex) {
      b.classList.add('active');
    } else {
      b.classList.remove('active');
    }
  });
}

function renderCurrentTimestep() {
  if (!nowcastData || !nowcastData.results) return;

  const tKey = String(timestepsList[currentTimestepIndex]);
  const step = nowcastData.results[tKey];
  if (!step) return;

  // 1. Update Map Layers
  window.MapEngine.renderRadarPoints(step.radar_points);
  window.MapEngine.renderInundationPolygons(step.inundation_polygons);
  window.MapEngine.renderDrainageNetwork(step.drainage, onPipeMapClicked);
  window.MapEngine.renderRoads(step.roads, onRoadMapClicked);

  // 2. Update Timeline Meta
  document.getElementById('leadTimeDisplay').innerText = `T+${step.timestep_min} min`;
  const confPct = Math.round(step.confidence_score * 100);
  document.getElementById('confidenceDisplay').innerText = `${confPct}%`;
  document.getElementById('confidenceFill').style.width = `${confPct}%`;

  // 3. Update Quick Telemetry
  document.getElementById('telemFloodedRoads').innerText = `${step.summary.total_roads_flooded} / ${step.roads.length}`;
  document.getElementById('telemSurchargeRate').innerText = `${step.summary.total_surcharge_lps} L/s`;
  document.getElementById('telemMaxDepth').innerText = `${step.summary.max_inundation_depth_cm} cm`;

  // 4. Update Panel Metrics
  document.getElementById('metricPeakRain').innerHTML = `${step.peak_rain_rate_mmh} <small>mm/h</small>`;
  document.getElementById('metricChokepoints').innerHTML = `${step.summary.severely_flooded_roads} <small>streets</small>`;
  document.getElementById('metricSurchargeNodes').innerHTML = `${step.summary.surcharging_manholes} <small>manholes</small>`;
  document.getElementById('metricPopulation').innerText = step.summary.estimated_population_impacted.toLocaleString();

  // 5. Update Vulnerable Roads List in Tab
  updateVulnerableRoadsList(step.roads);
}

function updateVulnerableRoadsList(roads) {
  const listEl = document.getElementById('vulnerableRoadsList');
  const countEl = document.getElementById('vulnerableCount');
  listEl.innerHTML = '';

  const alertRoads = roads.filter(r => r.max_depth_cm >= 8.0).sort((a, b) => b.max_depth_cm - a.max_depth_cm);
  countEl.innerText = `${alertRoads.length} Alerting`;

  if (alertRoads.length === 0) {
    listEl.innerHTML = `<p style="font-size: 0.76rem; color: #10b981; padding: 10px;">All street segments clear and within safe flow limits.</p>`;
    return;
  }

  alertRoads.forEach(r => {
    const item = document.createElement('div');
    const riskClass = r.max_depth_cm >= 45 ? 'risk-critical' : (r.max_depth_cm >= 25 ? 'risk-severe' : 'risk-moderate');
    item.className = `vulnerable-item ${riskClass}`;

    item.innerHTML = `
      <div>
        <div class="v-item-name">${r.name}</div>
        <div class="v-item-sub">TTF: ${r.time_to_flood_min}m | ${r.risk_level}</div>
      </div>
      <div class="v-item-stats">
        <div class="v-depth">${r.max_depth_cm} cm</div>
        <div class="v-ttf">${r.is_passable_ambulance ? 'Ambulance Passable' : 'ALL BLOCKED'}</div>
      </div>
    `;

    item.addEventListener('click', () => onRoadMapClicked(r));
    listEl.appendChild(item);
  });
}

function setupPlaybackControls() {
  const playBtn = document.getElementById('playBtn');
  const playIcon = document.getElementById('playIcon');
  const resetBtn = document.getElementById('resetTimeBtn');

  playBtn.addEventListener('click', () => {
    isPlaying = !isPlaying;
    if (isPlaying) {
      playBtn.style.background = '#ef4444';
      playIcon.setAttribute('data-lucide', 'pause');
      playInterval = setInterval(() => {
        currentTimestepIndex = (currentTimestepIndex + 1) % timestepsList.length;
        updateStepButtonsUI();
        renderCurrentTimestep();
      }, 1900);
    } else {
      playBtn.style.background = '';
      playIcon.setAttribute('data-lucide', 'play');
      clearInterval(playInterval);
    }
    lucide.createIcons();
  });

  resetBtn.addEventListener('click', () => {
    currentTimestepIndex = 0;
    updateStepButtonsUI();
    renderCurrentTimestep();
  });
}

function setupScenarioTrigger() {
  const select = document.getElementById('scenarioSelect');
  const triggerBtn = document.getElementById('triggerNowcastBtn');

  triggerBtn.addEventListener('click', async () => {
    const scenario = select.value;
    triggerBtn.disabled = true;
    triggerBtn.innerHTML = `<i data-lucide="loader" class="spin"></i> Running Loop...`;

    try {
      const resp = await fetch('/api/nowcast/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_id: scenario })
      });

      if (!resp.ok) throw new Error('Simulation failed');
      const data = await resp.json();
      nowcastData = data.data;
      timestepsList = nowcastData.timesteps;

      currentTimestepIndex = 2;
      buildStepButtons();
      renderCurrentTimestep();
      initHyetographChart();

      if (drainEditorHandle) drainEditorHandle.reloadNetwork();

      alert(`Nowcast re-executed for scenario: ${scenario}`);

    } catch (err) {
      console.error(err);
      alert('Error triggering nowcast: ' + err.message);
    } finally {
      triggerBtn.disabled = false;
      triggerBtn.innerHTML = `<i data-lucide="refresh-cw"></i> Run Nowcast`;
      lucide.createIcons();
    }
  });
}

function initHyetographChart() {
  const ctx = document.getElementById('hyetographChart');
  if (!ctx || !nowcastData) return;

  const labels = timestepsList.map(t => `T+${t}m`);
  const rainRates = timestepsList.map(t => nowcastData.results[String(t)].peak_rain_rate_mmh);
  const maxDepths = timestepsList.map(t => nowcastData.results[String(t)].summary.max_inundation_depth_cm);

  if (hyetographChart) {
    hyetographChart.destroy();
  }

  hyetographChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          type: 'bar',
          label: 'Peak Rain (mm/h)',
          data: rainRates,
          backgroundColor: 'rgba(6, 182, 212, 0.45)',
          borderColor: '#06b6d4',
          borderWidth: 1.5,
          yAxisID: 'yRain'
        },
        {
          type: 'line',
          label: 'Max Depth (cm)',
          data: maxDepths,
          borderColor: '#ef4444',
          backgroundColor: 'rgba(239, 68, 68, 0.15)',
          borderWidth: 2.5,
          pointRadius: 3,
          tension: 0.35,
          yAxisID: 'yDepth'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: { color: '#94a3b8', font: { size: 10 } }
        }
      },
      scales: {
        x: {
          ticks: { color: '#64748b', font: { size: 9 } },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        },
        yRain: {
          type: 'linear',
          position: 'left',
          title: { display: true, text: 'Rain (mm/h)', color: '#06b6d4', font: { size: 9 } },
          ticks: { color: '#64748b', font: { size: 9 } },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        },
        yDepth: {
          type: 'linear',
          position: 'right',
          title: { display: true, text: 'Depth (cm)', color: '#ef4444', font: { size: 9 } },
          ticks: { color: '#64748b', font: { size: 9 } },
          grid: { drawOnChartArea: false }
        }
      }
    }
  });
}

function onRoadMapClicked(road) {
  const modal = document.getElementById('inspectorModal');
  const title = document.getElementById('modalTitle');
  const metaGrid = document.getElementById('modalMetaGrid');

  title.innerText = road.name;
  metaGrid.innerHTML = `
    <div class="modal-meta-box">
      <span>Road Classification</span>
      <strong>${road.type.toUpperCase()}</strong>
    </div>
    <div class="modal-meta-box">
      <span>Current Inundation</span>
      <strong style="color: #f87171;">${road.max_depth_cm} cm</strong>
    </div>
    <div class="modal-meta-box">
      <span>Civilian Passable (&lt;15cm)</span>
      <strong>${road.is_passable_car ? 'PASSABLE' : 'BLOCKED'}</strong>
    </div>
    <div class="modal-meta-box">
      <span>Ambulance Passable (&lt;35cm)</span>
      <strong>${road.is_passable_ambulance ? 'PASSABLE' : 'BLOCKED'}</strong>
    </div>
  `;

  // Plot Depth profile for this road across all timesteps
  const depthsSeries = timestepsList.map(t => {
    const stepRoads = nowcastData.results[String(t)].roads;
    const match = stepRoads.find(r => r.id === road.id);
    return match ? match.max_depth_cm : 0.0;
  });

  renderModalChart(depthsSeries, 'Street Inundation Depth (cm)', '#ef4444');
  modal.style.display = 'flex';
}

function onPipeMapClicked(pipe) {
  if (drainEditorHandle) {
    drainEditorHandle.selectPipeFromMap(pipe);
  }
}

function renderModalChart(dataSeries, labelText, color) {
  const ctx = document.getElementById('modalChart');
  if (modalChart) modalChart.destroy();

  modalChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: timestepsList.map(t => `T+${t}m`),
      datasets: [{
        label: labelText,
        data: dataSeries,
        borderColor: color,
        backgroundColor: 'rgba(239, 68, 68, 0.15)',
        borderWidth: 2.5,
        fill: true,
        pointRadius: 4,
        tension: 0.3
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: 'rgba(255, 255, 255, 0.05)' } },
        y: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: 'rgba(255, 255, 255, 0.05)' } }
      }
    }
  });
}

function setupModal() {
  const modal = document.getElementById('inspectorModal');
  const closeBtn = document.getElementById('closeModalBtn');
  closeBtn.addEventListener('click', () => { modal.style.display = 'none'; });
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.style.display = 'none';
  });
}
// ── Natural Language Query Widget ──
// Add this at the bottom of frontend/js/app.js

function setupNLQWidget() {
  const widget = document.getElementById('nlqWidget');
  const input  = document.getElementById('nlqInput');
  const btn    = document.getElementById('nlqBtn');
  const answer = document.getElementById('nlqAnswer');
  const chips  = document.querySelectorAll('.nlq-chip');

  if (!widget) return;

  // Suggested question chips
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      input.value = chip.textContent;
      input.focus();
    });
  });

  async function askQuestion() {
    const q = input.value.trim();
    if (!q) return;

    btn.disabled = true;
    btn.textContent = '...';
    answer.style.display = 'block';
    answer.innerHTML = '<span class="nlq-thinking">🤖 JalRakshak AI is thinking...</span>';

    try {
      const res = await fetch('/api/nlq', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q })
      });
      const data = await res.json();
      answer.innerHTML = `<span class="nlq-q">Q: ${data.question}</span><span class="nlq-a">${data.answer}</span>`;
    } catch (e) {
      answer.innerHTML = '<span style="color:#ef4444">Error reaching AI. Check API key.</span>';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Ask';
    }
  }

  btn.addEventListener('click', askQuestion);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') askQuestion(); });
}

// Call this at the end of DOMContentLoaded in app.js
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(setupNLQWidget, 500);
});