import React from 'react';
import { Server, CheckCircle2, XCircle, AlertOctagon, Activity, Settings2, Sliders, Play, RotateCcw, Flame } from 'lucide-react';
import { BackendNodeAdmin } from '../types';
import { api } from '../services/api';

interface BackendListProps {
  backends: BackendNodeAdmin[];
  onRefresh: () => void;
}

export const BackendList: React.FC<BackendListProps> = ({ backends, onRefresh }) => {
  const [updatingId, setUpdatingId] = React.useState<string | null>(null);

  const handleWeightChange = async (backendId: string, newWeight: number) => {
    try {
      setUpdatingId(backendId);
      await api.updateBackendWeight(backendId, newWeight);
      onRefresh();
    } catch (e) {
      console.error(e);
    } finally {
      setUpdatingId(null);
    }
  };

  const handleToggle = async (backendId: string) => {
    try {
      setUpdatingId(backendId);
      await api.toggleBackend(backendId);
      onRefresh();
    } catch (e) {
      console.error(e);
    } finally {
      setUpdatingId(null);
    }
  };

  const handleSimulate = async (backendId: string, action: 'delay' | 'error' | 'status' | 'reset', params?: any) => {
    try {
      setUpdatingId(backendId);
      await api.simulateFault(backendId, action, params);
      setTimeout(onRefresh, 300);
    } catch (e) {
      console.error(e);
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="glass-panel p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Server className="w-5 h-5 text-blue-400" />
          <h2 className="text-base font-bold text-white tracking-wide">
            Backend Services Pool ({backends.length} Nodes)
          </h2>
        </div>
        <span className="text-xs text-slate-400 font-mono">
          Dynamic Circuit Breaker & Health Filter Active
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {backends.map((b) => {
          const isHealthy = b.is_healthy;
          const isFlapping = b.is_flapping;
          const isRoutable = b.is_routable;
          const cbState = b.circuit_state;

          // Status Badge styling
          let statusColor = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
          let statusText = 'HEALTHY';
          if (isFlapping) {
            statusColor = 'bg-amber-500/10 text-amber-400 border-amber-500/30';
            statusText = `FLAPPING (${Math.ceil(b.flapping_penalty_remaining)}s)`;
          } else if (!isHealthy) {
            statusColor = 'bg-rose-500/10 text-rose-400 border-rose-500/30';
            statusText = 'UNHEALTHY';
          }

          // Circuit Breaker badge
          let cbColor = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
          if (cbState === 'OPEN') {
            cbColor = 'bg-rose-500/20 text-rose-400 border-rose-500/40 animate-pulse';
          } else if (cbState === 'HALF_OPEN') {
            cbColor = 'bg-amber-500/20 text-amber-300 border-amber-500/40';
          }

          return (
            <div
              key={b.id}
              className={`p-4 rounded-xl border transition-all ${
                isRoutable
                  ? 'bg-slate-900/60 border-slate-800 hover:border-slate-700'
                  : 'bg-rose-950/20 border-rose-900/40 opacity-90'
              }`}
            >
              {/* Header row */}
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-white text-sm">{b.name}</h3>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                      {b.id}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 font-mono mt-0.5">{b.url}</div>
                </div>

                <div className="flex flex-col items-end gap-1.5">
                  {/* Health status */}
                  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border font-mono ${statusColor}`}>
                    {statusText}
                  </span>

                  {/* Circuit Breaker Status */}
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border font-mono ${cbColor}`}>
                    CB: {cbState} {cbState === 'OPEN' && b.circuit_retry_after > 0 ? `(${b.circuit_retry_after.toFixed(1)}s)` : ''}
                  </span>
                </div>
              </div>

              {/* Concurrency and Metrics Grid */}
              <div className="grid grid-cols-3 gap-2 py-2.5 my-2.5 border-y border-slate-800/80 text-xs">
                <div>
                  <span className="text-slate-400 block text-[11px]">In-Flight</span>
                  <span className="font-mono font-semibold text-white">
                    {b.active_connections}{' '}
                    <span className="text-slate-500 font-normal">/ {b.dynamic_concurrency_limit}</span>
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[11px]">P95 Latency</span>
                  <span className="font-mono font-semibold text-slate-200">
                    {b.p95_latency_ms} ms
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[11px]">Routed Req</span>
                  <span className="font-mono font-semibold text-indigo-400">
                    {b.total_routed.toLocaleString()}
                  </span>
                </div>
              </div>

              {/* Weight Adjustment */}
              <div className="mb-3">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                  <span>Routing Weight:</span>
                  <span className="font-mono font-bold text-white bg-slate-800 px-2 py-0.5 rounded">
                    {b.weight}x
                  </span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="10"
                  value={b.weight}
                  disabled={updatingId === b.id}
                  onChange={(e) => handleWeightChange(b.id, parseInt(e.target.value, 10))}
                  className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                />
              </div>

              {/* Fault Injection Quick Simulator Buttons */}
              <div className="mt-3 pt-3 border-t border-slate-800/80">
                <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold mb-2 flex items-center justify-between">
                  <span>Simulate Fault</span>
                  <Flame className="w-3.5 h-3.5 text-amber-500" />
                </div>
                <div className="grid grid-cols-4 gap-1.5 text-[11px]">
                  <button
                    onClick={() => handleSimulate(b.id, 'delay', { delay_ms: 400 })}
                    className="px-2 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded font-medium transition text-center"
                    title="Add 400ms latency to test adaptive load shedding"
                  >
                    +400ms
                  </button>
                  <button
                    onClick={() => handleSimulate(b.id, 'error', { error_rate: 0.6 })}
                    className="px-2 py-1 bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 rounded font-medium transition text-center"
                    title="Simulate 60% error rate to trip circuit breaker"
                  >
                    60% Err
                  </button>
                  <button
                    onClick={() => handleSimulate(b.id, 'status', { status_str: isHealthy ? 'DOWN' : 'UP' })}
                    className={`px-2 py-1 rounded font-medium transition text-center border ${
                      isHealthy
                        ? 'bg-red-600/20 hover:bg-red-600/30 text-red-300 border-red-500/40'
                        : 'bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border-emerald-500/40'
                    }`}
                    title={isHealthy ? 'Simulate server crash' : 'Restore server'}
                  >
                    {isHealthy ? 'Crash' : 'Revive'}
                  </button>
                  <button
                    onClick={() => handleSimulate(b.id, 'reset')}
                    className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded font-medium transition text-center flex items-center justify-center"
                    title="Reset simulation parameters to clean normal"
                  >
                    <RotateCcw className="w-3 h-3" />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
