import React from 'react';
import { Cpu, ShieldCheck, TrendingDown, TrendingUp, AlertTriangle, Info, Terminal } from 'lucide-react';
import { BackendAdaptiveStats } from '../types';

interface AdaptiveControlPanelProps {
  stats: Record<string, BackendAdaptiveStats>;
}

export const AdaptiveControlPanel: React.FC<AdaptiveControlPanelProps> = ({ stats }) => {
  // Collect all recent decisions across all backends
  const allDecisions = Object.values(stats)
    .flatMap((s) => s.recent_decisions || [])
    .sort((a, b) => b.timestamp - a.timestamp)
    .slice(0, 8);

  return (
    <div className="glass-panel p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Cpu className="w-5 h-5 text-cyan-400" />
          <h2 className="text-base font-bold text-white tracking-wide">
            Adaptive Traffic Controller (Explainable Decisions & Dynamic Concurrency)
          </h2>
        </div>
        <span className="text-xs font-mono text-cyan-400 bg-cyan-500/10 border border-cyan-500/30 px-2.5 py-0.5 rounded-full">
          AIMD Concurrency Limiter
        </span>
      </div>

      {/* Controller Specification & Signals Card */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4 text-xs">
        <div className="p-3 bg-slate-900/60 rounded-lg border border-slate-800">
          <span className="text-slate-400 block mb-0.5">Target SLA Latency</span>
          <span className="font-mono font-bold text-emerald-400 text-sm">120.0 ms</span>
          <span className="text-[10px] text-slate-500 block mt-1">Normal operating threshold</span>
        </div>
        <div className="p-3 bg-slate-900/60 rounded-lg border border-slate-800">
          <span className="text-slate-400 block mb-0.5">Max Latency Breach</span>
          <span className="font-mono font-bold text-rose-400 text-sm">350.0 ms</span>
          <span className="text-[10px] text-slate-500 block mt-1">Triggers load shedding</span>
        </div>
        <div className="p-3 bg-slate-900/60 rounded-lg border border-slate-800">
          <span className="text-slate-400 block mb-0.5">Backoff Factor (Decrease)</span>
          <span className="font-mono font-bold text-amber-400 text-sm">0.7x (30% drop)</span>
          <span className="text-[10px] text-slate-500 block mt-1">Multiplicative throttle</span>
        </div>
        <div className="p-3 bg-slate-900/60 rounded-lg border border-slate-800">
          <span className="text-slate-400 block mb-0.5">Additive Step (Recovery)</span>
          <span className="font-mono font-bold text-blue-400 text-sm">+1 / second</span>
          <span className="text-[10px] text-slate-500 block mt-1">Gradual probe increase</span>
        </div>
      </div>

      {/* Live Decisions Feed */}
      <div className="bg-slate-950/80 rounded-xl border border-slate-800/90 p-4">
        <div className="flex items-center justify-between text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
          <span className="flex items-center gap-1.5">
            <Terminal className="w-4 h-4 text-slate-400" />
            Explainable Decision Audit Log
          </span>
          <span className="text-[11px] font-mono lowercase text-slate-500">
            Signals: Rolling P95 Latency & Error Rate
          </span>
        </div>

        {allDecisions.length === 0 ? (
          <div className="py-6 text-center text-xs text-slate-500 font-mono">
            Traffic is currently stable within SLA (120ms). No overload or backoff events triggered yet.
            <br />
            Tip: Use the simulator above to inject latency or burst traffic to observe automated decisions.
          </div>
        ) : (
          <div className="space-y-2">
            {allDecisions.map((d, idx) => {
              const dateStr = new Date(d.timestamp * 1000).toLocaleTimeString();
              let badgeColor = 'bg-blue-500/10 text-blue-400 border-blue-500/30';
              let Icon = Info;

              if (d.action === 'SHED') {
                badgeColor = 'bg-rose-500/15 text-rose-400 border-rose-500/40';
                Icon = TrendingDown;
              } else if (d.action === 'EXPAND') {
                badgeColor = 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
                Icon = TrendingUp;
              } else if (d.action === 'REJECT') {
                badgeColor = 'bg-amber-500/15 text-amber-300 border-amber-500/30';
                Icon = AlertTriangle;
              }

              return (
                <div
                  key={idx}
                  className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800/80 flex flex-wrap items-center justify-between gap-3 text-xs font-mono"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-slate-500 text-[11px]">{dateStr}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border flex items-center gap-1 ${badgeColor}`}>
                      <Icon className="w-3 h-3" />
                      {d.action}
                    </span>
                    <span className="font-semibold text-white">{d.backend_id}</span>
                  </div>

                  <div className="text-slate-300 font-sans text-xs flex-1 truncate max-w-xl">
                    {d.reason}
                  </div>

                  <div className="flex items-center gap-3 text-[11px] text-slate-400">
                    <span>
                      Observed P95: <strong className="text-white">{d.observed_p95_ms}ms</strong>
                    </span>
                    <span>
                      Limit:{' '}
                      <strong className="text-slate-400">{d.previous_limit}</strong> →{' '}
                      <strong className="text-white">{d.new_limit}</strong>
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
