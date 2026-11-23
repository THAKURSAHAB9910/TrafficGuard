import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from gateway.config import BackendNode, LoadBalancerAlgorithm

logger = logging.getLogger("trafficguard.load_balancer")


class LoadBalancerStrategy(ABC):
    """Abstract Strategy interface for Load Balancing algorithms."""

    @abstractmethod
    def select(self, backends: List[BackendNode], state: Dict[str, any]) -> Optional[BackendNode]:
        """Select a backend from the pool of available healthy candidates."""
        pass


class RoundRobinStrategy(LoadBalancerStrategy):
    """Standard Round Robin algorithm distributes requests evenly in sequence."""

    def __init__(self):
        self._index = 0
        self._lock = asyncio.Lock()

    def select(self, backends: List[BackendNode], state: Dict[str, any]) -> Optional[BackendNode]:
        if not backends:
            return None
        # Non-blocking modulo pointer
        chosen = backends[self._index % len(backends)]
        self._index = (self._index + 1) % len(backends)
        return chosen


class LeastConnectionsStrategy(LoadBalancerStrategy):
    """Least Connections routes to the candidate with the fewest active in-flight requests."""

    def select(self, backends: List[BackendNode], state: Dict[str, any]) -> Optional[BackendNode]:
        if not backends:
            return None

        active_conns = state.get("active_connections", {})
        # Find backend with minimum active requests; tie-break deterministically
        min_conn = float("inf")
        selected = None

        for backend in backends:
            conns = active_conns.get(backend.id, 0)
            if conns < min_conn:
                min_conn = conns
                selected = backend

        return selected or backends[0]


class WeightedRoundRobinStrategy(LoadBalancerStrategy):
    """
    Smooth Weighted Round Robin (Nginx algorithm).
    Prevents burst clustering by dynamically adjusting current_weights:
      1. For all candidate nodes: current_weight += effective_weight
      2. Choose node with maximum current_weight
      3. For chosen node: current_weight -= sum(effective_weights)
    """

    def __init__(self):
        self._current_weights: Dict[str, int] = {}

    def select(self, backends: List[BackendNode], state: Dict[str, any]) -> Optional[BackendNode]:
        if not backends:
            return None

        # Clean up stale nodes
        valid_ids = {b.id for b in backends}
        self._current_weights = {bid: w for bid, w in self._current_weights.items() if bid in valid_ids}

        total_weight = 0
        best_backend = None
        max_current_weight = -float("inf")

        for backend in backends:
            bid = backend.id
            effective_weight = max(1, backend.weight)
            total_weight += effective_weight

            # Increment current weight
            self._current_weights[bid] = self._current_weights.get(bid, 0) + effective_weight

            if self._current_weights[bid] > max_current_weight:
                max_current_weight = self._current_weights[bid]
                best_backend = backend

        if best_backend:
            # Decrement chosen node's current weight by the sum of all effective weights
            self._current_weights[best_backend.id] -= total_weight

        return best_backend


class LoadBalancer:
    """
    Load Balancer core engine.
    Maintains backend candidate pool, active connection state, and routing statistics.
    """

    def __init__(self, default_algorithm: LoadBalancerAlgorithm = LoadBalancerAlgorithm.ROUND_ROBIN):
        self.algorithm = default_algorithm
        self._strategies: Dict[LoadBalancerAlgorithm, LoadBalancerStrategy] = {
            LoadBalancerAlgorithm.ROUND_ROBIN: RoundRobinStrategy(),
            LoadBalancerAlgorithm.LEAST_CONNECTIONS: LeastConnectionsStrategy(),
            LoadBalancerAlgorithm.WEIGHTED_ROUND_ROBIN: WeightedRoundRobinStrategy(),
        }
        self._active_connections: Dict[str, int] = {}
        self._routed_request_counts: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    def set_algorithm(self, algorithm: LoadBalancerAlgorithm) -> None:
        logger.info(f"Switching load balancing algorithm to: {algorithm.value}")
        self.algorithm = algorithm

    def get_algorithm(self) -> LoadBalancerAlgorithm:
        return self.algorithm

    def get_active_connections(self, backend_id: str) -> int:
        return self._active_connections.get(backend_id, 0)

    def get_all_active_connections(self) -> Dict[str, int]:
        return dict(self._active_connections)

    def get_routed_counts(self) -> Dict[str, int]:
        return dict(self._routed_request_counts)

    def increment_active_connection(self, backend_id: str) -> int:
        count = self._active_connections.get(backend_id, 0) + 1
        self._active_connections[backend_id] = count
        self._routed_request_counts[backend_id] = self._routed_request_counts.get(backend_id, 0) + 1
        return count

    def decrement_active_connection(self, backend_id: str) -> int:
        count = max(0, self._active_connections.get(backend_id, 0) - 1)
        self._active_connections[backend_id] = count
        return count

    def select_backend(self, candidates: List[BackendNode]) -> Optional[BackendNode]:
        """Select a backend from healthy candidate nodes using active strategy."""
        if not candidates:
            return None

        strategy = self._strategies.get(self.algorithm, self._strategies[LoadBalancerAlgorithm.ROUND_ROBIN])
        state = {
            "active_connections": self._active_connections,
            "routed_counts": self._routed_request_counts,
        }
        return strategy.select(candidates, state)

    def reset_stats(self) -> None:
        self._active_connections.clear()
        self._routed_request_counts.clear()
