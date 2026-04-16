# Security Policy

## Supported Version

The current `1.x` line is the supported submission version for StadiumChecker.

## Reporting A Vulnerability

Please do not open a public issue for security-sensitive findings.

Report vulnerabilities privately to:
- `security@stadiumchecker.example.com`

Before any public production launch, replace the placeholder address above with your real contact.

Please include:
- a short description of the issue
- reproduction steps
- likely impact
- any suggested mitigation if known

## Security Controls In This Repository

- Environment-aware CORS:
  Wildcard CORS is only allowed in debug mode. Production expects explicit origins.
- Security headers:
  `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Strict-Transport-Security` are injected in middleware.
- Rate limiting:
  Navigation, analytics, and assistant endpoints are protected by per-IP sliding-window rate limits.
- Input bounds:
  Request payloads are constrained with Pydantic validation to prevent oversized or malformed inputs.
- Deterministic routing:
  AI never chooses the navigation path. Routing stays in the deterministic engine.
- Grounded chatbot:
  The assistant answers from structured venue data first and only uses Gemini to phrase grounded responses.
- Mock fallbacks:
  Firestore, BigQuery, Maps, and Gemini can all degrade safely without taking down core routing.
- Container hardening:
  The Docker image runs as a non-root user.

## Production Notes

- Keep `DEBUG=false` in deployment.
- Set `DOCS_ENABLED=false` for production if you do not want interactive docs exposed.
- Use explicit `ALLOWED_ORIGINS_RAW` values.
- Never commit real secrets to `.env`, `.env.example`, README examples, or source files.
