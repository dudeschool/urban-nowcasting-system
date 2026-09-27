"""
Module E: Flood-Safe Navigation & Emergency Routing API
- Evaluates city road graph with dynamic edge penalties based on predicted flood depth
- Computes flood-resilient routes using Dijkstra / A*
- Supports distinct vehicle profiles:
  * Emergency / Ambulance Mode (NDRF / High clearance, passable up to 35 cm)
  * Commuter / Civilian Mode (Low clearance, diverts around >15 cm)
- Compares normal baseline route vs live flood-safe diversion route.
"""

import math
import heapq
from typing import Dict, List, Any, Tuple
from backend.data.sample_ward import ROADS

# Vehicle clearance limits (in cm)
VEHICLE_THRESHOLDS = {
    "commuter": {
        "max_passable_depth_cm": 15.0,
        "penalty_multiplier": 5.0,
        "name": "Civilian / Sedan / Two-Wheeler"
    },
    "emergency": {
        "max_passable_depth_cm": 35.0,
        "penalty_multiplier": 2.2,
        "name": "Ambulance / Fire / NDRF Rescue Truck"
    }
}

# Pre-defined navigation intersections across the ward
INTERSECTIONS = {
    "N_HOSPITAL": {"name": "Gurgaon Medical Centre North Gate", "coords": [28.4674, 77.0239]},
    "N_LBS": {"name": "Golf Course Road North Junction", "coords": [28.4680, 77.0234]},
    "PARK_BLVD": {"name": "Park Boulevard West", "coords": [28.4649, 77.0239]},
    "EAST_RIDGE_N": {"name": "East Ridge North", "coords": [28.4667, 77.0302]},
    "MARKET_HUB": {"name": "Sector 29 Market Center", "coords": [28.4617, 77.0270]},
    "EXPRESSWAY_INT": {"name": "Golf Course Road Link Interchange", "coords": [28.4590, 77.0239]},
    "SUBWAY_NORTH": {"name": "Metro Underpass North Portal", "coords": [28.4577, 77.0226]},
    "SUBWAY_SOUTH": {"name": "Metro Underpass South Portal", "coords": [28.4546, 77.0253]},
    "STATION_WEST": {"name": "Rapid Metro Station West Gate", "coords": [28.4541, 77.0242]},
    "STATION_EAST": {"name": "Metro Station Approach East", "coords": [28.4532, 77.0311]},
    "RIVER_CANAL_W": {"name": "Najafgarh Drain West", "coords": [28.4568, 77.0201]},
    "SOUTH_TERMINAL": {"name": "Sector 48 South Terminal", "coords": [28.4509, 77.0244]},
    "EAST_RIDGE_S": {"name": "East Ridge South", "coords": [28.4514, 77.0316]}
}

# Road graph topology connecting intersections
ROAD_GRAPH_EDGES = [
    # (u, v, road_id, base_length_m, base_time_sec)
    ("N_LBS", "N_HOSPITAL", "R9", 120, 15),
    ("N_HOSPITAL", "EAST_RIDGE_N", "R9", 750, 65),
    ("N_LBS", "PARK_BLVD", "R1", 390, 35),
    ("PARK_BLVD", "EAST_RIDGE_N", "R6", 800, 75),
    ("PARK_BLVD", "EXPRESSWAY_INT", "R1", 720, 65),
    ("PARK_BLVD", "MARKET_HUB", "R4", 510, 60),
    ("MARKET_HUB", "EAST_RIDGE_N", "R4", 580, 70),
    ("EXPRESSWAY_INT", "MARKET_HUB", "R2", 480, 40),
    ("EXPRESSWAY_INT", "RIVER_CANAL_W", "R2", 620, 50),
    ("RIVER_CANAL_W", "SUBWAY_NORTH", "R8", 420, 45),
    # Subway bottleneck segment (R3) - highly vulnerable to inundation!
    ("SUBWAY_NORTH", "SUBWAY_SOUTH", "R3", 450, 40),
    ("EXPRESSWAY_INT", "STATION_WEST", "R1", 620, 55),
    ("SUBWAY_SOUTH", "STATION_WEST", "R3", 180, 20),
    ("STATION_WEST", "STATION_EAST", "R5", 850, 95),
    ("STATION_WEST", "SOUTH_TERMINAL", "R1", 420, 40),
    ("STATION_EAST", "EAST_RIDGE_S", "R7", 320, 30),
    ("EAST_RIDGE_N", "EAST_RIDGE_S", "R7", 1850, 160), # Elevated safe bypass ridge
    ("RIVER_CANAL_W", "SOUTH_TERMINAL", "R8", 820, 95)
]

def find_shortest_path(
    start_node: str,
    end_node: str,
    road_depths: Dict[str, float],
    vehicle_mode: str = "commuter"
) -> Dict[str, Any]:
    """
    Computes optimal path considering live predicted flood depth.
    """
    cfg = VEHICLE_THRESHOLDS.get(vehicle_mode, VEHICLE_THRESHOLDS["commuter"])
    max_clearance = cfg["max_passable_depth_cm"]
    penalty_mult = cfg["penalty_multiplier"]
    
    # Build adjacency list with dynamic weights
    adj: Dict[str, List[Tuple[str, float, float, str, bool]]] = {node: [] for node in INTERSECTIONS}
    
    for u, v, road_id, dist_m, base_sec in ROAD_GRAPH_EDGES:
        depth = road_depths.get(road_id, 0.0)
        
        # Check if passable
        if depth >= max_clearance:
            is_blocked = True
            dynamic_sec = 999999.0 # Impassable
        else:
            is_blocked = False
            # Slowdown penalty: depth adds friction
            penalty = 1.0 + penalty_mult * ((depth / max(1.0, max_clearance)) ** 2)
            dynamic_sec = base_sec * penalty
            
        adj[u].append((v, dist_m, dynamic_sec, road_id, is_blocked))
        adj[v].append((u, dist_m, dynamic_sec, road_id, is_blocked)) # Bidirectional
        
    # Dijkstra
    dist = {n: float("inf") for n in INTERSECTIONS}
    prev = {n: None for n in INTERSECTIONS}
    dist[start_node] = 0.0
    
    pq = [(0.0, start_node)]
    
    while pq:
        cur_d, u = heapq.heappop(pq)
        if cur_d > dist[u]:
            continue
        if u == end_node:
            break
            
        for v, length_m, travel_sec, r_id, is_blocked in adj[u]:
            if is_blocked:
                continue
            new_cost = cur_d + travel_sec
            if new_cost < dist[v]:
                dist[v] = new_cost
                prev[v] = (u, r_id, length_m, travel_sec)
                heapq.heappush(pq, (new_cost, v))
                
    # Reconstruct path
    path_nodes = []
    curr = end_node
    total_dist_m = 0
    traversed_roads = []
    max_depth_encountered = 0.0
    
    if dist[end_node] == float("inf"):
        # No flood-safe route found!
        return {
            "success": False,
            "message": f"No passable route available for {cfg['name']}! Surrounding arterials submerged beyond {max_clearance} cm.",
            "mode": vehicle_mode
        }
        
    while curr is not None:
        path_nodes.append(curr)
        step = prev[curr]
        if step:
            curr = step[0]
            traversed_roads.append(step[1])
            total_dist_m += step[2]
            d = road_depths.get(step[1], 0.0)
            if d > max_depth_encountered:
                max_depth_encountered = d
        else:
            curr = None
            
    path_nodes.reverse()
    
    # Path coordinates for Leaflet GeoJSON polyline
    path_coords = [INTERSECTIONS[n]["coords"] for n in path_nodes]
    
    return {
        "success": True,
        "mode": vehicle_mode,
        "vehicle_name": cfg["name"],
        "start_node": start_node,
        "end_node": end_node,
        "start_name": INTERSECTIONS[start_node]["name"],
        "end_name": INTERSECTIONS[end_node]["name"],
        "path_nodes": path_nodes,
        "total_distance_km": round(total_dist_m / 1000.0, 2),
        "estimated_time_min": round(dist[end_node] / 60.0, 1),
        "max_depth_encountered_cm": round(max_depth_encountered, 1),
        "path_coords": path_coords,
        "traversed_roads": list(set(traversed_roads))
    }

def get_dual_mode_routes(start_node: str, end_node: str, road_depths: Dict[str, float]) -> Dict[str, Any]:
    """
    Returns comparative routing:
    1. Civilian Commuter Route (safely avoids all flooded spots >15cm)
    2. Emergency Responder Route (prioritizes speed, handles up to 35cm)
    3. Dry Weather Baseline (for travel time delay comparison)
    """
    dry_depths = {r["id"]: 0.0 for r in ROADS}
    
    baseline = find_shortest_path(start_node, end_node, dry_depths, vehicle_mode="commuter")
    commuter_route = find_shortest_path(start_node, end_node, road_depths, vehicle_mode="commuter")
    emergency_route = find_shortest_path(start_node, end_node, road_depths, vehicle_mode="emergency")
    
    delay_commuter = None
    if baseline.get("success") and commuter_route.get("success"):
        delay_commuter = round(commuter_route["estimated_time_min"] - baseline["estimated_time_min"], 1)
        
    return {
        "baseline_dry": baseline,
        "commuter": commuter_route,
        "emergency": emergency_route,
        "delay_commuter_min": delay_commuter,
        "intersections": INTERSECTIONS
    }

