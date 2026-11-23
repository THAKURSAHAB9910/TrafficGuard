from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Prometheus Metrics Definitions
HTTP_REQUESTS_TOTAL = Counter(
    "trafficguard_http_requests_total",
    "Total HTTP requests processed by TrafficGuard",
    ["method", "status", "backend", "cache_status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "trafficguard_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["backend"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

BACKEND_HEALTH_STATUS = Gauge(
    "trafficguard_backend_health_status",
    "Health status of backend service (1 = Healthy, 0 = Unhealthy)",
    ["backend_id"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "trafficguard_circuit_breaker_state",
    "Circuit breaker state (0 = CLOSED, 1 = HALF_OPEN, 2 = OPEN)",
    ["backend_id"],
)

ACTIVE_CONNECTIONS = Gauge(
    "trafficguard_active_connections",
    "Active in-flight connections to backend service",
    ["backend_id"],
)

ADAPTIVE_CONCURRENCY_LIMIT = Gauge(
    "trafficguard_adaptive_concurrency_limit",
    "Dynamic concurrency limit determined by Adaptive Traffic Controller",
    ["backend_id"],
)

RATE_LIMIT_DROPPED_TOTAL = Counter(
    "trafficguard_rate_limit_dropped_total",
    "Total requests rejected by rate limiter",
    ["algorithm", "route"],
)

LOAD_SHED_DROPPED_TOTAL = Counter(
    "trafficguard_load_shed_dropped_total",
    "Total requests shed by adaptive concurrency controller",
    ["backend_id"],
)


def export_prometheus_metrics() -> bytes:
    """Generate latest Prometheus metrics formatted string."""
    return generate_latest()
