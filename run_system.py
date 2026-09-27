"""
JalRakshak: Urban Flood Nowcasting System (SIH 2026 - MoES / NCMRWF)
Single-click launcher script.
Runs the FastAPI server with coupled simulation, dynamic routing, and web GIS dashboard.
"""

import sys
import uvicorn

def main():
    print("=" * 76)
    print("  JALRAKSHAK | Urban Flood Nowcasting System (Drainage-Rainfall Coupling)")
    print("  SIH 2026 Solution Design - MoES / NCMRWF (Disaster Management & Software)")
    print("=" * 76)
    print("  [+] Module A: Rainfall Nowcast Engine (IMD Radar Reflectivity -> Z-R QPE)")
    print("  [+] Module B: Surface 2D Overland Routing (Cellular-Automata Diffusive-Wave)")
    print("  [+] Module C: 1D Drainage Network Graph (Manning Hydraulics & Inferred Topology)")
    print("  [+] Module D: Two-Way Coupled Feedback Loop (Surface Inflow <-> Pipe Surcharge)")
    print("  [+] Module E: Flood-Safe Emergency Navigation API (Dynamic A* Routing)")
    print("=" * 76)
    print("  Starting Command Center Server at: http://127.0.0.1:8000")
    print("  Press Ctrl+C to stop.")
    print("=" * 76)

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)

if __name__ == "__main__":
    main()
