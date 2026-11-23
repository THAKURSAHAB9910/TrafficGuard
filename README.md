# TrafficGuard — Adaptive Traffic Management & Resilience Platform

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.14-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61dafb.svg)](https://react.dev)
[![Vercel Deployment](https://img.shields.io/badge/Vercel-Live%20Demo-black?logo=vercel)](https://trafficguard-vishesh9910.vercel.app)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ed.svg)](https://docker.com)
[![Tests](https://img.shields.io/badge/Tests-20%20Passed%20(100%25)-brightgreen.svg)]()

**TrafficGuard** is an intelligent, production-ready API gateway and reverse proxy platform designed to protect distributed microservices against cascading failures, unexpected traffic surges, failing downstreams, and degraded servers.

🌐 **Live Vercel Production Deployment:** [https://trafficguard-vishesh9910.vercel.app](https://trafficguard-vishesh9910.vercel.app)

It sits between clients and multiple upstream backend services, actively distributing load, detecting failures, enforcing distributed rate limits, isolating unhealthy services via circuit breakers, and dynamically shedding load using adaptive concurrency control.

---

## 1. Key Features

- **Real Asynchronous Reverse Proxy**: Custom reverse proxy built with FastAPI and `httpx` connection pooling. Preserves headers (`X-Forwarded-For`, `X-Forwarded-Proto`, `X-Request-ID`), strips hop-by-hop headers, handles timeouts, and injects observability headers.
- **Modular Load Balancing Engine**:
  - **Round Robin**: Atomic sequential distribution.
  - **Least Connections**: Real-time in-flight connection tracking routing to least loaded node.
  - **Smooth Weighted Round Robin**: Nginx-grade smooth weighted algorithm preventing traffic clustering.
- **Active & Passive Health Monitoring**:
  - Background asynchronous active polling of upstream `/health` endpoints.
  - Passive error interception on 5xx and connection timeouts.
  - **Flapping Detection & Dampening**: Mitigates bouncing servers with exponential cooldown quarantine.
  - Automatic zero-downtime pool restoration upon recovery.
- **Distributed Rate Limiting**:
  - **Token Bucket** & **Sliding Window Log** algorithms.
  - Atomic Redis Lua script execution with automatic in-memory fallback.
  - Returns standardized HTTP 429 responses with `Retry-After`, `X-RateLimit-*` headers.
- **3-State Circuit Breakers**:
  - `CLOSED`, `OPEN`, `HALF-OPEN` state machine.
  - Per-backend failure thresholds, recovery intervals, and trial probe limits.
  - Immediate fail-fast protection preventing server thrashing.
- **Adaptive Traffic Control (AIMD)**:
  - Continuously samples response latency ($P_{95}$) and error rates.
  - Uses Additive Increase / Multiplicative Decrease (AIMD) dynamic concurrency limiting.
  - Automatically sheds overload before downstream servers collapse.
  - Generates auditable, explainable decision records.
- **Safe HTTP Response Caching**:
  - Redis/memory cached GET responses with configurable TTL.
  - Automatically bypasses authenticated, session-cookie, and private responses.
  - Delivers sub-millisecond response times (~10x latency speedup on cache HITs).
- **Interactive React + TypeScript Dashboard**:
  - Displays real-time RPS, traffic distribution, backend health, latency percentiles (p50, p95, p99), error rates, rate limit blocks, circuit breaker badges, and a live request audit table.
  - Built-in simulation control panel for live fault injection and chaos testing.

---

## 2. Technology Stack

- **Gateway & Backends**: Python 3.11+, FastAPI, Uvicorn, HTTPX AsyncClient
- **Database**: PostgreSQL 16 (async SQLAlchemy + asyncpg, with resilient SQLite fallback)
- **Distributed Cache & Rate Limiting**: Redis 7 (with Lua scripting)
- **Frontend Dashboard**: React 18, TypeScript, Vite, Tailwind CSS, Lucide Icons
- **Deployment**: Docker & Docker Compose
- **Test Suite**: Pytest, Pytest-Asyncio
- **Load Testing**: Custom async Python benchmark harness and Locust

---

## 3. Quickstart Guide

### Option A: Running with Docker Compose (Recommended)

Start the full stack (PostgreSQL, Redis, 3 Backends, API Gateway, and Dashboard UI) with a single command:

```bash
docker compose up --build
```

Access the components:
- **React Dashboard UI**: [http://localhost:3000](http://localhost:3000)
- **Gateway Reverse Proxy**: [http://localhost:8000](http://localhost:8000)
- **Prometheus Telemetry**: [http://localhost:8000/metrics](http://localhost:8000/metrics)
- **Backend 1 (Alpha)**: [http://localhost:8001](http://localhost:8001)
- **Backend 2 (Beta)**: [http://localhost:8002](http://localhost:8002)
- **Backend 3 (Gamma)**: [http://localhost:8003](http://localhost:8003)

---

### Option B: Local Execution (Without Docker)

You can run TrafficGuard directly using Python and Node:

1. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Launch all services using the orchestrator**:
   ```bash
   python scripts/run_all.py
   ```
   *This automatically launches Backend 1, Backend 2, Backend 3, the Gateway on port 8000, and the React Dashboard on port 3000.*

---

## 4. Automated Testing & Verification

Run the comprehensive automated Pytest suite (20 unit, integration, and failover tests):

```bash
python -m pytest tests/ -v
```

### Running Failure Injection & Automatic Failover Scenario

Run the automated chaos and failure injection script:

```bash
python scripts/inject_failure.py
```

This script systematically tests:
1. Baseline healthy traffic distribution across all 3 nodes.
2. Injects simulated crash outage into Backend 2.
3. Verifies Gateway detects the failure and routes 100% of traffic to healthy nodes (zero dropped requests).
4. Restores Backend 2.
5. Verifies consecutive probe checks and automatic re-entry into the routing pool.

---

## 5. Performance Evaluation & Load Testing

Run the automated async load test harness to benchmark Round Robin vs Least Connections vs Weighted Round Robin across concurrency levels:

```bash
python scripts/load_test.py
```

*Results are recorded directly to [PERFORMANCE.md](file:///c:/Users/Vishe/Downloads/TRAFFIC%20GUARD/PERFORMANCE.md).*

### Running Locust Load Generator

```bash
locust -f scripts/locustfile.py --host http://localhost:8000
```
Then open [http://localhost:8089](http://localhost:8089) to run interactive distributed traffic simulation.

---

## 6. Architecture & Request Lifecycle

Detailed architectural flowcharts, sequence diagrams, and mathematical formulation of the algorithms are documented in [ARCHITECTURE.md](file:///c:/Users/Vishe/Downloads/TRAFFIC%20GUARD/ARCHITECTURE.md).

---

## 7. API Reference

### Proxy Traffic
- `GET/POST/PUT/DELETE /api/v1/proxy/{path}`: Entry point for proxied client traffic.

### Administration & Control
- `GET /api/admin/backends`: List backend nodes, weights, health, and circuit breaker states.
- `POST /api/admin/backends`: Register new backend node.
- `PUT /api/admin/backends/{id}/weight`: Dynamically adjust backend routing weight.
- `GET /api/admin/algorithm`: Get active load balancing algorithm.
- `POST /api/admin/algorithm`: Switch algorithm (`round_robin`, `least_connections`, `weighted_round_robin`).
- `POST /api/admin/ratelimit`: Update rate limiter policy (capacity, refill rate, window).
- `POST /api/admin/circuit-breaker/reset`: Reset all circuit breakers to CLOSED.
- `POST /api/admin/cache/clear`: Flush HTTP cache.
- `POST /api/admin/simulate/{backend_id}/{action}`: Inject faults (`delay`, `error`, `status`, `reset`).

### Observability & Metrics
- `GET /api/metrics/summary`: JSON real-time telemetry (RPS, latency percentiles, error rate).
- `GET /api/metrics/live-logs`: Stream of recent requests with latency and status codes.
- `GET /metrics`: Standard Prometheus metrics exposition.
- `GET /health`: Gateway operational status.
