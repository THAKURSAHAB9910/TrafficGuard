import time
import logging
from enum import Enum
from typing import Dict, Optional
from gateway.config import settings

logger = logging.getLogger("trafficguard.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerException(Exception):
    """Raised when a request is blocked because the Circuit Breaker is OPEN."""

    def __init__(self, backend_id: str, retry_after: float):
        self.backend_id = backend_id
        self.retry_after = retry_after
        super().__init__(
            f"Circuit Breaker for backend '{backend_id}' is OPEN. Retry after {retry_after:.1f}s"
        )


class BackendCircuitBreaker:
    """Manages the state machine for a single backend node."""

    def __init__(
        self,
        backend_id: str,
        failure_threshold: int = settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: float = settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
        half_open_success_threshold: int = settings.CIRCUIT_BREAKER_HALF_OPEN_SUCCESS_THRESHOLD,
    ):
        self.backend_id = backend_id
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_success_threshold = half_open_success_threshold

        self.state: CircuitState = CircuitState.CLOSED
        self.consecutive_failures: int = 0
        self.consecutive_successes: int = 0
        self.last_failure_time: float = 0.0
        self.last_state_change: float = time.time()
        self.open_until: float = 0.0
        self.trial_requests_in_flight: int = 0

    def can_execute(self) -> bool:
        """Determines if a request should be permitted or failed fast."""
        now = time.time()

        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if now >= self.open_until:
                # Transition from OPEN to HALF_OPEN
                self._transition_to(CircuitState.HALF_OPEN, now)
                self.trial_requests_in_flight += 1
                return True
            else:
                return False

        if self.state == CircuitState.HALF_OPEN:
            # Allow limited probe requests
            if self.trial_requests_in_flight < self.half_open_success_threshold:
                self.trial_requests_in_flight += 1
                return True
            return False

        return False

    def record_success(self) -> None:
        """Records a successful response from the downstream backend."""
        now = time.time()
        if self.state == CircuitState.HALF_OPEN:
            self.consecutive_successes += 1
            if self.consecutive_successes >= self.half_open_success_threshold:
                self._transition_to(CircuitState.CLOSED, now)
        elif self.state == CircuitState.CLOSED:
            # Reset consecutive failure counter on success
            self.consecutive_failures = 0

    def record_failure(self) -> None:
        """Records a failed request (e.g. 5xx, timeout, connect error)."""
        now = time.time()
        self.last_failure_time = now

        if self.state == CircuitState.HALF_OPEN:
            # Any failure during HALF-OPEN immediately trips back to OPEN
            logger.warning(
                f"[CIRCUIT BREAKER] Probe request failed for backend '{self.backend_id}'. Tripping back to OPEN."
            )
            self._transition_to(CircuitState.OPEN, now)
        elif self.state == CircuitState.CLOSED:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.failure_threshold:
                logger.warning(
                    f"[CIRCUIT BREAKER] Failure threshold ({self.failure_threshold}) reached for backend "
                    f"'{self.backend_id}'. Tripping to OPEN."
                )
                self._transition_to(CircuitState.OPEN, now)

    def _transition_to(self, new_state: CircuitState, now: float) -> None:
        prev = self.state
        self.state = new_state
        self.last_state_change = now

        if new_state == CircuitState.OPEN:
            self.open_until = now + self.recovery_timeout
            self.trial_requests_in_flight = 0
            self.consecutive_successes = 0
        elif new_state == CircuitState.HALF_OPEN:
            self.consecutive_successes = 0
            self.trial_requests_in_flight = 0
        elif new_state == CircuitState.CLOSED:
            self.consecutive_failures = 0
            self.consecutive_successes = 0
            self.trial_requests_in_flight = 0

        logger.info(f"[CIRCUIT BREAKER] Backend '{self.backend_id}' transition: {prev.value} -> {new_state.value}")

    def get_retry_after(self) -> float:
        now = time.time()
        return max(0.0, self.open_until - now)

    def get_info(self) -> dict:
        now = time.time()
        return {
            "backend_id": self.backend_id,
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "retry_after_seconds": round(max(0.0, self.open_until - now), 2) if self.state == CircuitState.OPEN else 0.0,
            "last_state_change": self.last_state_change,
        }


class CircuitBreakerManager:
    """Manages circuit breakers across all backend services."""

    def __init__(
        self,
        failure_threshold: int = settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: float = settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
        half_open_success_threshold: int = settings.CIRCUIT_BREAKER_HALF_OPEN_SUCCESS_THRESHOLD,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_success_threshold = half_open_success_threshold
        self.breakers: Dict[str, BackendCircuitBreaker] = {}

    def get_breaker(self, backend_id: str) -> BackendCircuitBreaker:
        if backend_id not in self.breakers:
            self.breakers[backend_id] = BackendCircuitBreaker(
                backend_id=backend_id,
                failure_threshold=self.failure_threshold,
                recovery_timeout=self.recovery_timeout,
                half_open_success_threshold=self.half_open_success_threshold,
            )
        return self.breakers[backend_id]

    def can_execute(self, backend_id: str) -> bool:
        return self.get_breaker(backend_id).can_execute()

    def record_success(self, backend_id: str) -> None:
        self.get_breaker(backend_id).record_success()

    def record_failure(self, backend_id: str) -> None:
        self.get_breaker(backend_id).record_failure()

    def get_all_states(self) -> Dict[str, dict]:
        return {bid: cb.get_info() for bid, cb in self.breakers.items()}

    def reset_all(self) -> None:
        for cb in self.breakers.values():
            cb._transition_to(CircuitState.CLOSED, time.time())
