import React, { useState } from 'react';
import { Shield, Activity, RefreshCw, Zap, Trash2, BarChart3, Globe, Server, Settings, Check } from 'lucide-react';
import { api, apiConfig, GatewayMode } from '../services/api';

interface HeaderProps {
  algorithm: string;
  rateLimitAlgorithm: string;
  onRefresh: () => void;
  isAutoRefresh: boolean;
  setIsAutoRefresh: (val: boolean) => void;
}

export const Header: React.FC<HeaderProps> = ({
  algorithm,
  rateLimitAlgorithm,
  onRefresh,
  isAutoRefresh,
  setIsAutoRefresh,
}) => {
  const [isSendingBurst, setIsSendingBurst] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [mode, setMode] = useState<GatewayMode>(apiConfig.getMode());
  const [customUrl, setCustomUrl] = useState(apiConfig.getUrl());
  const [burstToast, setBurstToast] = useState<string | null>(null);

  const handleSendBurst = async (count: number) => {
    try {
      setIsSendingBurst(true);
      await api.sendTestBurst(count);
      setBurstToast(`🚀 Successfully fired ${count} parallel requests!`);
      setTimeout(() => setBurstToast(null), 3000);
      setTimeout(onRefresh, 250);
    } catch (e: any) {
      console.error(e);
      setBurstToast(`❌ Error: ${e.message}`);
      setTimeout(() => setBurstToast(null), 3500);
    } finally {
      setIsSendingBurst(false);
    }
  };

  const handleResetMetrics = async () => {
    if (confirm('Reset all metrics, request counts, and telemetry counters?')) {
      await api.resetMetrics();
      onRefresh();
    }
  };

  const handleClearCache = async () => {
    await api.clearCache();
    setBurstToast('🧹 Cache cleared successfully!');
    setTimeout(() => setBurstToast(null), 2500);
    onRefresh();
  };

  const saveSettings = () => {
    apiConfig.setMode(mode);
    apiConfig.setUrl(customUrl);
    setShowSettings(false);
    onRefresh();
  };

  return (
    <header className="glass-panel p-4 mb-6 relative">
      {/* Toast Notification */}
      {burstToast && (
        <div className="absolute top-2 right-4 z-50 px-4 py-2 bg-indigo-600/90 text-white text-xs font-semibold rounded-lg shadow-lg shadow-indigo-500/20 border border-indigo-400/30 animate-bounce">
          {burstToast}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Brand & Status */}
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-gradient-to-br from-blue-600 to-indigo-700 rounded-xl shadow-lg shadow-blue-500/20 text-white flex-shrink-0">
            <Shield className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                TrafficGuard
                <span className="text-xs px-2.5 py-0.5 rounded-full font-mono bg-blue-500/10 text-blue-400 border border-blue-500/30 font-medium">
                  v1.0 RESILIENCE
                </span>
              </h1>
            </div>

            <div className="flex flex-wrap items-center gap-2.5 text-xs text-slate-400 mt-1">
              {/* Mode Badge */}
              <button
                onClick={() => setShowSettings(true)}
                className={`flex items-center gap-1.5 px-2 py-0.5 rounded-md font-medium border transition ${
                  mode === 'cloud'
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20'
                    : 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30 hover:bg-cyan-500/20'
                }`}
                title="Click to configure Gateway Connection"
              >
                {mode === 'cloud' ? (
                  <>
                    <Globe className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Cloud Interactive Mode</span>
                  </>
                ) : (
                  <>
                    <Server className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Local Gateway ({customUrl.replace(/^https?:\/\//, '')})</span>
                  </>
                )}
                <Settings className="w-3 h-3 text-slate-400 ml-1" />
              </button>

              <span className="text-slate-600">•</span>
              <span className="font-mono text-slate-300">
                LB: <span className="text-indigo-400 font-semibold">{algorithm.toUpperCase()}</span>
              </span>
              <span className="text-slate-600">•</span>
              <span className="font-mono text-slate-300">
                RL: <span className="text-cyan-400 font-semibold">{rateLimitAlgorithm.toUpperCase()}</span>
              </span>
            </div>
          </div>
        </div>

        {/* Control Actions */}
        <div className="flex items-center flex-wrap gap-2.5">
          {/* Test Burst Triggers */}
          <button
            onClick={() => handleSendBurst(25)}
            disabled={isSendingBurst}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition disabled:opacity-50 cursor-pointer"
            title="Fire 25 parallel requests through the proxy"
          >
            <Zap className="w-3.5 h-3.5 text-amber-300" />
            {isSendingBurst ? 'Bursting...' : 'Burst 25 Req'}
          </button>

          <button
            onClick={() => handleSendBurst(100)}
            disabled={isSendingBurst}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600/30 hover:bg-blue-600/50 text-blue-300 border border-blue-500/30 transition disabled:opacity-50 cursor-pointer"
            title="Fire 100 parallel requests to test rate limiting & load shedding"
          >
            <Activity className="w-3.5 h-3.5 text-blue-400" />
            Burst 100 Req
          </button>

          {/* Clear Cache */}
          <button
            onClick={handleClearCache}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition cursor-pointer"
            title="Flush all cached HTTP GET responses"
          >
            <Trash2 className="w-3.5 h-3.5 text-slate-400" />
            Flush Cache
          </button>

          {/* Reset Metrics */}
          <button
            onClick={handleResetMetrics}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition cursor-pointer"
            title="Reset latency and request counters"
          >
            <BarChart3 className="w-3.5 h-3.5 text-slate-400" />
            Reset Telemetry
          </button>

          {/* Auto Refresh Toggle */}
          <button
            onClick={() => setIsAutoRefresh(!isAutoRefresh)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition cursor-pointer ${
              isAutoRefresh
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-slate-800 text-slate-400 border-slate-700'
            }`}
            title="Toggle 1-second live telemetry polling"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isAutoRefresh ? 'animate-spin' : ''}`} />
            {isAutoRefresh ? 'Auto 1s' : 'Paused'}
          </button>
        </div>
      </div>

      {/* Gateway Connection Settings Modal */}
      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="glass-panel w-full max-w-md p-6 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl">
            <h2 className="text-lg font-bold text-white mb-2 flex items-center gap-2">
              <Settings className="w-5 h-5 text-indigo-400" />
              Gateway Connection Mode
            </h2>
            <p className="text-xs text-slate-400 mb-4">
              Select how this dashboard connects to the TrafficGuard infrastructure.
            </p>

            <div className="space-y-3 mb-5">
              <label
                onClick={() => setMode('cloud')}
                className={`p-3 rounded-xl border flex items-start gap-3 cursor-pointer transition ${
                  mode === 'cloud'
                    ? 'bg-indigo-600/15 border-indigo-500 text-white'
                    : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:bg-slate-800'
                }`}
              >
                <Globe className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <div className="font-semibold text-sm text-slate-200 flex items-center justify-between">
                    Cloud Interactive Simulation (Recommended for Vercel)
                    {mode === 'cloud' && <Check className="w-4 h-4 text-indigo-400" />}
                  </div>
                  <div className="text-xs text-slate-400 mt-1">
                    Simulates 3 real backends, live traffic generation, rate limiting, and fault injection in-browser. Zero external setup required.
                  </div>
                </div>
              </label>

              <label
                onClick={() => setMode('custom')}
                className={`p-3 rounded-xl border flex items-start gap-3 cursor-pointer transition ${
                  mode === 'custom'
                    ? 'bg-indigo-600/15 border-indigo-500 text-white'
                    : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:bg-slate-800'
                }`}
              >
                <Server className="w-5 h-5 text-cyan-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <div className="font-semibold text-sm text-slate-200 flex items-center justify-between">
                    Live Local / Remote Gateway
                    {mode === 'custom' && <Check className="w-4 h-4 text-indigo-400" />}
                  </div>
                  <div className="text-xs text-slate-400 mt-1">
                    Connects directly to your running Python FastAPI gateway (e.g. Docker or local uvicorn).
                  </div>
                </div>
              </label>
            </div>

            {mode === 'custom' && (
              <div className="mb-5">
                <label className="block text-xs font-mono text-slate-300 mb-1.5">
                  Gateway API Endpoint:
                </label>
                <input
                  type="text"
                  value={customUrl}
                  onChange={(e) => setCustomUrl(e.target.value)}
                  placeholder="http://localhost:8000"
                  className="w-full px-3 py-2 text-xs font-mono bg-slate-950 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                />
                <div className="text-[11px] text-amber-400/90 mt-1.5">
                  Note: If connecting to localhost from HTTPS Vercel, allow insecure content in your browser or run the dashboard locally with <code>npm run dev</code>.
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2.5">
              <button
                onClick={() => setShowSettings(false)}
                className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={saveSettings}
                className="px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg shadow-sm transition cursor-pointer"
              >
                Apply Changes
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};
