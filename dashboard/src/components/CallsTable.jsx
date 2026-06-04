import React from 'react';
import { Play, Trash2, Smile, Meh, Frown, PhoneIncoming, AlertCircle } from 'lucide-react';
import OutcomesBadge from './OutcomesBadge';
import api from '../api/client';

const formatTimeAndAgo = (dateStr) => {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  
  const timeStr = date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
  
  const seconds = Math.floor((new Date() - date) / 1000);
  if (seconds < 0) return `${timeStr} · Just now`;
  
  let interval = Math.floor(seconds / 86400);
  if (interval >= 1) return `${timeStr} · ${interval}d ago`;
  
  interval = Math.floor(seconds / 3600);
  if (interval >= 1) return `${timeStr} · ${interval}h ago`;
  
  interval = Math.floor(seconds / 60);
  if (interval >= 1) return `${timeStr} · ${interval}m ago`;
  
  return `${timeStr} · Just now`;
};

const formatDuration = (secs) => {
  if (isNaN(secs) || secs === null) return '0s';
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
};

const getSentimentTextClass = (sentiment) => {
  switch (sentiment) {
    case 'Positive':
      return { textClass: 'text-green-600', icon: <Smile className="text-green-500" size={15} /> };
    case 'Negative':
      return { textClass: 'text-red-500', icon: <Frown className="text-red-500" size={15} /> };
    case 'Neutral':
    default:
      return { textClass: 'text-gray-400', icon: <Meh className="text-gray-400" size={15} /> };
  }
};

export function CallsTable({
  calls,
  total,
  isLoading,
  page,
  limit,
  setPage,
  onRowClick,
  onDeleteSuccess
}) {
  const handleDelete = async (e, id) => {
    e.stopPropagation(); // prevent opening the drawer
    if (confirm("Are you sure you want to delete this call record and its recording?")) {
      try {
        await api.deleteCall(id);
        if (onDeleteSuccess) onDeleteSuccess();
      } catch (err) {
        console.error(err);
      }
    }
  };

  const handlePlayClick = (e, call) => {
    e.stopPropagation();
    onRowClick(call, true); // Open drawer and start audio playback
  };

  // Check if a call was added in the last 20 seconds
  const isNewCall = (dateStr) => {
    if (!dateStr) return false;
    const diff = new Date() - new Date(dateStr);
    return diff > 0 && diff < 20000;
  };

  if (isLoading) {
    return (
      <div className="bg-[#161E2E] border border-[#243048] rounded-xl overflow-hidden shadow-lg">
        <div className="p-6 divide-y divide-[#243048]/50">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="py-4 animate-pulse flex justify-between items-center">
              <div className="space-y-2">
                <div className="h-4 bg-[#243048] rounded w-48"></div>
                <div className="h-3 bg-[#243048] rounded w-32"></div>
              </div>
              <div className="h-6 bg-[#243048] rounded-full w-24"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (calls.length === 0) {
    return (
      <div className="bg-[#161E2E] border border-[#243048] rounded-xl p-12 text-center shadow-lg flex flex-col items-center justify-center">
        <div className="p-4 bg-emerald-500/10 text-emerald-400 rounded-full mb-4">
          <PhoneIncoming size={32} />
        </div>
        <h4 className="text-md font-bold text-white mb-1">No calls yet</h4>
        <p className="text-xs text-gray-500 max-w-sm mb-6">
          There are no outbound call records in the database. Upload a CSV of target businesses to start calling.
        </p>
      </div>
    );
  }

  const startIdx = page * limit + 1;
  const endIdx = Math.min(startIdx + calls.length - 1, total);

  return (
    <div className="bg-[#161E2E] border border-[#243048] rounded-xl overflow-hidden shadow-lg flex flex-col">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-gray-400">
          <thead className="bg-[#0B0F19] text-xs text-gray-400 uppercase tracking-wider font-semibold border-b border-[#243048]">
            <tr>
              <th className="px-6 py-4">Business</th>
              <th className="px-6 py-4">Time Called</th>
              <th className="px-6 py-4">Duration</th>
              <th className="px-6 py-4">Outcome</th>
              <th className="px-6 py-4">Sentiment</th>
              <th className="px-6 py-4 text-center">Audio</th>
              <th className="px-6 py-4 text-center">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#243048]/40">
            {calls.map((call) => {
              const { textClass, icon } = getSentimentTextClass(call.sentiment);
              const flash = isNewCall(call.called_at);
              
              return (
                <tr
                  key={call.id}
                  onClick={() => onRowClick(call, false)}
                  className={`hover:bg-[#243048]/30 transition-colors cursor-pointer group ${
                    flash ? 'new-call-flash' : ''
                  }`}
                >
                  {/* Business info */}
                  <td className="px-6 py-4">
                    <div className="font-semibold text-white group-hover:text-emerald-400 transition-colors">
                      {call.business_name}
                    </div>
                    <div className="text-xs text-gray-500 font-mono mt-0.5">{call.phone_number}</div>
                  </td>
                  
                  {/* Time called */}
                  <td className="px-6 py-4 text-xs font-medium text-gray-300">
                    {formatTimeAndAgo(call.called_at)}
                  </td>
                  
                  {/* Duration */}
                  <td className="px-6 py-4 text-xs font-mono text-gray-300">
                    {formatDuration(call.duration_seconds)}
                  </td>
                  
                  {/* Outcome badge */}
                  <td className="px-6 py-4">
                    <OutcomesBadge outcome={call.outcome} />
                  </td>
                  
                  {/* Sentiment */}
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-1.5 text-xs font-semibold">
                      {icon}
                      <span className={textClass}>{call.sentiment}</span>
                    </div>
                  </td>
                  
                  {/* Play Button */}
                  <td className="px-6 py-4 text-center">
                    <button
                      onClick={(e) => handlePlayClick(e, call)}
                      className="p-2 rounded-lg bg-[#0B0F19] hover:bg-emerald-500 text-gray-400 hover:text-darkBg border border-[#243048] hover:border-emerald-400 transition-all duration-200"
                    >
                      <Play size={13} fill="currentColor" />
                    </button>
                  </td>
                  
                  {/* Actions (Delete) */}
                  <td className="px-6 py-4 text-center">
                    <button
                      onClick={(e) => handleDelete(e, call.id)}
                      className="p-2 rounded-lg bg-[#0B0F19] hover:bg-red-500/20 text-gray-500 hover:text-red-400 border border-[#243048] hover:border-red-900/50 transition-all duration-200"
                    >
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {total > limit && (
        <div className="flex justify-between items-center px-6 py-4 bg-[#0B0F19] border-t border-[#243048]">
          <span className="text-xs text-gray-500">
            Showing <span className="font-semibold text-gray-300">{startIdx}</span>-
            <span className="font-semibold text-gray-300">{endIdx}</span> of{' '}
            <span className="font-semibold text-gray-300">{total}</span> calls
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 text-xs font-medium text-gray-300 bg-[#161E2E] hover:bg-[#243048] border border-[#243048] rounded-md disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={endIdx >= total}
              className="px-3 py-1.5 text-xs font-medium text-gray-300 bg-[#161E2E] hover:bg-[#243048] border border-[#243048] rounded-md disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default CallsTable;
