import React, { useState, useRef } from 'react';
import { Upload, FileSpreadsheet, Play, CheckCircle2, AlertCircle, X } from 'lucide-react';
import api from '../api/client';

export function UploadCSV({ onUploadSuccess }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState([]);
  const [error, setError] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [dryRun, setDryRun] = useState(true); // default to true to protect real phone lines
  const [limit, setLimit] = useState(5);
  const [dialerStatus, setDialerStatus] = useState(''); // 'idle', 'running', 'complete'
  
  const fileInputRef = useRef(null);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      processFile(droppedFile);
    }
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      processFile(selectedFile);
    }
  };

  const processFile = (selectedFile) => {
    setError('');
    setPreview([]);
    
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

      // Check header columns
      const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
      
      const hasName = headers.some(h => h.includes('name'));
      const hasPhone = headers.some(h => h.includes('phone'));
      const hasType = headers.some(h => h.includes('type'));

      if (!hasName || !hasPhone || !hasType) {
        setError('CSV must contain header columns: name, phone, type');
        return;
      }

      // Extract preview rows (up to 5)
      const previewRows = [];
      const colMap = {
        name: headers.findIndex(h => h.includes('name')),
        phone: headers.findIndex(h => h.includes('phone')),
        type: headers.findIndex(h => h.includes('type'))
      };

      for (let i = 1; i < Math.min(lines.length, 6); i++) {
        // Simple comma split, keeping in mind quoted strings if any (basic parser)
        const cols = lines[i].split(',').map(c => c.replace(/^["']|["']$/g, '').trim());
        if (cols.length >= 3) {
          previewRows.push({
            name: cols[colMap.name] || 'N/A',
            phone: cols[colMap.phone] || 'N/A',
            type: cols[colMap.type] || 'N/A'
          });
        }
      }

      setPreview(previewRows);
      setFile(selectedFile);
      setDialerStatus('idle');
    };
    
    reader.onerror = () => {
      setError('Error reading file.');
    };
    
    reader.readAsText(selectedFile);
  };

  const handleStartCalling = async () => {
    if (!file) return;
    setIsUploading(true);
    setDialerStatus('running');
    
    try {
      await api.postCSV(file, limit || null, dryRun);
      if (onUploadSuccess) {
        onUploadSuccess();
      }
    } catch (err) {
      console.error(err);
      setDialerStatus('idle');
    } finally {
      setIsUploading(false);
    }
  };

  const clearFile = () => {
    setFile(null);
    setPreview([]);
    setError('');
    setDialerStatus('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="bg-[#161E2E] border border-[#243048] rounded-xl p-6 mb-6 shadow-lg">
      <h3 className="text-md font-bold text-white mb-4 flex items-center gap-2">
        <FileSpreadsheet className="text-emerald-500" size={18} />
        Upload Target Businesses CSV
      </h3>

      {!file ? (
        /* Drag & Drop Area */
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
          <Upload className="mx-auto text-gray-500 mb-3 group-hover:text-emerald-400" size={32} />
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
        /* File selected & Configuration state */
        <div>
          {/* File details banner */}
          <div className="flex items-center justify-between bg-[#0B0F19] border border-[#243048] p-3 rounded-lg mb-4">
            <div className="flex items-center gap-2 text-xs">
              <FileSpreadsheet className="text-emerald-400" size={16} />
              <span className="font-semibold text-gray-200">{file.name}</span>
              <span className="text-gray-500">({Math.round(file.size / 1024)} KB)</span>
            </div>
            <button onClick={clearFile} className="text-gray-500 hover:text-white">
              <X size={16} />
            </button>
          </div>

          {/* Preview Table */}
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

          {/* Dialer Configuration Form */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-[#0B0F19]/60 p-4 rounded-xl border border-[#243048] mb-4">
            {/* Dry Run Option */}
            <div className="flex items-center justify-between">
              <div>
                <label className="text-xs font-semibold text-gray-300 block">Simulation Mode (Dry Run)</label>
                <span className="text-[10px] text-gray-500">Generates AI conversations without active calling charges.</span>
              </div>
              <input
                type="checkbox"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                className="w-4 h-4 rounded border-[#243048] bg-[#0B0F19] text-emerald-500 focus:ring-emerald-500"
              />
            </div>

            {/* Limit Option */}
            <div className="flex items-center justify-between">
              <div>
                <label className="text-xs font-semibold text-gray-300 block">Dial Limit</label>
                <span className="text-[10px] text-gray-500">Maximum businesses to dial from the CSV.</span>
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

          {/* Action buttons & Dial indicators */}
          <div className="flex justify-between items-center">
            {dialerStatus === 'running' ? (
              <div className="flex items-center gap-2 text-xs text-amber-400 font-medium font-mono animate-pulse">
                <span className="w-2 h-2 rounded-full bg-amber-500 inline-block animate-ping"></span>
                <span>Dialer Active. Live results will stream into table below...</span>
              </div>
            ) : dialerStatus === 'complete' ? (
              <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold font-mono">
                <CheckCircle2 size={15} />
                <span>Queue initialized. Monitor results below.</span>
              </div>
            ) : (
              <div className="text-xs text-gray-500">
                Ready to initiate dialing sequence.
              </div>
            )}

            <button
              onClick={handleStartCalling}
              disabled={isUploading || dialerStatus === 'running'}
              className="flex items-center gap-2 px-5 py-2 bg-emerald-500 hover:bg-emerald-400 text-darkBg font-semibold rounded-lg text-xs shadow-[0_0_15px_rgba(16,185,129,0.25)] hover:scale-[1.02] disabled:scale-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
            >
              <Play size={14} fill="currentColor" />
              <span>{isUploading ? 'Initializing...' : 'Start Calling'}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default UploadCSV;
