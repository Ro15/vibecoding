"""Shared core for the FinOps/Compliance/SRE app family.

Provides the reusable chassis every app instantiates:
- registry:  named-plugin registries (open/closed extension — one file per plugin)
- db:        SQLite engine + session helpers
- api:       FastAPI app-factory helpers (error envelope, optional API-key auth)
- web:       shared glassmorphism design tokens
"""
