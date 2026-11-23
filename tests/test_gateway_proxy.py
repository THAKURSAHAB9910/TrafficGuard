import pytest
from httpx import AsyncClient, ASGITransport
from gateway.main import app
from gateway.config import BackendNode, LoadBalancerAlgorithm


@pytest.mark.asyncio
async def test_gateway_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "UP"


@pytest.mark.asyncio
async def test_gateway_admin_algorithm_switch():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Check initial algorithm
        r1 = await client.get("/api/admin/algorithm")
        assert r1.status_code == 200
        assert r1.json()["algorithm"] in ["round_robin", "least_connections", "weighted_round_robin"]

        # Switch to least_connections
        r2 = await client.post("/api/admin/algorithm", json={"algorithm": "least_connections"})
        assert r2.status_code == 200
        assert r2.json()["algorithm"] == "least_connections"

        # Verify change
        r3 = await client.get("/api/admin/algorithm")
        assert r3.json()["algorithm"] == "least_connections"


@pytest.mark.asyncio
async def test_gateway_metrics_summary():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/metrics/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data
        assert "total_requests" in data["metrics"]
        assert "circuit_breakers" in data
        assert "cache" in data


@pytest.mark.asyncio
async def test_gateway_rate_limit_blocking():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Set rate limit capacity very low (e.g. 2)
        await client.post("/api/admin/ratelimit", json={"capacity": 2, "refill_rate": 0.1})

        # Send requests until 429
        responses = []
        for _ in range(5):
            r = await client.get("/api/v1/proxy/test")
            responses.append(r.status_code)

        assert 429 in responses
        # Reset rate limit back
        await client.post("/api/admin/ratelimit", json={"capacity": 50, "refill_rate": 20.0})


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        assert "trafficguard_http_requests_total" in resp.text
