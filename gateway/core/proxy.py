import time
import uuid
import logging
from typing import Dict, List, Optional, Tuple
import httpx
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from gateway.config import BackendNode, settings, RateLimitAlgorithm
from gateway.core.load_balancer import LoadBalancer
from gateway.core.health_checker import HealthChecker
from gateway.core.rate_limiter import RateLimiter, RateLimitResult
from gateway.core.circuit_breaker import CircuitBreakerManager
from gateway.core.adaptive_controller import AdaptiveTrafficController
from gateway.core.cache import HttpCacheManager
from gateway.metrics.collector import MetricsCollector
from gateway.metrics.prometheus import (
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    ACTIVE_CONNECTIONS,
    CIRCUIT_BREAKER_STATE,
    RATE_LIMIT_DROPPED_TOTAL,
    LOAD_SHED_DROPPED_TOTAL,
)

logger = logging.getLogger("trafficguard.proxy")

# Headers that must not be blindly forwarded hop-by-hop
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
}


class ProxyEngine:
    """
    Main reverse proxy engine orchestrating:
      1. Rate Limiting (Token Bucket / Sliding Window)
      2. Safe HTTP Caching
      3. Dynamic Health Filtering & Flapping Quarantine
      4. Load Balancing (Round Robin, Least Connections, Weighted Round Robin)
      5. Circuit Breaker Protection (Closed, Open, Half-Open)
      6. Adaptive Concurrency Control & Load Shedding
      7. Telemetry & Metrics Recording
    """

    def __init__(
        self,
        load_balancer: LoadBalancer,
        health_checker: HealthChecker,
        rate_limiter: RateLimiter,
        circuit_breaker: CircuitBreakerManager,
        adaptive_controller: AdaptiveTrafficController,
        cache_manager: HttpCacheManager,
        metrics_collector: MetricsCollector,
    ):
        self.load_balancer = load_balancer
        self.health_checker = health_checker
        self.rate_limiter = rate_limiter
        self.circuit_breaker = circuit_breaker
        self.adaptive_controller = adaptive_controller
        self.cache = cache_manager
        self.metrics = metrics_collector

        self._client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        limits = httpx.Limits(max_keepalive_connections=150, max_connections=500)
        self._client = httpx.AsyncClient(
            limits=limits,
            timeout=httpx.Timeout(settings.PROXY_TIMEOUT_SECONDS),
            follow_redirects=False,
        )
        await self.rate_limiter.init()
        logger.info("ProxyEngine initialized with HTTP client connection pool.")

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            logger.info("ProxyEngine HTTP client closed.")

    async def forward(self, request: Request, subpath: str) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        client_ip = request.client.host if request.client else "127.0.0.1"
        method = request.method
        path = f"/{subpath.lstrip('/')}"
        query_str = str(request.url.query)
        headers_dict = dict(request.headers)

        start_time = time.perf_counter()

        # -------------------------------------------------------------
        # 1. Rate Limiting Check
        # -------------------------------------------------------------
        rl_res: RateLimitResult = await self.rate_limiter.check(
            identifier=client_ip,
            route_prefix="proxy",
        )
        if not rl_res.allowed:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            RATE_LIMIT_DROPPED_TOTAL.labels(
                algorithm=self.rate_limiter.algorithm.value,
                route="/proxy"
            ).inc()
            self.metrics.record_request(
                request_id=request_id,
                client_ip=client_ip,
                method=method,
                path=path,
                backend_id=None,
                status_code=429,
                latency_ms=latency_ms,
                cache_status="BYPASS",
                algorithm=self.load_balancer.get_algorithm().value,
                error="Rate limit exceeded",
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Too many requests. Limit: {rl_res.limit}. Retry after {rl_res.retry_after}s.",
                        "retry_after": rl_res.retry_after,
                        "request_id": request_id,
                    }
                },
                headers={
                    "Retry-After": str(rl_res.retry_after),
                    "X-RateLimit-Limit": str(rl_res.limit),
                    "X-RateLimit-Remaining": str(rl_res.remaining),
                    "X-RateLimit-Reset": str(rl_res.reset_in),
                    "X-TrafficGuard-Request-ID": request_id,
                },
            )

        # -------------------------------------------------------------
        # 2. HTTP Caching Check
        # -------------------------------------------------------------
        cacheable, cache_reason = self.cache.is_request_cacheable(method, headers_dict)
        cache_key = ""
        if cacheable:
            cache_key = self.cache.compute_cache_key(method, path, query_str)
            cached_resp = await self.cache.get(cache_key)
            if cached_resp:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                HTTP_REQUESTS_TOTAL.labels(
                    method=method, status=str(cached_resp.status_code), backend="cache", cache_status="HIT"
                ).inc()
                self.metrics.record_request(
                    request_id=request_id,
                    client_ip=client_ip,
                    method=method,
                    path=path,
                    backend_id="cache",
                    status_code=cached_resp.status_code,
                    latency_ms=latency_ms,
                    cache_status="HIT",
                    algorithm=self.load_balancer.get_algorithm().value,
                )
                resp_headers = dict(cached_resp.headers)
                resp_headers["X-Cache"] = "HIT"
                resp_headers["X-TrafficGuard-Backend"] = "cache"
                resp_headers["X-TrafficGuard-Request-ID"] = request_id
                resp_headers["X-TrafficGuard-Latency-Ms"] = f"{latency_ms:.2f}"
                return Response(
                    content=cached_resp.body,
                    status_code=cached_resp.status_code,
                    headers=resp_headers,
                )
        else:
            self.cache.record_bypass()

        # -------------------------------------------------------------
        # 3. Healthy Backend Selection & Failover Loop
        # -------------------------------------------------------------
        routable_backends = self.health_checker.get_routable_backends()
        if not routable_backends:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            self.metrics.record_request(
                request_id=request_id,
                client_ip=client_ip,
                method=method,
                path=path,
                backend_id=None,
                status_code=503,
                latency_ms=latency_ms,
                cache_status="BYPASS",
                algorithm=self.load_balancer.get_algorithm().value,
                error="No healthy backends available",
            )
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "ALL_BACKENDS_UNHEALTHY",
                        "message": "All upstream backend services are currently unhealthy or in quarantine.",
                        "request_id": request_id,
                    }
                },
                headers={"X-TrafficGuard-Request-ID": request_id},
            )

        # Attempt to select a backend that is permitted by Circuit Breaker & Adaptive Control
        selected_backend: Optional[BackendNode] = None
        candidates = list(routable_backends)
        tried_backends = set()

        while candidates:
            candidate = self.load_balancer.select_backend(candidates)
            if not candidate or candidate.id in tried_backends:
                break
            tried_backends.add(candidate.id)

            # Check Circuit Breaker
            if not self.circuit_breaker.can_execute(candidate.id):
                # Candidate's breaker is OPEN, filter it out and try another candidate
                candidates = [c for c in candidates if c.id != candidate.id]
                continue

            # Check Adaptive Concurrency Control
            can_accept, shed_reason = self.adaptive_controller.can_accept(candidate.id)
            if not can_accept:
                LOAD_SHED_DROPPED_TOTAL.labels(backend_id=candidate.id).inc()
                # Candidate overloaded, try next candidate
                candidates = [c for c in candidates if c.id != candidate.id]
                continue

            selected_backend = candidate
            break

        if not selected_backend:
            # All available nodes were either tripped by Circuit Breaker or Load Shed
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            self.metrics.record_request(
                request_id=request_id,
                client_ip=client_ip,
                method=method,
                path=path,
                backend_id=None,
                status_code=503,
                latency_ms=latency_ms,
                cache_status="BYPASS",
                algorithm=self.load_balancer.get_algorithm().value,
                error="All backends tripped circuit breaker or shed load",
            )
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "BACKEND_CAPACITY_EXHAUSTED",
                        "message": "Available upstream nodes are currently tripped by Circuit Breaker or shedding load under overload.",
                        "request_id": request_id,
                    }
                },
                headers={"X-TrafficGuard-Request-ID": request_id},
            )

        # -------------------------------------------------------------
        # 4. Forwarding Request to Upstream Backend
        # -------------------------------------------------------------
        backend_id = selected_backend.id
        algo_name = self.load_balancer.get_algorithm().value

        # Increment in-flight tracking
        self.load_balancer.increment_active_connection(backend_id)
        self.adaptive_controller.record_start(backend_id)
        ACTIVE_CONNECTIONS.labels(backend_id=backend_id).set(
            self.load_balancer.get_active_connections(backend_id)
        )

        upstream_url = f"{selected_backend.url.rstrip('/')}{path}"
        if query_str:
            upstream_url = f"{upstream_url}?{query_str}"

        # Clean headers for proxy forwarding
        out_headers = {
            k: v for k, v in headers_dict.items()
            if k.lower() not in HOP_BY_HOP_HEADERS
        }
        out_headers["x-forwarded-for"] = f"{headers_dict.get('x-forwarded-for', client_ip)}, {client_ip}"
        out_headers["x-forwarded-proto"] = request.url.scheme
        out_headers["x-request-id"] = request_id

        req_body = await request.body()
        req_start = time.perf_counter()

        client = self._client or httpx.AsyncClient(timeout=settings.PROXY_TIMEOUT_SECONDS)
        should_close_client = (self._client is None)

        try:
            upstream_resp = await client.request(
                method=method,
                url=upstream_url,
                headers=out_headers,
                content=req_body,
            )
            req_latency_ms = (time.perf_counter() - req_start) * 1000.0

            # ---------------------------------------------------------
            # 5. Evaluate Response & Update Health / Circuit Breaker
            # ---------------------------------------------------------
            status_code = upstream_resp.status_code
            resp_bytes = upstream_resp.content

            if status_code < 500:
                self.health_checker.record_success(backend_id, req_latency_ms)
                self.circuit_breaker.record_success(backend_id)
                self.adaptive_controller.record_finish(backend_id, req_latency_ms, is_success=True)

                # Cache response if eligible
                if cacheable and self.cache.is_response_cacheable(status_code, dict(upstream_resp.headers), len(resp_bytes)):
                    await self.cache.set(
                        cache_key,
                        status_code=status_code,
                        headers=dict(upstream_resp.headers),
                        body=resp_bytes,
                        ttl=settings.CACHE_DEFAULT_TTL_SECONDS,
                    )
            else:
                # 5xx Backend Error
                error_msg = f"HTTP {status_code}"
                self.health_checker.record_failure(backend_id, error_msg)
                self.circuit_breaker.record_failure(backend_id)
                self.adaptive_controller.record_finish(backend_id, req_latency_ms, is_success=False)

            total_latency_ms = (time.perf_counter() - start_time) * 1000.0

            # Telemetry recording
            HTTP_REQUESTS_TOTAL.labels(
                method=method, status=str(status_code), backend=backend_id, cache_status="MISS"
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(backend=backend_id).observe(req_latency_ms / 1000.0)

            circuit_state = self.circuit_breaker.get_breaker(backend_id).state.value
            self.metrics.record_request(
                request_id=request_id,
                client_ip=client_ip,
                method=method,
                path=path,
                backend_id=backend_id,
                status_code=status_code,
                latency_ms=total_latency_ms,
                cache_status="MISS" if cacheable else "BYPASS",
                algorithm=algo_name,
                circuit_state=circuit_state,
                error=f"Backend returned HTTP {status_code}" if status_code >= 500 else None,
            )

            # Build response to client
            client_headers = {
                k: v for k, v in upstream_resp.headers.items()
                if k.lower() not in HOP_BY_HOP_HEADERS
            }
            client_headers["X-TrafficGuard-Backend"] = backend_id
            client_headers["X-TrafficGuard-Latency-Ms"] = f"{total_latency_ms:.2f}"
            client_headers["X-TrafficGuard-Request-ID"] = request_id
            client_headers["X-TrafficGuard-Algorithm"] = algo_name
            client_headers["X-TrafficGuard-Circuit"] = circuit_state
            client_headers["X-Cache"] = "MISS" if cacheable else "BYPASS"

            return Response(
                content=resp_bytes,
                status_code=status_code,
                headers=client_headers,
            )

        except httpx.TimeoutException:
            req_latency_ms = (time.perf_counter() - req_start) * 1000.0
            self.health_checker.record_failure(backend_id, "Timeout")
            self.circuit_breaker.record_failure(backend_id)
            self.adaptive_controller.record_finish(backend_id, req_latency_ms, is_success=False)

            self.metrics.record_request(
                request_id=request_id,
                client_ip=client_ip,
                method=method,
                path=path,
                backend_id=backend_id,
                status_code=504,
                latency_ms=req_latency_ms,
                cache_status="BYPASS",
                algorithm=algo_name,
                error="Gateway Timeout",
            )
            return JSONResponse(
                status_code=504,
                content={
                    "error": {
                        "code": "GATEWAY_TIMEOUT",
                        "message": f"Upstream backend '{backend_id}' timed out after {settings.PROXY_TIMEOUT_SECONDS}s.",
                        "backend": backend_id,
                        "request_id": request_id,
                    }
                },
                headers={
                    "X-TrafficGuard-Backend": backend_id,
                    "X-TrafficGuard-Request-ID": request_id,
                },
            )

        except httpx.ConnectError:
            req_latency_ms = (time.perf_counter() - req_start) * 1000.0
            self.health_checker.record_failure(backend_id, "Connection Refused")
            self.circuit_breaker.record_failure(backend_id)
            self.adaptive_controller.record_finish(backend_id, req_latency_ms, is_success=False)

            self.metrics.record_request(
                request_id=request_id,
                client_ip=client_ip,
                method=method,
                path=path,
                backend_id=backend_id,
                status_code=502,
                latency_ms=req_latency_ms,
                cache_status="BYPASS",
                algorithm=algo_name,
                error="Bad Gateway (Connection Refused)",
            )
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "code": "BAD_GATEWAY",
                        "message": f"Failed to connect to upstream backend '{backend_id}'. Connection refused.",
                        "backend": backend_id,
                        "request_id": request_id,
                    }
                },
                headers={
                    "X-TrafficGuard-Backend": backend_id,
                    "X-TrafficGuard-Request-ID": request_id,
                },
            )

        except Exception as e:
            req_latency_ms = (time.perf_counter() - req_start) * 1000.0
            self.health_checker.record_failure(backend_id, str(e))
            self.circuit_breaker.record_failure(backend_id)
            self.adaptive_controller.record_finish(backend_id, req_latency_ms, is_success=False)

            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "code": "BAD_GATEWAY",
                        "message": f"Proxy communication error: {str(e)}",
                        "backend": backend_id,
                        "request_id": request_id,
                    }
                },
                headers={"X-TrafficGuard-Request-ID": request_id},
            )

        finally:
            self.load_balancer.decrement_active_connection(backend_id)
            ACTIVE_CONNECTIONS.labels(backend_id=backend_id).set(
                self.load_balancer.get_active_connections(backend_id)
            )
            if should_close_client:
                await client.aclose()
