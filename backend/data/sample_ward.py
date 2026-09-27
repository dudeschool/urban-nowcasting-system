"""
Sample Urban Ward Data - Sector 29-48 Pilot Ward (Gurgaon Basin)
Realistic testbed representing an urban flood-prone basin:
- Center: 28.4595Â° N, 77.0266Â° E
- Features: Arterial roads (Golf Course Road, CST Road), Railway Subway (depressed elevation),
  Najafgarh Drain Canal Outfall, Central Storm Outfall, dense commercial/residential, open recreation ground.
"""

import numpy as np

# Ward Geospatial Boundary (approx 1.8km x 1.8km)
BOUNDS = {
    "min_lat": 28.4505,
    "max_lat": 28.4685,
    "min_lon": 77.0176,
    "max_lon": 77.0356,
    "center": [28.4595, 77.0266]
}

GRID_ROWS = 36
GRID_COLS = 36
CELL_SIZE_METERS = 50.0  # 50m resolution grid cell

def generate_dem():
    """
    Generates a 36x36 DEM (elevation in meters above sea level).
    Natural slope from East (ridge ~18m) and North (hillock ~22m)
    down towards West and South-West (Najafgarh Drain level ~3.0m).
    Features an engineered depression for Metro Underpass / Subway (elevation 2.1m)
    and Sector 29 Market depression (elevation 2.8m).
    """
    dem = np.zeros((GRID_ROWS, GRID_COLS), dtype=float)
    
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            # Base regional gradient: high in NE, sloping to SW
            norm_r = r / (GRID_ROWS - 1)  # 0 (North) to 1 (South)
            norm_c = c / (GRID_COLS - 1)  # 0 (West) to 1 (East)
            
            base_elev = 3.5 + 14.0 * norm_c + 6.0 * (1.0 - norm_r)
            # Add microtopography
            micro = 1.2 * np.sin(norm_r * 4.0 * np.pi) * np.cos(norm_c * 3.0 * np.pi)
            dem[r, c] = round(base_elev + micro, 2)
            
    # Depressions (natural low-lying choke points prone to severe flooding)
    # 1. Railway Subway / Culvert Underpass (around r=20..23, c=10..13)
    dem[19:24, 9:14] -= 3.8
    # 2. Market Lowland (around r=14..17, c=15..18)
    dem[13:17, 14:18] -= 2.6
    # 3. Najafgarh Drain Outfall Bank (Western edge r=24..35, c=0..4)
    dem[24:36, 0:5] = np.clip(dem[24:36, 0:5], 2.2, 3.8)

    # Ensure min elevation is 1.8m
    dem = np.clip(dem, 1.8, 25.0)
    return dem

def generate_land_use_cn():
    """
    Runoff Curve Number (SCS-CN):
    - Roads / Paved Surfaces: 98
    - Dense Commercial / Slum Rooftops: 92
    - Residential / Mixed: 84
    - Parks / Mangroves / Permeable: 62
    """
    cn_grid = np.full((GRID_ROWS, GRID_COLS), 86.0, dtype=float)
    
    # West edge (Najafgarh Drain green buffer)
    cn_grid[:, 0:4] = 62.0
    # Central Park / Recreation ground (r=7..11, c=18..23)
    cn_grid[7:12, 18:24] = 58.0
    # Dense commercial market area
    cn_grid[13:22, 12:20] = 94.0
    # Arterial road corridors (high CN 98)
    cn_grid[18, :] = 98.0
    cn_grid[:, 12] = 98.0
    cn_grid[:, 24] = 98.0
    
    return cn_grid

# Road network segments with metadata, connectivity, and approximate geo-paths
ROADS = [
    {
        "id": "R1",
        "name": "Golf Course Road (North-South Arterial)",
        "type": "arterial",
        "lanes": 4,
        "width_m": 22.0,
        "base_speed_kmh": 40.0,
        "path": [
            [28.4680, 77.0234],
            [28.4636, 77.0237],
            [28.4590, 77.0239],
            [28.4541, 77.0242],
            [28.4509, 77.0244]
        ],
        "dem_cells": [[r, 12] for r in range(2, 34, 2)]
    },
    {
        "id": "R2",
        "name": "Golf Course Road Link Road (West-East Expressway)",
        "type": "arterial",
        "lanes": 6,
        "width_m": 30.0,
        "base_speed_kmh": 50.0,
        "path": [
            [28.4586, 77.0185],
            [28.4588, 77.0230],
            [28.4590, 77.0284],
            [28.4593, 77.0347]
        ],
        "dem_cells": [[18, c] for c in range(2, 34, 2)]
    },
    {
        "id": "R3",
        "name": "Rapid Metro Culvert Underpass (Subway Road)",
        "type": "subway",
        "lanes": 2,
        "width_m": 12.0,
        "base_speed_kmh": 25.0,
        "path": [
            [28.4577, 77.0226],
            [28.4563, 77.0230],
            [28.4550, 77.0237],
            [28.4546, 77.0253]
        ],
        "dem_cells": [[20, 10], [21, 11], [22, 12], [22, 14]]
    },
    {
        "id": "R4",
        "name": "Market Bazaar Lane (Commercial Hub)",
        "type": "local",
        "lanes": 2,
        "width_m": 10.0,
        "base_speed_kmh": 20.0,
        "path": [
            [28.4622, 77.0239],
            [28.4617, 77.0270],
            [28.4613, 77.0307]
        ],
        "dem_cells": [[14, 13], [14, 16], [15, 20], [15, 24]]
    },
    {
        "id": "R5",
        "name": "Metro Station Approach Road",
        "type": "collector",
        "lanes": 2,
        "width_m": 14.0,
        "base_speed_kmh": 30.0,
        "path": [
            [28.4541, 77.0242],
            [28.4536, 77.0275],
            [28.4532, 77.0311]
        ],
        "dem_cells": [[25, 12], [25, 17], [25, 22], [25, 27]]
    },
    {
        "id": "R6",
        "name": "Park View Boulevard",
        "type": "collector",
        "lanes": 2,
        "width_m": 16.0,
        "base_speed_kmh": 35.0,
        "path": [
            [28.4649, 77.0239],
            [28.4651, 77.0288],
            [28.4654, 77.0342]
        ],
        "dem_cells": [[8, 12], [8, 18], [8, 24], [8, 30]]
    },
    {
        "id": "R7",
        "name": "East Ridge Avenue",
        "type": "collector",
        "lanes": 3,
        "width_m": 18.0,
        "base_speed_kmh": 40.0,
        "path": [
            [28.4667, 77.0302],
            [28.4613, 77.0307],
            [28.4568, 77.0311],
            [28.4514, 77.0316]
        ],
        "dem_cells": [[r, 25] for r in range(4, 34, 4)]
    },
    {
        "id": "R8",
        "name": "Najafgarh Drain Road (West Flood-Margin)",
        "type": "collector",
        "lanes": 2,
        "width_m": 12.0,
        "base_speed_kmh": 30.0,
        "path": [
            [28.4658, 77.0194],
            [28.4613, 77.0198],
            [28.4568, 77.0201],
            [28.4523, 77.0203]
        ],
        "dem_cells": [[r, 4] for r in range(4, 32, 4)]
    },
    {
        "id": "R9",
        "name": "Hospital Emergency Corridor",
        "type": "arterial",
        "lanes": 3,
        "width_m": 20.0,
        "base_speed_kmh": 45.0,
        "path": [
            [28.4671, 77.0198],
            [28.4674, 77.0239],
            [28.4678, 77.0302]
        ],
        "dem_cells": [[4, 4], [4, 12], [4, 25]]
    }
]

# Drainage Network: Nodes (Manholes, Catch-pits, Outfalls)
# Notes on Indian ULB Reality:
# - Invert elevation: depth beneath ground where pipe invert lies
# - Max depth: chamber height
# - Auto-inferred status: True for nodes deduced from DEM/Roads without ground-survey GIS
MANHOLES = [
    {"id": "MH-01", "name": "North LBS Inlet", "lat": 28.4671, "lon": 77.0234, "grid_r": 4, "grid_c": 12, "depth_m": 1.8, "is_outfall": False, "inferred": False},
    {"id": "MH-02", "name": "Park Boulevard Junction", "lat": 28.4649, "lon": 77.0237, "grid_r": 8, "grid_c": 12, "depth_m": 2.0, "is_outfall": False, "inferred": False},
    {"id": "MH-03", "name": "Market North Chamber", "lat": 28.4622, "lon": 77.0239, "grid_r": 13, "grid_c": 12, "depth_m": 2.2, "is_outfall": False, "inferred": False},
    {"id": "MH-04", "name": "Sector 29 Market Low-Point", "lat": 28.4617, "lon": 77.0262, "grid_r": 14, "grid_c": 16, "depth_m": 2.5, "is_outfall": False, "inferred": False},
    {"id": "MH-05", "name": "East Bazaar Catch-Pit", "lat": 28.4613, "lon": 77.0298, "grid_r": 15, "grid_c": 23, "depth_m": 1.8, "is_outfall": False, "inferred": True},
    {"id": "MH-06", "name": "Central Expressway Interchange", "lat": 28.4590, "lon": 77.0239, "grid_r": 18, "grid_c": 12, "depth_m": 2.4, "is_outfall": False, "inferred": False},
    {"id": "MH-07", "name": "Subway Entry Manhole", "lat": 28.4572, "lon": 77.0228, "grid_r": 20, "grid_c": 10, "depth_m": 2.8, "is_outfall": False, "inferred": False},
    {"id": "MH-08", "name": "Rapid Metro Culvert Sump", "lat": 28.4554, "lon": 77.0232, "grid_r": 22, "grid_c": 11, "depth_m": 3.2, "is_outfall": False, "inferred": False},
    {"id": "MH-09", "name": "Subway Exit Catch-Pit", "lat": 28.4546, "lon": 77.0246, "grid_r": 23, "grid_c": 13, "depth_m": 2.5, "is_outfall": False, "inferred": False},
    {"id": "MH-10", "name": "Station Circle Chamber", "lat": 28.4541, "lon": 77.0244, "grid_r": 25, "grid_c": 12, "depth_m": 2.0, "is_outfall": False, "inferred": False},
    {"id": "MH-11", "name": "Metro Station Approach East", "lat": 28.4536, "lon": 77.0280, "grid_r": 25, "grid_c": 19, "depth_m": 1.8, "is_outfall": False, "inferred": True},
    {"id": "MH-12", "name": "South LBS Terminal", "lat": 28.4509, "lon": 77.0244, "grid_r": 31, "grid_c": 12, "depth_m": 2.0, "is_outfall": False, "inferred": False},
    {"id": "MH-13", "name": "East Ridge Junction 1", "lat": 28.4654, "lon": 77.0307, "grid_r": 8, "grid_c": 25, "depth_m": 1.6, "is_outfall": False, "inferred": True},
    {"id": "MH-14", "name": "East Ridge Junction 2", "lat": 28.4568, "lon": 77.0311, "grid_r": 21, "grid_c": 25, "depth_m": 1.8, "is_outfall": False, "inferred": True},
    {"id": "MH-15", "name": "River Canal West Manhole 1", "lat": 28.4631, "lon": 77.0198, "grid_r": 11, "grid_c": 5, "depth_m": 2.0, "is_outfall": False, "inferred": True},
    {"id": "MH-16", "name": "River Canal West Manhole 2", "lat": 28.4586, "lon": 77.0194, "grid_r": 18, "grid_c": 4, "depth_m": 2.2, "is_outfall": False, "inferred": True},
    # Outfalls:
    {"id": "OUTFALL-01", "name": "Najafgarh Drain Drain Outfall (West)", "lat": 28.4550, "lon": 77.0190, "grid_r": 24, "grid_c": 2, "depth_m": 3.5, "is_outfall": True, "inferred": False},
    {"id": "OUTFALL-02", "name": "South Drain Discharge", "lat": 28.4505, "lon": 77.0203, "grid_r": 33, "grid_c": 4, "depth_m": 3.0, "is_outfall": True, "inferred": False}
]

# Drainage Conduits / Storm Pipes
# Key SIH bottleneck: Pipes P4, P7, P8 have undersized diameters (450-600mm)
# leading to rapid surcharge during >40 mm/hr downpours!
CONDUITS = [
    {"id": "P1", "from": "MH-01", "to": "MH-02", "diam_mm": 900, "length_m": 280, "manning_n": 0.015, "inferred": False},
    {"id": "P2", "from": "MH-02", "to": "MH-03", "diam_mm": 1000, "length_m": 340, "manning_n": 0.015, "inferred": False},
    {"id": "P3", "from": "MH-13", "to": "MH-05", "diam_mm": 600, "length_m": 380, "manning_n": 0.018, "inferred": True},
    {"id": "P4", "from": "MH-05", "to": "MH-04", "diam_mm": 600, "length_m": 320, "manning_n": 0.018, "inferred": False}, # Bottleneck
    {"id": "P5", "from": "MH-04", "to": "MH-03", "diam_mm": 800, "length_m": 260, "manning_n": 0.016, "inferred": False},
    {"id": "P6", "from": "MH-03", "to": "MH-06", "diam_mm": 1200, "length_m": 390, "manning_n": 0.014, "inferred": False},
    {"id": "P7", "from": "MH-06", "to": "MH-07", "diam_mm": 600, "length_m": 240, "manning_n": 0.018, "inferred": False}, # Bottleneck to subway
    {"id": "P8", "from": "MH-07", "to": "MH-08", "diam_mm": 500, "length_m": 220, "manning_n": 0.020, "inferred": False}, # Severe Culvert Bottleneck
    {"id": "P9", "from": "MH-08", "to": "MH-09", "diam_mm": 750, "length_m": 190, "manning_n": 0.016, "inferred": False},
    {"id": "P10", "from": "MH-09", "to": "MH-10", "diam_mm": 900, "length_m": 180, "manning_n": 0.015, "inferred": False},
    {"id": "P11", "from": "MH-11", "to": "MH-10", "diam_mm": 600, "length_m": 360, "manning_n": 0.018, "inferred": True},
    {"id": "P12", "from": "MH-10", "to": "MH-12", "diam_mm": 1000, "length_m": 420, "manning_n": 0.015, "inferred": False},
    {"id": "P13", "from": "MH-02", "to": "MH-15", "diam_mm": 800, "length_m": 450, "manning_n": 0.016, "inferred": True},
    {"id": "P14", "from": "MH-15", "to": "MH-16", "diam_mm": 1000, "length_m": 520, "manning_n": 0.015, "inferred": True},
    {"id": "P15", "from": "MH-16", "to": "OUTFALL-01", "diam_mm": 1600, "length_m": 480, "manning_n": 0.013, "inferred": False},
    {"id": "P16", "from": "MH-08", "to": "OUTFALL-01", "diam_mm": 900, "length_m": 410, "manning_n": 0.016, "inferred": False}, # Culvert discharge line
    {"id": "P17", "from": "MH-12", "to": "OUTFALL-02", "diam_mm": 1400, "length_m": 460, "manning_n": 0.014, "inferred": False},
    {"id": "P18", "from": "MH-14", "to": "MH-11", "diam_mm": 600, "length_m": 490, "manning_n": 0.018, "inferred": True}
]

