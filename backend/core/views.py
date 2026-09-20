"""DRF views.

Rules for this module:
- No magic numbers. Risk parameters come from the active RiskPolicy row.
- No risk logic. Views load state, call riskengine, persist, serialise.
- Endpoints are step-driven, never streamed: the client drives the clock.
"""
