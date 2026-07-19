"""Detection engine: run every registered detector over each service's error series."""
from __future__ import annotations

# Importing these packages registers all parsers + detectors.
from apps.watchdog.core import detectors, parsers  # noqa: F401
from apps.watchdog.core.models import Anomaly, severity_for_score
from apps.watchdog.core.registry import all_detectors


def run_detectors(timeline: dict, methods: list[str] | None = None,
                  ewma_threshold: float = 3.0, min_errors: int = 3) -> list[Anomaly]:
    """Run detectors per service. `min_errors` floors out trivial 1-2 error blips so
    a normally-quiet service isn't paged for a single stray error."""
    registered = all_detectors()
    methods = methods or list(registered)
    anomalies: list[Anomaly] = []
    for svc, series in timeline.get("services", {}).items():
        errors = [p.errors for p in series]
        for method in methods:
            fn = registered.get(method)
            if fn is None:
                continue
            kwargs = {"threshold": ewma_threshold} if method == "ewma_zscore" else {}
            for hit in fn(errors, **kwargs):
                point = series[hit["index"]]
                if point.errors < min_errors:
                    continue
                anomalies.append(Anomaly(
                    service=svc, bucket_start=point.bucket_start,
                    error_count=point.errors, score=hit["score"], method=hit["method"],
                    severity=severity_for_score(hit["score"])))
    anomalies.sort(key=lambda a: (a.bucket_start, a.service))
    return anomalies
