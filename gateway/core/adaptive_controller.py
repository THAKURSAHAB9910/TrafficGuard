import time
import logging
from typing import Dict, List, Optional
from collections import deque
from gateway.config import settings

logger = logging.getLogger("trafficguard.adaptive_controller")


class AdaptiveDecisionRecord:
    """Explainable record of an adaptive concurrency control decision."""

    def __init__(
        self,
        backend_id: str,
        timestamp: float,
        action: str,  # "SHED", "EXPAND", "HOLD", "REJECT"
        reason: str,
        observed_p95_ms: float,
        observed_error_rate: float,
        previous_limit: int,
        new_limit: int,
        in_flight: int,
    ):
        self.backend_id = backend_id
        self.timestamp = timestamp
        self.action = action
        self.reason = reason
        self.observed_p95_ms = round(observed_p95_ms, 2)
        self.observed_error_rate = round(observed_error_rate, 4)
        self.previous_limit = previous_limit
        self.new_limit = new_limit
        self.in_flight = in_flight

    def to_dict(self) -> dict:
        return {
            "backend_id": self.backend_id,
            "timestamp": self.timestamp,
            "action": self.action,
            "reason": self.reason,
            "observed_p95_ms": self.observed_p95_ms,
            "observed_error_rate": self.observed_error_rate,
            "previous_limit": self.previous_limit,
            "new_limit": self.new_limit,
            "in_flight": self.in_flight,
        }


class BackendAdaptiveState:
    """Manages dynamic concurrency limit and rolling latency/error signals for one backend."""

    def __init__(
        self,
        backend_id: str,
        target_latency_ms: float = settings.ADAPTIVE_TARGET_LATENCY_MS,
        max_latency_ms: float = settings.ADAPTIVE_MAX_LATENCY_MS,
        min_concurrency: int = settings.ADAPTIVE_MIN_CONCURRENCY,
        initial_concurrency: int = settings.ADAPTIVE_INITIAL_CONCURRENCY,
        max_concurrency: int = settings.ADAPTIVE_MAX_CONCURRENCY,
        backoff_factor: float = settings.ADAPTIVE_BACKOFF_FACTOR,
        increase_step: int = settings.ADAPTIVE_INCREASE_STEP,
        error_rate_threshold: float = settings.ADAPTIVE_ERROR_RATE_THRESHOLD,
        window_size: int = 50,
    ):
        self.backend_id = backend_id
        self.target_latency_ms = target_latency_ms
        self.max_latency_ms = max_latency_ms
        self.min_concurrency = min_concurrency
        self.current_limit = initial_concurrency
        self.max_concurrency = max_concurrency
        self.backoff_factor = backoff_factor
        self.increase_step = increase_step
        self.error_rate_threshold = error_rate_threshold

        self.latencies = deque(maxlen=window_size)
        self.results = deque(maxlen=window_size)  # True = success, False = error
        self.in_flight_count: int = 0
        self.total_shed_count: int = 0
        self.recent_decisions = deque(maxlen=20)
        self.last_adjustment_time: float = time.time()
        self.adjustment_cooldown_seconds: float = 1.0  # Don't adjust more than once per second

    def record_completion(self, latency_ms: float, is_success: bool) -> None:
        self.latencies.append(latency_ms)
        self.results.append(is_success)

        # Periodically evaluate and adapt limit
        now = time.time()
        if now - self.last_adjustment_time >= self.adjustment_cooldown_seconds and len(self.latencies) >= 5:
            self._evaluate_and_adapt(now)

    def can_accept(self) -> Tuple_CanAccept:
        if self.in_flight_count >= self.current_limit:
            self.total_shed_count += 1
            reason = (
                f"Shedding load: active concurrency ({self.in_flight_count}) >= dynamic limit ({self.current_limit})"
            )
            decision = AdaptiveDecisionRecord(
                backend_id=self.backend_id,
                timestamp=time.time(),
                action="REJECT",
                reason=reason,
                observed_p95_ms=self.get_p95_latency(),
                observed_error_rate=self.get_error_rate(),
                previous_limit=self.current_limit,
                new_limit=self.current_limit,
                in_flight=self.in_flight_count,
            )
            self.recent_decisions.append(decision)
            return False, reason
        return True, ""

    def increment_in_flight(self) -> None:
        self.in_flight_count += 1

    def decrement_in_flight(self) -> None:
        self.in_flight_count = max(0, self.in_flight_count - 1)

    def get_p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_lats = sorted(self.latencies)
        idx = int(0.95 * (len(sorted_lats) - 1))
        return sorted_lats[idx]

    def get_avg_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)

    def get_error_rate(self) -> float:
        if not self.results:
            return 0.0
        errors = sum(1 for r in self.results if not r)
        return errors / len(self.results)

    def _evaluate_and_adapt(self, now: float) -> None:
        self.last_adjustment_time = now
        p95 = self.get_p95_latency()
        error_rate = self.get_error_rate()
        prev = self.current_limit

        # Signal 1: Heavy Overload (Latency > max_latency_ms OR Error Rate > error_rate_threshold)
        if p95 > self.max_latency_ms or error_rate >= self.error_rate_threshold:
            new_limit = max(self.min_concurrency, int(self.current_limit * self.backoff_factor))
            if new_limit != prev:
                self.current_limit = new_limit
                reason = (
                    f"Overload detected: p95 latency {p95:.1f}ms (threshold {self.max_latency_ms}ms) "
                    f"or error rate {error_rate*100:.1f}%. Multiplicative decrease to {new_limit}."
                )
                logger.warning(f"[ADAPTIVE CONTROL] {self.backend_id}: {reason}")
                self.recent_decisions.append(
                    AdaptiveDecisionRecord(self.backend_id, now, "SHED", reason, p95, error_rate, prev, new_limit, self.in_flight_count)
                )

        # Signal 2: Healthy System Recovery (Latency <= target_latency_ms AND Error Rate < 5%)
        elif p95 <= self.target_latency_ms and error_rate < 0.05:
            new_limit = min(self.max_concurrency, self.current_limit + self.increase_step)
            if new_limit != prev:
                self.current_limit = new_limit
                reason = (
                    f"Performance healthy: p95 latency {p95:.1f}ms <= SLA {self.target_latency_ms}ms. "
                    f"Additive increase to {new_limit}."
                )
                self.recent_decisions.append(
                    AdaptiveDecisionRecord(self.backend_id, now, "EXPAND", reason, p95, error_rate, prev, new_limit, self.in_flight_count)
                )


# Helper type
from typing import Tuple as Tuple_CanAccept


class AdaptiveTrafficController:
    """Manages adaptive concurrency and load shedding across all backend nodes."""

    def __init__(self):
        self.states: Dict[str, BackendAdaptiveState] = {}

    def get_state(self, backend_id: str) -> BackendAdaptiveState:
        if backend_id not in self.states:
            self.states[backend_id] = BackendAdaptiveState(backend_id)
        return self.states[backend_id]

    def can_accept(self, backend_id: str) -> Tuple_CanAccept[bool, str]:
        return self.get_state(backend_id).can_accept()

    def record_start(self, backend_id: str) -> None:
        self.get_state(backend_id).increment_in_flight()

    def record_finish(self, backend_id: str, latency_ms: float, is_success: bool) -> None:
        state = self.get_state(backend_id)
        state.decrement_in_flight()
        state.record_completion(latency_ms, is_success)

    def get_backend_stats(self, backend_id: str) -> dict:
        state = self.get_state(backend_id)
        return {
            "backend_id": backend_id,
            "current_concurrency_limit": state.current_limit,
            "in_flight": state.in_flight_count,
            "p95_latency_ms": round(state.get_p95_latency(), 2),
            "avg_latency_ms": round(state.get_avg_latency(), 2),
            "error_rate": round(state.get_error_rate(), 4),
            "total_shed_requests": state.total_shed_count,
            "recent_decisions": [d.to_dict() for d in list(state.recent_decisions)[-5:]],
        }

    def get_all_stats(self) -> Dict[str, dict]:
        return {bid: self.get_backend_stats(bid) for bid in self.states.keys()}
