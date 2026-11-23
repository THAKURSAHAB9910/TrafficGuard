import { MetricsSummary, RequestLog, BackendNodeAdmin } from '../types';
import { cloudEngine } from './cloudEngine';

export type GatewayMode = 'cloud' | 'custom';

const STORAGE_KEY_MODE = 'tg_gateway_mode';
const STORAGE_KEY_URL = 'tg_gateway_url';

export const apiConfig = {
  getMode(): GatewayMode {
    const saved = localStorage.getItem(STORAGE_KEY_MODE);
    if (saved) return saved as GatewayMode;
    // Default to real local gateway when running locally
    if (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
      return 'custom';
    }
    return 'cloud';
  },
  setMode(mode: GatewayMode) {
    localStorage.setItem(STORAGE_KEY_MODE, mode);
  },
  getUrl(): string {
    return localStorage.getItem(STORAGE_KEY_URL) || 'http://localhost:8000';
  },
  setUrl(url: string) {
    localStorage.setItem(STORAGE_KEY_URL, url);
  },
};

export const api = {
  isCloudMode(): boolean {
    return apiConfig.getMode() === 'cloud';
  },

  async getSummary(): Promise<MetricsSummary> {
    if (this.isCloudMode()) {
      return cloudEngine.getSummary();
    }
    const base = apiConfig.getUrl().replace(/\/+$/, '');
    const res = await fetch(`${base}/api/metrics/summary`);
    const contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      throw new Error(`Invalid response from gateway: Expected JSON but got ${contentType || 'text/html'}`);
    }
    if (!res.ok) throw new Error(`Gateway returned error: ${res.statusText}`);
    return res.json();
  },

  async getLiveLogs(limit: number = 35): Promise<RequestLog[]> {
    if (this.isCloudMode()) {
      return cloudEngine.getLiveLogs(limit);
    }
    const base = apiConfig.getUrl().replace(/\/+$/, '');
    const res = await fetch(`${base}/api/metrics/live-logs?limit=${limit}`);
    const contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      throw new Error(`Invalid response from gateway: Expected JSON but got ${contentType || 'text/html'}`);
    }
    if (!res.ok) throw new Error(`Failed to fetch logs: ${res.statusText}`);
    const data = await res.json();
    return data.logs;
  },

  async getBackends(): Promise<BackendNodeAdmin[]> {
    if (this.isCloudMode()) {
      return cloudEngine.getBackends();
    }
    const base = apiConfig.getUrl().replace(/\/+$/, '');
    const res = await fetch(`${base}/api/admin/backends`);
    const contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      throw new Error(`Invalid response from gateway: Expected JSON but got ${contentType || 'text/html'}`);
    }
    if (!res.ok) throw new Error(`Failed to fetch backends: ${res.statusText}`);
    const data = await res.json();
    return data.backends;
  },

  async setAlgorithm(algorithm: string): Promise<void> {
    if (this.isCloudMode()) {
      cloudEngine.setAlgorithm(algorithm);
      return;
    }
    const base = apiConfig.getUrl().replace(/\/+$/, '');
    const res = await fetch(`${base}/api/admin/algorithm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ algorithm }),
    });
    if (!res.ok) throw new Error(`Failed to update algorithm: ${res.statusText}`);
  },

  async updateBackendWeight(backendId: string, weight: number): Promise<void> {
    if (this.isCloudMode()) {
      cloudEngine.updateBackendWeight(backendId, weight);
      return;
    }
    const base = apiConfig.getUrl().replace(/\/+$/, '');
    const res = await fetch(`${base}/api/admin/backends/${backendId}/weight`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ weight }),
    });
    if (!res.ok) throw new Error(`Failed to update weight: ${res.statusText}`);
  },

  async toggleBackend(backendId: string): Promise<void> {
    if (this.isCloudMode()) {
      cloudEngine.toggleBackend(backendId);
      return;
    }
    const base = apiConfig.getUrl().replace(/\/+$/, '');
    const res = await fetch(`${base}/api/admin/backends/${backendId}/toggle`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`Failed to toggle backend: ${res.statusText}`);
  },

  async updateRateLimit(params: {
    algorithm?: string;
    capacity?: number;
    refill_rate?: number;
    window_limit?: number;
  }): Promise<void> {
    if (this.isCloudMode()) {
      cloudEngine.updateRateLimit(params);
      return;
    }
    const base = apiConfig.getUrl().replace(/\/+$/, '');
    const res = await fetch(`${base}/api/admin/ratelimit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error(`Failed to update rate limit: ${res.statusText}`);
  },

  async resetCircuitBreakers(): Promise<void> {
    if (this.isCloudMode()) {
      cloudEngine.resetCircuitBreakers();
      return;
    }
    const base = apiConfig.getUrl().replace(/\/+$/, '');
    const res = await fetch(`${base}/api/admin/circuit-breaker/reset`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`Failed to reset circuit breakers: ${res.statusText}`);
  },

  async clearCache(): Promise<void> {
    if (this.isCloudMode()) {
      cloudEngine.clearCache();
      return;
    }
    const base = apiConfig.getUrl().replace(/\/+$/, '');
    const res = await fetch(`${base}/api/admin/cache/clear`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`Failed to clear cache: ${res.statusText}`);
  },

  async resetMetrics(): Promise<void> {
    if (this.isCloudMode()) {
      cloudEngine.resetMetrics();
      return;
    }
    const base = apiConfig.getUrl().replace(/\/+$/, '');
    const res = await fetch(`${base}/api/metrics/reset`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`Failed to reset metrics: ${res.statusText}`);
  },

  async simulateFault(
    backendId: string,
    action: 'delay' | 'error' | 'status' | 'reset',
    params?: { delay_ms?: number; error_rate?: number; status_str?: string }
  ): Promise<any> {
    if (this.isCloudMode()) {
      return cloudEngine.simulateFault(backendId, action, params);
    }
    const base = apiConfig.getUrl().replace(/\/+$/, '');
    const q = new URLSearchParams();
    if (params?.delay_ms !== undefined) q.set('delay_ms', params.delay_ms.toString());
    if (params?.error_rate !== undefined) q.set('error_rate', params.error_rate.toString());
    if (params?.status_str !== undefined) q.set('status_str', params.status_str);

    const res = await fetch(`${base}/api/admin/simulate/${backendId}/${action}?${q.toString()}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`Failed to apply simulation: ${res.statusText}`);
    return res.json();
  },

  async sendTestBurst(count: number = 25, endpoint: string = '/api/data'): Promise<void> {
    if (this.isCloudMode()) {
      cloudEngine.sendTestBurst(count, endpoint);
      return;
    }
    const base = apiConfig.getUrl().replace(/\/+$/, '');
    const promises = [];
    for (let i = 0; i < count; i++) {
      promises.push(
        fetch(`${base}/api/v1/proxy${endpoint}?burst=${Date.now()}_${i}`, {
          method: 'GET',
          headers: { 'X-Test-Burst': 'true' },
        }).catch(() => null)
      );
    }
    await Promise.all(promises);
  },
};
