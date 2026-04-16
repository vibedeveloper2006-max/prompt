# StadiumChecker

StadiumChecker is a smart crowd-navigation and event-assistance system for large sporting venues. It helps attendees move through gates, corridors, restrooms, and concessions with lower waiting time, better route choices, and live coordination support, while giving venue staff a lightweight operational view of crowd conditions.

## Chosen Vertical

This project targets the physical event experience at large-scale sporting venues.

Primary attendee scenarios:
- Find the best route to a seat, restroom, exit, or food court.
- Avoid crowded corridors during pre-entry, halftime, and post-match exit.
- Get accessibility-aware and family-friendly route options.
- Ask the event assistant about venue rules, prohibited items, bag policy, accessibility services, and event timing.

## Approach And Logic

The system is built as a modular FastAPI backend with a lightweight frontend mounted from `frontend/`.

Core logic:
- `crowd_engine` simulates live zone density and predicts short-term congestion.
- `decision_engine` uses Dijkstra pathfinding with crowd-aware penalties to produce deterministic routes.
- `ai_engine` uses Gemini for route explanations and chatbot phrasing, but never for the routing decision itself.
- `google_services` provides Firestore, BigQuery, and Maps integrations with local mock fallbacks.
- `middleware` adds rate limiting and production-minded safeguards.

This keeps the assistant smart and dynamic while ensuring the critical navigation decision remains explainable and deterministic.

## How The Solution Works

1. The frontend loads live crowd status, wait times, and analytics insights.
2. The attendee selects a starting zone, destination, and routing priority such as `fast_exit`, `low_crowd`, `accessible`, or `family_friendly`.
3. The backend builds a live density map, predicts near-future congestion, scores zones, and computes the best route using Dijkstra's algorithm.
4. The response includes route steps, estimated wait time, walking distance, route waypoints, and a Gemini-generated explanation.
5. The frontend keeps polling for crowd changes and can surface reroute alerts if a meaningfully faster path appears.
6. The chatbot answers event and venue questions from structured ground-truth data, with Gemini used only to phrase grounded responses.
7. The analytics view highlights busy zones and recommended entry points for both attendees and staff.

## Feature Set

- Smart route planning with deterministic routing
- Live reroute alerts with accept and dismiss flows
- Venue service wait-time prediction
- Route map view using zone coordinates and walking distances
- Event assistant chatbot for venue policy and event information
- Staff operations dashboard with hotspot and leaderboard insights
- Offline-safe mock mode when Google credentials are not configured

## Google Services Used

- Gemini API:
  Used for route explanations and grounded chatbot phrasing.
  Model calls are bounded by a short timeout and fall back safely if Gemini is unavailable or slow.
- Firestore:
  Stores active navigation sessions and reroute state.
- BigQuery:
  Supports analytics-style hotspot insights and historical trend queries.
- Google Maps style abstraction:
  Supplies walking distances and route waypoints through the maps client layer.
- Cloud Run:
  The app is containerized and ready for Cloud Run deployment.

All Google integrations degrade gracefully to mock implementations for local development and judging environments without credentials.

## API Summary

- `POST /navigate/suggest`
- `GET /navigate/alerts/{user_id}`
- `POST /navigate/accept/{user_id}`
- `POST /navigate/dismiss/{user_id}`
- `GET /crowd/status`
- `GET /crowd/predict`
- `GET /crowd/wait-times`
- `GET /analytics/insights`
- `POST /assistant/chat`
- `GET /health`

## Accessibility

The frontend includes:
- skip navigation
- keyboard-reachable controls
- live regions for route and assistant updates
- visible focus handling
- reduced-motion support
- non-color status cues

Route priorities also support accessibility-focused use cases through `accessible` and `family_friendly` modes.

See [ACCESSIBILITY.md](/run/media/shrey/Data/FlowSync-AI/FlowSync-AI/ACCESSIBILITY.md) for the focused accessibility notes used in the final submission pass.

## Security And Reliability

- Environment-aware CORS configuration
- Security headers including CSP, frame protection, and content-type hardening
- Rate limiting for navigation, analytics, and chatbot endpoints
- Bounded request models via Pydantic validation
- Non-root Docker runtime
- Mock fallbacks so optional services do not take down core routing

See [SECURITY.md](/run/media/shrey/Data/FlowSync-AI/FlowSync-AI/SECURITY.md) for the repository security policy and production notes.

## Assumptions

- Venue zones are represented as a graph with known neighbor connections.
- Crowd density is simulated for demo and judging purposes unless live data sources are connected.
- Maps, BigQuery, Firestore, and Gemini may run in mock mode during local or offline evaluation.
- The reroute flow is designed for short-lived attendee sessions rather than persistent user accounts.

## Project Structure

```text
FlowSync-AI/
├── app/
│   ├── api/
│   ├── ai_engine/
│   ├── crowd_engine/
│   ├── decision_engine/
│   ├── google_services/
│   ├── middleware/
│   ├── models/
│   ├── config.py
│   └── config_data.py
├── frontend/
│   ├── css/style.css
│   ├── js/app.js
│   └── index.html
├── tests/
├── Dockerfile
├── requirements.txt
└── README.md
```

## Running Locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Open `http://localhost:8080`.

## Testing

The repository currently contains 170 test cases across API, routing, chatbot, maps, analytics, security, and performance-focused modules.

```bash
python -m pytest tests/
```
