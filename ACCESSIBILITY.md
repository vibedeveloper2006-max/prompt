# Accessibility Notes

StadiumChecker is designed to support inclusive use in high-pressure venue conditions.

## Current Accessibility Coverage

- Skip navigation link for keyboard users
- Keyboard-reachable route controls
- Visible focus states
- `aria-live` announcements for route updates, reroute alerts, and assistant replies
- Non-color status cues in route and crowd UI
- Reduced-motion support in the frontend styles
- Text fallback for route understanding through summaries, not only the venue map
- Accessibility-focused routing modes:
  `accessible` and `family_friendly`

## Feature-Specific Accessibility

- Route Planner:
  Form validation is shown inline instead of relying only on modal browser alerts.
- Reroute Alerts:
  Alerts are announced and provide explicit accept and dismiss actions.
- Venue Map:
  The map is paired with route summary text so it is not the only source of meaning.
- Event Assistant:
  Chat updates are announced through live regions and remain keyboard accessible.
- Wait Times And Insights:
  Service wait states and leaderboard data are presented as readable text, not only visual color cues.

## Known Assumptions

- The UI is optimized for modern desktop and mobile browsers.
- The venue map is an SVG route visualization rather than a full GIS accessibility map.
