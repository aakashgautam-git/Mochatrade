"""Django app: the thin REST shell around riskengine.

This layer persists runs, actions and policy versions, and serialises frames.
It contains no risk logic and no magic numbers. Every parameter it passes into
riskengine comes from a versioned RiskPolicy row.
"""
