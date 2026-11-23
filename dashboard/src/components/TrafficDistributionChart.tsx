import React from 'react';
import { BarChart3, Shuffle, GitMerge, Cpu } from 'lucide-react';
import { api } from '../services/api';

interface TrafficDistributionProps {
  algorithm: string;
  routedCounts: Record<string, number>;
  onAlgorithmChange: () => void;
}

export const TrafficDistributionChart: React.FC<TrafficDistributionProps> = ({
  algorithm,
  routedCounts,
  onAlgorithmChange,
}) => {
  const [switching, setSwitching] = React.useState(false);

  const algorithms = [
    { id: 'round_robin', name: 'Round Robin', desc: 'Sequentially distributes traffic evenly across all healthy backends.' },
    { id: 'least_connections', name: 'Least Connections', desc: 'Routes incoming requests to the backend with the fewest active in-flight requests.' },
    { id: 'weighted_round_robin', name: 'Weighted Round Robin', desc: 'Smooth Weighted Round Robin (Nginx algorithm) distributing traffic proportionally by weight.' },
  ];

  const handleSelectAlgorithm = async (algoId: string) => {
    try {
      setSwitching(true);
      await api.setAlgorithm(algoId);
      onAlgorithmChange();
    } catch (e) {
      console.error(e);
    } finally {
      setSwitching(false);
    }
  };

  const totalRouted = Object.values(routedCounts).reduce((a, b) => a + b, 0);

  const backendColors: Record<string, { bar: string; text: string }> = {
    'backend-1': { bar: 'bg-blue-500', text: 'text-blue-400' },
    'backend-2': { bar: 'bg-indigo-500', text: 'text-indigo-400' },
    'backend-3': { bar: 'bg-cyan-500', text: 'text-cyan-400' },
  };

  return (
    <div className="glass-panel p-5 mb-6">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-5">
        <div>
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-indigo-400" />
            <h2 className="text-base font-bold text-white tracking-wide">
              Load Balancing Strategy & Traffic Distribution
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Compare routing strategies in real time under live test workloads.
          </p>
        </div>

        {/* Algorithm Selection Pills */}
        <div className="flex flex-wrap gap-2">
          {algorithms.map((algo) => {
            const isSelected = algorithm.toLowerCase() === algo.id;
            return (
              <button
                key={algo.id}
                onClick={() => handleSelectAlgorithm(algo.id)}
                disabled={switching}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition border ${
                  isSelected
                    ? 'bg-indigo-600 text-white border-indigo-500 shadow-md shadow-indigo-600/30'
                    : 'bg-slate-900/80 text-slate-300 border-slate-700/80 hover:bg-slate-800'
                }`}
                title={algo.desc}
              >
                {algo.name}
              </button>
            );
          })}
        </div>
      </div>

      {/* Traffic Distribution Bars */}
      <div className="bg-slate-900/70 p-4 rounded-xl border border-slate-800/80">
        <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
          <span>Backend Traffic Share (Total: {totalRouted.toLocaleString()} requests)</span>
          <span className="font-mono">Real Gateway Measurements</span>
        </div>

        {/* Multi-segment distribution progress bar */}
        <div className="w-full h-4 bg-slate-800 rounded-full overflow-hidden flex mb-4">
          {Object.entries(routedCounts).map(([bid, count]) => {
            const pct = totalRouted > 0 ? (count / totalRouted) * 100 : 0;
            const styling = backendColors[bid] || { bar: 'bg-slate-600', text: 'text-slate-400' };
            return (
              <div
                key={bid}
                style={{ width: `${pct}%` }}
                className={`h-full ${styling.bar} transition-all duration-300 relative group`}
                title={`${bid}: ${count} requests (${pct.toFixed(1)}%)`}
              />
            );
          })}
        </div>

        {/* Detailed Breakdown Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {['backend-1', 'backend-2', 'backend-3'].map((bid) => {
            const count = routedCounts[bid] ?? 0;
            const pct = totalRouted > 0 ? (count / totalRouted) * 100 : 0;
            const styling = backendColors[bid] || { bar: 'bg-slate-600', text: 'text-slate-400' };

            return (
              <div
                key={bid}
                className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 flex items-center justify-between"
              >
                <div className="flex items-center gap-2">
                  <div className={`w-3 h-3 rounded-full ${styling.bar}`} />
                  <div>
                    <span className="font-semibold text-xs text-white block">{bid}</span>
                    <span className="text-[11px] text-slate-400 font-mono">
                      {count.toLocaleString()} requests
                    </span>
                  </div>
                </div>

                <div className="text-right">
                  <span className={`font-mono text-base font-bold ${styling.text}`}>
                    {pct.toFixed(1)}%
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
