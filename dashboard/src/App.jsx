import React, { useState, useEffect } from 'react';
import { LayoutDashboard, PhoneCall, BarChart3, Settings, Search, Calendar, Filter, X, ArrowUpRight, CheckCircle2, AlertCircle } from 'lucide-react';
import { useCalls } from './hooks/useCalls';
import { useStats } from './hooks/useStats';
import LiveIndicator from './components/LiveIndicator';
import MetricCards from './components/MetricCards';
import CallsTable from './components/CallsTable';
import UploadCSV from './components/UploadCSV';
import CallDrawer from './components/CallDrawer';
import { showToast } from './api/client';

export function App() {
  const [time, setTime] = useState(new Date());
  const [activeTab, setActiveTab] = useState('dashboard'); // 'dashboard', 'calls', 'analytics', 'settings'
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [selectedCall, setSelectedCall] = useState(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [toasts, setToasts] = useState([]);

  // Hooks
  const {
    calls,
    total,
    isLoading: isCallsLoading,
    filters,
    setFilter,
    page,
    limit,
    setPage,
    refetch: refetchCalls
  } = useCalls();

  const { stats, isLoading: isStatsLoading, refetch: refetchStats } = useStats();

  // Digital Clock
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Listen to Toast Events from api/client
  useEffect(() => {
    const handleToast = (e) => {
      const { message, type, id } = e.detail;
      setToasts((prev) => [...prev, { message, type, id }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 4500);
    };

    window.addEventListener('app-toast', handleToast);
    return () => window.removeEventListener('app-toast', handleToast);
  }, []);

  const handleRowClick = (call, startAudio = false) => {
    // If startAudio is true, we pass it to the drawer state
    setSelectedCall(call);
    setIsDrawerOpen(true);
    
    if (startAudio) {
      // Small timeout to allow player component to mount if not ready
      setTimeout(() => {
        const audioEl = document.querySelector('audio');
        if (audioEl) {
          audioEl.play().catch(e => console.log("Auto-play error:", e));
        }
      }, 300);
    }
  };

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setFilter('search', '');
    setFilter('outcome', '');
    setFilter('date', '');
    setPage(0);
  };

  const handleDialerInitiated = () => {
    refetchStats();
    refetchCalls();
  };

  const formattedTime = time.toLocaleString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  });

  return (
    <div className="min-h-screen bg-[#0B0F19] text-gray-100 flex flex-col relative">
      
      {/* TopBar (Fixed, full width) */}
      <header className="fixed top-0 left-0 right-0 h-16 bg-[#161E2E]/90 backdrop-blur-md border-b border-[#243048] flex items-center justify-between px-6 z-40 select-none">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-emerald-500 flex items-center justify-center text-darkBg font-bold text-md shadow-[0_0_15px_rgba(16,185,129,0.3)]">
              SR
            </div>
            <span className="font-bold text-white tracking-tight text-lg">SmartReception</span>
          </div>
          <LiveIndicator />
        </div>

        <div className="flex items-center gap-4">
          {/* Live digital clock */}
          <div className="hidden md:block text-xs font-mono text-gray-400 bg-[#0B0F19] border border-[#243048]/80 px-3 py-1.5 rounded-lg">
            {formattedTime}
          </div>
          
          <button
            onClick={() => setIsUploadOpen(!isUploadOpen)}
            className="flex items-center gap-1.5 px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-darkBg font-semibold rounded-lg text-xs shadow-[0_0_15px_rgba(16,185,129,0.2)] hover:scale-[1.02] active:scale-95 transition-all duration-200"
          >
            <span>Start Calling</span>
            <ArrowUpRight size={14} />
          </button>
        </div>
      </header>

      {/* Main Layout Container */}
      <div className="flex flex-1 pt-16">
        
        {/* Sidebar (Fixed left, 56px wide) */}
        <aside className="fixed left-0 top-16 bottom-0 w-14 bg-[#161E2E] border-r border-[#243048] flex flex-col items-center py-4 justify-between z-30 select-none">
          <div className="flex flex-col gap-2">
            {/* Tab 1: Dashboard */}
            <button
              onClick={() => handleTabChange('dashboard')}
              title="Dashboard Overview"
              className={`p-2.5 rounded-lg border transition-all duration-200 ${
                activeTab === 'dashboard'
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25'
                  : 'text-gray-400 hover:text-white border-transparent hover:bg-gray-800/30'
              }`}
            >
              <LayoutDashboard size={18} />
            </button>
            
            {/* Tab 2: Calls */}
            <button
              onClick={() => handleTabChange('calls')}
              title="Call Log"
              className={`p-2.5 rounded-lg border transition-all duration-200 ${
                activeTab === 'calls'
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25'
                  : 'text-gray-400 hover:text-white border-transparent hover:bg-gray-800/30'
              }`}
            >
              <PhoneCall size={18} />
            </button>

            {/* Tab 3: Analytics */}
            <button
              onClick={() => handleTabChange('analytics')}
              title="Analytics"
              className={`p-2.5 rounded-lg border transition-all duration-200 ${
                activeTab === 'analytics'
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25'
                  : 'text-gray-400 hover:text-white border-transparent hover:bg-gray-800/30'
              }`}
            >
              <BarChart3 size={18} />
            </button>
          </div>

          {/* Tab 4: Settings */}
          <button
            onClick={() => handleTabChange('settings')}
            title="Settings"
            className={`p-2.5 rounded-lg border transition-all duration-200 ${
              activeTab === 'settings'
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25'
                : 'text-gray-400 hover:text-white border-transparent hover:bg-gray-800/30'
            }`}
          >
            <Settings size={18} />
          </button>
        </aside>

        {/* Main Content Area (Scrollable, right of sidebar) */}
        <main className="flex-1 ml-14 p-6 overflow-y-auto max-w-7xl mx-auto w-full">
          
          {activeTab === 'dashboard' && (
            <>
              {/* Stat cards section */}
              <MetricCards stats={stats} />

              {/* CSV Upload zone (Toggleable) */}
              {isUploadOpen && (
                <div className="mb-6 transition-all duration-300">
                  <UploadCSV onUploadSuccess={handleDialerInitiated} />
                </div>
              )}

              {/* Filters Bar & Search */}
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4 bg-[#161E2E] border border-[#243048]/80 p-4 rounded-xl shadow-md">
                
                {/* Left search input */}
                <div className="flex-1 max-w-md relative">
                  <Search className="absolute left-3 top-2.5 text-gray-500" size={16} />
                  <input
                    type="text"
                    placeholder="Search calls by business, phone, category..."
                    value={filters.search}
                    onChange={(e) => setFilter('search', e.target.value)}
                    className="w-full pl-9 pr-4 py-2 bg-[#0B0F19] border border-[#243048] focus:border-emerald-500 rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none transition-all duration-200"
                  />
                  {filters.search && (
                    <button
                      onClick={() => setFilter('search', '')}
                      className="absolute right-3 top-2.5 text-gray-500 hover:text-white"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>

                {/* Right controls: filters & date picker */}
                <div className="flex flex-wrap items-center gap-3">
                  {/* Outcome dropdown */}
                  <div className="flex items-center gap-1.5 bg-[#0B0F19] border border-[#243048] rounded-lg px-2 py-1.5">
                    <Filter className="text-gray-500" size={13} />
                    <select
                      value={filters.outcome}
                      onChange={(e) => setFilter('outcome', e.target.value)}
                      className="bg-transparent border-0 text-xs text-gray-300 focus:outline-none cursor-pointer pr-4"
                    >
                      <option value="">All Outcomes</option>
                      <option value="Interested">Interested</option>
                      <option value="Callback">Callback</option>
                      <option value="Pitched">Pitched</option>
                      <option value="Not interested">Not interested</option>
                    </select>
                  </div>

                  {/* Date picker */}
                  <div className="flex items-center gap-1.5 bg-[#0B0F19] border border-[#243048] rounded-lg px-2.5 py-1.5">
                    <Calendar className="text-gray-500" size={13} />
                    <input
                      type="date"
                      value={filters.date}
                      onChange={(e) => setFilter('date', e.target.value)}
                      className="bg-transparent border-0 text-xs text-gray-300 focus:outline-none cursor-pointer placeholder-gray-500 font-mono"
                    />
                    {filters.date && (
                      <button onClick={() => setFilter('date', '')} className="text-gray-500 hover:text-white">
                        <X size={12} />
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* Table section */}
              <CallsTable
                calls={calls}
                total={total}
                isLoading={isCallsLoading}
                page={page}
                limit={limit}
                setPage={setPage}
                onRowClick={handleRowClick}
                onDeleteSuccess={() => {
                  refetchStats();
                  refetchCalls();
                }}
              />
            </>
          )}

          {activeTab === 'calls' && (
            <div>
              <h2 className="text-xl font-bold text-white mb-1">Call Logs</h2>
              <p className="text-xs text-gray-500 mb-6">Historical view of all telephonic contacts made by AI Mia.</p>
              
              <CallsTable
                calls={calls}
                total={total}
                isLoading={isCallsLoading}
                page={page}
                limit={limit}
                setPage={setPage}
                onRowClick={handleRowClick}
                onDeleteSuccess={() => {
                  refetchStats();
                  refetchCalls();
                }}
              />
            </div>
          )}

          {activeTab === 'analytics' && (
            <div className="bg-[#161E2E] border border-[#243048] rounded-xl p-6">
              <h2 className="text-xl font-bold text-white mb-2">System Analytics</h2>
              <p className="text-xs text-gray-500 mb-6">Real-time charts and sentiment ratios generated from live interactions.</p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Outcome ratios */}
                <div className="bg-[#0B0F19] border border-[#243048] rounded-xl p-5">
                  <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">Outcomes breakdown</h4>
                  <div className="space-y-3">
                    {Object.entries(stats.outcomes || {}).map(([key, val]) => {
                      const percentage = stats.total_calls > 0 ? Math.round((val / stats.total_calls) * 100) : 0;
                      return (
                        <div key={key} className="space-y-1">
                          <div className="flex justify-between text-xs font-mono">
                            <span className="text-gray-400">{key}</span>
                            <span className="text-gray-200 font-semibold">{val} ({percentage}%)</span>
                          </div>
                          <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                key === 'Interested' ? 'bg-green-500' :
                                key === 'Callback' ? 'bg-amber-500' :
                                key === 'Pitched' ? 'bg-blue-500' : 'bg-gray-600'
                              }`}
                              style={{ width: `${percentage}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Sentiment breakdown */}
                <div className="bg-[#0B0F19] border border-[#243048] rounded-xl p-5">
                  <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">Sentiment Breakdown</h4>
                  <div className="space-y-3">
                    {Object.entries(stats.sentiment_breakdown || {}).map(([key, val]) => {
                      const percentage = stats.total_calls > 0 ? Math.round((val / stats.total_calls) * 100) : 0;
                      return (
                        <div key={key} className="space-y-1">
                          <div className="flex justify-between text-xs font-mono">
                            <span className="text-gray-400">{key}</span>
                            <span className="text-gray-200 font-semibold">{val} ({percentage}%)</span>
                          </div>
                          <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                key === 'Positive' ? 'bg-emerald-500' :
                                key === 'Negative' ? 'bg-red-500' : 'bg-gray-400'
                              }`}
                              style={{ width: `${percentage}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'settings' && (
            <div className="bg-[#161E2E] border border-[#243048] rounded-xl p-6 max-w-2xl">
              <h2 className="text-xl font-bold text-white mb-2">Telephony & AI Configuration</h2>
              <p className="text-xs text-gray-500 mb-6">Read-only view of environment variables loaded by services.</p>
              
              <div className="space-y-4 text-xs">
                <div className="grid grid-cols-3 gap-2 py-2 border-b border-[#243048]/50">
                  <span className="text-gray-500 font-mono">VOICE_PROVIDER</span>
                  <span className="col-span-2 text-gray-300 font-semibold">ElevenLabs TTS (Rachel)</span>
                </div>
                <div className="grid grid-cols-3 gap-2 py-2 border-b border-[#243048]/50">
                  <span className="text-gray-500 font-mono">LLM_PROVIDER</span>
                  <span className="col-span-2 text-gray-300 font-semibold">Google Gemini 2.5 Flash</span>
                </div>
                <div className="grid grid-cols-3 gap-2 py-2 border-b border-[#243048]/50">
                  <span className="text-gray-500 font-mono">TELEPHONY_PROVIDER</span>
                  <span className="col-span-2 text-gray-300 font-semibold">Telnyx WebRTC Connection</span>
                </div>
                <div className="grid grid-cols-3 gap-2 py-2 border-b border-[#243048]/50">
                  <span className="text-gray-500 font-mono">RECORDINGS_SAVE</span>
                  <span className="col-span-2 text-emerald-400 font-semibold font-mono">Active (/recordings)</span>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Sliding Call Details Drawer */}
      <CallDrawer
        call={selectedCall}
        isOpen={isDrawerOpen}
        onClose={() => {
          setIsDrawerOpen(false);
          // Pause audio if playing when closing
          const audioEl = document.querySelector('audio');
          if (audioEl) audioEl.pause();
        }}
      />

      {/* Floating Premium Toast Notifications */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-sm pointer-events-none">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`p-4 rounded-xl border shadow-2xl flex items-start gap-3 pointer-events-auto transform translate-y-0 transition-all duration-300 animate-slide-in ${
              toast.type === 'success'
                ? 'bg-emerald-950/90 text-emerald-300 border-emerald-900/60 shadow-emerald-950/20'
                : toast.type === 'error'
                ? 'bg-red-950/90 text-red-300 border-red-900/60 shadow-red-950/20'
                : 'bg-[#161E2E]/90 text-gray-300 border-[#243048] shadow-black/40'
            }`}
          >
            {toast.type === 'success' ? (
              <CheckCircle2 className="text-emerald-400 mt-0.5 shrink-0" size={16} />
            ) : toast.type === 'error' ? (
              <AlertCircle className="text-red-400 mt-0.5 shrink-0" size={16} />
            ) : (
              <AlertCircle className="text-blue-400 mt-0.5 shrink-0" size={16} />
            )}
            <div>
              <p className="text-xs font-semibold leading-normal">{toast.message}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
