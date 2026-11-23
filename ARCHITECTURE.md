# TrafficGuard Architecture & Systems Specification

## 1. Architectural Overview

**TrafficGuard** is an adaptive traffic management, reverse proxy, and resilience platform designed to protect distributed microservices from cascading failures, traffic spikes, and slow downstreams.

Unlike static reverse proxies, TrafficGuard integrates active telemetry feedback loops between request execution, failure detection, dynamic concurrency control, and rate limiting.

```mermaid
flowchart TD
    Client(["Client Traffic (HTTP/HTTPS)"])

    subgraph TrafficGuard Gateway ["TrafficGuard API Gateway (Port 8000)"]
        Router["Reverse Proxy Router & Header Processor"]
        RL{"Rate Limiter<br/>Token Bucket / Sliding Window"}
        Cache{"HTTP Cache<br/>Redis / Memory"}
        HC["Health Checker & Flapping Detector"]
        LB["Load Balancer Engine<br/>RR / LeastConn / WeightedRR"]
        CB{"Circuit Breakers<br/>CLOSED / OPEN / HALF-OPEN"}
        AC{"Adaptive Concurrency<br/>AIMD Load Shedder"}
        Proxy["Async HTTP Client Connection Pool"]
        Tele["Metrics Collector & Prometheus Exporter"]
    end

    subgraph Distributed State
        Redis[("Redis 7<br/>Rate Limits & Cache")]
        Postgres[("PostgreSQL 16<br/>Logs & Config")]
    end

    subgraph Upstream Backend Pool
        B1["Backend 1: Alpha<br/>(Weight: 3, Port 8001)"]
        B2["Backend 2: Beta<br/>(Weight: 2, Port 8002)"]
        B3["Backend 3: Gamma<br/>(Weight: 1, Port 8003)"]
    end

    subgraph Observability & Control
        Dashboard["React + TypeScript Dashboard (Port 3000)"]
        Prom["Prometheus Scraper (/metrics)"]
    end

    Client --> Router
    Router --> RL
    RL -- Exceeded (429) --> Client
    RL -- Permitted --> Cache
    Cache -- Cache HIT (200) --> Client
    Cache -- Cache MISS --> HC
    HC --> LB
    LB --> CB
    CB -- Breaker OPEN (503) --> Client
    CB -- Permitted --> AC
    AC -- Concurrency Exceeded (503) --> Client
    AC -- Permitted --> Proxy

    Proxy --> B1
    Proxy --> B2
    Proxy --> B3

    Proxy -. Feedback Latency & Status .-> HC
    Proxy -. Feedback Latency & Status .-> CB
    Proxy -. Feedback Latency & Status .-> AC
    Proxy -. Record Log .-> Tele

    Tele --> Dashboard
    Tele --> Prom
    RL <--> Redis
    Cache <--> Redis
    Tele --> Postgres
```

---

## 2. Request Lifecycle & Decision Tree

When a request enters TrafficGuard (`/api/v1/proxy/{path}`), it passes through seven distinct protective gates before touching downstream servers:

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant GW as Gateway Proxy
    participant RL as Rate Limiter (Redis)
    participant Cache as HTTP Cache
    participant LB as Load Balancer
    participant CB as Circuit Breaker
    participant AC as Adaptive Controller
    participant Backend as Upstream Backend

    Client->>GW: HTTP Request (Method, Path, Headers)
    GW->>RL: Check Rate Limit (IP / Route)
    alt Rate Limit Exceeded
        RL-->>GW: Limit Exceeded (Tokens Exhausted)
        GW-->>Client: HTTP 429 Too Many Requests (Retry-After)
    else Rate Limit Permitted
        RL-->>GW: Permitted (Tokens Remaining)
    end

    GW->>Cache: Query Cache (Safe GET)
    alt Cache HIT
        Cache-->>GW: Cached Payload
        GW-->>Client: HTTP 200 OK (X-Cache: HIT)
    else Cache MISS
        Cache-->>GW: Cache Miss (Proceed)
    end

    GW->>LB: Select Candidate (Active & Healthy Nodes)
    LB-->>GW: Candidate Node (e.g. backend-1)

    GW->>CB: Verify Circuit State (backend-1)
    alt Circuit Breaker is OPEN
        CB-->>GW: Breaker Tripped (Cooldown Active)
        GW->>LB: Failover to Next Healthy Node
    else Circuit CLOSED / HALF-OPEN
        CB-->>GW: Proceed
    end

    GW->>AC: Check Dynamic Concurrency (backend-1)
    alt In-flight >= Dynamic Concurrency Limit
        AC-->>GW: Load Shed (Overload Prevention)
        GW-->>Client: HTTP 503 Service Overloaded (Shedding)
    else Concurrency Permitted
        AC-->>GW: Proceed & Increment In-flight
    end

    GW->>Backend: Forward Request (Stripped Hop-by-Hop, Injected X-Forwarded-*)
    Backend-->>GW: Upstream Response (Status, Payload, Headers)

    par Async Telemetry Feedback
        GW->>CB: Record Success/Failure
        GW->>AC: Record Latency & Adjust Limit
        GW->>Cache: Store Response (if GET & Cacheable)
        GW->>LB: Decrement Active Connection
    end

    GW-->>Client: Response (X-TrafficGuard-Backend, X-TrafficGuard-Latency-Ms)
```

---

## 3. Core Subsystems & Algorithmic Design

### 3.1 Load Balancing Engine (`gateway/core/load_balancer.py`)
Modular strategy pattern supporting dynamic hot-swapping at runtime:
1. **Round Robin**: Thread-safe index increment modulo healthy backend count ($O(1)$).
2. **Least Connections**: Dynamically inspects `active_connections` map, routing to the candidate with minimum in-flight load.
3. **Smooth Weighted Round Robin (Nginx Algorithm)**:
   - For all available nodes: $current\_weight_i \leftarrow current\_weight_i + effective\_weight_i$
   - Select node $k$ with maximum $current\_weight_k$.
   - Decrement selected node: $current\_weight_k \leftarrow current\_weight_k - \sum effective\_weights$.
   - **Advantage**: Avoids burst-clustering where high-weight nodes receive all requests consecutively.

### 3.2 Active & Passive Health Checker (`gateway/core/health_checker.py`)
- **Active Polling**: Background asyncio task asynchronously pings `/health` endpoints at configurable intervals (`HEALTH_CHECK_INTERVAL_SECONDS = 3.0s`).
- **Consecutive Thresholds**:
  - `unhealthy_threshold = 3`: 3 consecutive failures mark node as `UNHEALTHY`.
  - `healthy_threshold = 2`: 2 consecutive successes required to restore node to `HEALTHY`.
- **Flapping Detection & Dampening**:
  - Tracks state flips ($HEALTHY \leftrightarrow UNHEALTHY$) in a rolling window of 60s.
  - If state flips $\ge 3$, the backend is flagged as **FLAPPING**.
  - Imposes an exponential dampening quarantine (`FLAPPING_PENALTY_SECONDS = 30.0s`). During quarantine, the node is barred from routing even if ping probes return 200 OK.

### 3.3 Distributed Rate Limiting (`gateway/core/rate_limiter.py`)
- **Token Bucket Algorithm**:
  - Refills tokens at steady rate $r$ up to capacity $C$.
  - Atomic Redis Lua script prevents race conditions across multi-worker deployments.
- **Sliding Window Log Algorithm**:
  - Redis sorted set (`ZADD`, `ZREMRANGEBYSCORE`, `ZCARD`) calculating exact request timestamps in rolling window $[now - window, now]$.
- **Graceful Fallback**: In-memory high-precision fallback when Redis is absent.

### 3.4 3-State Circuit Breaker (`gateway/core/circuit_breaker.py`)
- **CLOSED**: Traffic passes freely. Consecutive failures are tracked.
- **OPEN**: Tripped when failure threshold (4 consecutive failures or >50% failure rate) is breached. All requests fail fast with `HTTP 503` without contacting backend.
- **HALF-OPEN**: Initiated when `recovery_timeout` (8.0s) elapses. Permits a limited trial budget (3 probe requests).
  - If all probe requests succeed $\rightarrow$ transitions to **CLOSED**.
  - If ANY probe fails $\rightarrow$ immediately trips back to **OPEN** with extended cooldown.

### 3.5 Adaptive Traffic Controller (`gateway/core/adaptive_controller.py`)
- **Signals**: Monitors rolling $P_{95}$ latency and rolling error rate.
- **AIMD Dynamic Concurrency**:
  - When $P_{95} \le \text{SLA Target (120ms)}$ and Error Rate $< 5\%$:
    $$\text{Limit}_{new} = \min(\text{Limit}_{max}, \text{Limit} + 1)$$
  - When $P_{95} > \text{Max SLA (350ms)}$ or Error Rate $\ge 15\%$:
    $$\text{Limit}_{new} = \max(\text{Limit}_{min}, \lfloor \text{Limit} \times 0.7 \rfloor)$$
- **Explainability**: Every decision creates an auditable record logging timestamp, action, reason, previous limit, new limit, and observed metrics.

### 3.6 HTTP Caching Engine (`gateway/core/cache.py`)
- **Cache Key**: SHA-256 hash of `METHOD:PATH:SORTED_QUERY_PARAMS`.
- **Safety**: Automatically bypasses requests with `Authorization`, session cookies, or `Cache-Control: no-cache`. Responses with `Set-Cookie` or `Cache-Control: private` are never stored.
