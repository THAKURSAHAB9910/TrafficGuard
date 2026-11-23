import httpx
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Request
from gateway.config import BackendNode, LoadBalancerAlgorithm, RateLimitAlgorithm

router = APIRouter(prefix="/api/admin", tags=["Admin & Control"])


class BackendCreateRequest(BaseModel):
    id: str
    name: str
    url: str
    weight: int = Field(default=1, ge=1, le=100)
    max_concurrency: int = Field(default=50, ge=1)


class WeightUpdateRequest(BaseModel):
    weight: int = Field(ge=1, le=100)


class AlgorithmUpdateRequest(BaseModel):
    algorithm: LoadBalancerAlgorithm


class RateLimitUpdateRequest(BaseModel):
    algorithm: Optional[RateLimitAlgorithm] = None
    capacity: Optional[int] = Field(default=None, ge=1)
    refill_rate: Optional[float] = Field(default=None, gt=0)
    window_limit: Optional[int] = Field(default=None, ge=1)
    window_seconds: Optional[int] = Field(default=None, ge=1)


@router.get("/backends")
async def list_backends(request: Request):
    proxy_engine = request.app.state.proxy_engine
    health_statuses = proxy_engine.health_checker.get_all_statuses()
    cb_states = proxy_engine.circuit_breaker.get_all_states()
    adaptive_stats = proxy_engine.adaptive_controller.get_all_stats()
    active_conns = proxy_engine.load_balancer.get_all_active_connections()
    routed_counts = proxy_engine.load_balancer.get_routed_counts()

    nodes = []
    for bid, b in proxy_engine.health_checker.backends.items():
        h = health_statuses.get(bid, {})
        cb = cb_states.get(bid, {})
        ad = adaptive_stats.get(bid, {})
        nodes.append({
            "id": bid,
            "name": b.name,
            "url": b.url,
            "weight": b.weight,
            "is_active": b.is_active,
            "is_healthy": h.get("is_healthy", True),
            "is_routable": h.get("is_routable", True),
            "is_flapping": h.get("is_flapping", False),
            "flapping_penalty_remaining": h.get("flapping_penalty_remaining", 0.0),
            "circuit_state": cb.get("state", "CLOSED"),
            "circuit_retry_after": cb.get("retry_after_seconds", 0.0),
            "active_connections": active_conns.get(bid, 0),
            "total_routed": routed_counts.get(bid, 0),
            "dynamic_concurrency_limit": ad.get("current_concurrency_limit", b.max_concurrency),
            "p95_latency_ms": ad.get("p95_latency_ms", 0.0),
            "error_rate": ad.get("error_rate", 0.0),
            "last_error": h.get("last_error"),
        })
    return {"backends": nodes}


@router.post("/backends")
async def add_backend(node_data: BackendCreateRequest, request: Request):
    proxy_engine = request.app.state.proxy_engine
    node = BackendNode(
        id=node_data.id,
        name=node_data.name,
        url=node_data.url,
        weight=node_data.weight,
        max_concurrency=node_data.max_concurrency,
        is_active=True,
    )
    proxy_engine.health_checker.add_or_update_backend(node)
    # Check its health immediately
    await proxy_engine.health_checker.check_backend(node.id)
    return {"message": f"Backend '{node.id}' registered successfully", "backend": node}


@router.put("/backends/{backend_id}/weight")
async def update_weight(backend_id: str, req: WeightUpdateRequest, request: Request):
    proxy_engine = request.app.state.proxy_engine
    b = proxy_engine.health_checker.backends.get(backend_id)
    if not b:
        raise HTTPException(status_code=404, detail=f"Backend '{backend_id}' not found")
    b.weight = req.weight
    return {"message": f"Backend '{backend_id}' weight updated to {req.weight}", "weight": b.weight}


@router.post("/backends/{backend_id}/toggle")
async def toggle_backend_active(backend_id: str, request: Request):
    proxy_engine = request.app.state.proxy_engine
    b = proxy_engine.health_checker.backends.get(backend_id)
    if not b:
        raise HTTPException(status_code=404, detail=f"Backend '{backend_id}' not found")
    b.is_active = not b.is_active
    return {"message": f"Backend '{backend_id}' is_active set to {b.is_active}", "is_active": b.is_active}


@router.get("/algorithm")
async def get_algorithm(request: Request):
    proxy_engine = request.app.state.proxy_engine
    return {"algorithm": proxy_engine.load_balancer.get_algorithm().value}


@router.post("/algorithm")
async def set_algorithm(req: AlgorithmUpdateRequest, request: Request):
    proxy_engine = request.app.state.proxy_engine
    proxy_engine.load_balancer.set_algorithm(req.algorithm)
    return {"message": f"Load balancing algorithm changed to {req.algorithm.value}", "algorithm": req.algorithm.value}


@router.get("/ratelimit")
async def get_ratelimit_config(request: Request):
    proxy_engine = request.app.state.proxy_engine
    rl = proxy_engine.rate_limiter
    return {
        "algorithm": rl.algorithm.value,
        "default_capacity": request.app.state.settings.DEFAULT_RATE_LIMIT_CAPACITY,
        "default_refill_rate": request.app.state.settings.DEFAULT_RATE_LIMIT_REFILL_RATE,
        "default_sliding_limit": request.app.state.settings.DEFAULT_SLIDING_WINDOW_LIMIT,
        "default_sliding_window_seconds": request.app.state.settings.DEFAULT_SLIDING_WINDOW_SECONDS,
    }


@router.post("/ratelimit")
async def update_ratelimit_config(req: RateLimitUpdateRequest, request: Request):
    proxy_engine = request.app.state.proxy_engine
    app_settings = request.app.state.settings
    if req.algorithm:
        proxy_engine.rate_limiter.algorithm = req.algorithm
    if req.capacity:
        app_settings.DEFAULT_RATE_LIMIT_CAPACITY = req.capacity
        proxy_engine.rate_limiter._memory_token_buckets.clear()
        proxy_engine.rate_limiter._memory_sliding_windows.clear()
    if req.refill_rate:
        app_settings.DEFAULT_RATE_LIMIT_REFILL_RATE = req.refill_rate
    if req.window_limit:
        app_settings.DEFAULT_SLIDING_WINDOW_LIMIT = req.window_limit
    if req.window_seconds:
        app_settings.DEFAULT_SLIDING_WINDOW_SECONDS = req.window_seconds

    return {
        "message": "Rate limit settings updated",
        "algorithm": proxy_engine.rate_limiter.algorithm.value,
        "capacity": app_settings.DEFAULT_RATE_LIMIT_CAPACITY,
        "refill_rate": app_settings.DEFAULT_RATE_LIMIT_REFILL_RATE,
        "window_limit": app_settings.DEFAULT_SLIDING_WINDOW_LIMIT,
        "window_seconds": app_settings.DEFAULT_SLIDING_WINDOW_SECONDS,
    }


@router.post("/circuit-breaker/reset")
async def reset_circuit_breakers(request: Request):
    proxy_engine = request.app.state.proxy_engine
    proxy_engine.circuit_breaker.reset_all()
    return {"message": "All circuit breakers reset to CLOSED"}


@router.post("/cache/clear")
async def clear_cache(request: Request):
    proxy_engine = request.app.state.proxy_engine
    proxy_engine.cache.clear()
    return {"message": "Cache successfully cleared"}


@router.post("/simulate/{backend_id}/{action}")
async def control_backend_simulation(
    backend_id: str,
    action: str,
    request: Request,
    delay_ms: Optional[int] = 0,
    error_rate: Optional[float] = 0.0,
    status_str: Optional[str] = "UP",
):
    """Convenience proxy to inject simulated faults directly into running backends."""
    proxy_engine = request.app.state.proxy_engine
    b = proxy_engine.health_checker.backends.get(backend_id)
    if not b:
        raise HTTPException(status_code=404, detail=f"Backend '{backend_id}' not found")

    target_url = b.url.rstrip("/")
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            if action == "delay":
                res = await client.post(f"{target_url}/simulate/delay?ms={delay_ms}")
                return res.json()
            elif action == "error":
                res = await client.post(f"{target_url}/simulate/error?rate={error_rate}")
                return res.json()
            elif action == "status":
                res = await client.post(f"{target_url}/simulate/status?status_str={status_str}")
                # Trigger health checks so state updates immediately
                for _ in range(max(proxy_engine.health_checker.unhealthy_threshold, proxy_engine.health_checker.healthy_threshold)):
                    await proxy_engine.health_checker.check_backend(backend_id)
                return res.json()
            elif action == "reset":
                res = await client.post(f"{target_url}/simulate/reset")
                await proxy_engine.health_checker.check_backend(backend_id)
                return res.json()
            else:
                raise HTTPException(status_code=400, detail=f"Unknown simulation action: {action}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to communicate with backend: {str(e)}")
