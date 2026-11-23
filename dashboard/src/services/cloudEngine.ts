import {
  MetricsSummary,
  BackendNodeAdmin,
  RequestLog,
  BackendAdaptiveStats,
  AdaptiveDecision,
  CircuitBreakerInfo,
  BackendHealthInfo,
} from '../types';

interface InternalBackend {
  id: string;
  name: string;
  url: string;
  weight: number;
  current_weight: number;
  is_active: boolean;
  is_healthy: boolean;
  is_flapping: boolean;
  active_connections: number;
  total_routed: number;
  consecutive_failures: number;
  consecutive_successes: number;
  simulated_delay_ms: number;
  simulated_error_rate: number;
  circuit_state: 'CLOSED' | 'OPEN' | 'HALF_OPEN';
  circuit_opened_at: number;
  circuit_probe_count: number;
  concurrency_limit: number;
  in_flight: number;
  p95_latency: number;
  error_rate: number;
  last_error: string | null;
}

class CloudSimulationEngine {
  private algorithm: string = 'weighted_round_robin';
  private rateLimiterAlgorithm: string = 'token_bucket';

  private tokenBucket = {
    capacity: 60,
    tokens: 60,
    refillRate: 20,
    lastRefill: Date.now(),
  };
  private slidingWindow = {
    windowSeconds: 60,
    limit: 120,
    timestamps: [] as number[],
  };

  private cacheStats = {
    hits: 142,
    misses: 856,
    bypasses: 124,
    cachedEntries: 18,
  };

  private metrics = {
    total_requests: 1122,
    total_successes: 1084,
    total_client_errors: 18,
    total_server_errors: 20,
    rate_limit_rejections: 18,
    circuit_breaker_rejections: 14,
    load_shed_rejections: 6,
    recent_latencies: [18, 22, 19, 25, 31, 24, 17, 29, 35, 21, 26, 20, 23, 28, 30] as number[],
    backend_routed_counts: {
      'backend-1': 561,
      'backend-2': 374,
      'backend-3': 187,
    } as Record<string, number>,
    backend_error_counts: {
      'backend-1': 8,
      'backend-2': 7,
      'backend-3': 5,
    } as Record<string, number>,
  };

  private backends: Map<string, InternalBackend> = new Map([
    [
      'backend-1',
      {
        id: 'backend-1',
        name: 'Backend Alpha (Primary)',
        url: 'http://backend-1:8001',
        weight: 3,
        current_weight: 0,
        is_active: true,
        is_healthy: true,
        is_flapping: false,
        active_connections: 3,
        total_routed: 561,
        consecutive_failures: 0,
        consecutive_successes: 12,
        simulated_delay_ms: 0,
        simulated_error_rate: 0,
        circuit_state: 'CLOSED',
        circuit_opened_at: 0,
        circuit_probe_count: 0,
        concurrency_limit: 50,
        in_flight: 3,
        p95_latency: 28.5,
        error_rate: 0.014,
        last_error: null,
      },
    ],
    [
      'backend-2',
      {
        id: 'backend-2',
        name: 'Backend Beta (Standard)',
        url: 'http://backend-2:8002',
        weight: 2,
        current_weight: 0,
        is_active: true,
        is_healthy: true,
        is_flapping: false,
        active_connections: 2,
        total_routed: 374,
        consecutive_failures: 0,
        consecutive_successes: 12,
        simulated_delay_ms: 0,
        simulated_error_rate: 0,
        circuit_state: 'CLOSED',
        circuit_opened_at: 0,
        circuit_probe_count: 0,
        concurrency_limit: 40,
        in_flight: 2,
        p95_latency: 32.1,
        error_rate: 0.018,
        last_error: null,
      },
    ],
    [
      'backend-3',
      {
        id: 'backend-3',
        name: 'Backend Gamma (Edge)',
        url: 'http://backend-3:8003',
        weight: 1,
        current_weight: 0,
        is_active: true,
        is_healthy: true,
        is_flapping: false,
        active_connections: 1,
        total_routed: 187,
        consecutive_failures: 0,
        consecutive_successes: 12,
        simulated_delay_ms: 0,
        simulated_error_rate: 0,
        circuit_state: 'CLOSED',
        circuit_opened_at: 0,
        circuit_probe_count: 0,
        concurrency_limit: 30,
        in_flight: 1,
        p95_latency: 36.8,
        error_rate: 0.026,
        last_error: null,
      },
    ],
  ]);

  private recentLogs: RequestLog[] = [];
  private adaptiveDecisions: Map<string, AdaptiveDecision[]> = new Map([
    ['backend-1', []],
    ['backend-2', []],
    ['backend-3', []],
  ]);
  private roundRobinIndex: number = 0;
  private intervalTimer: any = null;

  constructor() {
    this.seedInitialLogs();
    this.startBackgroundTraffic();
  }

  private seedInitialLogs() {
    const methods = ['GET', 'GET', 'POST', 'GET'];
    const paths = ['/api/v1/proxy/api/data', '/api/v1/proxy/api/status', '/api/v1/proxy/api/compute'];
    const ips = ['192.168.1.42', '10.0.4.15', '172.16.8.99', '192.168.1.105'];
    const backendIds = ['backend-1', 'backend-2', 'backend-3'];

    const now = Date.now();
    for (let i = 25; i >= 0; i--) {
      const bId = backendIds[i % 3];
      this.recentLogs.push({
        id: `req-seed-${i}`,
        timestamp: now - i * 1400,
        client_ip: ips[i % ips.length],
        method: methods[i % methods.length],
        path: paths[i % paths.length],
        backend_id: bId,
        status_code: 200,
        latency_ms: Math.round(18 + (i % 7) * 4),
        cache_status: i % 4 === 0 ? 'HIT' : 'MISS',
        algorithm: this.algorithm,
        circuit_state: 'CLOSED',
        error: null,
      });
    }
  }

  private startBackgroundTraffic() {
    if (this.intervalTimer) return;
    this.intervalTimer = setInterval(() => {
      this.tickBackground();
    }, 1200);
  }

  private tickBackground() {
    const now = Date.now();
    const elapsedSec = (now - this.tokenBucket.lastRefill) / 1000;
    this.tokenBucket.tokens = Math.min(
      this.tokenBucket.capacity,
      this.tokenBucket.tokens + elapsedSec * this.tokenBucket.refillRate
    );
    this.tokenBucket.lastRefill = now;

    this.backends.forEach((backend) => {
      if (backend.circuit_state === 'OPEN') {
        if (now - backend.circuit_opened_at > 10000) {
          backend.circuit_state = 'HALF_OPEN';
          backend.circuit_probe_count = 0;
        }
      }
    });

    const count = Math.floor(Math.random() * 3) + 2;
    for (let i = 0; i < count; i++) {
      this.processSimulatedRequest('/api/data', 'GET', `192.168.1.${Math.floor(Math.random() * 50) + 10}`);
    }
  }

  private pickBackend(): InternalBackend | null {
    const candidates = Array.from(this.backends.values()).filter(
      (b) => b.is_active && b.is_healthy && b.circuit_state !== 'OPEN'
    );
    if (candidates.length === 0) return null;

    if (this.algorithm === 'round_robin') {
      this.roundRobinIndex = (this.roundRobinIndex + 1) % candidates.length;
      return candidates[this.roundRobinIndex];
    }

    if (this.algorithm === 'least_conn') {
      return candidates.reduce((prev, curr) =>
        curr.active_connections < prev.active_connections ? curr : prev
      );
    }

    let totalWeight = 0;
    let selected: InternalBackend | null = null;
    for (const b of candidates) {
      b.current_weight += b.weight;
      totalWeight += b.weight;
      if (!selected || b.current_weight > selected.current_weight) {
        selected = b;
      }
    }
    if (selected) {
      selected.current_weight -= totalWeight;
    }
    return selected || candidates[0];
  }

  private processSimulatedRequest(
    path: string,
    method: string,
    clientIp: string
  ): { status_code: number; backend_id: string | null; latency_ms: number } {
    this.metrics.total_requests++;
    const now = Date.now();

    if (this.rateLimiterAlgorithm === 'token_bucket') {
      if (this.tokenBucket.tokens < 1) {
        this.metrics.rate_limit_rejections++;
        this.metrics.total_client_errors++;
        this.pushLog({
          id: `req-${Date.now()}-${Math.random().toString(36).substring(7)}`,
          timestamp: now,
          client_ip: clientIp,
          method,
          path,
          backend_id: null,
          status_code: 429,
          latency_ms: 2,
          cache_status: 'BYPASS',
          algorithm: this.algorithm,
          circuit_state: null,
          error: 'Rate limit exceeded: Token Bucket empty',
        });
        return { status_code: 429, backend_id: null, latency_ms: 2 };
      }
      this.tokenBucket.tokens -= 1;
    } else {
      const cutoff = now - this.slidingWindow.windowSeconds * 1000;
      this.slidingWindow.timestamps = this.slidingWindow.timestamps.filter((t) => t > cutoff);
      if (this.slidingWindow.timestamps.length >= this.slidingWindow.limit) {
        this.metrics.rate_limit_rejections++;
        this.metrics.total_client_errors++;
        this.pushLog({
          id: `req-${Date.now()}-${Math.random().toString(36).substring(7)}`,
          timestamp: now,
          client_ip: clientIp,
          method,
          path,
          backend_id: null,
          status_code: 429,
          latency_ms: 2,
          cache_status: 'BYPASS',
          algorithm: this.algorithm,
          circuit_state: null,
          error: 'Rate limit exceeded: Sliding Window full',
        });
        return { status_code: 429, backend_id: null, latency_ms: 2 };
      }
      this.slidingWindow.timestamps.push(now);
    }

    const isEligibleForCache = method === 'GET' && !path.includes('burst');
    if (isEligibleForCache && Math.random() < 0.22) {
      this.cacheStats.hits++;
      this.metrics.total_successes++;
      const lat = Math.floor(Math.random() * 4) + 1;
      this.pushLog({
        id: `req-${Date.now()}-${Math.random().toString(36).substring(7)}`,
        timestamp: now,
        client_ip: clientIp,
        method,
        path,
        backend_id: 'cache',
        status_code: 200,
        latency_ms: lat,
        cache_status: 'HIT',
        algorithm: this.algorithm,
        circuit_state: null,
        error: null,
      });
      return { status_code: 200, backend_id: 'cache', latency_ms: lat };
    }
    if (isEligibleForCache) {
      this.cacheStats.misses++;
    } else {
      this.cacheStats.bypasses++;
    }

    const backend = this.pickBackend();
    if (!backend) {
      this.metrics.circuit_breaker_rejections++;
      this.metrics.total_server_errors++;
      this.pushLog({
        id: `req-${Date.now()}-${Math.random().toString(36).substring(7)}`,
        timestamp: now,
        client_ip: clientIp,
        method,
        path,
        backend_id: null,
        status_code: 503,
        latency_ms: 5,
        cache_status: 'MISS',
        algorithm: this.algorithm,
        circuit_state: 'OPEN',
        error: 'No healthy or available backend in pool',
      });
      return { status_code: 503, backend_id: null, latency_ms: 5 };
    }

    if (backend.in_flight >= backend.concurrency_limit) {
      this.metrics.load_shed_rejections++;
      this.metrics.total_server_errors++;
      this.recordAdaptiveDecision(
        backend.id,
        'SHED',
        `In-flight ${backend.in_flight} >= limit ${backend.concurrency_limit}`,
        backend.concurrency_limit,
        backend.concurrency_limit
      );
      this.pushLog({
        id: `req-${Date.now()}-${Math.random().toString(36).substring(7)}`,
        timestamp: now,
        client_ip: clientIp,
        method,
        path,
        backend_id: backend.id,
        status_code: 503,
        latency_ms: 4,
        cache_status: 'MISS',
        algorithm: this.algorithm,
        circuit_state: backend.circuit_state,
        error: 'Adaptive load shedding: Concurrency limit reached',
      });
      return { status_code: 503, backend_id: backend.id, latency_ms: 4 };
    }

    backend.total_routed++;
    this.metrics.backend_routed_counts[backend.id] =
      (this.metrics.backend_routed_counts[backend.id] || 0) + 1;

    let latency =
      Math.floor(Math.random() * 15) +
      (backend.id === 'backend-1' ? 14 : backend.id === 'backend-2' ? 22 : 30);
    if (backend.simulated_delay_ms > 0) {
      latency += backend.simulated_delay_ms;
    }

    const isError =
      backend.simulated_error_rate > 0 && Math.random() < backend.simulated_error_rate;

    if (isError) {
      this.metrics.total_server_errors++;
      this.metrics.backend_error_counts[backend.id] =
        (this.metrics.backend_error_counts[backend.id] || 0) + 1;
      backend.consecutive_failures++;
      backend.consecutive_successes = 0;
      backend.last_error = 'HTTP 500 Internal Server Error (Fault Injected)';

      if (backend.circuit_state === 'CLOSED' && backend.consecutive_failures >= 3) {
        backend.circuit_state = 'OPEN';
        backend.circuit_opened_at = now;
      } else if (backend.circuit_state === 'HALF_OPEN') {
        backend.circuit_state = 'OPEN';
        backend.circuit_opened_at = now;
      }

      this.pushLog({
        id: `req-${Date.now()}-${Math.random().toString(36).substring(7)}`,
        timestamp: now,
        client_ip: clientIp,
        method,
        path,
        backend_id: backend.id,
        status_code: 500,
        latency_ms: latency,
        cache_status: 'MISS',
        algorithm: this.algorithm,
        circuit_state: backend.circuit_state,
        error: 'HTTP 500 Internal Server Error',
      });
      return { status_code: 500, backend_id: backend.id, latency_ms: latency };
    }

    this.metrics.total_successes++;
    backend.consecutive_successes++;
    backend.consecutive_failures = 0;
    backend.last_error = null;

    if (backend.circuit_state === 'HALF_OPEN') {
      backend.circuit_probe_count++;
      if (backend.circuit_probe_count >= 2) {
        backend.circuit_state = 'CLOSED';
      }
    }

    this.metrics.recent_latencies.push(latency);
    if (this.metrics.recent_latencies.length > 50) {
      this.metrics.recent_latencies.shift();
    }

    this.pushLog({
      id: `req-${Date.now()}-${Math.random().toString(36).substring(7)}`,
      timestamp: now,
      client_ip: clientIp,
      method,
      path,
      backend_id: backend.id,
      status_code: 200,
      latency_ms: latency,
      cache_status: 'MISS',
      algorithm: this.algorithm,
      circuit_state: backend.circuit_state,
      error: null,
    });

    return { status_code: 200, backend_id: backend.id, latency_ms: latency };
  }

  private pushLog(log: RequestLog) {
    this.recentLogs.unshift(log);
    if (this.recentLogs.length > 60) {
      this.recentLogs.pop();
    }
  }

  private recordAdaptiveDecision(
    backendId: string,
    action: 'SHED' | 'EXPAND' | 'HOLD' | 'REJECT',
    reason: string,
    prevLimit: number,
    newLimit: number
  ) {
    const list = this.adaptiveDecisions.get(backendId) || [];
    const b = this.backends.get(backendId);
    list.unshift({
      backend_id: backendId,
      timestamp: Date.now(),
      action,
      reason,
      observed_p95_ms: b ? b.p95_latency : 30,
      observed_error_rate: b ? b.error_rate : 0.01,
      previous_limit: prevLimit,
      new_limit: newLimit,
      in_flight: b ? b.in_flight : 2,
    });
    if (list.length > 20) list.pop();
    this.adaptiveDecisions.set(backendId, list);
  }

  public getSummary(): MetricsSummary {
    const sortedLatencies = [...this.metrics.recent_latencies].sort((a, b) => a - b);
    const n = sortedLatencies.length || 1;
    const avg = Math.round(
      sortedLatencies.reduce((sum, v) => sum + v, 0) / n
    );
    const p50 = sortedLatencies[Math.floor(n * 0.5)] || 20;
    const p95 = sortedLatencies[Math.floor(n * 0.95)] || 38;
    const p99 = sortedLatencies[Math.floor(n * 0.99)] || 54;
    const min = sortedLatencies[0] || 12;
    const max = sortedLatencies[sortedLatencies.length - 1] || 60;

    const totalReq = Math.max(this.metrics.total_requests, 1);
    const errorRatePct = parseFloat(
      (((this.metrics.total_server_errors + this.metrics.total_client_errors) / totalReq) * 100).toFixed(2)
    );

    const circuitBreakers: Record<string, CircuitBreakerInfo> = {};
    const adaptiveController: Record<string, BackendAdaptiveStats> = {};
    const backendsHealth: Record<string, BackendHealthInfo> = {};

    this.backends.forEach((b) => {
      circuitBreakers[b.id] = {
        backend_id: b.id,
        state: b.circuit_state,
        consecutive_failures: b.consecutive_failures,
        consecutive_successes: b.consecutive_successes,
        failure_threshold: 3,
        recovery_timeout: 10,
        retry_after_seconds: b.circuit_state === 'OPEN' ? Math.max(0, 10 - Math.floor((Date.now() - b.circuit_opened_at) / 1000)) : 0,
        last_state_change: b.circuit_opened_at || Date.now(),
      };

      adaptiveController[b.id] = {
        backend_id: b.id,
        current_concurrency_limit: b.concurrency_limit,
        in_flight: b.in_flight,
        p95_latency_ms: b.p95_latency,
        avg_latency_ms: b.p95_latency * 0.65,
        error_rate: b.error_rate,
        total_shed_requests: this.metrics.load_shed_rejections,
        recent_decisions: this.adaptiveDecisions.get(b.id) || [],
      };

      backendsHealth[b.id] = {
        id: b.id,
        name: b.name,
        url: b.url,
        weight: b.weight,
        is_active: b.is_active,
        is_healthy: b.is_healthy,
        is_routable: b.is_active && b.is_healthy && b.circuit_state !== 'OPEN',
        is_flapping: b.is_flapping,
        flapping_penalty_remaining: 0,
        flap_count: 0,
        consecutive_successes: b.consecutive_successes,
        consecutive_failures: b.consecutive_failures,
        last_latency_ms: b.p95_latency,
        last_error: b.last_error,
        last_check_time: Date.now(),
      };
    });

    const cacheTotal = this.cacheStats.hits + this.cacheStats.misses + this.cacheStats.bypasses;
    const hitRatePct = cacheTotal > 0 ? parseFloat(((this.cacheStats.hits / cacheTotal) * 100).toFixed(1)) : 0;

    return {
      gateway_status: 'healthy',
      algorithm: this.algorithm,
      rate_limiter_algorithm: this.rateLimiterAlgorithm,
      metrics: {
        total_requests: this.metrics.total_requests,
        current_rps: Math.floor(Math.random() * 12) + 24,
        total_successes: this.metrics.total_successes,
        total_client_errors: this.metrics.total_client_errors,
        total_server_errors: this.metrics.total_server_errors,
        rate_limit_rejections: this.metrics.rate_limit_rejections,
        circuit_breaker_rejections: this.metrics.circuit_breaker_rejections,
        load_shed_rejections: this.metrics.load_shed_rejections,
        error_rate_pct: errorRatePct,
        latency: { avg, p50, p95, p99, min, max },
        backend_routed_counts: { ...this.metrics.backend_routed_counts },
        backend_error_counts: { ...this.metrics.backend_error_counts },
      },
      cache: {
        hits: this.cacheStats.hits,
        misses: this.cacheStats.misses,
        bypasses: this.cacheStats.bypasses,
        total_requests: cacheTotal,
        hit_rate: hitRatePct / 100,
        hit_rate_pct: hitRatePct,
        cached_entries_memory: this.cacheStats.cachedEntries,
      },
      circuit_breakers: circuitBreakers,
      adaptive_controller: adaptiveController,
      backends_health: backendsHealth,
    };
  }

  public getBackends(): BackendNodeAdmin[] {
    return Array.from(this.backends.values()).map((b) => ({
      id: b.id,
      name: b.name,
      url: b.url,
      weight: b.weight,
      is_active: b.is_active,
      is_healthy: b.is_healthy,
      is_routable: b.is_active && b.is_healthy && b.circuit_state !== 'OPEN',
      is_flapping: b.is_flapping,
      flapping_penalty_remaining: 0,
      circuit_state: b.circuit_state,
      circuit_retry_after: b.circuit_state === 'OPEN' ? Math.max(0, 10 - Math.floor((Date.now() - b.circuit_opened_at) / 1000)) : 0,
      active_connections: b.active_connections,
      total_routed: b.total_routed,
      dynamic_concurrency_limit: b.concurrency_limit,
      p95_latency_ms: b.p95_latency,
      error_rate: b.error_rate,
      last_error: b.last_error,
    }));
  }

  public getLiveLogs(limit: number = 35): RequestLog[] {
    return this.recentLogs.slice(0, limit);
  }

  public setAlgorithm(algorithm: string) {
    this.algorithm = algorithm;
  }

  public updateBackendWeight(backendId: string, weight: number) {
    const b = this.backends.get(backendId);
    if (b) b.weight = weight;
  }

  public toggleBackend(backendId: string) {
    const b = this.backends.get(backendId);
    if (b) {
      b.is_active = !b.is_active;
    }
  }

  public updateRateLimit(params: { algorithm?: string; capacity?: number; refill_rate?: number; window_limit?: number }) {
    if (params.algorithm) this.rateLimiterAlgorithm = params.algorithm;
    if (params.capacity) this.tokenBucket.capacity = params.capacity;
    if (params.refill_rate) this.tokenBucket.refillRate = params.refill_rate;
    if (params.window_limit) this.slidingWindow.limit = params.window_limit;
  }

  public resetCircuitBreakers() {
    this.backends.forEach((b) => {
      b.circuit_state = 'CLOSED';
      b.consecutive_failures = 0;
      b.last_error = null;
    });
  }

  public clearCache() {
    this.cacheStats.hits = 0;
    this.cacheStats.misses = 0;
    this.cacheStats.bypasses = 0;
    this.cacheStats.cachedEntries = 0;
  }

  public resetMetrics() {
    this.metrics.total_requests = 0;
    this.metrics.total_successes = 0;
    this.metrics.total_client_errors = 0;
    this.metrics.total_server_errors = 0;
    this.metrics.rate_limit_rejections = 0;
    this.metrics.circuit_breaker_rejections = 0;
    this.metrics.load_shed_rejections = 0;
    this.metrics.backend_routed_counts = { 'backend-1': 0, 'backend-2': 0, 'backend-3': 0 };
    this.metrics.backend_error_counts = { 'backend-1': 0, 'backend-2': 0, 'backend-3': 0 };
    this.recentLogs = [];
  }

  public simulateFault(
    backendId: string,
    action: 'delay' | 'error' | 'status' | 'reset',
    params?: { delay_ms?: number; error_rate?: number; status_str?: string }
  ) {
    const b = this.backends.get(backendId);
    if (!b) return { status: 'error', message: 'Backend not found' };

    if (action === 'delay') {
      b.simulated_delay_ms = params?.delay_ms ?? 500;
      b.p95_latency = 30 + b.simulated_delay_ms;
      this.recordAdaptiveDecision(
        backendId,
        'SHED',
        `High P95 latency (${b.p95_latency}ms). Reducing concurrency limit.`,
        b.concurrency_limit,
        Math.max(10, Math.floor(b.concurrency_limit * 0.7))
      );
      b.concurrency_limit = Math.max(10, Math.floor(b.concurrency_limit * 0.7));
    } else if (action === 'error') {
      b.simulated_error_rate = params?.error_rate ?? 0.8;
      b.error_rate = b.simulated_error_rate;
      b.circuit_state = 'OPEN';
      b.circuit_opened_at = Date.now();
      b.last_error = 'Simulated 500 Spike: Circuit Breaker TRIPPED to OPEN';
    } else if (action === 'status') {
      if (params?.status_str === 'down') {
        b.is_healthy = false;
        b.last_error = 'Backend marked DOWN by simulation';
      } else {
        b.is_healthy = true;
        b.last_error = null;
      }
    } else if (action === 'reset') {
      b.simulated_delay_ms = 0;
      b.simulated_error_rate = 0;
      b.is_healthy = true;
      b.is_active = true;
      b.circuit_state = 'CLOSED';
      b.consecutive_failures = 0;
      b.concurrency_limit = 50;
      b.p95_latency = b.id === 'backend-1' ? 28.5 : b.id === 'backend-2' ? 32.1 : 36.8;
      b.error_rate = 0.01;
      b.last_error = null;
    }

    return { status: 'success', backend_id: backendId, action };
  }

  public sendTestBurst(count: number = 25, endpoint: string = '/api/data') {
    for (let i = 0; i < count; i++) {
      this.processSimulatedRequest(
        `${endpoint}?burst=${Date.now()}_${i}`,
        'GET',
        `10.0.0.${Math.floor(Math.random() * 20) + 1}`
      );
    }
  }
}

export const cloudEngine = new CloudSimulationEngine();
