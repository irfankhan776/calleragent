import React, { useState, useEffect } from 'react';
import { Phone, CheckCircle, Clock, Mic } from 'lucide-react';

function AnimatedNumber({ value }) {
  const [displayValue, setDisplayValue] = useState(0);
  
  useEffect(() => {
    let start = displayValue;
    const end = parseInt(value, 10) || 0;
    if (start === end) return;
    
    const duration = 400; // ms
    const startTime = performance.now();
    let animationFrameId;
    
    const animate = (currentTime) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // Easing outQuad
      const easeProgress = progress * (2 - progress);
      const currentVal = Math.round(start + (end - start) * easeProgress);
      
      setDisplayValue(currentVal);
      
      if (progress < 1) {
        animationFrameId = requestAnimationFrame(animate);
      }
    };
    
    animationFrameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrameId);
  }, [value]);
  
  return <span>{displayValue}</span>;
}

function AnimatedDuration({ seconds }) {
  const [displaySeconds, setDisplaySeconds] = useState(0);
  
  useEffect(() => {
    let start = displaySeconds;
    const end = parseInt(seconds, 10) || 0;
    if (start === end) return;
    
    const duration = 400;
    const startTime = performance.now();
    let animationFrameId;
    
    const animate = (currentTime) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const easeProgress = progress * (2 - progress);
      const currentVal = Math.round(start + (end - start) * easeProgress);
      
      setDisplaySeconds(currentVal);
      
      if (progress < 1) {
        animationFrameId = requestAnimationFrame(animate);
      }
    };
    
    animationFrameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrameId);
  }, [seconds]);
  
  // Format as "Xm Ys"
  const m = Math.floor(displaySeconds / 60);
  const s = displaySeconds % 60;
  
  if (m === 0 && s === 0) return <span>0s</span>;
  return <span>{m > 0 ? `${m}m ` : ''}{s}s</span>;
}

export function MetricCards({ stats }) {
  const { total_calls = 0, today_calls = 0, outcomes = {}, avg_duration_seconds = 0, recordings_saved = 0 } = stats;
  
  const interestedCount = outcomes.Interested || 0;
  const conversionRate = total_calls > 0 ? Math.round((interestedCount / total_calls) * 100) : 0;
  
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {/* Card 1: Today's Calls */}
      <div className="bg-[#161E2E] border border-[#243048]/80 rounded-xl p-5 shadow-lg relative overflow-hidden transition-all duration-300 hover:border-emerald-500/30 group">
        <div className="flex justify-between items-start">
          <div>
            <p className="text-gray-400 text-xs font-semibold uppercase tracking-wider">Today's Calls</p>
            <h3 className="text-3xl font-bold font-mono text-white mt-2">
              <AnimatedNumber value={today_calls} />
            </h3>
          </div>
          <div className="p-3 bg-emerald-500/10 text-emerald-400 rounded-lg group-hover:bg-emerald-500/20 transition-all duration-300">
            <Phone size={20} />
          </div>
        </div>
        <div className="text-[11px] text-gray-500 mt-4 flex items-center gap-1">
          <span className="text-emerald-400 font-semibold">{total_calls}</span> total calls recorded all-time
        </div>
      </div>

      {/* Card 2: Interested / Conversion */}
      <div className="bg-[#161E2E] border border-[#243048]/80 rounded-xl p-5 shadow-lg relative overflow-hidden transition-all duration-300 hover:border-blue-500/30 group">
        <div className="flex justify-between items-start">
          <div>
            <p className="text-gray-400 text-xs font-semibold uppercase tracking-wider">Interested leads</p>
            <h3 className="text-3xl font-bold font-mono text-white mt-2">
              <AnimatedNumber value={interestedCount} />
            </h3>
          </div>
          <div className="p-3 bg-blue-500/10 text-blue-400 rounded-lg group-hover:bg-blue-500/20 transition-all duration-300">
            <CheckCircle size={20} />
          </div>
        </div>
        <div className="text-[11px] text-gray-400 mt-4">
          <span className="text-blue-400 font-bold font-mono text-xs">{conversionRate}%</span> conversion rate from calls
        </div>
      </div>

      {/* Card 3: Avg Duration */}
      <div className="bg-[#161E2E] border border-[#243048]/80 rounded-xl p-5 shadow-lg relative overflow-hidden transition-all duration-300 hover:border-amber-500/30 group">
        <div className="flex justify-between items-start">
          <div>
            <p className="text-gray-400 text-xs font-semibold uppercase tracking-wider">Avg Call Duration</p>
            <h3 className="text-3xl font-bold font-mono text-white mt-2">
              <AnimatedDuration seconds={avg_duration_seconds} />
            </h3>
          </div>
          <div className="p-3 bg-amber-500/10 text-amber-400 rounded-lg group-hover:bg-amber-500/20 transition-all duration-300">
            <Clock size={20} />
          </div>
        </div>
        <div className="text-[11px] text-gray-500 mt-4">
          Weighted average across all outbound dial runs
        </div>
      </div>

      {/* Card 4: Recordings Saved */}
      <div className="bg-[#161E2E] border border-[#243048]/80 rounded-xl p-5 shadow-lg relative overflow-hidden transition-all duration-300 hover:border-purple-500/30 group">
        <div className="flex justify-between items-start">
          <div>
            <p className="text-gray-400 text-xs font-semibold uppercase tracking-wider">Recordings Saved</p>
            <h3 className="text-3xl font-bold font-mono text-white mt-2">
              <AnimatedNumber value={recordings_saved} />
            </h3>
          </div>
          <div className="p-3 bg-purple-500/10 text-purple-400 rounded-lg group-hover:bg-purple-500/20 transition-all duration-300">
            <Mic size={20} />
          </div>
        </div>
        <div className="text-[11px] text-gray-500 mt-4">
          Saved as high-quality mono WAV files
        </div>
      </div>
    </div>
  );
}

export default MetricCards;
