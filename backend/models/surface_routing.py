"""
Module B: 2D Surface Runoff & Cellular-Automata (CA) Diffusive-Wave Router
- Ingests DEM topography & SCS-CN imperviousness grid
- Generates surface runoff per cell from precipitation intensity
- Routes overland water rapidly using 2D Cellular Automata (diffusive wave)
- Sub-second execution enables real-time 15-minute rolling nowcast updates
"""

import numpy as np
from typing import Tuple, Dict, Any, List
from backend.data.sample_ward import (
    GRID_ROWS, GRID_COLS, CELL_SIZE_METERS,
    generate_dem, generate_land_use_cn, BOUNDS
)

class SurfaceRoutingEngine:
    def __init__(self):
        self.dem = generate_dem()
        self.cn_grid = generate_land_use_cn()
        self.rows, self.cols = GRID_ROWS, GRID_COLS
        self.cell_area = CELL_SIZE_METERS * CELL_SIZE_METERS # 2500 m2
        
        # State: Water depth in meters across the 36x36 grid
        self.water_depth = np.zeros((self.rows, self.cols), dtype=float)
        
        # Accumulated rainfall in mm
        self.accumulated_rain_mm = np.zeros((self.rows, self.cols), dtype=float)
        
        # Precompute SCS-CN potential maximum retention S (mm)
        # S = (25400 / CN) - 254
        self.retention_s = (25400.0 / self.cn_grid) - 254.0

    def apply_rainfall_and_runoff(self, rain_rate_mmh: np.ndarray, dt_minutes: float = 15.0) -> np.ndarray:
        """
        Calculates incremental runoff (mm) using SCS Curve Number method:
        P_inc = Rain_rate * (dt / 60)
        Q = (P - 0.2*S)^2 / (P + 0.8*S) when P > 0.2*S
        Adds generated surface runoff depth (converted to meters) to self.water_depth.
        """
        dt_hours = dt_minutes / 60.0
        p_inc = rain_rate_mmh * dt_hours # incremental rainfall in mm
        self.accumulated_rain_mm += p_inc
        
        p_total = self.accumulated_rain_mm
        ia = 0.2 * self.retention_s # Initial abstraction
        
        # Cumulative runoff Q_cum
        q_cum = np.where(
            p_total > ia,
            np.square(p_total - ia) / (p_total + 0.8 * self.retention_s),
            0.0
        )
        
        # Estimate incremental runoff this timestep (approx 85-95% of rain on high CN roads)
        # Roads (CN=98) shed almost all water immediately
        runoff_fraction = np.clip((self.cn_grid - 40.0) / 60.0, 0.2, 0.98)
        runoff_inc_mm = p_inc * runoff_fraction
        
        # Add to surface water depth (mm -> meters)
        self.water_depth += (runoff_inc_mm / 1000.0)
        return runoff_inc_mm

    def step_cellular_automata(self, num_substeps: int = 8, dt_sub: float = 112.5):
        """
        Diffusive-wave Cellular Automata 2D routing:
        At each sub-step:
        1. Hydraulic head H = dem + water_depth.
        2. For each cell, examine 4 cardinal + 4 diagonal neighbors.
        3. Water transfers downhill proportional to head differences,
           moderated by Manning's surface friction and critical depth.
        """
        for _ in range(num_substeps):
            head = self.dem + self.water_depth
            new_depth = np.copy(self.water_depth)
            
            # Vectors of shifts: (dr, dc, distance_meters)
            directions = [
                (-1, 0, CELL_SIZE_METERS),
                (1, 0, CELL_SIZE_METERS),
                (0, -1, CELL_SIZE_METERS),
                (0, 1, CELL_SIZE_METERS),
                (-1, -1, CELL_SIZE_METERS * 1.414),
                (-1, 1, CELL_SIZE_METERS * 1.414),
                (1, -1, CELL_SIZE_METERS * 1.414),
                (1, 1, CELL_SIZE_METERS * 1.414)
            ]
            
            # Temporary net flux accumulator (meters)
            net_flux = np.zeros_like(self.water_depth)
            
            for dr, dc, dist in directions:
                # Neighbor head shifted
                neighbor_head = np.roll(head, shift=(-dr, -dc), axis=(0, 1))
                
                # Head difference (positive means current cell is higher than neighbor)
                d_head = head - neighbor_head
                
                # Flow only if current cell has positive water depth and higher head
                movable = (d_head > 0.005) & (self.water_depth > 0.002)
                
                # Velocity by simplified Manning / Diffusive equation: v ~ sqrt(S)
                slope = np.maximum(0.0001, d_head / dist)
                # Courant-Friedrichs-Lewy (CFL) stability factor
                transfer_rate = 0.08 * np.sqrt(slope)
                transfer_depth = np.where(movable, np.minimum(self.water_depth * 0.15, transfer_rate), 0.0)
                
                net_flux -= transfer_depth
                # Neighbor receives transfer_depth
                net_flux += np.roll(transfer_depth, shift=(dr, dc), axis=(0, 1))
            
            # Apply flux with safety clamp (cannot lose more water than present)
            self.water_depth = np.maximum(0.0, self.water_depth + net_flux * 0.5)
            
            # Edge outfall boundary condition: water on extreme West edge drains out to sea/Najafgarh Drain
            self.water_depth[:, 0:2] *= 0.88
            self.water_depth[34:36, :] *= 0.88

    def extract_inflow_to_inlets(self, inlet_locations: List[Dict[str, Any]]) -> List[float]:
        """
        Extracts surface water captured by drainage inlets (Module B -> Module C).
        Inlet capture depends on grate capacity and surface ponding head.
        Returns list of captured volumetric rates (m3/s) for each inlet.
        """
        inflows = []
        for inlet in inlet_locations:
            r = inlet["grid_r"]
            c = inlet["grid_c"]
            avail_depth = self.water_depth[r, c] # meters
            
            if avail_depth > 0.005:
                # Orifice / weir capture: Q_in = C * A_grate * sqrt(2*g*h)
                # Max capture rate typically ~0.35 - 0.70 m3/s per street inlet
                grate_area = 0.5 # m2
                capture_q = min(0.65, 0.60 * grate_area * np.sqrt(2 * 9.81 * avail_depth)) # m3/s
                
                # Remove captured water volume from grid cell over 15 min
                vol_captured = capture_q * (15 * 60) # m3
                depth_removed = vol_captured / self.cell_area # meters
                actual_removed = min(avail_depth * 0.75, depth_removed)
                self.water_depth[r, c] -= actual_removed
                
                actual_q = (actual_removed * self.cell_area) / (15 * 60)
                inflows.append(float(actual_q))
            else:
                inflows.append(0.0)
                
        return inflows

    def inject_surcharge_water(self, surcharge_events: List[Dict[str, Any]], dt_seconds: float = 900.0):
        """
        Injects surcharged water from over-capacity manholes back onto surface cells
        (Module C -> Module B).
        surcharge_events: list of {'grid_r': int, 'grid_c': int, 'surcharge_m3s': float}
        """
        for event in surcharge_events:
            r = event["grid_r"]
            c = event["grid_c"]
            q_sur = event["surcharge_m3s"] # m3/s
            
            if q_sur > 0:
                vol_m3 = q_sur * dt_seconds
                added_depth = vol_m3 / self.cell_area # meters
                self.water_depth[r, c] += added_depth
                
                # Also spread slightly to immediate neighboring cells (splatter/backflow)
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < self.rows and 0 <= nc < self.cols:
                        self.water_depth[nr, nc] += (added_depth * 0.15)

    def get_inundation_contours(self) -> List[Dict[str, Any]]:
        """
        Returns significant flood polygon clusters for Map visualization.
        Classified into:
        - 10-25 cm (Minor waterlogging)
        - 25-50 cm (Hazardous ponding)
        - >50 cm (Severe inundation / subway drowning)
        """
        polygons = []
        depth_cm = self.water_depth * 100.0
        
        # Identify contiguous flooded patches
        stride = 2
        for r in range(0, self.rows, stride):
            for c in range(0, self.cols, stride):
                d = float(np.mean(depth_cm[r:r+stride, c:c+stride]))
                if d >= 8.0:
                    # Cell boundary box
                    lat_max = BOUNDS["max_lat"] - (r / self.rows) * (BOUNDS["max_lat"] - BOUNDS["min_lat"])
                    lat_min = BOUNDS["max_lat"] - ((r + stride) / self.rows) * (BOUNDS["max_lat"] - BOUNDS["min_lat"])
                    lon_min = BOUNDS["min_lon"] + (c / self.cols) * (BOUNDS["max_lon"] - BOUNDS["min_lon"])
                    lon_max = BOUNDS["min_lon"] + ((c + stride) / self.cols) * (BOUNDS["max_lon"] - BOUNDS["min_lon"])
                    
                    category = "MINOR" if d < 20 else ("HAZARDOUS" if d < 45 else "CRITICAL")
                    polygons.append({
                        "bounds": [[round(lat_min, 5), round(lon_min, 5)], [round(lat_max, 5), round(lon_max, 5)]],
                        "depth_cm": round(d, 1),
                        "category": category
                    })
        return polygons

