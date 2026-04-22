import React, { useState } from 'react';
import axios from 'axios';
import { Send, FileText, Loader2, User, Bot, UploadCloud, Database, Paperclip } from 'lucide-react';

interface Message {
  role: 'user' | 'ai';
  content: string;
}

interface ChatResponse {
  answer: string;
}

const App: React.FC = () => {
  // --- 狀態管理 ---
  const [question, setQuestion] = useState<string>('');
  const [chatHistory, setChatHistory] = useState<Message[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  // 新增：檔案上傳相關狀態
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);

  // --- 1. 處理對話發送 ---
  const handleSend = async (): Promise<void> => {
    if (!question.trim()) return;
    const userMsg: Message = { role: 'user', content: question };
    setChatHistory((prev) => [...prev, userMsg]);
    setQuestion('');
    setLoading(true);

    try {
      const res = await axios.post<ChatResponse>('http://127.0.0.1:8000/api/chat/ask', {
        question: question
      });
      const aiMsg: Message = { role: 'ai', content: res.data.answer };
      setChatHistory((prev) => [...prev, aiMsg]);
    } catch (err) {
      console.error("API Error:", err);
      const errMsg: Message = { role: 'ai', content: "系統連線失敗，請檢查後端是否開啟。" };
      setChatHistory((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  // --- 2. 處理檔案上傳 ---
  const handleFileUpload = async () => {
    if (!selectedFiles || selectedFiles.length === 0) return;

    setIsUploading(true);
    // 使用 FormData 來包裝檔案資料，這對應到後端的 UploadFile
    const formData = new FormData();
    Array.from(selectedFiles).forEach((file) => {
      formData.append('files', file); // 這裡的 'files' 必須跟後端 API 的參數名稱一致
    });

    try {
      const res = await axios.post('http://127.0.0.1:8000/api/document/upload/bulk', formData, {
        headers: { 'Content-Type': 'multipart/form-data' } // 告訴後端這是檔案
      });

      alert(`✅ 上傳成功！共切出 ${res.data.total_chunks} 個知識區塊並存入資料庫。`);
      setSelectedFiles(null); // 清空選擇
    } catch (err) {
      console.error("Upload Error:", err);
      alert("❌ 上傳失敗，請檢查控制台錯誤訊息。");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="flex h-screen bg-slate-50 font-sans text-slate-900 overflow-hidden">

      {/* 🟢 左側：知識庫管理面板 (Sidebar) */}
      <aside className="w-80 bg-white border-r border-slate-200 flex flex-col shadow-sm z-10 hidden md:flex">
        <div className="p-6 border-b border-slate-100 flex items-center gap-3">
          <div className="bg-blue-600 p-2 rounded-lg text-white">
            <Database size={20} />
          </div>
          <h2 className="text-lg font-bold text-slate-800">DocuMind 知識庫</h2>
        </div>

        <div className="p-6 flex-1 flex flex-col gap-4">
          <p className="text-sm text-slate-500 mb-2">上傳企業法規、說明書或 PDF 文件，讓 AI 成為你的專屬顧問。</p>

          {/* 檔案選擇按鈕 */}
          <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-slate-300 border-dashed rounded-xl cursor-pointer bg-slate-50 hover:bg-slate-100 transition-colors">
            <div className="flex flex-col items-center justify-center pt-5 pb-6">
              <UploadCloud className="w-8 h-8 mb-3 text-slate-400" />
              <p className="mb-2 text-sm text-slate-500"><span className="font-semibold">點擊選擇</span> 或拖曳檔案</p>
              <p className="text-xs text-slate-400">支援 PDF 格式</p>
            </div>
            <input
              type="file"
              className="hidden"
              multiple
              accept=".pdf"
              onChange={(e) => setSelectedFiles(e.target.files)}
            />
          </label>

          {/* 顯示已選擇的檔案 */}
          {selectedFiles && selectedFiles.length > 0 && (
            <div className="bg-blue-50 p-3 rounded-lg border border-blue-100">
              <p className="text-xs font-semibold text-blue-800 mb-2 flex items-center gap-1">
                <Paperclip size={14} /> 已選擇 {selectedFiles.length} 個檔案：
              </p>
              <ul className="text-xs text-blue-600 truncate space-y-1 pl-1">
                {Array.from(selectedFiles).map((f, i) => <li key={i}>{f.name}</li>)}
              </ul>
            </div>
          )}

          {/* 上傳執行按鈕 */}
          <button
            onClick={handleFileUpload}
            disabled={!selectedFiles || isUploading}
            className="w-full mt-auto bg-slate-800 text-white py-3 rounded-xl font-medium hover:bg-slate-900 disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors flex justify-center items-center gap-2"
          >
            {isUploading ? <Loader2 className="animate-spin" size={18} /> : <Database size={18} />}
            {isUploading ? '正在分析並寫入大腦...' : '向量化並寫入知識庫'}
          </button>
        </div>
      </aside>

      {/* 🔵 右側：主要對話區塊 */}
      <main className="flex-1 flex flex-col h-full bg-slate-50 relative">
        {/* 手機版標題列 (桌機隱藏) */}
        <header className="md:hidden bg-white border-b p-4 flex items-center gap-2 shadow-sm z-10">
          <FileText className="text-blue-600" />
          <h1 className="font-bold">DocuMind AI</h1>
        </header>

        {/* 對話記錄區 */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8">
          <div className="max-w-3xl mx-auto space-y-6">
            {chatHistory.length === 0 && (
              <div className="text-center py-20 text-slate-400">
                <Bot size={48} className="mx-auto mb-4 text-slate-300" />
                <h2 className="text-2xl font-semibold text-slate-700">準備好回答問題了！</h2>
                <p className="mt-2 text-sm">請先在左側上傳文件，然後在下方發問。</p>
              </div>
            )}

            {chatHistory.map((msg, idx) => (
              <div key={idx} className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 shadow-sm ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 border'}`}>
                  {msg.role === 'user' ? <User size={20} /> : <Bot size={20} />}
                </div>
                <div className={`p-4 rounded-2xl shadow-sm max-w-[85%] leading-relaxed ${msg.role === 'user' ? 'bg-blue-600 text-white rounded-tr-none' : 'bg-white border border-slate-200 text-slate-800 rounded-tl-none'}`}>
                  {msg.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start gap-4">
                <div className="w-10 h-10 rounded-full bg-white border flex items-center justify-center"><Bot size={20} className="text-slate-400" /></div>
                <div className="p-4 rounded-2xl bg-white border rounded-tl-none flex items-center gap-2 text-slate-500">
                  <Loader2 className="animate-spin" size={16} /> 思考中...
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 輸入框 */}
        <footer className="p-4 md:p-6 bg-transparent">
          <div className="max-w-3xl mx-auto relative flex items-center shadow-lg rounded-2xl bg-white border border-slate-200">
            <input
              className="w-full bg-transparent border-none rounded-2xl pl-6 pr-14 py-4 focus:ring-0 outline-none text-slate-800 placeholder:text-slate-400"
              placeholder="詢問已上傳的文件內容..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            />
            <button
              onClick={handleSend}
              disabled={loading || !question.trim()}
              className="absolute right-2 bg-blue-600 text-white p-2.5 rounded-xl hover:bg-blue-700 disabled:bg-slate-200 disabled:text-slate-400 transition-colors"
            >
              <Send size={18} />
            </button>
          </div>
        </footer>
      </main>

    </div>
  );
};

export default App;