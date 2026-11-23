import React from 'react';
import { Sliders, ShieldAlert, Zap, RotateCcw, Database } from 'lucide-react';
import { api } from '../services/api';

interface SimulatorControlProps {
  currentRateAlgo: string;
  onRefresh: () => void;
}

export const SimulatorControl: React.FC<SimulatorControlProps> = ({ currentRateAlgo, onRefresh }) => {
  const [algo, setAlgo] = React.useState(currentRateAlgo);
  const [capacity, setCapacity] = React.useState(30);
  const [refillRate, setRefillRate] = React.useState(10);
  const [burstEndpoint, setBurstEndpoint] = React.useState('/api/data');
  const [burstCount, setBurstCount] = React.useState(30);
  const [loading, setLoading] = React.useState(false);
  const [statusMsg, setStatusMsg] = React.useState<string | null>(null);

  const handleApplyRateLimit = async () => {
    try {
      setLoading(true);
      await api.updateRateLimit({
        algorithm: algo,
        capacity: Number(capacity),
        refill_rate: Number(refillRate),
      });
      setStatusMsg('Rate limit parameters applied successfully');
      setTimeout(() => setStatusMsg(null), 3000);
      onRefresh();
    } catch (e: any) {
      setStatusMsg(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleTriggerBurst = async () => {
    try {
      setLoading(true);
      setStatusMsg(`Sending ${burstCount} requests to ${burstEndpoint}...`);
      await api.sendTestBurst(burstCount, burstEndpoint);
      setStatusMsg(`Burst of ${burstCount} requests completed`);
      setTimeout(() => setStatusMsg(null), 3000);
      onRefresh();
    } catch (e: any) {
      setStatusMsg(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleResetBreakers = async () => {
    await api.resetCircuitBreakers();
    setStatusMsg('All circuit breakers reset to CLOSED');
    setTimeout(() => setStatusMsg(null), 3000);
    onRefresh();
  };

  return (
    <div className="glass-panel p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sliders className="w-5 h-5 text-amber-400" />
          <h2 className="text-base font-bold text-white tracking-wide">
            Traffic Control & Rate Limiter Configuration
          </h2>
        </div>
        {statusMsg && (
          <span className="text-xs font-mono px-2.5 py-1 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            {statusMsg}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Rate Limiting Tuner */}
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center gap-2 mb-3">
            <ShieldAlert className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-white">Rate Limiter Policies</h3>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <label className="text-slate-400 block mb-1">Algorithm</label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setAlgo('token_bucket')}
                  className={`px-3 py-1.5 rounded-lg border font-mono font-medium transition ${
                    algo === 'token_bucket'
                      ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                >
                  Token Bucket
                </button>
                <button
                  type="button"
                  onClick={() => setAlgo('sliding_window')}
                  className={`px-3 py-1.5 rounded-lg border font-mono font-medium transition ${
                    algo === 'sliding_window'
                      ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                >
                  Sliding Window Log
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-slate-400 block mb-1">Burst Capacity (Tokens / Limit)</label>
                <input
                  type="number"
                  min="1"
                  max="500"
                  value={capacity}
                  onChange={(e) => setCapacity(Number(e.target.value))}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono"
                />
              </div>
              <div>
                <label className="text-slate-400 block mb-1">Refill Rate (tokens/sec)</label>
                <input
                  type="number"
                  min="0.1"
                  step="0.5"
                  max="100"
                  value={refillRate}
                  onChange={(e) => setRefillRate(Number(e.target.value))}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono"
                />
              </div>
            </div>

            <div className="pt-2 flex justify-between items-center">
              <button
                type="button"
                onClick={handleResetBreakers}
                className="text-slate-400 hover:text-white flex items-center gap-1.5 text-xs"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reset Circuit Breakers
              </button>

              <button
                type="button"
                onClick={handleApplyRateLimit}
                disabled={loading}
                className="px-4 py-1.5 bg-amber-600 hover:bg-amber-500 text-white rounded-lg font-semibold transition shadow"
              >
                Apply Policies
              </button>
            </div>
          </div>
        </div>

        {/* Live Traffic Generator */}
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-white">Live Traffic Generator</h3>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <label className="text-slate-400 block mb-1">Target Endpoint</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setBurstEndpoint('/api/data')}
                  className={`px-3 py-1.5 rounded-lg border font-mono font-medium transition text-left ${
                    burstEndpoint === '/api/data'
                      ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                >
                  /api/data (Cacheable GET)
                </button>
                <button
                  type="button"
                  onClick={() => setBurstEndpoint('/api/compute')}
                  className={`px-3 py-1.5 rounded-lg border font-mono font-medium transition text-left ${
                    burstEndpoint === '/api/compute'
                      ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                >
                  /api/compute (CPU Workload)
                </button>
              </div>
            </div>

            <div>
              <label className="text-slate-400 block mb-1">Burst Volume (Number of Parallel Requests)</label>
              <div className="flex gap-2">
                {[10, 30, 60, 120].map((cnt) => (
                  <button
                    key={cnt}
                    type="button"
                    onClick={() => setBurstCount(cnt)}
                    className={`flex-1 py-1.5 rounded-lg border font-mono font-bold transition ${
                      burstCount === cnt
                        ? 'bg-indigo-600 text-white border-indigo-500'
                        : 'bg-slate-800 text-slate-400 border-slate-700'
                    }`}
                  >
                    {cnt}
                  </button>
                ))}
              </div>
            </div>

            <div className="pt-2 text-right">
              <button
                type="button"
                onClick={handleTriggerBurst}
                disabled={loading}
                className="w-full py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white rounded-lg font-bold transition shadow-lg shadow-indigo-600/30 flex items-center justify-center gap-2"
              >
                <Zap className="w-4 h-4 text-amber-300" />
                Dispatch {burstCount} Requests Now
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
