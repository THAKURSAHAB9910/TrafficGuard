import asyncio
import time
import logging
from typing import Dict, List, Optional
import httpx
from gateway.config import BackendNode, settings

logger = logging.getLogger("trafficguard.health_checker")


class BackendHealthState:
    """Tracks dynamic health, consecutive checks, and flapping state for one backend."""

    def __init__(self, backend: BackendNode):
        self.backend = backend
        self.is_healthy: bool = True
        self.consecutive_successes: int = 0
        self.consecutive_failures: int = 0
        self.last_check_time: float = 0.0
        self.last_latency_ms: float = 0.0
        self.last_error: Optional[str] = None

        # Flapping detection
        self.state_flips: List[float] = []  # Timestamps of state changes
        self.is_flapping: bool = False
        self.flapping_penalty_until: float = 0.0
        self.flap_count: int = 0

    def record_transition(self, new_state: bool, current_time: float) -> None:
        if self.is_healthy != new_state:
            self.is_healthy = new_state
            self.state_flips.append(current_time)
            self.flap_count += 1
            logger.info(
                f"[HEALTH] Backend {self.backend.id} transitioned to "
                f"{'HEALTHY' if new_state else 'UNHEALTHY'} (flip count: {self.flap_count})"
            )

    def prune_flips(self, current_time: float, window_seconds: float) -> None:
        cutoff = current_time - window_seconds
        self.state_flips = [t for t in self.state_flips if t >= cutoff]

    def check_flapping(self, current_time: float, window_seconds: float, flip_threshold: int, penalty_seconds: float) -> bool:
        self.prune_flips(current_time, window_seconds)

        # If currently under quarantine, check if the cooldown period has expired
        if self.is_flapping:
            if current_time >= self.flapping_penalty_until:
                self.is_flapping = False
                self.state_flips.clear()
                logger.info(f"[FLAPPING CLEARED] Backend {self.backend.id} quarantine expired. Restoring to pool.")
                return False
            return True

        # Check if recent flips breach threshold
        if len(self.state_flips) >= flip_threshold:
            self.is_flapping = True
            self.flapping_penalty_until = current_time + penalty_seconds
            logger.warning(
                f"[FLAPPING DETECTED] Backend {self.backend.id} flipped {len(self.state_flips)} times "
                f"in {window_seconds}s. Imposing {penalty_seconds}s quarantine."
            )
            return True

        return False


class HealthChecker:
    """
    Manages active polling and passive health feedback for all backend nodes.
    Includes flapping mitigation, consecutive thresholds, and automatic pool restoration.
    """

    def __init__(
        self,
        backends: List[BackendNode],
        check_interval: float = settings.HEALTH_CHECK_INTERVAL_SECONDS,
        timeout: float = settings.HEALTH_CHECK_TIMEOUT_SECONDS,
        healthy_threshold: int = settings.HEALTHY_THRESHOLD,
        unhealthy_threshold: int = settings.UNHEALTHY_THRESHOLD,
        flapping_window: float = settings.FLAPPING_WINDOW_SECONDS,
        flapping_threshold: int = settings.FLAPPING_THRESHOLD_FLIPS,
        flapping_penalty: float = settings.FLAPPING_PENALTY_SECONDS,
    ):
        self.backends = {b.id: b for b in backends}
        self.states: Dict[str, BackendHealthState] = {b.id: BackendHealthState(b) for b in backends}
        self.check_interval = check_interval
        self.timeout = timeout
        self.healthy_threshold = healthy_threshold
        self.unhealthy_threshold = unhealthy_threshold
        self.flapping_window = flapping_window
        self.flapping_threshold = flapping_threshold
        self.flapping_penalty = flapping_penalty

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None

    def add_or_update_backend(self, backend: BackendNode) -> None:
        self.backends[backend.id] = backend
        if backend.id not in self.states:
            self.states[backend.id] = BackendHealthState(backend)
        else:
            self.states[backend.id].backend = backend

    def remove_backend(self, backend_id: str) -> None:
        self.backends.pop(backend_id, None)
        self.states.pop(backend_id, None)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._client = httpx.AsyncClient(timeout=self.timeout)
        self._task = asyncio.create_task(self._health_check_loop())
        logger.info(f"Health Checker started. Polling every {self.check_interval}s.")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
        logger.info("Health Checker stopped.")

    async def _health_check_loop(self) -> None:
        while self._running:
            try:
                await self.check_all_backends()
            except Exception as e:
                logger.error(f"Error during health check cycle: {e}")
            await asyncio.sleep(self.check_interval)

    async def check_backend(self, backend_id: str) -> bool:
        """Actively ping a single backend /health endpoint."""
        state = self.states.get(backend_id)
        if not state:
            return False

        url = f"{state.backend.url.rstrip('/')}/health"
        now = time.time()
        state.last_check_time = now

        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        should_close_client = (self._client is None)

        try:
            start_time = time.perf_counter()
            resp = await client.get(url)
            latency = (time.perf_counter() - start_time) * 1000.0
            state.last_latency_ms = latency

            if resp.status_code == 200:
                self.record_success(backend_id, latency)
                return True
            else:
                self.record_failure(backend_id, f"HTTP {resp.status_code}")
                return False
        except httpx.TimeoutException:
            self.record_failure(backend_id, "Connection Timeout")
            return False
        except httpx.ConnectError:
            self.record_failure(backend_id, "Connection Refused")
            return False
        except Exception as e:
            self.record_failure(backend_id, str(e))
            return False
        finally:
            if should_close_client:
                await client.aclose()

    async def check_all_backends(self) -> None:
        tasks = [self.check_backend(bid) for bid in list(self.states.keys())]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def record_success(self, backend_id: str, latency_ms: float = 0.0) -> None:
        state = self.states.get(backend_id)
        if not state:
            return

        now = time.time()
        state.consecutive_successes += 1
        state.consecutive_failures = 0
        state.last_error = None
        state.last_latency_ms = latency_ms

        # Transition to healthy if threshold met
        if not state.is_healthy and state.consecutive_successes >= self.healthy_threshold:
            state.record_transition(True, now)

        # Evaluate flapping state after possible transition
        state.check_flapping(
            now, self.flapping_window, self.flapping_threshold, self.flapping_penalty
        )

    def record_failure(self, backend_id: str, error_message: str) -> None:
        state = self.states.get(backend_id)
        if not state:
            return

        now = time.time()
        state.consecutive_failures += 1
        state.consecutive_successes = 0
        state.last_error = error_message

        # Transition to unhealthy if threshold met
        if state.is_healthy and state.consecutive_failures >= self.unhealthy_threshold:
            state.record_transition(False, now)

        # Evaluate flapping state after possible transition
        state.check_flapping(
            now, self.flapping_window, self.flapping_threshold, self.flapping_penalty
        )

    def is_routable(self, backend_id: str) -> bool:
        """Determines if a backend is healthy, active, and not under flapping penalty."""
        state = self.states.get(backend_id)
        if not state:
            return False

        backend = self.backends.get(backend_id)
        if not backend or not backend.is_active:
            return False

        now = time.time()
        # Still in flapping quarantine?
        if state.is_flapping and now < state.flapping_penalty_until:
            return False

        return state.is_healthy

    def get_routable_backends(self) -> List[BackendNode]:
        """Returns all backend nodes eligible to receive traffic."""
        return [
            b for bid, b in self.backends.items()
            if self.is_routable(bid)
        ]

    def get_all_statuses(self) -> Dict[str, dict]:
        """Returns comprehensive status dictionary for dashboard and telemetry."""
        now = time.time()
        result = {}
        for bid, state in self.states.items():
            b = self.backends.get(bid)
            result[bid] = {
                "id": bid,
                "name": b.name if b else bid,
                "url": b.url if b else "",
                "weight": b.weight if b else 1,
                "is_active": b.is_active if b else False,
                "is_healthy": state.is_healthy,
                "is_routable": self.is_routable(bid),
                "is_flapping": state.is_flapping,
                "flapping_penalty_remaining": max(0.0, state.flapping_penalty_until - now),
                "flap_count": state.flap_count,
                "consecutive_successes": state.consecutive_successes,
                "consecutive_failures": state.consecutive_failures,
                "last_latency_ms": round(state.last_latency_ms, 2),
                "last_error": state.last_error,
                "last_check_time": state.last_check_time,
            }
        return result
