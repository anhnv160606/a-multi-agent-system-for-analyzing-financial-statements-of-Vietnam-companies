import React, { useState } from 'react';
import { Plus, Search, Settings, PanelLeftClose, Trash2 } from 'lucide-react';
import logoImg from '../assets/logo.png';

export default function SidebarLeft({
  isOpen,
  onToggleSidebar,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
}) {
  const [search, setSearch] = useState('');

  const filtered = sessions.filter((s) =>
    s.title.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <aside
      className={`h-screen bg-[#13161C] flex flex-col justify-between py-4 px-3 select-none flex-shrink-0 z-30 border-r border-white/[0.04] transition-all duration-300 ease-in-out ${
        isOpen ? 'w-[270px] translate-x-0' : 'w-0 -translate-x-full px-0 border-r-0 overflow-hidden'
      }`}
    >
      {/* Top Section */}
      <div className="flex flex-col gap-3 min-w-[245px]">
        {/* Brand & Sidebar Toggle with New Custom Logo */}
        <div className="flex items-center justify-between px-2 py-1">
          <div className="flex items-center gap-2.5 text-slate-100 font-display font-bold text-[17px]">
            <img
              src={logoImg}
              alt="FinAgent Logo"
              className="w-7 h-7 rounded-full object-cover shadow-[0_0_10px_rgba(59,130,246,0.5)] border border-white/20"
            />
            <span>FinAgent</span>
          </div>
          <button
            onClick={onToggleSidebar}
            className="text-slate-400 hover:text-white p-1 rounded-lg transition-colors cursor-pointer"
            title="Thu gọn sidebar"
          >
            <PanelLeftClose size={18} />
          </button>
        </div>

        {/* New Chat Button */}
        <button
          onClick={onNewChat}
          className="flex items-center gap-3 px-3.5 py-2.5 rounded-full bg-white/[0.06] hover:bg-white/[0.1] text-slate-200 hover:text-white text-[13.5px] font-medium transition-all cursor-pointer"
        >
          <Plus size={16} />
          <span>New chat</span>
        </button>

        {/* Search Chats */}
        <div className="relative px-1">
          <Search size={14} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Search chats"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-transparent border-none py-1.5 pl-8 pr-2 text-[13px] text-slate-300 placeholder:text-slate-500 outline-none"
          />
        </div>

        {/* Recents Section */}
        <div className="mt-2 flex flex-col gap-1 overflow-y-auto max-h-[calc(100vh-280px)] pr-1">
          <div className="text-[11.5px] font-semibold text-slate-500 px-3 py-1">Recents</div>
          {filtered.length === 0 ? (
            <div className="text-[12px] text-slate-500 px-3 py-2">Chưa có đoạn chat nào</div>
          ) : (
            filtered.map((item) => {
              const isActive = activeSessionId === item.id;
              return (
                <div
                  key={item.id}
                  onClick={() => onSelectSession(item.id)}
                  className={`group flex items-center justify-between px-3 py-2 rounded-lg text-[13px] transition-colors cursor-pointer ${
                    isActive
                      ? 'bg-white/[0.08] text-white font-medium'
                      : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-200'
                  }`}
                >
                  <span className="truncate flex-1">{item.title}</span>
                  {onDeleteSession && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteSession(item.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-rose-400 p-0.5 rounded transition-opacity"
                      title="Xóa đoạn chat"
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Bottom Profile & Settings */}
      <div className="pt-3 border-t border-white/[0.06] flex items-center justify-between px-2 min-w-[245px]">
        <div className="flex items-center gap-2.5">
          <img
            src={logoImg}
            alt="User Avatar"
            className="w-7 h-7 rounded-full object-cover border border-white/10 shadow-sm"
          />
          <div className="flex flex-col">
            <span className="text-[12px] font-medium text-slate-200">Financial Analyst</span>
            <span className="text-[10px] text-slate-500">Multi-Agent PRO</span>
          </div>
        </div>
        <button className="text-slate-400 hover:text-white p-1 rounded transition-colors" title="Settings">
          <Settings size={16} />
        </button>
      </div>
    </aside>
  );
}
