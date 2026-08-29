import React, { useState, useRef } from 'react';
import { Plus, ArrowUp, FileText, X } from 'lucide-react';

export default function FloatingComposer({ onSend, isProcessing }) {
  const [input, setInput] = useState('');
  const [attachedFile, setAttachedFile] = useState(null);
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setAttachedFile({
        name: file.name,
        size: Math.round(file.size / 1024),
      });
    }
  };

  const handleRemoveFile = (e) => {
    e.stopPropagation();
    setAttachedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleSend = () => {
    if ((!input.trim() && !attachedFile) || isProcessing) return;
    let queryToSend = input.trim();
    if (attachedFile) {
      queryToSend = queryToSend
        ? `${queryToSend} (Kèm tài liệu tải lên: ${attachedFile.name})`
        : `Phân tích dữ liệu từ tài liệu tải lên: ${attachedFile.name}`;
    }
    onSend(queryToSend);
    setInput('');
    setAttachedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="w-full max-w-[820px] mx-auto px-4 pb-6 pt-2 z-30">
      {/* Hidden File Picker */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept=".pdf,.csv,.docx,.xlsx,.txt"
        className="hidden"
      />

      {/* Selected File Badge */}
      {attachedFile && (
        <div className="mb-2 inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#2A2B32] border border-white/10 text-xs text-slate-200 shadow-sm animate-fadeIn">
          <FileText size={14} className="text-cyan-400" />
          <span className="font-medium truncate max-w-[200px]">{attachedFile.name}</span>
          <span className="text-slate-400 text-[10px]">({attachedFile.size} KB)</span>
          <button
            onClick={handleRemoveFile}
            className="hover:text-rose-400 p-0.5 rounded-full transition-colors cursor-pointer"
            title="Gỡ file"
          >
            <X size={13} />
          </button>
        </div>
      )}

      {/* Floating Input Pill Bar */}
      <div className="bg-[#1E1F24] hover:bg-[#23242A] focus-within:bg-[#23242A] border border-white/[0.08] focus-within:border-white/[0.2] rounded-full py-2.5 px-4 flex items-center gap-3 shadow-[0_10px_35px_rgba(0,0,0,0.6)] transition-all">
        {/* Plus / Upload Button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="w-8 h-8 rounded-full hover:bg-white/[0.08] text-slate-400 hover:text-slate-200 flex items-center justify-center transition-colors flex-shrink-0 cursor-pointer"
          title="Chọn file PDF / CSV tải lên"
        >
          <Plus size={18} />
        </button>

        {/* Text Input */}
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask FinAgent..."
          className="flex-1 bg-transparent border-none outline-none text-[15px] text-slate-100 placeholder:text-slate-400 font-body"
        />

        {/* Send Button */}
        <button
          type="button"
          onClick={handleSend}
          disabled={isProcessing || (!input.trim() && !attachedFile)}
          className={`w-8 h-8 rounded-full flex items-center justify-center transition-all flex-shrink-0 ${
            input.trim() || attachedFile
              ? 'bg-white text-slate-900 hover:bg-slate-200 shadow-md cursor-pointer'
              : 'bg-white/[0.06] text-slate-500 cursor-not-allowed'
          }`}
          title="Gửi câu hỏi"
        >
          <ArrowUp size={16} strokeWidth={2.5} />
        </button>
      </div>

      <div className="text-center text-[11px] text-slate-500 mt-2 font-normal">
        FinAgent can make mistakes. Check important financial info.
      </div>
    </div>
  );
}
