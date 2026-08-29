import React from 'react';
import { marked } from 'marked';
import { Copy, Download, ThumbsUp, ThumbsDown, CheckCircle2, TrendingUp, Cpu, Database, Calculator, FileSpreadsheet, ShieldCheck } from 'lucide-react';
import logoImg from '../assets/logo.png';

export default function ChatStream({ messages, isProcessing, activeAgentStep, streamingText, onStarterClick }) {
  const copyText = (text) => {
    navigator.clipboard.writeText(text);
    alert('Đã sao chép nội dung báo cáo!');
  };

  const downloadFile = (filename, content) => {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getAgentIcon = (step) => {
    switch (step) {
      case 'router': return <Cpu size={14} className="text-cyan-400" />;
      case 'retriever': return <Database size={14} className="text-emerald-400" />;
      case 'calculator': return <Calculator size={14} className="text-amber-400" />;
      case 'analysis': return <TrendingUp size={14} className="text-purple-400" />;
      case 'report': return <FileSpreadsheet size={14} className="text-rose-400" />;
      case 'evaluator': return <ShieldCheck size={14} className="text-emerald-400" />;
      default: return <Cpu size={14} className="text-indigo-400" />;
    }
  };

  const safeRenderMarkdown = (content) => {
    try {
      if (!content || typeof content !== 'string') return '';
      return marked.parse(content);
    } catch (err) {
      console.error('Markdown parse error:', err);
      return `<pre class="whitespace-pre-wrap">${content}</pre>`;
    }
  };

  // If no messages and not processing, render Gemini "Where should we start?" empty state
  if (!messages.length && !isProcessing) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center max-w-[800px] mx-auto z-10 select-none">
        <div className="flex flex-col items-center gap-3 mb-8">
          <img
            src={logoImg}
            alt="FinAgent AI"
            className="w-16 h-16 rounded-full object-cover shadow-[0_0_25px_rgba(59,130,246,0.6)] mb-2 border border-white/20"
          />
          <div className="text-4xl sm:text-5xl font-display font-medium text-slate-100 tracking-tight">
            Where should we start?
          </div>
          <div className="text-slate-400 text-sm max-w-md">
            Hệ thống Multi-Agent AI sẵn sàng bóc tách BCTC, mô hình DuPont và định giá thị trường.
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-[680px]">
          <button
            onClick={() => onStarterClick('Phân tích toàn diện tình hình tài chính và bóc tách DuPont 3 bước FPT 2023')}
            className="p-4 rounded-2xl bg-[#1E1F24]/70 hover:bg-[#23242A] border border-white/[0.05] hover:border-white/[0.12] text-left transition-all group flex flex-col gap-1 cursor-pointer"
          >
            <div className="text-[13.5px] font-medium text-slate-200 group-hover:text-white flex items-center gap-2">
              <TrendingUp size={14} className="text-indigo-400" />
              <span>Phân tích DuPont FPT 2023</span>
            </div>
            <div className="text-[12px] text-slate-400">Bóc tách ROE theo Biên LN, Vòng quay tài sản và Đòn bẩy.</div>
          </button>

          <button
            onClick={() => onStarterClick('Tiến độ dự án Dung Quất 2 và triển vọng ngành thép của Hòa Phát HPG')}
            className="p-4 rounded-2xl bg-[#1E1F24]/70 hover:bg-[#23242A] border border-white/[0.05] hover:border-white/[0.12] text-left transition-all group flex flex-col gap-1 cursor-pointer"
          >
            <div className="text-[13.5px] font-medium text-slate-200 group-hover:text-white flex items-center gap-2">
              <TrendingUp size={14} className="text-cyan-400" />
              <span>Tiến độ Dung Quất 2 — HPG</span>
            </div>
            <div className="text-[12px] text-slate-400">Truy xuất Báo cáo thường niên về tiến độ lò cao & công suất.</div>
          </button>

          <button
            onClick={() => onStarterClick('Đánh giá chất lượng tài sản và tăng trưởng tín dụng VietinBank CTG')}
            className="p-4 rounded-2xl bg-[#1E1F24]/70 hover:bg-[#23242A] border border-white/[0.05] hover:border-white/[0.12] text-left transition-all group flex flex-col gap-1 cursor-pointer"
          >
            <div className="text-[13.5px] font-medium text-slate-200 group-hover:text-white flex items-center gap-2">
              <CheckCircle2 size={14} className="text-emerald-400" />
              <span>Chất lượng tài sản VietinBank (CTG)</span>
            </div>
            <div className="text-[12px] text-slate-400">Đánh giá CASA, trích lập dự phòng và tỷ lệ an toàn vốn.</div>
          </button>

          <button
            onClick={() => onStarterClick('Phân tích cấu trúc nợ và tài sản Vingroup VIC')}
            className="p-4 rounded-2xl bg-[#1E1F24]/70 hover:bg-[#23242A] border border-white/[0.05] hover:border-white/[0.12] text-left transition-all group flex flex-col gap-1 cursor-pointer"
          >
            <div className="text-[13.5px] font-medium text-slate-200 group-hover:text-white flex items-center gap-2">
              <TrendingUp size={14} className="text-purple-400" />
              <span>Cấu trúc nợ Vingroup (VIC)</span>
            </div>
            <div className="text-[12px] text-slate-400">Phân tích hệ số đòn bẩy D/E và chi phí lãi vay BCTC 2023.</div>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 flex flex-col gap-6 max-w-[860px] w-full mx-auto relative z-10">
      {messages.map((msg, index) => {
        if (msg.role === 'user') {
          return (
            <div key={index} className="flex justify-end gap-3 self-end max-w-[85%]">
              <div className="bg-[#2A2B32] text-slate-100 px-4 py-3 rounded-2xl text-[14.5px] leading-relaxed">
                {msg.content}
              </div>
            </div>
          );
        }

        // Assistant Message
        const data = msg.data || {};
        const ticker = data.ticker || 'N/A';
        const priceStr = data.price ? `${data.price.toLocaleString()} VND` : null;
        const roeStr = data.roe !== null && data.roe !== undefined ? `${(data.roe * 100).toFixed(2)}%` : null;
        const netMarginStr = data.net_margin !== null && data.net_margin !== undefined ? `${(data.net_margin * 100).toFixed(2)}%` : null;
        const confidence = (data.confidence || 0.95).toFixed(2);
        const reportMd = data.final_report || data.executive_summary || msg.content || '';
        const renderedHtml = safeRenderMarkdown(reportMd);

        return (
          <div key={index} className="flex gap-4 items-start w-full py-2">
            {/* Custom Circular AI Logo Avatar */}
            <img
              src={logoImg}
              alt="FinAgent"
              className="w-8 h-8 rounded-full object-cover shadow-[0_0_10px_rgba(59,130,246,0.5)] border border-white/20 flex-shrink-0 mt-0.5"
            />

            {/* Seamless Body */}
            <div className="flex-1 flex flex-col gap-3 text-[14.5px] text-slate-200 leading-relaxed">
              {/* Stepper Tags */}
              <div className="flex items-center gap-2 flex-wrap text-[12px] text-slate-400">
                <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 font-medium border border-emerald-500/30">
                  🧭 Router: analysis
                </span>
                {priceStr && (
                  <span className="px-2.5 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300 font-medium border border-cyan-500/30">
                    📈 {ticker}: {priceStr}
                  </span>
                )}
                {roeStr && (
                  <span className="px-2.5 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 font-medium border border-indigo-500/30">
                    ROE: {roeStr}
                  </span>
                )}
                {netMarginStr && (
                  <span className="px-2.5 py-0.5 rounded-full bg-purple-500/15 text-purple-300 font-medium border border-purple-500/30">
                    Biên LN: {netMarginStr}
                  </span>
                )}
                <span className="text-[11px] text-slate-500">
                  Confidence: {confidence}/1.00
                </span>
              </div>

              {/* Rendered Markdown */}
              <div
                className="markdown-body leading-relaxed text-slate-200 font-normal"
                dangerouslySetInnerHTML={{ __html: renderedHtml }}
              />

              {/* Action Toolbar */}
              <div className="flex items-center gap-3 pt-2 text-slate-400 text-xs">
                <button
                  onClick={() => copyText(reportMd)}
                  className="hover:text-white transition-colors flex items-center gap-1.5 p-1 rounded cursor-pointer"
                  title="Sao chép"
                >
                  <Copy size={14} />
                </button>
                <button
                  onClick={() => downloadFile(`Bao_Cao_${ticker}_2023.md`, reportMd)}
                  className="hover:text-white transition-colors flex items-center gap-1.5 p-1 rounded cursor-pointer"
                  title="Tải về Markdown"
                >
                  <Download size={14} />
                </button>
                <button className="hover:text-white transition-colors p-1 cursor-pointer" title="Hữu ích">
                  <ThumbsUp size={14} />
                </button>
                <button className="hover:text-white transition-colors p-1 cursor-pointer" title="Chưa hữu ích">
                  <ThumbsDown size={14} />
                </button>
              </div>
            </div>
          </div>
        );
      })}

      {/* Real-time Agent Thinking & Streaming State */}
      {isProcessing && (
        <div className="flex gap-4 items-start w-full py-2 animate-fadeIn">
          <img
            src={logoImg}
            alt="FinAgent Thinking"
            className="w-8 h-8 rounded-full object-cover shadow-[0_0_12px_rgba(59,130,246,0.6)] border border-white/20 flex-shrink-0 mt-0.5 animate-pulse"
          />

          <div className="flex-1 flex flex-col gap-3">
            {/* Live Agent Thinking Badge */}
            {activeAgentStep && (
              <div className="inline-flex items-center gap-2.5 px-3.5 py-1.5 rounded-full bg-[#1E1F24] border border-indigo-500/30 text-xs text-slate-200 shadow-md animate-pulse max-w-fit">
                {getAgentIcon(activeAgentStep.step)}
                <span className="font-semibold text-indigo-300">
                  {activeAgentStep.name}:
                </span>
                <span className="text-slate-300">{activeAgentStep.message}</span>
              </div>
            )}

            {/* Live Streaming Markdown Output */}
            {streamingText ? (
              <div
                className="markdown-body leading-relaxed text-slate-200 font-normal"
                dangerouslySetInnerHTML={{ __html: safeRenderMarkdown(streamingText + ' ▍') }}
              />
            ) : (
              <div className="text-slate-400 text-sm flex items-center gap-2 py-1">
                <span className="inline-block w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                <span>Đang điều phối đồ thị LangGraph & truy xuất Vector Store...</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
