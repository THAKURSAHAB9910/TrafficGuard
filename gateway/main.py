import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis

from gateway.config import settings
from gateway.db.database import init_db
from gateway.core.load_balancer import LoadBalancer
from gateway.core.health_checker import HealthChecker
from gateway.core.rate_limiter import RateLimiter
from gateway.core.circuit_breaker import CircuitBreakerManager
from gateway.core.adaptive_controller import AdaptiveTrafficController
from gateway.core.cache import HttpCacheManager
from gateway.metrics.collector import MetricsCollector
from gateway.metrics.prometheus import export_prometheus_metrics
from gateway.core.proxy import ProxyEngine

from gateway.api import admin, metrics_api, proxy_api

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("trafficguard.gateway")


def create_gateway_components(redis_client=None):
    load_balancer = LoadBalancer(default_algorithm=settings.DEFAULT_ALGORITHM)
    health_checker = HealthChecker(backends=settings.DEFAULT_BACKENDS)
    rate_limiter = RateLimiter(redis_client=redis_client, default_algorithm=settings.DEFAULT_RATE_LIMIT_ALGORITHM)
    circuit_breaker = CircuitBreakerManager(
        failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout=settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
        half_open_success_threshold=settings.CIRCUIT_BREAKER_HALF_OPEN_SUCCESS_THRESHOLD,
    )
    adaptive_controller = AdaptiveTrafficController()
    cache_manager = HttpCacheManager(redis_client=redis_client, enabled=settings.CACHE_ENABLED)
    metrics_collector = MetricsCollector()

    proxy_engine = ProxyEngine(
        load_balancer=load_balancer,
        health_checker=health_checker,
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        adaptive_controller=adaptive_controller,
        cache_manager=cache_manager,
        metrics_collector=metrics_collector,
    )
    return proxy_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing TrafficGuard Resilience Platform...")

    # 1. Connect Redis (with fallback)
    redis_client = None
    try:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            socket_timeout=1.0,
            decode_responses=False,
        )
        await redis_client.ping()
        logger.info(f"Connected to Redis at {settings.REDIS_URL}")
        # update redis client on components
        app.state.proxy_engine.rate_limiter.redis = redis_client
        app.state.proxy_engine.cache.redis = redis_client
    except Exception as e:
        logger.warning(f"Redis unavailable ({e}). Operating in resilient in-memory mode.")

    # 2. Initialize Database
    try:
        await init_db()
    except Exception as e:
        logger.warning(f"Database init exception: {e}")

    # 3. Start background workers
    await app.state.proxy_engine.health_checker.start()
    await app.state.proxy_engine.start()

    logger.info("TrafficGuard API Gateway ready to accept traffic.")
    yield

    logger.info("Shutting down TrafficGuard...")
    await app.state.proxy_engine.health_checker.stop()
    await app.state.proxy_engine.stop()
    if redis_client:
        await redis_client.aclose()


app = FastAPI(
    title="TrafficGuard — Adaptive Traffic Management & Resilience Platform",
    version="1.0.0",
    description="Intelligent API Gateway with Load Balancing, Circuit Breakers, Rate Limiting, and Adaptive Concurrency.",
    lifespan=lifespan,
)

# Initialize app state so it is always present
app.state.settings = settings
app.state.proxy_engine = create_gateway_components()

# CORS middleware for React dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(proxy_api.router)
app.include_router(admin.router)
app.include_router(metrics_api.router)


@app.get("/health", tags=["Gateway Health"])
async def gateway_health():
    """Self-health endpoint for the TrafficGuard Gateway."""
    return {
        "status": "UP",
        "service": "TrafficGuard Gateway",
        "version": "1.0.0",
    }


@app.get("/metrics", tags=["Prometheus Telemetry"])
async def prometheus_metrics():
    """Prometheus-compatible metrics exposition endpoint."""
    return Response(
        content=export_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("gateway.main:app", host="0.0.0.0", port=8000, reload=False)
