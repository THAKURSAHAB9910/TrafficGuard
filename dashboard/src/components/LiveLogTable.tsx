import React from 'react';
import { Terminal, Database } from 'lucide-react';
import { RequestLog } from '../types';

interface LiveLogTableProps {
  logs: RequestLog[];
}

export const LiveLogTable: React.FC<LiveLogTableProps> = ({ logs }) => {
  return (
    <div className="glass-panel p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Terminal className="w-5 h-5 text-emerald-400" />
          <h2 className="text-base font-bold text-white tracking-wide">
            Real Gateway Live Access Logs (Last {logs.length} Requests)
          </h2>
        </div>
        <span className="text-xs text-slate-400 font-mono">
          Actual live telemetry streamed from gateway
        </span>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/70">
        <table className="w-full text-left border-collapse text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 uppercase text-[11px] bg-slate-900/50">
              <th className="py-2.5 px-3">Time</th>
              <th className="py-2.5 px-3">Method</th>
              <th className="py-2.5 px-3">Path</th>
              <th className="py-2.5 px-3">Backend</th>
              <th className="py-2.5 px-3">Status</th>
              <th className="py-2.5 px-3">Latency</th>
              <th className="py-2.5 px-3">Cache</th>
              <th className="py-2.5 px-3">Details / Error</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {logs.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-6 text-center text-slate-500 font-sans">
                  No requests recorded yet. Fire a burst or send requests to <code>/api/v1/proxy/*</code>.
                </td>
              </tr>
            ) : (
              logs.map((log) => {
                const dateStr = new Date(log.timestamp > 1e11 ? log.timestamp : log.timestamp * 1000).toLocaleTimeString();
                
                // Status styling
                let statusColor = 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30';
                if (log.status_code === 429) {
                  statusColor = 'text-amber-400 bg-amber-500/10 border-amber-500/30 font-bold';
                } else if (log.status_code >= 400 && log.status_code < 500) {
                  statusColor = 'text-orange-400 bg-orange-500/10 border-orange-500/30';
                } else if (log.status_code >= 500) {
                  statusColor = 'text-rose-400 bg-rose-500/20 border-rose-500/40 font-bold';
                }

                // Cache badge
                let cacheColor = 'text-slate-500 bg-slate-800/40';
                if (log.cache_status === 'HIT') {
                  cacheColor = 'text-emerald-300 bg-emerald-500/20 border border-emerald-500/30';
                } else if (log.cache_status === 'MISS') {
                  cacheColor = 'text-cyan-300 bg-cyan-500/10';
                }

                return (
                  <tr key={log.id} className="hover:bg-slate-900/40 transition">
                    <td className="py-2 px-3 text-slate-400 whitespace-nowrap">{dateStr}</td>
                    <td className="py-2 px-3">
                      <span className="font-bold text-slate-200">{log.method}</span>
                    </td>
                    <td className="py-2 px-3 text-slate-300 truncate max-w-xs">{log.path}</td>
                    <td className="py-2 px-3">
                      <span className="px-1.5 py-0.5 rounded bg-slate-800 text-blue-300 border border-slate-700">
                        {log.backend_id || 'none'}
                      </span>
                    </td>
                    <td className="py-2 px-3">
                      <span className={`px-2 py-0.5 rounded border text-[11px] ${statusColor}`}>
                        {log.status_code}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-slate-300 whitespace-nowrap">{log.latency_ms} ms</td>
                    <td className="py-2 px-3">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${cacheColor}`}>
                        {log.cache_status}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-slate-400 truncate max-w-sm text-[11px] font-sans">
                      {log.error ? (
                        <span className="text-rose-400 font-mono">{log.error}</span>
                      ) : (
                        <span className="text-slate-500 font-mono">OK ({log.algorithm || 'gateway'})</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
