import pytest
import time
from gateway.core.adaptive_controller import AdaptiveTrafficController


def test_adaptive_concurrency_load_shedding():
    controller = AdaptiveTrafficController()
    state = controller.get_state("backend-1")
    state.current_limit = 2  # Set low limit for testing

    # Can accept 2 requests
    can1, _ = controller.can_accept("backend-1")
    assert can1 is True
    controller.record_start("backend-1")

    can2, _ = controller.can_accept("backend-1")
    assert can2 is True
    controller.record_start("backend-1")

    # 3rd request reaches limit (2) -> shed/reject
    can3, reason = controller.can_accept("backend-1")
    assert can3 is False
    assert "Shedding load" in reason
    assert state.total_shed_count == 1

    # Finish one request -> should be able to accept again
    controller.record_finish("backend-1", latency_ms=45.0, is_success=True)
    can4, _ = controller.can_accept("backend-1")
    assert can4 is True


def test_adaptive_concurrency_adjustment_on_overload():
    controller = AdaptiveTrafficController()
    state = controller.get_state("backend-2")
    state.current_limit = 20
    state.adjustment_cooldown_seconds = 0.0  # Instant adjustment for testing

    # Feed high latency (500ms > max SLA 350ms)
    for _ in range(10):
        controller.record_start("backend-2")
        controller.record_finish("backend-2", latency_ms=500.0, is_success=True)

    # Concurrency limit should have backed off (20 * 0.7 = 14)
    assert state.current_limit < 20
    assert len(state.recent_decisions) > 0
    assert state.recent_decisions[-1].action == "SHED"
