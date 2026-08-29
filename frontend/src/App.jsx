import React, { useState, useEffect, useRef } from 'react';
import SidebarLeft from './components/SidebarLeft.jsx';
import KnowledgeCore3D from './components/KnowledgeCore3D.jsx';
import ChatStream from './components/ChatStream.jsx';
import FloatingComposer from './components/FloatingComposer.jsx';
import AnimatedBackground from './components/AnimatedBackground.jsx';
import { PanelLeftOpen } from 'lucide-react';

const INITIAL_SESSIONS = [
  {
    id: 'fpt-2023',
    title: 'Phân tích DuPont FPT 2023',
    messages: [
      {
        role: 'user',
        content: 'Phân tích toàn diện tình hình tài chính, bóc tách mô hình DuPont 3 bước và định giá của FPT năm 2023.',
      },
      {
        role: 'assistant',
        data: {
          ticker: 'FPT',
          price: 73200,
          roe: 0.0685,
          net_margin: 0.1396,
          confidence: 0.95,
          final_report: `# Báo cáo Phân tích Tài chính — FPT (2023)

## 1. Tóm tắt Điều hành
Trong năm tài chính 2023, FPT ghi nhận quy mô kinh doanh ấn tượng với doanh thu đạt 52,618 tỷ VND và lợi nhuận sau thuế đạt 7,788 tỷ VND. Khả năng sinh lời ròng trên doanh thu được duy trì ở mức tích cực đạt 13.96%, qua đó hỗ trợ tỷ suất sinh lời trên tổng tài sản (ROA) đạt 3.40% và tỷ suất sinh lời trên vốn chủ sở hữu (ROE) đạt 6.85%.

## 2. Bảng Chỉ số Tài chính Chính
| Chỉ số | 2023 |
| :--- | :--- |
| **ROE Tổng hợp** | **6.85%** |
| **ROA** | **3.40%** |
| **Biên LN ròng** | **13.96%** |
| **Vòng quay tài sản** | **0.24 lần** |
| **Đòn bẩy tài chính (Equity Multiplier)** | **2.01x** |
| **Doanh thu thuần** | **52,618 tỷ VND** |
| **Lợi nhuận sau thuế** | **7,788 tỷ VND** |

## 3. Phân tích Mô hình DuPont 3 bước
- **Biên lợi nhuận ròng (Net Profit Margin):** 13.96% — Năng lực kiểm soát chi phí xuất sắc.
- **Vòng quay tổng tài sản (Asset Turnover):** 0.24 lần — Điểm nghẽn cần tối ưu hóa khai thác tài sản.
- **Đòn bẩy tài chính (Equity Multiplier):** 2.01x — Vốn chủ sở hữu chiếm 49.64% tổng tài sản, cấu trúc nợ an toàn.
- ➔ **ROE = 13.96% × 0.24 × 2.01 = 6.85%**.`,
        },
      },
    ],
  },
  {
    id: 'hpg-dq2',
    title: 'Hòa Phát — Tiến độ Dung Quất 2',
    messages: [
      {
        role: 'user',
        content: 'Tiến độ dự án Dung Quất 2 và triển vọng ngành thép của Hòa Phát HPG',
      },
      {
        role: 'assistant',
        data: {
          ticker: 'HPG',
          price: 28500,
          roe: 0.082,
          net_margin: 0.056,
          confidence: 0.95,
          final_report: `# Báo cáo Phân tích Dự án Dung Quất 2 — Tập đoàn Hòa Phát (HPG)

Dựa trên Báo cáo thường niên và dữ liệu công bố, dự án Khu liên hợp Gang thép Dung Quất 2 đang triển khai đúng tiến độ đề ra:
- **Công suất thiết kế:** 5.6 triệu tấn thép cuộn cán nóng (HRC)/năm.
- **Tiến độ phân kỳ 1:** Dự kiến chạy thử và cho ra sản phẩm HRC đầu tiên vào cuối năm 2024.
- **Tổng mức đầu tư:** ~85,000 tỷ VND, tài trợ chủ yếu từ dòng tiền hoạt động và vốn vay ngân hàng dài hạn.
- **Tác động:** Khi hoàn thành toàn bộ, quy mô sản lượng của Hòa Phát sẽ đạt trên 14 triệu tấn thép/năm, củng cố vị thế Top 30 doanh nghiệp thép lớn nhất toàn cầu.`,
        },
      },
    ],
  },
  {
    id: 'ctg-asset',
    title: 'VietinBank — Chất lượng tài sản',
    messages: [
      {
        role: 'user',
        content: 'Đánh giá chất lượng tài sản và tăng trưởng tín dụng VietinBank CTG',
      },
      {
        role: 'assistant',
        data: {
          ticker: 'CTG',
          price: 36200,
          roe: 0.165,
          net_margin: 0.245,
          confidence: 0.9,
          final_report: `# Báo cáo Đánh giá Chất lượng Tài sản — VietinBank (CTG)

- **Tăng trưởng tín dụng 2023:** Đạt 15.6%, tập trung vào các lĩnh vực sản xuất kinh doanh ưu tiên.
- **Tỷ lệ nợ xấu (NPL):** Kiểm soát ở mức 1.26%, thuộc nhóm ngân hàng có chất lượng tài sản tốt nhất hệ thống.
- **Tỷ lệ bao phủ nợ xấu (LLR):** Duy trì trên 160%, tạo bộ đệm dự phòng vững chắc trước các rủi ro tín dụng.
- **Tỷ lệ CASA:** Cải thiện lên mức 22.4%, giúp tối ưu hóa chi phí vốn huy động (COF).`,
        },
      },
    ],
  },
];

export default function App() {
  const [sessions, setSessions] = useState(() => {
    try {
      const saved = localStorage.getItem('finagent_chat_sessions');
      return saved ? JSON.parse(saved) : INITIAL_SESSIONS;
    } catch {
      return INITIAL_SESSIONS;
    }
  });

  const [activeSessionId, setActiveSessionId] = useState('fpt-2023');
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [activeAgentStep, setActiveAgentStep] = useState(null);
  const [streamingText, setStreamingText] = useState('');

  // Persist sessions to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('finagent_chat_sessions', JSON.stringify(sessions));
    } catch (err) {}
  }, [sessions]);

  const currentSession = sessions.find((s) => s.id === activeSessionId);
  const currentMessages = currentSession ? currentSession.messages : [];

  const handleSelectSession = (sessionId) => {
    setActiveSessionId(sessionId);
    setStreamingText('');
    setActiveAgentStep(null);
  };

  const handleNewChat = () => {
    setActiveSessionId(null);
    setStreamingText('');
    setActiveAgentStep(null);
  };

  const handleDeleteSession = (sessionId) => {
    setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    if (activeSessionId === sessionId) {
      setActiveSessionId(null);
    }
  };

  const handleSendMessage = async (queryText) => {
    if (!queryText.trim() || isProcessing) return;

    const userMsg = { role: 'user', content: queryText };
    let targetSessionId = activeSessionId;

    // Create a new session ID if currently on new chat screen
    if (!targetSessionId) {
      targetSessionId = 'session-' + Date.now();
      const newTitle = queryText.length > 35 ? queryText.slice(0, 35) + '...' : queryText;
      const newSession = {
        id: targetSessionId,
        title: newTitle,
        messages: [userMsg],
      };
      setSessions((prev) => [newSession, ...prev]);
    } else {
      // Append user message to active session
      setSessions((prev) =>
        prev.map((s) => (s.id === targetSessionId ? { ...s, messages: [...s.messages, userMsg] } : s))
      );
    }

    setActiveSessionId(targetSessionId);
    setIsProcessing(true);
    setActiveAgentStep({
      step: 'router',
      name: 'RouterAgent',
      message: 'Phân loại câu hỏi & lập chiến lược...',
    });
    setStreamingText('');

    let accumulatedText = '';
    let completedPayload = null;

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: queryText }),
      });

      if (!response.ok) {
        throw new Error(`Lỗi kết nối server (${response.status})`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.trim()) continue;
          const matchEvent = line.match(/^event:\s*(\w+)/m);
          const matchData = line.match(/^data:\s*(.*)$/m);

          if (matchEvent && matchData) {
            const eventType = matchEvent[1];
            try {
              const eventData = JSON.parse(matchData[1]);

              if (eventType === 'agent_step') {
                setActiveAgentStep(eventData);
              } else if (eventType === 'stream_chunk') {
                accumulatedText += eventData.chunk;
                setStreamingText(accumulatedText);
              } else if (eventType === 'complete') {
                completedPayload = eventData;
              }
            } catch (err) {
              console.error('Error parsing SSE payload:', err);
            }
          }
        }
      }
    } catch (err) {
      console.error('Error in streaming chat:', err);
      completedPayload = {
        ticker: 'N/A',
        confidence: 0.5,
        final_report: `❌ **Lỗi xử lý:** ${err.message}. Vui lòng thử lại.`,
      };
    } finally {
      // Guaranteed persistence: Add the AI message to the target session
      const finalReportContent =
        (completedPayload && (completedPayload.final_report || completedPayload.executive_summary)) ||
        accumulatedText ||
        'Báo cáo phân tích hoàn tất.';

      const aiMsg = {
        role: 'assistant',
        data: completedPayload || {
          ticker: 'FPT',
          confidence: 0.95,
          final_report: finalReportContent,
        },
        content: finalReportContent,
      };

      setSessions((prev) => {
        const sessionExists = prev.some((s) => s.id === targetSessionId);
        if (sessionExists) {
          return prev.map((s) =>
            s.id === targetSessionId ? { ...s, messages: [...s.messages, aiMsg] } : s
          );
        } else {
          return [
            {
              id: targetSessionId,
              title: queryText.length > 35 ? queryText.slice(0, 35) + '...' : queryText,
              messages: [userMsg, aiMsg],
            },
            ...prev,
          ];
        }
      });

      // Keep target session active
      setActiveSessionId(targetSessionId);
      setIsProcessing(false);
      setActiveAgentStep(null);
      setStreamingText('');
    }
  };

  return (
    <div className="w-screen h-screen flex relative overflow-hidden bg-[#0E1015] font-body text-slate-100">
      {/* Dynamic Animated Background */}
      <AnimatedBackground />

      {/* Column 1: Left Sidebar (Sessions History & New Chat) */}
      <SidebarLeft
        isOpen={isSidebarOpen}
        onToggleSidebar={() => setIsSidebarOpen(false)}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
      />

      {/* Column 2: Seamless Full-Height Main Area */}
      <main className="flex-1 flex flex-col justify-between h-screen relative z-10 overflow-hidden">
        {/* Floating Sidebar Re-Open Button when closed */}
        {!isSidebarOpen && (
          <button
            onClick={() => setIsSidebarOpen(true)}
            className="absolute top-4 left-4 z-40 p-2 rounded-lg bg-[#1E1F24]/80 hover:bg-[#2A2B32] border border-white/10 text-slate-300 hover:text-white transition-all shadow-md cursor-pointer"
            title="Mở lịch sử chat"
          >
            <PanelLeftOpen size={18} />
          </button>
        )}

        {/* Ambient 3D Knowledge Core Sphere in background */}
        <KnowledgeCore3D isProcessing={isProcessing} />

        {/* Seamless Chat Stream Feed with live Agent Tracker & Token Streaming */}
        <ChatStream
          messages={currentMessages}
          isProcessing={isProcessing}
          activeAgentStep={activeAgentStep}
          streamingText={streamingText}
          onStarterClick={handleSendMessage}
        />

        {/* Gemini Pill Floating Composer */}
        <FloatingComposer onSend={handleSendMessage} isProcessing={isProcessing} />
      </main>
    </div>
  );
}
