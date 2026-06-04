import React from 'react';

export function LiveIndicator() {
  return (
    <div className="flex items-center space-x-2 bg-emerald-950/40 border border-emerald-900/60 px-2.5 py-1 rounded-full">
      <span className="relative flex h-2 w-2">
        <span className="pulse-indicator absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
      </span>
      <span className="text-[10px] font-semibold text-emerald-400 uppercase tracking-widest font-mono">Live</span>
    </div>
  );
}

export default LiveIndicator;
