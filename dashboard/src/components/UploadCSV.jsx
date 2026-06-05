import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Upload, FileSpreadsheet, Play, CheckCircle2, AlertCircle, X,
  Phone, Clock, CheckCircle, XCircle, Loader2, RefreshCw, TerminalSquare
} from 'lucide-react';
import api from '../api/client';

const MAX_LOG_ENTRIES = 200;

const nowStamp = () => new Date().toLocaleTimeString();
const formatJobLabel = (value) => {
  if (!value) return 'unknown';
  return String(value).slice(0, 8);
};

export function UploadCSV({ onUploadSuccess }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState([]);
  const [error, setError] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [dryRun, setDryRun] = useState(true);
  const [limit, setLimit] = useState(5);

  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [callResults, setCallResults] = useState([]);
  const [warnings, setWarnings] = useState([]);
  const [globalError, setGlobalError] = useState('');
  const [preflight, setPreflight] = useState(null);
  const [activityLog, setActivityLog] = useState([]);

  const fileInputRef = useRef(null);
  const pollIntervalRef = useRef(null);
  const seenLogKeysRef = useRef(new Set());

  const addLog = useCallback((level, message, meta = {}) => {
    const entry = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      level,
      message,
      meta,
      timestamp: nowStamp(),
    };

    setActivityLog((prev) => [...prev, entry].slice(-MAX_LOG_ENTRIES));

    const fn = level === 'error' ? console.error : level === 'warn' ? console.warn : console.log;
    fn('[Campaign]', message, meta);
  }, []);

  const resetCampaignState = useCallback(() => {
    setGlobalError('');
    setJobId(null);
    setJobStatus(null);
    setCallResults([]);
    setWarnings([]);
    setPreflight(null);
    setActivityLog([]);
    seenLogKeysRef.current = new Set();
  }, []);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  const ingestJobStatus = useCallback((data) => {
    setJobStatus(data.status);
    setCallResults(data.call_results || []);
    setWarnings(data.warnings || []);
    setGlobalError(data.error_message || '');

    if (data.error_message) {
      addLog('error', `Job error: ${data.error_message}`, data);
    }

    (data.warnings || []).forEach((warning, index) => {
      const key = `warning:${warning}:${index}`;
      if (!seenLogKeysRef.current.has(key)) {
        seenLogKeysRef.current.add(key);
        addLog('warn', warning);
      }
    });

    (data.call_results || []).forEach((item, index) => {
      const key = `${item.step}:${item.status}:${item.title || ''}:${item.note || ''}:${item.error || ''}:${index}`;
      if (seenLogKeysRef.current.has(key)) return;
      seenLogKeysRef.current.add(key);

      const message = item.title
        ? `${item.title}${item.detail ? ` — ${item.detail}` : ''}`
        : item.business_name
          ? `${item.business_name}: ${item.status}${item.error ? ` — ${item.error}` : item.note ? ` — ${item.note}` : ''}`
          : `${item.status}${item.error ? ` — ${item.error}` : item.note ? ` — ${item.note}` : ''}`;

      const level = item.level || (item.status === 'error' || item.status === 'failed' ? 'error' : item.status === 'simulated' ? 'warn' : 'info');
      addLog(level, message, item);
    });

    if (data.status === 'completed') {
      addLog('info', 'Campaign completed.', data);
      stopPolling();
      if (onUploadSuccess) onUploadSuccess();
    }

    if (data.status === 'failed') {
      addLog('error', 'Campaign failed.', data);
      stopPolling();
      if (onUploadSuccess) onUploadSuccess();
    }
  }, [addLog, onUploadSuccess, stopPolling]);

  const pollJobStatus = useCallback(async (currentJobId) => {
    if (!currentJobId) {
      const message = 'Campaign started, but the server did not return a job ID.';
      setGlobalError(message);
      addLog('error', message);
      stopPolling();
      return;
    }

    try {
      addLog('info', `Polling status for job ${formatJobLabel(currentJobId)}...`);
      const data = await api.getJobStatus(currentJobId);
      ingestJobStatus(data);
    } catch (err) {
      const message = err?.response?.data?.detail || err.message || 'Unknown polling error';
      setGlobalError(`Could not fetch campaign status: ${message}`);
      addLog('error', `Status polling failed: ${message}`, err?.response?.data || {});
    }
  }, [addLog, ingestJobStatus, stopPolling]);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  useEffect(() => {
    stopPolling();
    if (!jobId || jobStatus === 'completed' || jobStatus === 'failed') {
      return;
    }

    pollIntervalRef.current = setInterval(() => {
      pollJobStatus(jobId);
    }, 3000);

    return () => stopPolling();
  }, [jobId, jobStatus, pollJobStatus, stopPolling]);

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

  const processFile = (selectedFile) => {
    setError('');
    setPreview([]);
    resetCampaignState();

    if (!selectedFile.name.endsWith('.csv')) {
      setError('Please upload a valid CSV file (.csv)');
      addLog('error', 'Rejected file upload because the selected file is not a CSV.');
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target.result;
      const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);

      if (lines.length < 2) {
        setError('CSV is empty or missing data rows.');
        addLog('error', 'CSV validation failed: file has no business rows.');
        return;
      }

      const headers = lines[0].split(',').map((h) => h.trim().toLowerCase());
      const hasName = headers.some((h) => h.includes('name'));
      const hasPhone = headers.some((h) => h.includes('phone'));
      const hasType = headers.some((h) => h.includes('type'));

      if (!hasName || !hasPhone || !hasType) {
        setError('CSV must contain header columns: name, phone, type');
        addLog('error', 'CSV validation failed: required columns name, phone, type are missing.', { headers });
        return;
      }

      const previewRows = [];
      const colMap = {
        name: headers.findIndex((h) => h.includes('name')),
        phone: headers.findIndex((h) => h.includes('phone')),
        type: headers.findIndex((h) => h.includes('type')),
      };

      for (let i = 1; i < Math.min(lines.length, 6); i++) {
        const cols = lines[i].split(',').map((c) => c.replace(/^["']|["']$/g, '').trim());
        if (cols.length >= 3) {
          previewRows.push({
            name: cols[colMap.name] || 'N/A',
            phone: cols[colMap.phone] || 'N/A',
            type: cols[colMap.type] || 'N/A',
          });
        }
      }

      setPreview(previewRows);
      setFile(selectedFile);
      addLog('info', `CSV ready: ${selectedFile.name} with ${lines.length - 1} row(s).`);
    };

    reader.onerror = () => {
      setError('Error reading file.');
      addLog('error', 'Browser failed to read the selected CSV file.');
    };

    reader.readAsText(selectedFile);
  };

  const handleStartCalling = async () => {
    if (!file) return;

    stopPolling();
    setIsUploading(true);
    resetCampaignState();
    addLog('info', `Starting campaign upload for ${file.name}...`, { dryRun, limit });

    try {
      const resp = await api.postCSV(file, limit || null, dryRun);
      const nextJobId = resp?.job_id ?? resp?.jobId ?? resp?.id ?? null;

      setPreflight(resp.preflight || null);
      setJobId(nextJobId);
      setJobStatus(nextJobId ? 'pending' : null);

      if (!nextJobId) {
        const message = resp?.message || resp?.detail || 'Upload succeeded, but no job ID was returned by the server.';
        setGlobalError(message);
        addLog('error', message, resp || {});
        return;
      }

      addLog('info', `Campaign queued successfully. Job ID: ${nextJobId}`, resp);
      if (resp.preflight) {
        addLog(resp.preflight.ok ? 'info' : 'error', `Preflight result: ${resp.preflight.summary}`, resp.preflight);
      }

      await pollJobStatus(nextJobId);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const message = typeof detail === 'string'
        ? detail
        : detail?.message || err.message || 'Upload failed. Please try again.';
      const preflightData = detail?.preflight || null;

      setGlobalError(message);
      setPreflight(preflightData);
      addLog('error', `Campaign rejected: ${message}`, detail || {});

      if (preflightData?.errors?.length) {
        preflightData.errors.forEach((item) => addLog('error', item));
      }
    } finally {
      setIsUploading(false);
    }
  };

  const clearFile = () => {
    stopPolling();
    setFile(null);
    setPreview([]);
    setError('');
    resetCampaignState();
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const isRunning = jobStatus === 'pending' || jobStatus === 'running';
  const isDone = jobStatus === 'completed' || jobStatus === 'failed';

  const statusLabel = {
    pending: { text: 'Job queued — waiting for worker...', color: 'text-amber-400' },
    running: { text: 'Calls in progress...', color: 'text-blue-400' },
    completed: { text: 'All calls finished', color: 'text-emerald-400' },
    failed: { text: 'Job failed', color: 'text-red-400' },
  }[jobStatus] || { text: '', color: 'text-gray-400' };

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

  const renderPreflight = () => {
    if (!preflight) return null;

    return (
      <div className={`mb-4 rounded-xl border ${preflight.ok ? 'border-emerald-900/50 bg-emerald-950/10' : 'border-red-900/50 bg-red-950/10'} p-4`}>
        <div className="flex items-center gap-2 mb-2">
          {preflight.ok ? (
            <CheckCircle2 size={16} className="text-emerald-400" />
          ) : (
            <XCircle size={16} className="text-red-400" />
          )}
          <span className={`text-sm font-semibold ${preflight.ok ? 'text-emerald-300' : 'text-red-300'}`}>
            {preflight.summary}
          </span>
        </div>

        <div className="space-y-2 text-xs">
          {(preflight.checks || []).map((check, index) => (
            <div key={`${check.name}-${index}`} className="flex items-start gap-2">
              {check.ok ? (
                <CheckCircle size={13} className="text-emerald-400 mt-0.5 shrink-0" />
              ) : (
                <XCircle size={13} className="text-red-400 mt-0.5 shrink-0" />
              )}
              <span className="text-gray-300">
                <span className="font-semibold">{check.name}:</span> {check.detail}
              </span>
            </div>
          ))}

          {(preflight.warnings || []).map((warning, index) => (
            <div key={`warn-${index}`} className="flex items-start gap-2">
              <AlertCircle size={13} className="text-amber-400 mt-0.5 shrink-0" />
              <span className="text-amber-300">{warning}</span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderActivityLog = () => (
    <div className="mb-4 rounded-xl border border-[#243048] bg-[#0B0F19] overflow-hidden">
      <div className="px-4 py-3 border-b border-[#243048] flex items-center gap-2">
        <TerminalSquare size={15} className="text-cyan-400" />
        <span className="text-xs font-semibold text-gray-200">Campaign Activity Log</span>
        <span className="ml-auto text-[10px] text-gray-500 font-mono">Console mirrored</span>
      </div>
      <div className="max-h-64 overflow-y-auto font-mono text-[11px]">
        {activityLog.length === 0 ? (
          <div className="px-4 py-3 text-gray-500">No campaign events yet.</div>
        ) : (
          activityLog.map((entry) => (
            <div key={entry.id} className="px-4 py-2 border-b border-[#243048]/40 last:border-b-0 flex gap-3">
              <span className="text-gray-600 shrink-0">{entry.timestamp}</span>
              <span className={`shrink-0 ${entry.level === 'error' ? 'text-red-400' : entry.level === 'warn' ? 'text-amber-400' : 'text-cyan-300'}`}>
                {entry.level.toUpperCase()}
              </span>
              <span className="text-gray-300 break-all">{entry.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );

  return (
    <div className="bg-[#161E2E] border border-[#243048] rounded-xl p-6 mb-6 shadow-lg">
      <h3 className="text-md font-bold text-white mb-4 flex items-center gap-2">
        <FileSpreadsheet className="text-emerald-500" size={18} />
        Upload Target Businesses CSV
      </h3>

      {!file ? (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-300 ${
            isDragging ? 'border-emerald-500 bg-emerald-500/5' : 'border-gray-700 bg-[#0B0F19] hover:border-gray-500'
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

          {renderPreflight()}

          {globalError && (
            <div className="mb-4 flex items-start gap-2 px-4 py-3 bg-red-950/20 border border-red-900/30 rounded-xl text-xs text-red-300">
              <XCircle size={14} className="mt-0.5 shrink-0 text-red-400" />
              <span>{globalError}</span>
            </div>
          )}

          {warnings.map((w, i) => (
            <div key={i} className="mb-4 flex items-start gap-2 px-4 py-3 bg-amber-950/20 border border-amber-900/30 rounded-xl text-xs text-amber-300">
              <AlertCircle size={14} className="mt-0.5 shrink-0 text-amber-400" />
              <span>{w}</span>
            </div>
          ))}

          {jobId && (
            <div className="mb-4 rounded-xl border border-[#243048] bg-[#0B0F19] overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-[#243048]/50">
                {isRunning ? (
                  <Loader2 size={14} className={`${statusLabel.color} animate-spin shrink-0`} />
                ) : jobStatus === 'completed' ? (
                  <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                ) : jobStatus === 'failed' ? (
                  <XCircle size={14} className="text-red-400 shrink-0" />
                ) : null}
                <span className={`text-xs font-mono font-semibold ${statusLabel.color}`}>{statusLabel.text}</span>
                <span className="ml-auto text-[10px] text-gray-600 font-mono">job: {formatJobLabel(jobId)}...</span>
              </div>

              {callResults.length > 0 && (
                <div className="divide-y divide-[#243048]/50">
                  {callResults.filter((r) => r.type !== 'event').map((r, i) => (
                    <div key={i} className="flex items-center gap-3 px-4 py-2.5 hover:bg-[#161E2E]/30">
                      {getResultIcon(r.status)}
                      <span className="text-xs font-mono text-gray-400 w-5 text-right shrink-0">#{r.step}</span>
                      <span className="text-xs font-semibold text-gray-200 min-w-0 truncate flex-1">{r.business_name || 'Unknown'}</span>
                      <span className="text-xs font-mono text-gray-500 shrink-0">{r.phone_number || ''}</span>
                      {r.status === 'error' || r.status === 'failed' ? (
                        <span className="text-[10px] text-red-400 font-mono shrink-0 max-w-52 truncate" title={r.error || r.note}>
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

              {isDone && (
                <div className="px-4 py-3 border-t border-[#243048]/50">
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-400">{callResults.filter((r) => r.type !== 'event').length} call(s) processed</span>
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

          {renderActivityLog()}

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
                  onChange={(e) => setLimit(parseInt(e.target.value, 10) || 0)}
                  className="w-16 bg-[#0B0F19] border border-[#243048] focus:border-emerald-500 rounded px-2 py-1 text-xs text-white font-mono text-center"
                />
              </div>
            </div>
          )}

          <div className="flex justify-between items-center">
            {!isRunning && (
              <div className="text-xs text-gray-500">
                {file ? `Ready to dial up to ${limit} businesses${dryRun ? ' (dry run)' : ''}.` : 'Upload a CSV to begin.'}
              </div>
            )}

            {!jobId || jobStatus === 'failed' ? (
              <button
                onClick={handleStartCalling}
                disabled={isUploading}
                className="flex items-center gap-2 px-5 py-2 bg-emerald-500 hover:bg-emerald-400 text-darkBg font-semibold rounded-lg text-xs shadow-[0_0_15px_rgba(16,185,129,0.25)] hover:scale-[1.02] disabled:scale-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 ml-auto"
              >
                <Play size={14} fill="currentColor" />
                <span>{isUploading ? 'Uploading...' : 'Start Calling'}</span>
              </button>
            ) : (
              <div className="ml-auto text-[10px] text-gray-600 font-mono">Polling for results every 3s</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default UploadCSV;
