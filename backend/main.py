"""
FastAPI Backend Application - Urban Flood Nowcasting System
Serves the two-way coupled simulation, routing API, ULB drain calibration,
and historical validation benchmarks.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import os
import time

from google import genai
from google.genai import types

from backend.data.sample_ward import BOUNDS, ROADS, MANHOLES, CONDUITS
from backend.data.backtest_events import HISTORICAL_EVENTS, evaluate_backtest
from backend.models.coupling_engine import CouplingEngine
from backend.models.drainage_network import DrainageNetworkEngine
from backend.models.routing_engine import get_dual_mode_routes, INTERSECTIONS
from backend.models.radar_nowcast import predict_flood_risk_ai

app = FastAPI(
    title="Urban Flood Nowcasting System (MoES / NCMRWF - SIH 2026)",
    description="Two-way coupled 1D/2D drainage-rainfall nowcasting platform with sub-street resolution.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gemini setup (key name: GEMINI_API_KEY)
# Model can be overridden with a GEMINI_MODEL env var in Vercel without code changes.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
gemini_client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None


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


class NLQueryRequest(BaseModel):
    question: str


# ---------------------------------------------------------------------------
# Fallback answers (used when the Gemini key is missing or the API call fails)
# ---------------------------------------------------------------------------
# Last-resort static answers, used only if live nowcast data is unavailable too.
STATIC_FALLBACK_ANSWERS = {
    "roads_30min": (
        "Within 30 minutes, low-lying stretches near underpasses and the main "
        "arterial junctions in the Sector 29-48 pilot basin are most likely to "
        "flood first, with depths building past 10 cm on the worst segments. "
        "Avoid underpasses and use elevated roads."
    ),
    "ambulance_sadar_bazar": (
        "Sadar Bazar is a high-risk segment during heavy rain. Ambulance access "
        "is not guaranteed once water depth crosses roughly 30 cm, so dispatch "
        "should use the alternate route suggested by the routing module and "
        "re-check the live depth before committing."
    ),
    "drain_bottleneck": (
        "The biggest bottleneck is normally the smallest-diameter conduit "
        "downstream of a high-inflow manhole, where surcharging begins first. "
        "Check the Network tab for surcharging nodes and consider upsizing "
        "that conduit using the calibration tool."
    ),
    "generic": (
        "The AI assistant is temporarily offline. Please check the map and "
        "dashboard panels for live flood depths, blocked roads and surcharging "
        "manholes."
    ),
}


def _classify_question(q: str) -> str:
    """Map a free-text question to one of the canned answer types."""
    q = q.lower()
    if "sadar" in q or "ambulance" in q:
        return "ambulance_sadar_bazar"
    if any(w in q for w in ("drain", "bottleneck", "conduit", "manhole", "pipe")):
        return "drain_bottleneck"
    if any(w in q for w in ("flood", "road", "30 min", "30min", "waterlog")):
        return "roads_30min"
    return "generic"


def _get_step(preferred: str):
    """Return (step_key, step_data) from the cached nowcast, or (None, {})."""
    results = (state.cached_nowcast or {}).get("results", {})
    for key in (preferred, "45", "60"):
        if key in results:
            return key, results[key]
    return None, {}


def build_fallback_answer(question: str) -> str:
    """Build an answer from live simulation data, falling back to static text."""
    kind = _classify_question(question)
    try:
        if kind == "roads_30min":
            key, step = _get_step("30")
            roads = step.get("roads", [])
            flooded = sorted(
                [r for r in roads if r.get("max_depth_cm", 0) >= 10],
                key=lambda r: r.get("max_depth_cm", 0),
                reverse=True,
            )[:4]
            if flooded:
                names = ", ".join(
                    f"{r['name']} ({r['max_depth_cm']:.0f} cm)" for r in flooded
                )
                return (
                    f"At T+{key} min, the roads expected to flood are: {names}. "
                    f"Avoid these stretches and use higher-ground alternatives."
                )
            if roads:
                return (
                    f"At T+{key} min, no road is forecast to exceed 10 cm of "
                    f"flooding. Conditions should stay passable, but keep monitoring."
                )

        elif kind == "ambulance_sadar_bazar":
            key, step = _get_step("45")
            roads = step.get("roads", [])
            match = [r for r in roads if "sadar" in r.get("name", "").lower()]
            if match:
                worst = max(match, key=lambda r: r.get("max_depth_cm", 0))
                depth = worst.get("max_depth_cm", 0)
                ok = worst.get("is_passable_ambulance", True)
                if ok:
                    return (
                        f"Yes, {worst['name']} is passable for ambulances at "
                        f"T+{key} min with about {depth:.0f} cm of water. Proceed "
                        f"with caution and re-check the live depth before dispatch."
                    )
                return (
                    f"No, do not send an ambulance via {worst['name']}. Forecast "
                    f"depth at T+{key} min is about {depth:.0f} cm, above the safe "
                    f"limit. Use the alternate route from the routing panel."
                )

        elif kind == "drain_bottleneck":
            conduits = list(state.drainage_engine.conduits.values())
            summary = (state.cached_nowcast or {}).get("results", {}).get("45", {}).get("summary", {})
            surcharging = summary.get("surcharging_manholes")

            def diam(c):
                return c.get("diameter_mm", c.get("diam_mm", c.get("diameter", 10 ** 9)))

            if conduits:
                smallest = min(conduits, key=diam)
                cid = smallest.get("id", smallest.get("conduit_id", "unknown"))
                extra = (
                    f" {surcharging} manholes are surcharging at T+45 min."
                    if surcharging is not None else ""
                )
                return (
                    f"The biggest bottleneck is conduit {cid}, the smallest "
                    f"diameter pipe in the network ({diam(smallest)} mm).{extra} "
                    f"Upsizing it with the calibration tool would relieve the "
                    f"most backflow."
                )
    except Exception:
        pass  # fall through to static text

    return STATIC_FALLBACK_ANSWERS[kind]


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
    step_key = str(req.timestep_min)
    if not state.cached_nowcast or step_key not in state.cached_nowcast["results"]:
        step_key = "45"

    step_data = state.cached_nowcast["results"][step_key]
    road_depths = {r["id"]: r["max_depth_cm"] for r in step_data["roads"]}

    if req.start_node not in INTERSECTIONS or req.end_node not in INTERSECTIONS:
        raise HTTPException(status_code=400, detail="Invalid start or destination intersection node.")

    return get_dual_mode_routes(req.start_node, req.end_node, road_depths)


@app.get("/api/ai-flood-prediction")
def get_ai_flood_prediction():
    if not state.cached_nowcast:
        state.execute_nowcast()

    nowcast_series = state.coupling_engine.radar_engine.generate_nowcast_series()
    drain_util = state.cached_nowcast.get("summary", {}).get("surcharge_backflow_ls", 50) / 100.0
    drain_util = min(max(drain_util, 0.1), 0.95)

    predictions = predict_flood_risk_ai(nowcast_series, drain_utilization=drain_util)

    return {
        "status": "SUCCESS",
        "model": "Empirical Weighted Accumulation + Drain Saturation Model",
        "predictions": predictions
    }


@app.post("/api/nlq")
def natural_language_query(req: NLQueryRequest):
    if not state.cached_nowcast:
        state.execute_nowcast()

    # No API key configured -> serve pre-saved / data-driven answer
    if gemini_client is None:
        return {
            "status": "SUCCESS",
            "source": "fallback",
            "question": req.question,
            "answer": build_fallback_answer(req.question),
        }

    tkey = "45"
    step = state.cached_nowcast["results"].get(tkey, {})
    summary = step.get("summary", {})
    roads = step.get("roads", [])

    flooded_roads = [r for r in roads if r.get("max_depth_cm", 0) >= 10]
    blocked_roads = [r for r in roads if not r.get("is_passable_ambulance", True)]

    context = f"""You are JalRakshak AI — an urban flood emergency assistant for Gurgaon, India.
Answer concisely in 2-3 sentences. Mention specific road names and depths.

LIVE DATA (T+45 min):
- Scenario: {state.scenario_id}
- Peak Rainfall: {step.get('peak_rain_rate_mmh', 'N/A')} mm/h
- Max Flood Depth: {summary.get('max_inundation_depth_cm', 'N/A')} cm
- Flooded Roads: {', '.join([r['name'] for r in flooded_roads[:5]])}
- Blocked to Ambulances: {', '.join([r['name'] for r in blocked_roads[:3]])}
- Surcharging Manholes: {summary.get('surcharging_manholes', 0)}"""

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=req.question,
            config=types.GenerateContentConfig(
                system_instruction=context,
                max_output_tokens=800,
            ),
        )
        answer = response.text
        if not answer:
            raise ValueError("Empty response from Gemini")
        return {
            "status": "SUCCESS",
            "source": "gemini",
            "question": req.question,
            "answer": answer,
        }
    except Exception as e:
        # Any Gemini failure (quota, bad key, bad model name, network) -> fallback
        print(f"[NLQ] Gemini failed, using fallback: {e}")
        return {
            "status": "SUCCESS",
            "source": "fallback",
            "question": req.question,
            "answer": build_fallback_answer(req.question),
        }


@app.get("/api/test-key")
def test_api_key():
    return {"key_found": bool(gemini_api_key), "model": GEMINI_MODEL}


@app.get("/api/backtest")
def get_backtest_results(event_id: str = "gurgaon_2023"):
    if event_id not in HISTORICAL_EVENTS:
        event_id = "gurgaon_2023"

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


# Mount static files
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
static_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")