# Project 3 — Intelligent Observability & Event Watchdog — Design Spec

Date: 2026-07-19
Status: Approved (monorepo + scope decisions locked Turn 12)

## Purpose

Parse application / platform logs, detect anomalous spikes in error rates using both
statistical (online EWMA + z-score) and lightweight ML (IsolationForest) logic, trigger
**simulated webhook alerts** when thresholds are breached, and visualize health trends
with a live-replay demo mode.

## Architecture (on the shared `common` core)

```
apps/watchdog/
  core/
    models.py       LogEvent, BucketPoint, Anomaly
    registry.py     parser + detector registries (on common.registry)
    parsers/
      json_log.py   @parser("json")     JSON lines
      syslog.py     @parser("syslog")   RFC3164-ish
      text.py       @parser("text")     generic timestamp+level regex
    bucketing.py    events -> per-service time-bucketed error/total counts
    detectors/
      ewma.py       @detector("ewma_zscore")     online, O(1)/point
      isolation.py  @detector("isolation_forest") sklearn, deterministic
    engine.py       run_detectors(timeline) -> anomalies
    alerting.py     anomalies -> alerts + simulated webhook POST (cooldown dedup)
  adapters/ orm.py db.py       SQLite: ingests, events(bucketed), anomalies, alerts, config
  api/ schemas.py main.py
  static/ index.html style.css app.js   health-trend dashboard + Replay
  sample_data/ generate.py + app.log (json), platform.log (syslog)
  tests/ unit/ api/ e2e/
```

## Performance (the core requirement)

Streaming/online design: parse O(N) events; bucketing O(N); the EWMA+z-score detector
is **O(1) time and O(1) space per series per point** — memory bounded by
services × window, independent of N. The ML detector fits on the small bucketed series
(B buckets, B << N), O(B log B). Space O(services × buckets).

## Normalized IR

`LogEvent`: `ts, level (normalized), service, message`. `is_error` = level in
{error, err, fatal, critical, crit, emerg, alert, panic}. Parsers degrade missing
service → "unknown", missing level → "info".

## Detection

- **ewma_zscore**: maintain EWMA mean + variance of per-bucket error counts; flag a
  bucket when its z-score ≥ threshold (default 3.0) after a warmup. Adaptive baseline.
- **isolation_forest**: fit `IsolationForest(random_state=0)` on the error-count series,
  flag points predicted -1 that are also above the series median (spikes, not dips).

Anomaly: `{service, bucket_start, error_count, score, method, severity}`. Severity from
score: ≥6 → critical, ≥4 → high, else medium.

## Alerting

Each anomaly → an `Alert` (audit row) with the JSON payload that a webhook receives.
If a webhook URL is configured, POST it (best-effort); otherwise it is recorded as a
simulated alert. Cooldown dedup: at most one alert per service per cooldown window
(default 3 buckets) so a sustained incident doesn't storm.

## API

`POST /api/ingest` (file + format) → parse, bucket, run both detectors, create alerts,
return summary. `GET /api/health` (per-service timeline + anomaly markers),
`GET /api/anomalies`, `GET /api/alerts`, `GET /api/summary`, `GET/PUT /api/config`
(webhook_url, ewma_threshold, bucket_seconds), `GET /api/ingests`, `GET /health`, `GET /`.

## Dashboard

Health-trend line (error rate over time, per service) with anomaly markers; service
health tiles (status good/warn/critical); alerts feed; detector-comparison view; a
**▶ Replay** button that animates the trend drawing over ~8s to simulate a live feed.
Dark/light glassmorphism (shared theme).

## Testing

Unit: parsers, bucketing (gap-filling), each detector (spike flagged / flat series
clean), alerting cooldown. API E2E: every endpoint. Playwright: upload → health chart +
anomaly markers render → alerts populate → replay animates → theme toggle. agent-browser
manual pass.
