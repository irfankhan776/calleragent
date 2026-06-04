import React, { useEffect } from 'react';
import { X, Smile, Meh, Frown, Calendar, Clock, Landmark } from 'lucide-react';
import OutcomesBadge from './OutcomesBadge';
import AudioPlayer from './AudioPlayer';
import TranscriptView from './TranscriptView';

const formatDateTime = (dateStr) => {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
};

const formatDuration = (secs) => {
  if (isNaN(secs) || secs === null) return '0s';
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
};

const getSentimentIcon = (sentiment) => {
  switch (sentiment) {
    case 'Positive':
      return <Smile className="text-green-500" size={16} />;
    case 'Negative':
      return <Frown className="text-red-500" size={16} />;
    case 'Neutral':
    default:
      return <Meh className="text-gray-400" size={16} />;
  }
};

export function CallDrawer({ call, isOpen, onClose }) {
  // Listen to Escape key to close the drawer
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }
    
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!call) return null;

  return (
    <div className={`fixed inset-0 z-50 transition-opacity duration-300 ${isOpen ? 'visible' : 'invisible'}`}>
      {/* Backdrop */}
      <div
        onClick={onClose}
        className={`absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity duration-300 ${
          isOpen ? 'opacity-100' : 'opacity-0'
        }`}
      />

      {/* Drawer Body */}
      <div
        className={`absolute right-0 top-0 bottom-0 w-full max-w-[450px] bg-[#161E2E] border-l border-[#243048] shadow-2xl flex flex-col transition-transform duration-300 transform ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {/* Header */}
        <div className="p-5 border-b border-[#243048] flex justify-between items-start">
          <div>
            <h3 className="text-lg font-bold text-white leading-snug">{call.business_name}</h3>
            <p className="text-xs font-mono text-gray-500 mt-0.5">{call.phone_number}</p>
            <div className="mt-2.5">
              <OutcomesBadge outcome={call.outcome} />
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg bg-[#0B0F19] hover:bg-[#243048] border border-[#243048] text-gray-400 hover:text-white transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Scrollable Content Container */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* Section 1: Audio Player */}
          <div>
            <h4 className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-3 font-mono">
              Call Recording
            </h4>
            <AudioPlayer callId={call.id} businessName={call.business_name} />
          </div>

          {/* Section 2: Details Row */}
          <div>
            <h4 className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-3 font-mono">
              Call metadata
            </h4>
            <div className="bg-[#0B0F19] rounded-xl border border-[#243048] divide-y divide-[#243048]/50 overflow-hidden text-xs">
              <div className="flex items-center justify-between p-3">
                <span className="text-gray-500 flex items-center gap-1.5">
                  <Calendar size={14} /> Called At
                </span>
                <span className="text-gray-300 font-medium">{formatDateTime(call.called_at)}</span>
              </div>
              <div className="flex items-center justify-between p-3">
                <span className="text-gray-500 flex items-center gap-1.5">
                  <Clock size={14} /> Duration
                </span>
                <span className="text-gray-300 font-mono font-medium">{formatDuration(call.duration_seconds)}</span>
              </div>
              <div className="flex items-center justify-between p-3">
                <span className="text-gray-500 flex items-center gap-1.5">
                  {getSentimentIcon(call.sentiment)} Sentiment
                </span>
                <span className="font-semibold text-gray-300">{call.sentiment}</span>
              </div>
              <div className="flex items-center justify-between p-3">
                <span className="text-gray-500 flex items-center gap-1.5">
                  <Landmark size={14} /> Category
                </span>
                <span className="text-gray-300 font-medium capitalize">{call.business_type}</span>
              </div>
            </div>
          </div>

          {/* Section 3: Transcript Chat UI */}
          <div>
            <h4 className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-3 font-mono">
              Conversation Transcript
            </h4>
            <TranscriptView transcript={call.transcript} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default CallDrawer;
