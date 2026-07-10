import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Send, FileText, Loader2, User, Bot, UploadCloud, Database, Paperclip, Download } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

interface Message {
  role: 'user' | 'ai';
  content: string;
}

interface ChatResponse {
  answer: string;
}

const App: React.FC = () => {
  const [question, setQuestion] = useState<string>('');
  const [chatHistory, setChatHistory] = useState<Message[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const [modelProvider, setModelProvider] = useState<string>("openai");
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);

  const [accessCode, setAccessCode] = useState<string>(() => localStorage.getItem('documind_access_code') || '');
  const [showAccessModal, setShowAccessModal] = useState<boolean>(!localStorage.getItem('documind_access_code'));
  const [codeInput, setCodeInput] = useState<string>('');

  const handleUnauthorized = () => {
    localStorage.removeItem('documind_access_code');
    setAccessCode('');
    setCodeInput('');
    setShowAccessModal(true);
  };

  const handleAccessCodeSubmit = () => {
    if (!codeInput.trim()) return;
    localStorage.setItem('documind_access_code', codeInput);
    setAccessCode(codeInput);
    setShowAccessModal(false);
  };

  useEffect(() => {
    if (!accessCode) return;
    axios.get(`${API_BASE_URL}/api/document/list`, {
      headers: { 'X-Access-Code': accessCode }
    }).then((res) => {
      setUploadedFiles(res.data.filenames);
    }).catch((err: any) => {
      if (err.response?.status === 401) handleUnauthorized();
    });
  }, [accessCode]);

  const handleSend = async (): Promise<void> => {
    if (!question.trim()) return;
    const userMsg: Message = { role: 'user', content: question };
    setChatHistory((prev) => [...prev, userMsg]);
    setQuestion('');
    setLoading(true);

    try {
      const res = await axios.post<ChatResponse>(`${API_BASE_URL}/api/chat/ask`, {
        question: question,
        model_provider: modelProvider
      }, {
        headers: { 'X-Access-Code': accessCode }
      });
      const aiMsg: Message = { role: 'ai', content: res.data.answer };
      setChatHistory((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      if (err.response?.status === 401) {
        handleUnauthorized();
      } else {
        console.error("API Error:", err);
        const errMsg: Message = { role: 'ai', content: "系統連線失敗，請檢查後端是否開啟。" };
        setChatHistory((prev) => [...prev, errMsg]);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async (filename: string) => {
    try {
      const res = await axios.get(`${API_BASE_URL}/api/document/download/${encodeURIComponent(filename)}`, {
        headers: { 'X-Access-Code': accessCode },
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      if (err.response?.status === 401) {
        handleUnauthorized();
      } else {
        console.error("Download Error:", err);
        alert("❌ 下載失敗，請檢查控制台錯誤訊息。");
      }
    }
  };

  const handleFileUpload = async () => {
    if (!selectedFiles || selectedFiles.length === 0) return;
    setIsUploading(true);
    const formData = new FormData();
    Array.from(selectedFiles).forEach((file) => {
      formData.append('files', file);
    });

    try {
      const res = await axios.post(`${API_BASE_URL}/api/document/upload/bulk`, formData, {
        headers: { 'Content-Type': 'multipart/form-data', 'X-Access-Code': accessCode }
      });
      alert(`✅ 上傳成功！共切出 ${res.data.total_chunks} 個知識區塊並存入資料庫。`);
      setSelectedFiles(null);
      axios.get(`${API_BASE_URL}/api/document/list`, {
        headers: { 'X-Access-Code': accessCode }
      }).then((res) => {
        setUploadedFiles(res.data.filenames);
      });
    } catch (err: any) {
      if (err.response?.status === 401) {
        handleUnauthorized();
      } else {
        console.error("Upload Error:", err);
        alert("❌ 上傳失敗，請檢查控制台錯誤訊息。");
      }
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="flex h-screen bg-slate-50 font-sans text-slate-900 overflow-hidden">

      {/* 🔒 Access Code Modal */}
      {showAccessModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-8 shadow-2xl w-full max-w-sm mx-4">
            <div className="bg-blue-600 w-12 h-12 rounded-xl flex items-center justify-center mb-4">
              <Database size={24} className="text-white" />
            </div>
            <h2 className="text-xl font-bold text-slate-800 mb-1">DocuMind</h2>
            <p className="text-sm text-slate-500 mb-6">請輸入存取密碼以繼續</p>
            <input
              type="password"
              className="w-full border border-slate-300 rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent mb-4"
              placeholder="輸入存取密碼..."
              value={codeInput}
              onChange={(e) => setCodeInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAccessCodeSubmit()}
              autoFocus
            />
            <button
              onClick={handleAccessCodeSubmit}
              disabled={!codeInput.trim()}
              className="w-full bg-blue-600 text-white py-3 rounded-xl font-medium hover:bg-blue-700 disabled:bg-slate-200 disabled:text-slate-400 transition-colors"
            >
              進入
            </button>
          </div>
        </div>
      )}

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

          <select
            value={modelProvider}
            onChange={(e) => setModelProvider(e.target.value)}
            className="w-full border border-slate-300 rounded-xl px-4 py-2 text-sm text-slate-700 bg-white"
          >
            <option value="openai">OpenAI GPT-4o</option>
            <option value="ollama">Ollama（本地）</option>
          </select>

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

          <button
            onClick={handleFileUpload}
            disabled={!selectedFiles || isUploading}
            className="w-full bg-slate-800 text-white py-3 rounded-xl font-medium hover:bg-slate-900 disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors flex justify-center items-center gap-2"
          >
            {isUploading ? <Loader2 className="animate-spin" size={18} /> : <Database size={18} />}
            {isUploading ? '正在分析並寫入大腦...' : '向量化並寫入知識庫'}
          </button>

          {uploadedFiles.length > 0 && (
            <div className="border-t border-slate-100 pt-4 overflow-y-auto">
              <p className="text-xs font-semibold text-slate-500 mb-2">知識庫已收錄</p>
              <ul className="space-y-1">
                {uploadedFiles.map((name, i) => (
                  <li key={i} className="flex items-center gap-2 text-xs text-slate-600 group">
                    <FileText size={12} className="shrink-0 text-blue-500" />
                    <span className="truncate flex-1">{name}</span>
                    <button
                      onClick={() => handleDownload(name)}
                      className="shrink-0 text-slate-400 hover:text-blue-600 opacity-0 group-hover:opacity-100 transition-opacity"
                      title="下載檔案"
                    >
                      <Download size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </aside>

      {/* 🔵 右側：主要對話區塊 */}
      <main className="flex-1 flex flex-col h-full bg-slate-50 relative">
        <header className="md:hidden bg-white border-b p-4 flex items-center gap-2 shadow-sm z-10">
          <FileText className="text-blue-600" />
          <h1 className="font-bold">DocuMind AI</h1>
        </header>

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
