"""Risk scoring: severity-weighted 0-100 score (higher = worse) + letter grade."""
from __future__ import annotations

SEVERITY_WEIGHTS = {"critical": 40, "high": 20, "medium": 8, "low": 3}


def risk_score(findings) -> int:
    raw = sum(SEVERITY_WEIGHTS.get(f.severity, 0) for f in findings)
    return min(100, raw)


def grade(score: int) -> str:
    if score == 0:
        return "A+"
    if score < 15:
        return "A"
    if score < 30:
        return "B"
    if score < 50:
        return "C"
    if score < 75:
        return "D"
    return "F"
