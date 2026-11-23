import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { MetricCards } from './components/MetricCards';
import { BackendList } from './components/BackendList';
import { TrafficDistributionChart } from './components/TrafficDistributionChart';
import { AdaptiveControlPanel } from './components/AdaptiveControlPanel';
import { SimulatorControl } from './components/SimulatorControl';
import { LiveLogTable } from './components/LiveLogTable';
import { api, apiConfig } from './services/api';
import { MetricsSummary, BackendNodeAdmin, RequestLog } from './types';
import { AlertCircle, RefreshCw, Globe } from 'lucide-react';

export const App: React.FC = () => {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [backends, setBackends] = useState<BackendNodeAdmin[]>([]);
  const [logs, setLogs] = useState<RequestLog[]>([]);
  const [isAutoRefresh, setIsAutoRefresh] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [sumData, backendsData, logsData] = await Promise.all([
        api.getSummary(),
        api.getBackends(),
        api.getLiveLogs(35),
      ]);
      setSummary(sumData);
      setBackends(backendsData);
      setLogs(logsData);
      setError(null);
    } catch (e: any) {
      setError(e.message || 'Connecting to TrafficGuard Gateway...');
    }
  }, []);

  useEffect(() => {
    fetchData();
    if (!isAutoRefresh) return;
    const interval = setInterval(fetchData, 1000);
    return () => clearInterval(interval);
  }, [fetchData, isAutoRefresh]);

  const switchToCloudMode = () => {
    apiConfig.setMode('cloud');
    fetchData();
  };

  return (
    <div className="max-w-[1600px] mx-auto p-4 md:p-6 lg:p-8">
      {/* Offline Alert with Quick Fix */}
      {error && (
        <div className="mb-5 p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl flex flex-wrap items-center justify-between gap-3 text-rose-400 text-xs font-mono">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 flex-shrink-0 text-rose-500" />
            <span>
              {error} — Cannot reach local gateway at <code>{apiConfig.getUrl()}</code>.
            </span>
          </div>
          <button
            onClick={switchToCloudMode}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-sans font-semibold transition cursor-pointer"
          >
            <Globe className="w-3.5 h-3.5" />
            Switch to Cloud Interactive Mode
          </button>
        </div>
      )}

      {/* Main Header */}
      <Header
        algorithm={summary?.algorithm || 'weighted_round_robin'}
        rateLimitAlgorithm={summary?.rate_limiter_algorithm || 'token_bucket'}
        onRefresh={fetchData}
        isAutoRefresh={isAutoRefresh}
        setIsAutoRefresh={setIsAutoRefresh}
      />

      {/* KPI Metric Cards */}
      <MetricCards summary={summary} />

      {/* Backend Pool & Health Status */}
      <BackendList backends={backends} onRefresh={fetchData} />

      {/* Load Balancing & Traffic Distribution */}
      <TrafficDistributionChart
        algorithm={summary?.algorithm || 'weighted_round_robin'}
        routedCounts={summary?.metrics?.backend_routed_counts || {}}
        onAlgorithmChange={fetchData}
      />

      {/* Adaptive Controller & Explainable Decisions */}
      <AdaptiveControlPanel stats={summary?.adaptive_controller || {}} />

      {/* Rate Limiting & Live Burst Generator */}
      <SimulatorControl
        currentRateAlgo={summary?.rate_limiter_algorithm || 'token_bucket'}
        onRefresh={fetchData}
      />

      {/* Live Request Stream Table */}
      <LiveLogTable logs={logs} />

      {/* Footer */}
      <footer className="mt-8 text-center text-xs text-slate-500 font-mono py-4 border-t border-slate-800/60">
        TrafficGuard Adaptive Traffic Management Platform • Built with FastAPI, Redis, PostgreSQL, and React
      </footer>
    </div>
  );
};

export default App;
