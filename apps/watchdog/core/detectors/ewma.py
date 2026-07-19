"""Online EWMA + z-score spike detector.

O(1) time and space per point: keep an exponentially-weighted mean and variance,
flag a point whose z-score against that adaptive baseline exceeds the threshold.
This is the streaming detector that makes memory independent of log volume.
"""
from __future__ import annotations

from apps.watchdog.core.registry import detector


@detector("ewma_zscore")
def ewma_zscore(counts: list[float], alpha: float = 0.3, threshold: float = 3.0,
                warmup: int = 3) -> list[dict]:
    anomalies = []
    mean = None
    var = 0.0
    for i, x in enumerate(counts):
        if mean is None:
            mean = float(x)
            continue
        std = var ** 0.5
        if i >= warmup and std > 0:
            z = (x - mean) / std
            if z >= threshold:
                anomalies.append({"index": i, "score": round(float(z), 2),
                                  "method": "ewma_zscore"})
        diff = x - mean
        mean += alpha * diff
        var = (1 - alpha) * (var + alpha * diff * diff)
    return anomalies
