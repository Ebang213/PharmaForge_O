"""
Prometheus metrics for PharmaForge OS.

Exposes application-level counters, histograms, and gauges
that Prometheus can scrape via the /metrics endpoint.
"""
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# ---------------------------------------------------------------------------
# Watchtower
# ---------------------------------------------------------------------------
WATCHTOWER_FEED_SYNC_DURATION = Histogram(
    "watchtower_feed_sync_duration_seconds",
    "Duration of a Watchtower feed sync operation",
    labelnames=["source"],
)

WATCHTOWER_FEED_ITEMS_PROCESSED = Counter(
    "watchtower_feed_items_processed_total",
    "Total feed items ingested by Watchtower",
    labelnames=["source"],
)

# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------
EVIDENCE_PROCESSING_TOTAL = Counter(
    "evidence_processing_total",
    "Total evidence documents processed",
    labelnames=["status"],  # processed, failed
)

# ---------------------------------------------------------------------------
# Golden Workflow
# ---------------------------------------------------------------------------
WORKFLOW_RUNS_TOTAL = Counter(
    "workflow_runs_total",
    "Total Golden Workflow runs",
    labelnames=["status"],  # success, failed
)

# ---------------------------------------------------------------------------
# Audit Packet Export
# ---------------------------------------------------------------------------
AUDIT_PACKET_EXPORTS_TOTAL = Counter(
    "audit_packet_exports_total",
    "Total audit packet exports",
)

# ---------------------------------------------------------------------------
# War Council
# ---------------------------------------------------------------------------
WAR_COUNCIL_QUERIES_TOTAL = Counter(
    "war_council_queries_total",
    "Total War Council queries executed",
)

# ---------------------------------------------------------------------------
# HTTP request metrics (populated by middleware)
# ---------------------------------------------------------------------------
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "path", "status_code"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "path", "status_code"],
)
