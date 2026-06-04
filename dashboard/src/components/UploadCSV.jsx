import React, { useState, useRef, useEffect } from 'react';
import {
  Upload, FileSpreadsheet, Play, CheckCircle2, AlertCircle, X,
  Phone, PhoneOff, Clock, CheckCircle, XCircle, Loader2, RefreshCw
} from 'lucide-react';
import api from '../api/client';

export function UploadCSV({ onUploadSuccess }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState([]);
  const [error, setError] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [dryRun, setDryRun] = useState(true);
  const [limit, setLimit] = useState(5);

  // Job tracking state
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null); // null | 'pending' | 'running' | 'completed' | 'failed'
  const [callResults, setCallResults] = useState([]);
  const [warnings, setWarnings] = useState([]);
  const [globalError, setGlobalError] = useState('');
  const [pollCount, setPollCount] = useState(0);

  const fileInputRef = useRef(null);
  const pollIntervalRef = useRef(null);

  // ── Poll job status ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!jobId || jobStatus === 'completed' || jobStatus === 'failed') {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      return;
    }

    const poll = async () => {
      try {
        const resp = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}/jobs/${jobId}/status`);
        if (!resp.ok) throw new Error(`Status poll failed: ${resp.status}`);
        const data = await resp.json();

        setJobStatus(data.status);
        setCallResults(data.call_results || []);
        setWarnings(data.warnings || []);
        setGlobalError(data.error_message || '');

        // Stop polling on terminal states
        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
          if (onUploadSuccess) onUploadSuccess();
        }
      } catch (err) {
        // Don't spam errors — only show after several failed polls
        setPollCount(c => {
          const next = c + 1;
          if (next >= 3) {
            setGlobalError(
              `Cannot reach backend to check job status. Is the backend running? Error: ${err.message}`
            );
          }
          return next;
        });
      }
    };

    pollIntervalRef.current = setInterval(poll, 3000);
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [jobId, jobStatus, onUploadSuccess]);

  // ── Cleanup on unmount ────────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  // ── Drag & drop ─────────────────────────────────────────────────────────────
  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) processFile(droppedFile);
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) processFile(selectedFile);
  };

  // ── File processing ──────────────────────────────────────────────────────────
  const processFile = (selectedFile) => {
    setError('');
    setPreview([]);
    setGlobalError('');
    setJobId(null);
    setJobStatus(null);
    setCallResults([]);
    setWarnings([]);

    if (!selectedFile.name.endsWith('.csv')) {
      setError('Please upload a valid CSV file (.csv)');
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target.result;
      const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

      if (lines.length < 2) {
        setError('CSV is empty or missing data rows.');
        return;
      }

      const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
      const hasName  = headers.some(h => h.includes('name'));
      const hasPhone = headers.some(h => h.includes('phone'));
      const hasType  = headers.some(h => h.includes('type'));

      if (!hasName || !hasPhone || !hasType) {
        setError('CSV must contain header columns: name, phone, type');
        return;
      }

      const previewRows = [];
      const colMap = {
        name:  headers.findIndex(h => h.includes('name')),
        phone: headers.findIndex(h => h.includes('phone')),
        type:  headers.findIndex(h => h.includes('type')),
      };

      for (let i = 1; i < Math.min(lines.length, 6); i++) {
        const cols = lines[i].split(',').map(c => c.replace(/^["']|["']$/g, '').trim());
        if (cols.length >= 3) {
          previewRows.push({
            name:  cols[colMap.name]  || 'N/A',
            phone: cols[colMap.phone] || 'N/A',
            type:  cols[colMap.type]  || 'N/A',
          });
        }
      }

      setPreview(previewRows);
      setFile(selectedFile);
    };

    reader.onerror = () => setError('Error reading file.');
    reader.readAsText(selectedFile);
  };

  // ── Start calling ─────────────────────────────────────────────────────────────
  const handleStartCalling = async () => {
    if (!file) return;
    setIsUploading(true);
    setGlobalError('');
    setCallResults([]);
    setWarnings([]);
    setPollCount(0);
    setJobId(null);
    setJobStatus(null);

    try {
      const resp = await api.postCSV(file, limit || null, dryRun);
      const newJobId = resp.job_id;
      setJobId(newJobId);
      setJobStatus('pending');
    } catch (err) {
      setGlobalError(err?.response?.data?.detail || err.message || 'Upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  const clearFile = () => {
    setFile(null);
    setPreview([]);
    setError('');
    setGlobalError('');
    setJobId(null);
    setJobStatus(null);
    setCallResults([]);
    setWarnings([]);
    setPollCount(0);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // ── Status helpers ────────────────────────────────────────────────────────────
  const isRunning = jobStatus === 'pending' || jobStatus === 'running';
  const isDone    = jobStatus === 'completed' || jobStatus === 'failed';
  const hasErrors = globalError || warnings.length > 0 ||
    callResults.some(r => r.status === 'error' || r.status === 'failed');

  const statusLabel = {
    pending:   { text: 'Job queued — waiting for worker...', color: 'text-amber-400', pulse: true },
    running:   { text: 'Calls in progress...',              color: 'text-blue-400',   pulse: true },
    completed: { text: 'All calls finished',                  color: 'text-emerald-400', pulse: false },
    failed:    { text: 'Job failed',                          color: 'text-red-400',    pulse: false },
  }[jobStatus] || { text: '', color: 'text-gray-400', pulse: false };

  const getResultIcon = (status) => {
    switch (status) {
      case 'initiated':
      case 'running':
        return <Phone size={13} className="text-blue-400 animate-pulse" />;
      case 'simulated':
        return <RefreshCw size={13} className="text-amber-400" />;
      case 'error':
      case 'failed':
        return <XCircle size={13} className="text-red-400" />;
      case 'completed':
        return <CheckCircle size={13} className="text-emerald-400" />;
      default:
        return <Clock size={13} className="text-gray-500" />;
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="bg-[#161E2E] border border-[#243048] rounded-xl p-6 mb-6 shadow-lg">

      {/* ── Header ── */}
      <h3 className="text-md font-bold text-white mb-4 flex items-center gap-2">
        <FileSpreadsheet className="text-emerald-500" size={18} />
        Upload Target Businesses CSV
      </h3>

      {/* ── Upload Area (no file selected) ── */}
      {!file ? (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-300 ${
            isDragging
              ? 'border-emerald-500 bg-emerald-500/5'
              : 'border-gray-700 bg-[#0B0F19] hover:border-gray-500'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={handleFileChange}
          />
          <Upload className="mx-auto text-gray-500 mb-3" size={32} />
          <p className="text-sm font-semibold text-gray-300">Drag & drop your CSV file here, or click to browse</p>
          <p className="text-xs text-gray-500 mt-2 font-mono">Requires columns: name, phone, type</p>

          {error && (
            <div className="mt-4 flex items-center justify-center gap-1.5 text-xs text-red-400 bg-red-950/20 py-1.5 px-3 rounded-lg border border-red-900/30">
              <AlertCircle size={14} />
              <span>{error}</span>
            </div>
          )}
        </div>
      ) : (
        <div>

          {/* ── File banner ── */}
          <div className="flex items-center justify-between bg-[#0B0F19] border border-[#243048] p-3 rounded-lg mb-4">
            <div className="flex items-center gap-2 text-xs">
              <FileSpreadsheet className="text-emerald-400" size={16} />
              <span className="font-semibold text-gray-200">{file.name}</span>
              <span className="text-gray-500">({Math.round(file.size / 1024)} KB)</span>
            </div>
            {!isRunning && (
              <button onClick={clearFile} className="text-gray-500 hover:text-white">
                <X size={16} />
              </button>
            )}
          </div>

          {/* ── CSV Preview ── */}
          <div className="mb-4">
            <p className="text-xs font-semibold text-gray-400 mb-2">CSV Data Preview (First 5 Rows)</p>
            <div className="overflow-x-auto rounded-lg border border-[#243048]">
              <table className="w-full text-xs text-left text-gray-400 bg-[#0B0F19]">
                <thead className="bg-[#161E2E] text-gray-300 font-semibold border-b border-[#243048]">
                  <tr>
                    <th className="px-4 py-2">Business Name</th>
                    <th className="px-4 py-2">Phone Number</th>
                    <th className="px-4 py-2">Business Type</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.map((row, index) => (
                    <tr key={index} className="border-b border-[#243048]/50 last:border-0 hover:bg-[#161E2E]/30">
                      <td className="px-4 py-2 font-medium text-gray-300">{row.name}</td>
                      <td className="px-4 py-2 font-mono">{row.phone}</td>
                      <td className="px-4 py-2">{row.type}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── Job Progress Panel ── */}
          {jobId && (
            <div className="mb-4 rounded-xl border border-[#243048] bg-[#0B0F19] overflow-hidden">

              {/* Global warnings */}
              {warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-2 px-4 py-3 bg-amber-950/20 border-b border-amber-900/30 text-xs text-amber-300">
                  <AlertCircle size={14} className="mt-0.5 shrink-0 text-amber-400" />
                  <span>{w}</span>
                </div>
              ))}

              {/* Global error (from backend job) */}
              {globalError && (
                <div className="flex items-start gap-2 px-4 py-3 bg-red-950/20 border-b border-red-900/30 text-xs text-red-300">
                  <XCircle size={14} className="mt-0.5 shrink-0 text-red-400" />
                  <span className="font-semibold">JOB FAILED: </span>
                  <span>{globalError}</span>
                </div>
              )}

              {/* Status bar */}
              <div className={`flex items-center gap-2 px-4 py-3 ${warnings.length > 0 ? '' : 'border-b border-[#243048]/50'}`}>
                {isRunning ? (
                  <Loader2 size={14} className={`${statusLabel.color} animate-spin shrink-0`} />
                ) : jobStatus === 'completed' ? (
                  <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                ) : jobStatus === 'failed' ? (
                  <XCircle size={14} className="text-red-400 shrink-0" />
                ) : null}

                <span className={`text-xs font-mono font-semibold ${statusLabel.color}`}>
                  {statusLabel.text}
                </span>

                {jobId && (
                  <span className="ml-auto text-[10px] text-gray-600 font-mono">
                    job: {jobId.slice(0, 8)}...
                  </span>
                )}
              </div>

              {/* Per-call results */}
              {callResults.length > 0 && (
                <div className="divide-y divide-[#243048]/50">
                  {callResults.map((r, i) => (
                    <div key={i} className="flex items-center gap-3 px-4 py-2.5 hover:bg-[#161E2E]/30">
                      {getResultIcon(r.status)}
                      <span className="text-xs font-mono text-gray-400 w-5 text-right shrink-0">
                        #{r.step}
                      </span>
                      <span className="text-xs font-semibold text-gray-200 min-w-0 truncate flex-1">
                        {r.business_name || 'Unknown'}
                      </span>
                      <span className="text-xs font-mono text-gray-500 shrink-0">
                        {r.phone_number || r.phone_number || ''}
                      </span>
                      {r.status === 'error' || r.status === 'failed' ? (
                        <span className="text-[10px] text-red-400 font-mono shrink-0 max-w-40 truncate" title={r.error || r.note}>
                          ✕ {r.error || r.note || 'Unknown error'}
                        </span>
                      ) : r.status === 'simulated' ? (
                        <span className="text-[10px] text-amber-400 font-mono shrink-0">DRY RUN</span>
                      ) : (
                        <span className="text-[10px] text-emerald-400 font-mono shrink-0">✓ {r.outcome || r.note || 'OK'}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Done state — summary */}
              {isDone && (
                <div className="px-4 py-3 border-t border-[#243048]/50">
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-400">
                      {callResults.length} call(s) processed
                    </span>
                    <span className="ml-auto flex items-center gap-1 text-[10px] text-gray-600">
                      {jobStatus === 'completed' ? (
                        <><CheckCircle size={12} className="text-emerald-600" /> completed</>
                      ) : (
                        <><XCircle size={12} className="text-red-600" /> failed</>
                      )}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Config form ── */}
          {!isRunning && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-[#0B0F19]/60 p-4 rounded-xl border border-[#243048] mb-4">
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-xs font-semibold text-gray-300 block">Simulation Mode (Dry Run)</label>
                  <span className="text-[10px] text-gray-500">No real calls — simulates AI conversations</span>
                </div>
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={(e) => setDryRun(e.target.checked)}
                  className="w-4 h-4 rounded border-[#243048] bg-[#0B0F19] text-emerald-500 focus:ring-emerald-500"
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <label className="text-xs font-semibold text-gray-300 block">Dial Limit</label>
                  <span className="text-[10px] text-gray-500">Maximum businesses to dial from CSV</span>
                </div>
                <input
                  type="number"
                  min="1"
                  max="50"
                  value={limit}
                  onChange={(e) => setLimit(parseInt(e.target.value) || 0)}
                  className="w-16 bg-[#0B0F19] border border-[#243048] focus:border-emerald-500 rounded px-2 py-1 text-xs text-white font-mono text-center"
                />
              </div>
            </div>
          )}

          {/* ── Action bar ── */}
          <div className="flex justify-between items-center">
            {!isRunning && (
              <div className="text-xs text-gray-500">
                {file ? `Ready to dial up to ${limit} businesses${dryRun ? ' (dry run)' : ''}.` : 'Upload a CSV to begin.'}
              </div>
            )}

            {!jobId ? (
              <button
                onClick={handleStartCalling}
                disabled={isUploading}
                className="flex items-center gap-2 px-5 py-2 bg-emerald-500 hover:bg-emerald-400 text-darkBg font-semibold rounded-lg text-xs shadow-[0_0_15px_rgba(16,185,129,0.25)] hover:scale-[1.02] disabled:scale-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 ml-auto"
              >
                <Play size={14} fill="currentColor" />
                <span>{isUploading ? 'Uploading...' : 'Start Calling'}</span>
              </button>
            ) : (
              <div className="ml-auto text-[10px] text-gray-600 font-mono">
                Polling for results every 3s
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  );
}

export default UploadCSV;
