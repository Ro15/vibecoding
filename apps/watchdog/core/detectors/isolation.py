"""Lightweight ML spike detector: IsolationForest over the error-count series.

Deterministic (random_state=0). Only flags anomalies that sit above the series
median, so it reports spikes (the thing we alert on), not quiet dips.
"""
from __future__ import annotations

from apps.watchdog.core.registry import detector


@detector("isolation_forest")
def isolation_forest(counts: list[float], contamination: float = 0.12) -> list[dict]:
    if len(counts) < 6 or len(set(counts)) < 2:
        return []
    import numpy as np
    from sklearn.ensemble import IsolationForest

    arr = np.asarray(counts, dtype=float)
    median = float(np.median(arr))
    clf = IsolationForest(contamination=contamination, random_state=0, n_estimators=100)
    preds = clf.fit_predict(arr.reshape(-1, 1))
    scores = -clf.score_samples(arr.reshape(-1, 1))  # higher = more anomalous
    out = []
    for i, (p, val) in enumerate(zip(preds, arr)):
        if p == -1 and val > median:
            out.append({"index": i, "score": round(float(scores[i]) * 10, 2),
                        "method": "isolation_forest"})
    return out
