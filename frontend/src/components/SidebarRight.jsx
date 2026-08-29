import React from 'react';
import { MoreHorizontal } from 'lucide-react';

export default function SidebarRight({ onSelectDoc }) {
  const documents = [
    {
      id: 'fpt',
      filename: 'FPT_BCTN_2023.pdf',
      type: 'PDF',
      typeClass: 'bg-rose-500',
      confidence: '95%',
      snippet: 'Báo cáo thường niên FPT 2023: Doanh thu 146.904 tỷ VND, lợi nhuận sau thuế 1.728 tỷ VND, định hướng AI Cloud.',
      ticker: 'FPT',
    },
    {
      id: 'hpg',
      filename: 'HPG_DungQuat2_BCTN.pdf',
      type: 'PDF',
      typeClass: 'bg-rose-500',
      confidence: '95%',
      snippet: 'Tập đoàn Hòa Phát: Tiến độ phân kỳ dự án Khu liên hợp sản xuất Gang thép Dung Quất 2 và công suất HRC.',
      ticker: 'HPG',
    },
    {
      id: 'ctg',
      filename: 'VietinBank_CTG_2023.csv',
      type: 'CSV',
      typeClass: 'bg-emerald-500',
      confidence: '90%',
      snippet: 'Bảng cân đối kế toán & Báo cáo kết quả kinh doanh Ngân hàng TMCP Công Thương Việt Nam năm 2023.',
      ticker: 'CTG',
    },
    {
      id: 'vic',
      filename: 'VIC_Vingroup_Overview.docx',
      type: 'DOCX',
      typeClass: 'bg-blue-500',
      confidence: '88%',
      snippet: 'Báo cáo phân tích cấu trúc tài chính, cơ cấu vốn và quản trị rủi ro nợ vay Tập đoàn Vingroup năm 2023.',
      ticker: 'VIC',
    },
  ];

  return (
    <aside className="bg-panel backdrop-blur-xl border border-white/10 rounded-2xl flex flex-col p-5 shadow-ambient h-full overflow-hidden select-none">
      {/* Header */}
      <div className="flex items-center justify-between mb-3.5">
        <span className="font-display text-[16px] font-bold text-slate-100">Advanced RAG Sources</span>
        <button className="text-slate-400 hover:text-white p-1 rounded transition-colors">
          <MoreHorizontal size={18} />
        </button>
      </div>

      {/* 3D Isometric Widgets */}
      <div className="flex items-center justify-around p-3 bg-black/30 rounded-xl border border-white/10 mb-4 shadow-inner">
        <div
          onClick={() => onSelectDoc('FPT BCTN')}
          className="flex flex-col items-center gap-1 cursor-pointer transition-transform hover:-translate-y-0.5"
        >
          <span className="text-2xl drop-shadow-[0_4px_8px_rgba(0,0,0,0.5)]">📚</span>
          <span className="text-[11px] font-semibold text-slate-300">PDF BCTN</span>
        </div>
        <div
          onClick={() => onSelectDoc('BCTC CSV')}
          className="flex flex-col items-center gap-1 cursor-pointer transition-transform hover:-translate-y-0.5"
        >
          <span className="text-2xl drop-shadow-[0_4px_8px_rgba(0,0,0,0.5)]">📦</span>
          <span className="text-[11px] font-semibold text-slate-300">CSDL BCTC</span>
        </div>
        <div
          onClick={() => onSelectDoc('VNStock')}
          className="flex flex-col items-center gap-1 cursor-pointer transition-transform hover:-translate-y-0.5"
        >
          <span className="text-2xl drop-shadow-[0_4px_8px_rgba(0,0,0,0.5)]">⚡</span>
          <span className="text-[11px] font-semibold text-slate-300">VNStock</span>
        </div>
      </div>

      <div className="font-display text-[13.5px] font-bold text-white mb-2.5">
        Retrieved Documents
      </div>

      {/* Documents List */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-2.5 pr-1">
        {documents.map((doc, idx) => (
          <div
            key={doc.id}
            id={`ragDocCard-${idx}`}
            onClick={() => onSelectDoc(doc.ticker)}
            className="bg-card hover:bg-cardHover border border-white/10 hover:border-indigo-500/40 rounded-xl p-3.5 flex flex-col gap-1.5 cursor-pointer transition-all duration-200 hover:-translate-x-0.5 shadow-md group"
          >
            <div className="flex items-center gap-2">
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded text-white ${doc.typeClass}`}>
                {doc.type}
              </span>
              <span className="text-[13px] font-semibold text-slate-100 truncate group-hover:text-cyan-300 transition-colors">
                {doc.filename}
              </span>
            </div>

            <div className="text-[11px] font-semibold text-emerald-400 flex items-center gap-1.5">
              <span>● Source Confidence: {doc.confidence}</span>
            </div>

            <div className="text-[11.5px] text-slate-400 leading-relaxed line-clamp-2">
              {doc.snippet}
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
