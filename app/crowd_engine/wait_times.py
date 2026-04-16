"""
crowd_engine/wait_times.py
--------------------------
Calculates estimated wait times for various venue services based on live density.
"""

from typing import Dict, Any

def calculate_service_wait_time(zone_id: str, zone_data: Dict[str, Any], density: int) -> int:
    """
    Computes an estimated wait time in minutes for a specific zone based on 
    it's type and current density constraints.
    """
    base_wait = 0
    zone_type = zone_data.get("type", "corridor")
    
    if density < 20:
        return 0  # Essentially walk-up
    
    # Wait multiplier based on density percentage
    # If density is 80%, multiplier is huge, if 40%, moderate
    density_factor = density / 100.0
    
    if zone_type == "gate":
        # Gates have heavy security queues, wait times explode at high density
        # E.g. at 85% density -> 85 / 100 -> ~ 20-30 mins
        base_wait = int(30 * (density_factor ** 2))
    elif zone_type == "restroom":
        # Restrooms queue linearly. Max wait ~ 15 mins
        base_wait = int(15 * density_factor)
    elif zone_type == "amenity":
        # Concession stands / Food Courts. Max wait ~ 25 mins
        base_wait = int(25 * density_factor)
    else:
        # Venue and Corridors don't really have "wait lines" aside from slow walking
        return 0
        
    return base_wait

def determine_wait_trend(density: int, prediction: Dict[str, Any]) -> str:
    """
    Returns string mapping of WAIT trend (Increaing/Stable/Decreasing)
    based on predicted density.
    """
    pred_density = prediction.get("predicted_density", density)
    if pred_density > density + 5:
        return "INCREASING"
    elif pred_density < density - 5:
        return "DECREASING"
    return "STABLE"

def get_wait_status(wait_minutes: int) -> str:
    if wait_minutes < 5:
        return "LOW"
    elif wait_minutes < 15:
        return "MODERATE"
    return "HIGH"
