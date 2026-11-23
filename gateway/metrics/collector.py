import time
from collections import deque
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class RequestLogEntry:
    id: str
    timestamp: float
    client_ip: str
    method: str
    path: str
    backend_id: Optional[str]
    status_code: int
    latency_ms: float
    cache_status: str
    algorithm: Optional[str]
    circuit_state: Optional[str]
    error: Optional[str] = None


class MetricsCollector:
    """
    High-performance in-memory metrics aggregator.
    Maintains rolling windows, latency percentiles, and live logs for real-time dashboard.
    """

    def __init__(self, window_size: int = 2000, log_history_size: int = 100):
        self.window_size = window_size
        self.log_history_size = log_history_size

        self.latencies = deque(maxlen=window_size)
        self.timestamps = deque(maxlen=window_size)
        self.live_logs = deque(maxlen=log_history_size)

        # Global counters
        self.total_requests: int = 0
        self.total_successes: int = 0
        self.total_client_errors: int = 0  # 4xx
        self.total_server_errors: int = 0  # 5xx
        self.total_rate_limited: int = 0
        self.total_circuit_breaker_rejected: int = 0
        self.total_load_shed: int = 0

        # Per-backend routed request counters
        self.backend_routed_counts: Dict[str, int] = {}
        self.backend_error_counts: Dict[str, int] = {}

    def record_request(
        self,
        request_id: str,
        client_ip: str,
        method: str,
        path: str,
        backend_id: Optional[str],
        status_code: int,
        latency_ms: float,
        cache_status: str = "BYPASS",
        algorithm: Optional[str] = None,
        circuit_state: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        now = time.time()
        self.total_requests += 1
        self.latencies.append(latency_ms)
        self.timestamps.append(now)

        if 200 <= status_code < 400:
            self.total_successes += 1
        elif 400 <= status_code < 500:
            self.total_client_errors += 1
            if status_code == 429:
                self.total_rate_limited += 1
        elif status_code >= 500:
            self.total_server_errors += 1
            if error and "Circuit Breaker" in error:
                self.total_circuit_breaker_rejected += 1
            elif error and "Shedding" in error:
                self.total_load_shed += 1

        if backend_id:
            self.backend_routed_counts[backend_id] = self.backend_routed_counts.get(backend_id, 0) + 1
            if status_code >= 500:
                self.backend_error_counts[backend_id] = self.backend_error_counts.get(backend_id, 0) + 1

        # Store in live logs
        entry = RequestLogEntry(
            id=request_id,
            timestamp=now,
            client_ip=client_ip,
            method=method,
            path=path,
            backend_id=backend_id,
            status_code=status_code,
            latency_ms=round(latency_ms, 2),
            cache_status=cache_status,
            algorithm=algorithm,
            circuit_state=circuit_state,
            error=error,
        )
        self.live_logs.append(entry)

    def get_current_rps(self, window_seconds: float = 5.0) -> float:
        """Calculate incoming requests per second over the last N seconds."""
        if not self.timestamps:
            return 0.0
        now = time.time()
        cutoff = now - window_seconds
        recent_count = sum(1 for t in self.timestamps if t >= cutoff)
        return round(recent_count / window_seconds, 2)

    def get_latency_percentiles(self) -> dict:
        if not self.latencies:
            return {"avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0}

        sorted_lats = sorted(self.latencies)
        n = len(sorted_lats)

        def percentile(p: float) -> float:
            idx = int(p * (n - 1))
            return sorted_lats[idx]

        return {
            "avg": round(sum(sorted_lats) / n, 2),
            "p50": round(percentile(0.50), 2),
            "p95": round(percentile(0.95), 2),
            "p99": round(percentile(0.99), 2),
            "min": round(sorted_lats[0], 2),
            "max": round(sorted_lats[-1], 2),
        }

    def get_error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round((self.total_server_errors / self.total_requests) * 100.0, 2)

    def get_summary(self) -> dict:
        percentiles = self.get_latency_percentiles()
        return {
            "total_requests": self.total_requests,
            "current_rps": self.get_current_rps(),
            "total_successes": self.total_successes,
            "total_client_errors": self.total_client_errors,
            "total_server_errors": self.total_server_errors,
            "rate_limit_rejections": self.total_rate_limited,
            "circuit_breaker_rejections": self.total_circuit_breaker_rejected,
            "load_shed_rejections": self.total_load_shed,
            "error_rate_pct": self.get_error_rate(),
            "latency": percentiles,
            "backend_routed_counts": dict(self.backend_routed_counts),
            "backend_error_counts": dict(self.backend_error_counts),
        }

    def get_recent_logs(self, limit: int = 50) -> List[dict]:
        logs = list(self.live_logs)
        return [asdict(e) for e in reversed(logs[-limit:])]

    def reset(self) -> None:
        self.latencies.clear()
        self.timestamps.clear()
        self.live_logs.clear()
        self.total_requests = 0
        self.total_successes = 0
        self.total_client_errors = 0
        self.total_server_errors = 0
        self.total_rate_limited = 0
        self.total_circuit_breaker_rejected = 0
        self.total_load_shed = 0
        self.backend_routed_counts.clear()
        self.backend_error_counts.clear()
