import React, { useState, useEffect, useRef } from 'react';
import { Play, Pause, Download, Volume2, VolumeX } from 'lucide-react';

const getAudioUrl = (callId) => {
  const base = import.meta.env.VITE_API_BASE_URL || '/api';
  return `${base.replace(/\/$/, '')}/calls/${callId}/audio`;
};

export function AudioPlayer({ callId, businessName }) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const [volume, setVolume] = useState(0.8);
  const [error, setError] = useState(false);
  
  const audioRef = useRef(null);
  const progressBarRef = useRef(null);
  const audioUrl = callId ? getAudioUrl(callId) : null;

  useEffect(() => {
    // Reset player on call change
    setIsPlaying(false);
    setCurrentTime(0);
    setDuration(0);
    setError(false);
    
    if (audioRef.current) {
      audioRef.current.load();
    }
  }, [callId]);

  const togglePlay = () => {
    if (error || !audioUrl) return;
    
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play().catch(err => {
        console.error("Audio playback error:", err);
        setError(true);
      });
    }
  };

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration);
    }
  };

  const handleAudioEnded = () => {
    setIsPlaying(false);
    setCurrentTime(0);
  };

  const handleAudioError = (e) => {
    console.error("Audio resource error:", e);
    setError(true);
    setIsPlaying(false);
  };

  const handleProgressClick = (e) => {
    if (!audioRef.current || duration === 0) return;
    
    const rect = progressBarRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const width = rect.width;
    const newPercentage = clickX / width;
    const newTime = newPercentage * duration;
    
    audioRef.current.currentTime = newTime;
    setCurrentTime(newTime);
  };

  const handleVolumeChange = (e) => {
    const val = parseFloat(e.target.value);
    setVolume(val);
    if (audioRef.current) {
      audioRef.current.volume = val;
      audioRef.current.muted = val === 0;
    }
    setIsMuted(val === 0);
  };

  const toggleMute = () => {
    const nextMute = !isMuted;
    setIsMuted(nextMute);
    if (audioRef.current) {
      audioRef.current.muted = nextMute;
      audioRef.current.volume = nextMute ? 0 : volume;
    }
  };

  // Format time (e.g. 02:45)
  const formatTime = (timeInSecs) => {
    if (isNaN(timeInSecs)) return '00:00';
    const mins = Math.floor(timeInSecs / 60);
    const secs = Math.floor(timeInSecs % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const progressPercentage = duration > 0 ? (currentTime / duration) * 100 : 0;

  // Render dummy waveform bar representation (looks extremely premium!)
  const renderWaveform = () => {
    const barsCount = 35;
    const bars = [];
    // Deterministic random heights for beautiful waveform display
    const seedHeights = [
      20, 45, 30, 60, 75, 40, 55, 90, 35, 65, 
      80, 50, 45, 70, 85, 30, 60, 75, 95, 40, 
      55, 70, 50, 30, 65, 80, 45, 60, 75, 35, 
      50, 65, 40, 30, 20
    ];
    
    for (let i = 0; i < barsCount; i++) {
      const isPlayed = (i / barsCount) * 100 <= progressPercentage;
      const height = seedHeights[i % seedHeights.length];
      
      bars.push(
        <div
          key={i}
          className={`w-[3px] rounded-full mx-[1px] transition-all duration-150`}
          style={{
            height: `${height}%`,
            backgroundColor: isPlayed ? '#10B981' : '#374151'
          }}
        />
      );
    }
    return bars;
  };

  return (
    <div className="bg-[#0B0F19] border border-[#243048] rounded-xl p-4 shadow-inner mb-6">
      {audioUrl && (
        <audio
          ref={audioRef}
          src={audioUrl}
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onEnded={handleAudioEnded}
          onError={handleAudioError}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
        />
      )}

      <div className="flex items-center gap-4">
        {/* Play/Pause Button */}
        <button
          onClick={togglePlay}
          disabled={error || !audioUrl}
          className={`flex items-center justify-center w-12 h-12 rounded-full transition-all duration-300 ${
            error
              ? 'bg-red-500/10 text-red-500 border border-red-500/30'
              : 'bg-emerald-500 hover:bg-emerald-400 text-darkBg shadow-[0_0_15px_rgba(16,185,129,0.3)] hover:scale-105'
          }`}
        >
          {isPlaying ? <Pause size={20} fill="currentColor" /> : <Play size={20} className="ml-1" fill="currentColor" />}
        </button>

        {/* Waveform & Progress Container */}
        <div className="flex-1">
          <div className="flex justify-between items-center mb-1 text-[10px] font-mono text-gray-500">
            <span>{formatTime(currentTime)}</span>
            <span>{formatTime(duration)}</span>
          </div>
          
          {/* Waveform Wrapper with seek capability */}
          <div
            ref={progressBarRef}
            onClick={handleProgressClick}
            className="h-10 flex items-center cursor-pointer relative select-none"
          >
            <div className="absolute inset-0 flex items-center justify-between opacity-80 pointer-events-none">
              {renderWaveform()}
            </div>
            
            {/* Invisibly handle click/hover tracking on top */}
            <div className="absolute inset-0 z-10 w-full h-full" />
          </div>
        </div>

        {/* Volume & Download controls */}
        <div className="flex flex-col items-end gap-2 pl-2">
          {/* Download button */}
          <a
            href={audioUrl ? `${audioUrl}?download=true` : '#'}
            download={`${businessName.replace(/\s+/g, '_')}_call.wav`}
            className="flex items-center gap-1.5 px-2.5 py-1 bg-[#161E2E] hover:bg-[#243048] border border-[#243048] hover:border-gray-500 text-gray-300 hover:text-white rounded-md text-xs font-medium transition-all duration-200"
            onClick={(e) => {
              if (!audioUrl || error) e.preventDefault();
            }}
          >
            <Download size={14} />
            <span>Download</span>
          </a>

          {/* Volume Control */}
          <div className="flex items-center gap-1.5">
            <button onClick={toggleMute} className="text-gray-400 hover:text-white transition-colors">
              {isMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}
            </button>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={isMuted ? 0 : volume}
              onChange={handleVolumeChange}
              className="w-12 h-1 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
            />
          </div>
        </div>
      </div>
      
      {error && (
        <div className="text-[11px] text-red-400 mt-2 font-mono text-center">
          ⚠️ Recording audio unavailable or failed to stream.
        </div>
      )}
    </div>
  );
}

export default AudioPlayer;
