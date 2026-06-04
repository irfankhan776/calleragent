import React from 'react';

export function parseTranscript(transcript) {
  if (!transcript) return [];
  
  const lines = transcript.split('\n');
  const messages = [];
  
  let currentSender = '';
  let currentText = '';
  
  for (let line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    
    if (trimmed.startsWith('Agent:')) {
      if (currentSender && currentText) {
        messages.push({ sender: currentSender, text: currentText });
      }
      currentSender = 'Agent';
      currentText = trimmed.substring(6).trim();
    } else if (trimmed.startsWith('Owner:')) {
      if (currentSender && currentText) {
        messages.push({ sender: currentSender, text: currentText });
      }
      currentSender = 'Owner';
      currentText = trimmed.substring(6).trim();
    } else {
      if (currentSender) {
        currentText += '\n' + trimmed;
      } else {
        messages.push({ sender: 'System', text: trimmed });
      }
    }
  }
  
  if (currentSender && currentText) {
    messages.push({ sender: currentSender, text: currentText });
  }
  
  return messages;
}

export function TranscriptView({ transcript }) {
  const messages = parseTranscript(transcript);

  if (messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 bg-[#0B0F19] rounded-xl border border-[#243048] text-gray-500 text-xs">
        <p>No conversation transcript available.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col space-y-4 max-h-[320px] overflow-y-auto p-4 bg-[#0B0F19] rounded-xl border border-[#243048] scrollbar-thin">
      {messages.map((msg, index) => {
        const isAgent = msg.sender === 'Agent';
        
        return (
          <div
            key={index}
            className={`flex flex-col max-w-[80%] ${
              isAgent ? 'self-start items-start' : 'self-end items-end'
            }`}
          >
            {/* Sender Label */}
            <span className="text-[10px] text-gray-500 font-semibold mb-1 uppercase tracking-wider px-1">
              {isAgent ? 'Mia (Agent)' : 'Business Owner'}
            </span>
            
            {/* Bubble */}
            <div
              className={`px-3.5 py-2.5 rounded-2xl text-xs leading-relaxed whitespace-pre-wrap ${
                isAgent
                  ? 'bg-gray-800 text-gray-100 rounded-tl-none'
                  : 'bg-white text-gray-900 border border-gray-200 rounded-tr-none shadow-sm'
              }`}
            >
              {msg.text}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default TranscriptView;
