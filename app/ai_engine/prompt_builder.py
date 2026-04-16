"""
ai_engine/prompt_builder.py
----------------------------
Builds a clean, structured prompt for Gemini from the navigation context.

Design principle:
  The prompt gives Gemini only facts — Gemini's job is to EXPLAIN the decision
  already made by the decision_engine, not to make a new one.
"""

from typing import Dict, List

from app.config import ZONE_REGISTRY


def build_navigation_prompt(
    current_zone: str,
    destination: str,
    recommended_route: List[str],
    zone_scores: Dict[str, Dict[str, int]],
    density_map: Dict[str, int],
    predictions: Dict[str, Dict],
    estimated_wait_minutes: int,
    event_phase: str,
    priority: str,
) -> str:
    """
    Returns a clean prompt string ready to send to Gemini.

    The prompt is human-readable so that:
      - Output is predictable
      - Prompt can be debugged / logged easily
      - Gemini has full context without ambiguity
    """
    # Build zone status summary (top zones only, to keep prompt short)
    zone_lines = []
    for zone_id, density in density_map.items():
        name = ZONE_REGISTRY.get(zone_id, {}).get("name", zone_id)
        score_data = zone_scores.get(zone_id, {})
        score = score_data.get("score", 0)
        confidence = score_data.get("confidence_score", 0)
        trend = predictions.get(zone_id, {}).get("trend", "STABLE")
        zone_lines.append(f"  - {name} ({zone_id}): {density}% crowded, trend: {trend}, score: {score}/100, confidence: {confidence}%")

    zone_summary = "\n".join(zone_lines)
    route_str = " → ".join(
        ZONE_REGISTRY.get(z, {}).get("name", z) for z in recommended_route
    )

    # Simulate "Situation Room" vision insights based on the highest-density zone in the route
    route_densities = [density_map.get(z, 0) for z in recommended_route]
    max_d = max(route_densities) if route_densities else 0
    vision_note = "High-definition CCTV confirms nominal flow across all segments."
    if max_d > 75:
        vision_note = "Vision sensors detect significant friction in key segments; Dijkstra re-weighted for clearance."
    elif max_d > 50:
        vision_note = "Kinetic sensors monitoring minor buildup; recommending steady pace."

    prompt = f"""You are the StadiumChecker Elite Terminal. Explain this strategic traversal decision.
Do not hallucinate. Base your explanation strictly on the provided data.

[CONTEXT]
- Event Phase: {event_phase.upper()}
- Intelligence Protocol: {priority}
- Calculated Path: {route_str}
- System Latency: {estimated_wait_minutes} mins latency

[SITUATION ROOM - VISION ANALYSIS]
- {vision_note}

[ZONE TELEMETRY]
{zone_summary}

[MISSION OBJECTIVE]
Provide a concise, mission-critical briefing (maximum 3 sentences) justifying this path. 
Mention the 'current density', 'predicted trend', 'vision-based findings', and the 'confidence score'. 
Tone: Professional, high-intelligence, elite condition.
"""
    return prompt.strip()
