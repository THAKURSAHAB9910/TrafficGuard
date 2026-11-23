import React from 'react';
import { Activity, Clock, AlertTriangle, ShieldAlert, Database, Zap, Layers } from 'lucide-react';
import { MetricsSummary } from '../types';

interface MetricCardsProps {
  summary: MetricsSummary | null;
}

export const MetricCards: React.FC<MetricCardsProps> = ({ summary }) => {
  const m = summary?.metrics;
  const c = summary?.cache;
  const l = m?.latency;

  const cards = [
    {
      title: 'Current Throughput',
      value: `${m?.current_rps ?? 0} RPS`,
      sub: `${m?.total_requests?.toLocaleString() ?? 0} total requests`,
      icon: Activity,
      color: 'from-blue-500/20 to-cyan-500/10 text-cyan-400 border-cyan-500/30',
      badge: 'Real-Time',
    },
    {
      title: 'Latency (Avg / p95)',
      value: `${l?.avg ?? 0}ms`,
      sub: `p50: ${l?.p50 ?? 0}ms  •  p95: ${l?.p95 ?? 0}ms  •  p99: ${l?.p99 ?? 0}ms`,
      icon: Clock,
      color: 'from-purple-500/20 to-indigo-500/10 text-purple-400 border-purple-500/30',
      badge: `${l?.p95 ?? 0}ms p95`,
    },
    {
      title: 'Error Rate',
      value: `${m?.error_rate_pct ?? 0}%`,
      sub: `${m?.total_server_errors ?? 0} server errors (5xx)`,
      icon: AlertTriangle,
      color: (m?.error_rate_pct ?? 0) > 5
        ? 'from-rose-500/20 to-red-500/10 text-rose-400 border-rose-500/30'
        : 'from-slate-500/20 to-slate-600/10 text-slate-300 border-slate-700/50',
      badge: (m?.error_rate_pct ?? 0) > 5 ? 'ELEVATED' : 'STABLE',
    },
    {
      title: 'Rate-Limit Rejections',
      value: `${m?.rate_limit_rejections ?? 0}`,
      sub: 'Blocked by Token Bucket / Sliding Window',
      icon: ShieldAlert,
      color: 'from-amber-500/20 to-yellow-500/10 text-amber-400 border-amber-500/30',
      badge: '429 Shield',
    },
    {
      title: 'Circuit & Load Shed',
      value: `${(m?.circuit_breaker_rejections ?? 0) + (m?.load_shed_rejections ?? 0)}`,
      sub: `CB: ${m?.circuit_breaker_rejections ?? 0}  •  Adaptive Shed: ${m?.load_shed_rejections ?? 0}`,
      icon: Layers,
      color: 'from-rose-500/20 to-orange-500/10 text-orange-400 border-orange-500/30',
      badge: 'Fault Isolation',
    },
    {
      title: 'Cache Hit Rate',
      value: `${c?.hit_rate_pct ?? 0}%`,
      sub: `Hits: ${c?.hits ?? 0}  •  Misses: ${c?.misses ?? 0}  •  Bypass: ${c?.bypasses ?? 0}`,
      icon: Database,
      color: 'from-emerald-500/20 to-teal-500/10 text-emerald-400 border-emerald-500/30',
      badge: `${c?.hits ?? 0} Served`,
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3 mb-6">
      {cards.map((card, idx) => {
        const Icon = card.icon;
        return (
          <div
            key={idx}
            className={`glass-panel p-4 bg-gradient-to-br ${card.color} border flex flex-col justify-between`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-slate-400 tracking-wide uppercase">
                {card.title}
              </span>
              <Icon className="w-4 h-4 opacity-80" />
            </div>

            <div className="my-1">
              <div className="text-2xl font-bold font-mono tracking-tight text-white">
                {card.value}
              </div>
            </div>

            <div className="flex items-center justify-between text-xs text-slate-400 mt-2 pt-2 border-t border-slate-700/40">
              <span className="truncate max-w-[140px] font-mono text-[11px]">{card.sub}</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800/80 text-slate-300">
                {card.badge}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};
