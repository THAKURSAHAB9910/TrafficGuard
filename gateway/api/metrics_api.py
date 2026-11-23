from fastapi import APIRouter, Request
from gateway.metrics.prometheus import export_prometheus_metrics

router = APIRouter(prefix="/api/metrics", tags=["Metrics & Telemetry"])


@router.get("/summary")
async def get_metrics_summary(request: Request):
    proxy_engine = request.app.state.proxy_engine
    metrics_collector = proxy_engine.metrics
    cache_stats = proxy_engine.cache.get_stats()
    adaptive_stats = proxy_engine.adaptive_controller.get_all_stats()
    cb_states = proxy_engine.circuit_breaker.get_all_states()
    health_statuses = proxy_engine.health_checker.get_all_statuses()

    summary = metrics_collector.get_summary()
    return {
        "gateway_status": "ONLINE",
        "algorithm": proxy_engine.load_balancer.get_algorithm().value,
        "rate_limiter_algorithm": proxy_engine.rate_limiter.algorithm.value,
        "metrics": summary,
        "cache": cache_stats,
        "circuit_breakers": cb_states,
        "adaptive_controller": adaptive_stats,
        "backends_health": health_statuses,
    }


@router.get("/live-logs")
async def get_live_logs(request: Request, limit: int = 50):
    proxy_engine = request.app.state.proxy_engine
    return {"logs": proxy_engine.metrics.get_recent_logs(limit=limit)}


@router.post("/reset")
async def reset_metrics(request: Request):
    proxy_engine = request.app.state.proxy_engine
    proxy_engine.metrics.reset()
    proxy_engine.cache.clear()
    return {"message": "Metrics and telemetry successfully reset"}
