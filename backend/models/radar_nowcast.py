"""
Module A: Quantitative Precipitation Nowcast (QPN) Engine
- Simulates IMD Doppler Weather Radar (DWR) reflectivity (dBZ) loop
- Converts Reflectivity -> Rain Intensity (Z-R Marshall-Palmer relation)
- Extrapolates storm cell propagation via advection vector field (Optical Flow analogue)
- Models lead-time nowcasting confidence decay
"""

import numpy as np
from typing import Dict, List, Any
from backend.data.sample_ward import GRID_ROWS, GRID_COLS, BOUNDS

# Z-R Marshall-Palmer constants for Indian Monsoon Convective Precipitation:
# Z = a * R^b  => R = (Z / a) ^ (1 / b)
ZR_A = 200.0
ZR_B = 1.6

SCENARIOS = {
    "cloudburst": {
        "name": "Cloudburst Deluge (105 mm/h peak)",
        "peak_dbz": 58.0,
        "base_dbz": 36.0,
        "storm_radius_cells": 11.0,
        "center_start": [12.0, 6.0], # starts SW
        "velocity_cells_per_15m": [1.4, 2.0], # moves NE
        "growth_decay": [0.75, 0.95, 1.0, 1.0, 0.92, 0.85, 0.70, 0.55] # 8 timesteps
    },
    "severe_monsoon": {
        "name": "Severe Monsoon Squall (65 mm/h peak)",
        "peak_dbz": 51.5,
        "base_dbz": 30.0,
        "storm_radius_cells": 14.0,
        "center_start": [10.0, 4.0],
        "velocity_cells_per_15m": [1.2, 1.6],
        "growth_decay": [0.60, 0.85, 0.98, 0.95, 0.88, 0.78, 0.65, 0.50]
    },
    "moderate_shower": {
        "name": "Moderate Convective Shower (32 mm/h peak)",
        "peak_dbz": 44.0,
        "base_dbz": 22.0,
        "storm_radius_cells": 9.0,
        "center_start": [8.0, 6.0],
        "velocity_cells_per_15m": [1.6, 2.2],
        "growth_decay": [0.50, 0.80, 1.0, 0.85, 0.65, 0.45, 0.30, 0.15]
    }
}

TIMESTEPS = [0, 15, 30, 45, 60, 90, 120, 180] # minutes

def dbz_to_rainfall_intensity(dbz: np.ndarray) -> np.ndarray:
    """
    Converts Doppler Radar reflectivity (dBZ) to rainfall intensity (mm/hr)
    using Z-R relation: Z = 10^(dBZ / 10), R = (Z / a) ^ (1 / b)
    """
    z_linear = np.power(10.0, dbz / 10.0)
    rainfall_rate = np.power(z_linear / ZR_A, 1.0 / ZR_B)
    return np.where(dbz < 18.0, 0.0, rainfall_rate)

def calculate_confidence(lead_time_min: int) -> float:
    """
    Nowcast skill decreases as lead time extends from 0 to 180 minutes.
    High optical flow skill (0.94) at 15m decaying to ~0.45 at 180m.
    """
    decay = 0.95 * np.exp(-0.0042 * lead_time_min)
    return round(float(np.clip(decay, 0.35, 0.96)), 3)

class RadarNowcastEngine:
    def __init__(self, scenario_id: str = "cloudburst"):
        self.scenario_id = scenario_id if scenario_id in SCENARIOS else "cloudburst"
        self.params = SCENARIOS[self.scenario_id]

    def generate_nowcast_series(self) -> Dict[int, Dict[str, Any]]:
        """
        Computes 2D radar reflectivity grid (dBZ), rainfall rate (mm/hr),
        and confidence score for each timestep t in [0, 15, 30, 45, 60, 90, 120, 180].
        """
        series = {}
        c_start = np.array(self.params["center_start"], dtype=float)
        v_vel = np.array(self.params["velocity_cells_per_15m"], dtype=float)
        radius = self.params["storm_radius_cells"]
        peak_dbz = self.params["peak_dbz"]
        base_dbz = self.params["base_dbz"]

        for idx, t in enumerate(TIMESTEPS):
            # Time step steps count (15m units)
            steps = t / 15.0
            scale = self.params["growth_decay"][min(idx, len(self.params["growth_decay"]) - 1)]
            
            # Storm center advection
            storm_center = c_start + v_vel * steps
            
            # Build 2D Gaussian radar reflectivity grid
            y_indices, x_indices = np.indices((GRID_ROWS, GRID_COLS))
            dist_sq = (y_indices - storm_center[0])**2 + (x_indices - storm_center[1])**2
            
            # Reflectivity profile: peak at center, decaying outwards
            profile = np.exp(-0.5 * dist_sq / (radius**2))
            current_dbz = base_dbz * 0.4 + (peak_dbz - base_dbz * 0.4) * profile * scale
            
            # Add realistic small-scale radar noise / turbulence
            noise = np.sin(y_indices * 0.7 + steps) * np.cos(x_indices * 0.7 - steps) * 1.5
            current_dbz = np.clip(current_dbz + noise, 0.0, 70.0)
            
            # Convert to rainfall intensity (mm/hr)
            rain_rate = dbz_to_rainfall_intensity(current_dbz)
            
            confidence = calculate_confidence(t)
            
            # Downsample / sample for map rendering (lat, lon, dbz, rain_rate)
            # Create a 12x12 sample for efficient GeoJSON / raster transfer
            stride = 3
            sub_r = current_dbz[::stride, ::stride]
            sub_rain = rain_rate[::stride, ::stride]
            
            heatmap_points = []
            sub_rows, sub_cols = sub_r.shape
            for sr in range(sub_rows):
                for sc in range(sub_cols):
                    val_dbz = float(sub_r[sr, sc])
                    if val_dbz > 22.0:
                        # Convert grid cell to geo-coords
                        lat = BOUNDS["max_lat"] - (sr * stride / GRID_ROWS) * (BOUNDS["max_lat"] - BOUNDS["min_lat"])
                        lon = BOUNDS["min_lon"] + (sc * stride / GRID_COLS) * (BOUNDS["max_lon"] - BOUNDS["min_lon"])
                        heatmap_points.append([
                            round(lat, 5),
                            round(lon, 5),
                            round(val_dbz, 1),
                            round(float(sub_rain[sr, sc]), 1)
                        ])

            series[t] = {
                "timestep_min": t,
                "confidence_score": confidence,
                "peak_dbz": round(float(np.max(current_dbz)), 1),
                "peak_rainfall_rate_mmh": round(float(np.max(rain_rate)), 1),
                "mean_rainfall_rate_mmh": round(float(np.mean(rain_rate)), 1),
                "full_rain_rate_grid": rain_rate, # passed to surface model
                "full_dbz_grid": current_dbz,
                "radar_heatmap_points": heatmap_points
            }

        return series
def predict_flood_risk_ai(nowcast_series: Dict[int, Dict[str, Any]], drain_utilization: float = 0.7) -> Dict[int, Dict[str, Any]]:
    """
    AI Flood Risk Predictor — uses exponential weighted rainfall accumulation
    + drain saturation model to predict flood depth at each timestep.
    Returns risk level, predicted depth, and confidence-adjusted score.
    """
    predictions = {}
    accumulated_rain = 0.0

    for t in TIMESTEPS:
        data = nowcast_series.get(t, {})
        rain_rate = data.get("peak_rainfall_rate_mmh", 0.0)
        confidence = data.get("confidence_score", 1.0)

        # Accumulate rainfall (convert mm/h to mm per timestep)
        dt_hours = (t - (TIMESTEPS[TIMESTEPS.index(t) - 1] if t > 0 else 0)) / 60.0
        accumulated_rain += rain_rate * dt_hours

        # Drain absorption model: drains absorb at fixed rate, excess floods
        drain_absorption_rate_mm = 15.0  # mm drain can handle per hour
        drain_absorbed = drain_absorption_rate_mm * dt_hours * (1.0 - drain_utilization)
        excess_mm = max(0.0, accumulated_rain - drain_absorbed * (t / 15.0 + 1))

        # Predicted flood depth (empirical surface runoff coefficient)
        predicted_depth_cm = round(excess_mm * 0.6 * confidence, 1)

        # Risk classification
        if predicted_depth_cm < 10:
            risk = "Safe"
            risk_color = "green"
        elif predicted_depth_cm < 25:
            risk = "Disruptive"
            risk_color = "orange"
        elif predicted_depth_cm < 45:
            risk = "Hazardous"
            risk_color = "red"
        else:
            risk = "Severe Inundation"
            risk_color = "darkred"

        predictions[t] = {
            "timestep_min": t,
            "predicted_depth_cm": predicted_depth_cm,
            "accumulated_rainfall_mm": round(accumulated_rain, 1),
            "risk_level": risk,
            "risk_color": risk_color,
            "ai_confidence": round(confidence * 100, 1)
        }

    return predictions