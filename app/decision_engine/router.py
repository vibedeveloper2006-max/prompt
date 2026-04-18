"""
decision_engine/router.py
--------------------------
Finds the best route from a source zone to a destination zone.

Algorithm: Dijkstra's shortest path over the zone graph.
- Minimizes physical distance between zones.
- Includes a penalty based on crowd score so congested zones are avoided.

This is intentionally simple and readable for hackathon evaluation.
"""

import heapq
from typing import List, Dict, Optional, Any

from app.config import ZONE_REGISTRY
from app.models.navigation_models import Priority


def _calculate_edge_cost(
    distance: int,
    score: int,
    constraints: Optional[List[str]],
    priority: Priority = Priority.fast_exit,
    neighbor_id: str = "",
    trend: str = "STABLE",
) -> int:
    """
    Calculates the cost of traversing an edge.
    Balances distance, congestion penalty, trend analysis, and user constraints.
    """
    # 0 is best score, 100 is worst (congested)
    congestion_penalty = 100 - score

    # Predictive Trend Penalty: Penalize zones that are increasingly becoming congested
    trend_penalty = 0
    if trend == "INCREASING":
        trend_penalty = 20
    elif trend == "DECREASING":
        trend_penalty = -10  # Incentivize zones that are clearing up

    if priority == Priority.fast_exit or priority == Priority.fastest:
        congestion_penalty = int(congestion_penalty * 0.4)  # Prioritize distance more
    elif priority == Priority.low_crowd or priority == Priority.least_crowded:
        congestion_penalty = int(congestion_penalty * 2.5)  # Heavy weight on crowd
        trend_penalty *= 2
    elif priority == Priority.accessible:
        zone_data = ZONE_REGISTRY.get(neighbor_id, {})
        if not zone_data.get("accessible", True):
            congestion_penalty += 300  # Severe barrier for accessibility
    elif priority == Priority.family_friendly:
        zone_data = ZONE_REGISTRY.get(neighbor_id, {})
        if not zone_data.get("family_friendly", True):
            congestion_penalty += 150
        congestion_penalty = int(congestion_penalty * 1.5)

    if constraints:
        if "avoid_crowd" in constraints and score < 60:
            congestion_penalty *= 6
        if "prefer_fastest" in constraints:
            congestion_penalty = int(
                congestion_penalty * 0.1
            )  # Fast exit still cares slightly about safety
            trend_penalty = 0

    return distance + congestion_penalty + trend_penalty


def find_best_route(
    source: str,
    destination: str,
    zone_scores: Dict[str, Dict[str, int]],
    predictions: Optional[Dict[str, Dict[str, Any]]] = None,
    constraints: Optional[List[str]] = None,
    priority: Priority = Priority.fast_exit,
) -> Optional[List[str]]:
    """
    Returns the recommended path as an ordered list of zone IDs,
    or None if no path exists.

    Uses Dijkstra's algorithm to find the optimal path balancing
    physical distance and crowd congestion.
    """
    if source == destination:
        return [source]

    # Priority queue stores (cost, current_zone, path_so_far)
    pq = [(0, source, [source])]
    visited = set()

    while pq:
        current_cost, current, path = heapq.heappop(pq)

        if current in visited:
            continue

        visited.add(current)

        if current == destination:
            return path

        # Neighbors is now a dict of {neighbor_id: distance}
        neighbors = ZONE_REGISTRY.get(current, {}).get("neighbors", {})

        for neighbor, distance in neighbors.items():
            if neighbor not in visited:
                score = zone_scores.get(neighbor, {}).get("score", 50)
                trend = (
                    predictions.get(neighbor, {}).get("trend", "STABLE")
                    if predictions
                    else "STABLE"
                )
                edge_cost = _calculate_edge_cost(
                    distance, score, constraints, priority, neighbor, trend
                )
                heapq.heappush(
                    pq, (current_cost + edge_cost, neighbor, path + [neighbor])
                )

    return None


def estimate_wait_minutes(
    route: List[str],
    density_map: Dict[str, int],
) -> int:
    """
    Estimates total walking + wait time in minutes for the given route.

    Simple formula:
      - Each zone hop ≈ 1 min walking
      - High-density zones (>70%) add 3 min wait; medium (40-70%) add 1 min.
    """
    wait = 0
    for zone_id in route:
        density = density_map.get(zone_id, 0)
        wait += 1  # walking time per zone
        if density >= 70:
            wait += 3
        elif density >= 40:
            wait += 1
    return wait
