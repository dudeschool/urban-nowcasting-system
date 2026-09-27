"""
FastAPI Backend Application - Urban Flood Nowcasting System
Serves the two-way coupled simulation, routing API, ULB drain calibration,
and historical validation benchmarks.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import time

from backend.data.sample_ward import BOUNDS, ROADS, MANHOLES, CONDUITS
from backend.data.backtest_events import HISTORICAL_EVENTS, evaluate_backtest
from backend.models.coupling_engine import CouplingEngine
from backend.models.drainage_network import DrainageNetworkEngine
from backend.models.routing_engine import get_dual_mode_routes, INTERSECTIONS

app = FastAPI(
    title="Urban Flood Nowcasting System (MoES / NCMRWF - SIH 2026)",
    description="Two-way coupled 1D/2D drainage-rainfall nowcasting platform with sub-street resolution.",
    version="1.0.0"
)

# Enable CORS for frontend interactions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory system state
class SystemState:
    def __init__(self):
        self.scenario_id = "cloudburst"
        self.drainage_engine = DrainageNetworkEngine(use_inferred_network=True)
        self.coupling_engine = CouplingEngine(
            scenario_id=self.scenario_id,
            drainage_engine=self.drainage_engine
        )
        self.cached_nowcast = None
        self.last_run_timestamp = time.time()
        
    def execute_nowcast(self, scenario: str = None):
        if scenario:
            self.scenario_id = scenario
            self.coupling_engine = CouplingEngine(
                scenario_id=self.scenario_id,
                drainage_engine=self.drainage_engine
            )
        self.cached_nowcast = self.coupling_engine.run_coupled_nowcast()
        self.last_run_timestamp = time.time()
        return self.cached_nowcast

state = SystemState()
# Run initial simulation on startup
state.execute_nowcast()

# Request schemas
class TriggerNowcastRequest(BaseModel):
    scenario_id: str = "cloudburst"

class CalibrateConduitRequest(BaseModel):
    conduit_id: str
    new_diam_mm: int
    manning_n: Optional[float] = None

class RouteRequest(BaseModel):
    start_node: str = "N_HOSPITAL"
    end_node: str = "SOUTH_TERMINAL"
    timestep_min: int = 45

# API Endpoints
@app.get("/api/status")
def get_system_status():
    return {
        "status": "OPERATIONAL",
        "system": "Urban Flood Nowcasting Platform (Drainage-Rainfall Coupling)",
        "radar_ingestion": "ACTIVE (IMD Doppler DWR Synthetic Feed)",
        "active_scenario": state.scenario_id,
        "last_nowcast_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state.last_run_timestamp)),
        "coupling_mode": "2-Way Surface <-> 1D Hydraulic Feedback (EPA SWMM/CA Protocol)",
        "drainage_mode": "Hybrid (Municipal GIS + Data-Sparse Auto-Inference)",
        "ward": "Sector 29-48 Pilot Basin (Gurgaon)",
        "resolution": "50m grid / Street segment scale"
    }

@app.get("/api/ward-info")
def get_ward_info():
    return {
        "bounds": BOUNDS,
        "roads_count": len(ROADS),
        "manholes_count": len(state.drainage_engine.nodes),
        "conduits_count": len(state.drainage_engine.conduits),
        "intersections": INTERSECTIONS
    }

@app.get("/api/nowcast")
def get_nowcast():
    if not state.cached_nowcast:
        state.execute_nowcast()
    return state.cached_nowcast

@app.post("/api/nowcast/trigger")
def trigger_nowcast(req: TriggerNowcastRequest):
    data = state.execute_nowcast(req.scenario_id)
    return {
        "status": "SUCCESS",
        "scenario": req.scenario_id,
        "message": f"Coupled nowcast regenerated for {req.scenario_id}",
        "data": data
    }

@app.get("/api/network")
def get_drainage_network():
    return {
        "nodes": list(state.drainage_engine.nodes.values()),
        "conduits": list(state.drainage_engine.conduits.values())
    }

@app.post("/api/network/calibrate")
def calibrate_conduit(req: CalibrateConduitRequest):
    success = state.drainage_engine.update_conduit_params(
        conduit_id=req.conduit_id,
        new_diam_mm=req.new_diam_mm,
        new_n=req.manning_n
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Conduit {req.conduit_id} not found")
        
    # Re-run simulation with the calibrated drainage pipe
    state.execute_nowcast()
    
    return {
        "status": "SUCCESS",
        "conduit_id": req.conduit_id,
        "new_diameter_mm": req.new_diam_mm,
        "message": f"Updated conduit {req.conduit_id}. Hydraulics and surface coupling recomputed.",
        "updated_conduit": state.drainage_engine.conduits[req.conduit_id],
        "new_nowcast": state.cached_nowcast
    }

@app.post("/api/route")
def compute_route(req: RouteRequest):
    # Extract road depths at the requested timestep
    step_key = str(req.timestep_min)
    if not state.cached_nowcast or step_key not in state.cached_nowcast["results"]:
        step_key = "45"
        
    step_data = state.cached_nowcast["results"][step_key]
    road_depths = {r["id"]: r["max_depth_cm"] for r in step_data["roads"]}
    
    if req.start_node not in INTERSECTIONS or req.end_node not in INTERSECTIONS:
        raise HTTPException(status_code=400, detail="Invalid start or destination intersection node.")
        
    return get_dual_mode_routes(req.start_node, req.end_node, road_depths)

@app.get("/api/backtest")
def get_backtest_results(event_id: str = "gurgaon_2023"):
    if event_id not in HISTORICAL_EVENTS:
        event_id = "gurgaon_2023"
        
    # Use the 60m peak timestep predictions for benchmark evaluation
    step_key = "60"
    if not state.cached_nowcast:
        state.execute_nowcast("cloudburst")
        
    step_data = state.cached_nowcast["results"].get(step_key, state.cached_nowcast["results"]["45"])
    roads = step_data["roads"]
    
    benchmark = evaluate_backtest(roads, event_id=event_id)
    return {
        "events_available": list(HISTORICAL_EVENTS.keys()),
        "selected_event": benchmark
    }

# Mount frontend directory for static web files
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
static_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

