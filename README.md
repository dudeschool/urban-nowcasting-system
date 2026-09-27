# JalRakshak | Urban Flood Nowcasting System

> **SIH 2026 Solution Design — Ministry of Earth Sciences (MoES) / NCMRWF**  
> Dynamic two-way coupled 1D/2D drainage-rainfall nowcasting platform with sub-street resolution and flood-safe emergency navigation.

---

## 🌊 Overview

**JalRakshak** is an advanced urban flood modeling and decision support platform engineered to predict street-level inundation during extreme convective precipitation events in real-time. By dynamically coupling radar-derived quantitative precipitation estimates with surface overland hydraulics and subsurface storm sewer networks, the system delivers actionable nowcasts and resilient routing paths before flash floods paralyze urban centers.

---

## 🚀 Key Modules & Capabilities

- **Module A: Radar Rainfall Nowcasting Engine**
  - Converts Doppler weather radar reflectivity (dBZ) into Quantitative Precipitation Estimates (QPE) using the Marshall-Palmer $Z = aR^b$ relationship.
  - Generates spatio-temporal rainfall grids across 15-minute lead-time intervals (T+15, T+30, T+45, T+60 min).

- **Module B: 2D Surface Overland Routing**
  - Cellular-automata diffusive-wave 2D overland routing accounting for micro-topography, surface slope, and land-use roughness (Manning's $n$).

- **Module C: 1D Subsurface Drainage Network Graph**
  - Network-graph hydraulic solver using Manning's equation for circular pipe conduit flow and gravitational energy slopes.
  - Accommodates siltation factors, pipe diameters, and manhole hydraulic heads.

- **Module D: Dynamic Two-Way Coupled Feedback Loop**
  - Continuous feedback between surface ponding and underground drainage:
    - *Under-capacity*: Storm grates intake runoff from streets into conduits.
    - *Over-capacity / Surcharge*: Pressurized pipes backflow water onto the street surface as fountain surcharge.

- **Module E: Flood-Safe Emergency Navigation API**
  - Dynamic cost-weighted A* routing algorithm prioritizing flood-free roads.
  - Automatically avoids inundated roads exceeding critical vehicle safety clearance thresholds (e.g., >0.2m for light vehicles, >0.5m for emergency response units).

- **Interactive GIS Command Center & Calibration Studio**
  - Real-time Leaflet GIS mapping with depth-classified color ramps.
  - Historical storm backtesting validation suite against recorded waterlogging logs.
  - ULB drain editor for real-time asset calibration, siltation adjustments, and pump station scenarios.

---

## 📂 Project Architecture

```
urban-nowcasting-system/
│
├── backend/
│   ├── data/
│   │   ├── sample_ward.py        # Ward topology, DEM elevation, conduits, roads
│   │   └── backtest_events.py    # Historical monsoon storm scenarios
│   ├── models/
│   │   ├── radar_nowcast.py      # Module A: Radar QPE & advection
│   │   ├── surface_routing.py    # Module B: 2D diffusive wave surface solver
│   │   ├── drainage_network.py   # Module C: 1D Manning pipe hydraulics
│   │   ├── coupling_engine.py    # Module D: 2-way surface-pipe coupling
│   │   └── routing_engine.py     # Module E: Flood-aware A* routing
│   └── main.py                   # FastAPI REST API & static file service
│
├── frontend/
│   ├── index.html                # GIS Command Center Dashboard
│   ├── css/
│   │   └── style.css             # Glassmorphism dark-mode UI styling
│   └── js/
│       ├── app.js                # Core state management and UI controller
│       ├── map.js                # Leaflet map rendering & heatmaps
│       ├── routing.js            # Emergency route calculator & waypoint controls
│       ├── editor.js             # Drain network calibration & inspection panel
│       └── backtest.js           # Historical scenario replay & metrics
│
├── run_system.py                 # Single-click launcher script
├── requirements.txt              # Python dependencies
└── README.md                     # Documentation
```

---

## 🛠️ Quick Start

### 1. Prerequisites
- Python 3.9+ installed
- Git

### 2. Installation
Clone the repository and install dependencies:

```bash
git clone https://github.com/itsAbhijeetT/urban-nowcasting-system.git
cd urban-nowcasting-system
pip install -r requirements.txt
```

### 3. Run the Application
Launch the system with a single command:

```bash
python run_system.py
```

Open your browser and navigate to:
```
http://127.0.0.1:8000
```

---

## 📡 API Endpoints

- `GET /api/status` — System health and active module status.
- `GET /api/simulation/run` — Run coupled 2-way simulation across forecast lead times.
- `POST /api/routing/safe-path` — Calculate emergency flood-safe navigation routes.
- `GET /api/drainage/network` — Fetch conduit network geometry and siltation metrics.
- `POST /api/drainage/calibrate` — Update drain pipe attributes and siltation percentages.
- `GET /api/backtest/events` — Retrieve historical monsoon events and validation logs.

---

## 📜 License
Developed for the Smart India Hackathon (SIH 2026).
