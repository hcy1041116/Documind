# DocuMind 技術筆記（第二份）：前端 + Eval Dataset + Phase B

---

## 一、前端 `frontend/src/App.tsx`

### 整體結構

DocuMind 前端是單一 component，分兩個區塊：
- **左側 Sidebar**：上傳 PDF、切換 LLM 模型、顯示已收錄文件清單
- **右側 Main**：對話介面（輸入框 + 訊息串）

### Import

```tsx
import React, { useState, useEffect } from 'react';
```
- `useState`：管理 component 的狀態（問題輸入、對話歷史、loading 狀態等）
- `useEffect`：component 掛載時執行一次（這裡用來在頁面載入時撈已上傳的文件清單）

```tsx
import axios from 'axios';
```
HTTP 請求庫，比原生 `fetch` 好用：自動處理 JSON 序列化/反序列化，錯誤處理更直覺。

```tsx
import { Send, FileText, Loader2, ... } from 'lucide-react';
```
Lucide 是 React 的 icon 庫，每個 icon 是一個 React component，用 `size` 和 `className` 控制大小和樣式。

### TypeScript Interface

```tsx
interface Message {
  role: 'user' | 'ai';
  content: string;
}
```
TypeScript 的 interface 定義物件的「形狀」，`'user' | 'ai'` 是 union type，表示 role 只能是這兩個字串之一。這讓 IDE 可以在你打錯 role 時立刻報錯。

```tsx
interface ChatResponse {
  answer: string;
}
```
定義 API 回應的格式。之後 `axios.post<ChatResponse>(...)` 用這個告訴 TypeScript 回應的型別，可以安全地存取 `res.data.answer`。

### State 管理

```tsx
const [question, setQuestion] = useState<string>('');
const [chatHistory, setChatHistory] = useState<Message[]>([]);
const [loading, setLoading] = useState<boolean>(false);
const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
const [modelProvider, setModelProvider] = useState<string>("openai");
const [isUploading, setIsUploading] = useState<boolean>(false);
const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);
```

`useState<T>(initialValue)` 回傳 `[value, setter]`：
- `value`：目前的值
- `setter`：呼叫它就觸發 re-render，並更新畫面

每個狀態的用途：
| 狀態 | 用途 |
|------|------|
| `question` | input 框目前的文字 |
| `chatHistory` | 所有對話訊息的陣列 |
| `loading` | 等 AI 回應時顯示 loading spinner |
| `selectedFiles` | 使用者選了哪些 PDF（還沒上傳）|
| `modelProvider` | `"openai"` 或 `"ollama"` |
| `isUploading` | 上傳中時 disable 按鈕 |
| `uploadedFiles` | 知識庫已有的文件清單 |

### useEffect

```tsx
useEffect(() => {
  axios.get('http://127.0.0.1:8000/api/document/list').then((res) => {
    setUploadedFiles(res.data.filenames);
  });
}, []);
```
- `useEffect(callback, deps)`：deps 是依賴陣列，`[]` 代表只在 component **第一次掛載**時執行一次
- 頁面載入時自動呼叫 `/api/document/list`，把已在 ChromaDB 的文件顯示在 sidebar

### handleSend

```tsx
const handleSend = async (): Promise<void> => {
  if (!question.trim()) return;
```
`question.trim()` 去掉頭尾空白後如果是空字串（falsy），直接 return，避免送出空問題。

```tsx
  const userMsg: Message = { role: 'user', content: question };
  setChatHistory((prev) => [...prev, userMsg]);
  setQuestion('');
  setLoading(true);
```
- 先把使用者的訊息加進 chatHistory（讓 UI 立刻顯示），不等 API 回應
- `(prev) => [...prev, userMsg]`：用 callback 形式確保拿到最新的 state，`...prev` 展開原本的陣列，加上新訊息
- 馬上清空 input 框（`setQuestion('')`），使用者體驗更順暢

```tsx
  const res = await axios.post<ChatResponse>('http://127.0.0.1:8000/api/chat/ask', {
    question: question,
    model_provider: modelProvider
  });
```
POST 送出 JSON body，後端的 FastAPI 用 `ChatRequest` pydantic model 自動解析。

```tsx
  } finally {
    setLoading(false);
  }
```
`finally` 不管成功或失敗都會跑，確保 loading 一定會被關掉。

### handleFileUpload

```tsx
const formData = new FormData();
Array.from(selectedFiles).forEach((file) => {
  formData.append('files', file);
});
```
- `FormData`：瀏覽器的 API，用來發送 `multipart/form-data`（上傳檔案的格式）
- `Array.from(selectedFiles)`：`FileList` 不是陣列，要轉換才能用 `.forEach()`
- `'files'`：field name 必須跟後端的參數名 `files` 完全一致

```tsx
await axios.post('http://127.0.0.1:8000/api/document/upload/bulk', formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
});
```
上傳檔案要指定 `Content-Type: multipart/form-data`，讓後端知道這不是 JSON 而是檔案。

### JSX 重點

```tsx
<aside className="w-80 bg-white ... hidden md:flex">
```
Tailwind 的響應式前綴：`hidden` 預設隱藏，`md:flex` 在中等螢幕以上顯示為 flex。sidebar 在手機上隱藏，桌機才顯示。

```tsx
<label className="...">
  ...
  <input type="file" className="hidden" multiple accept=".pdf"
    onChange={(e) => setSelectedFiles(e.target.files)}
  />
</label>
```
把 `<input type="file">` 藏起來，用 `<label>` 包住，讓整個 label 區域都可以點擊觸發選檔。`multiple` 允許同時選多個檔案，`accept=".pdf"` 限制只能選 PDF。

```tsx
{chatHistory.map((msg, idx) => (
  <div key={idx} className={`... ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
```
- `key={idx}`：React 需要 list 裡每個元素有唯一的 key，方便它知道哪個元素變了
- 三元運算子根據 role 決定排版方向：user 訊息靠右（`flex-row-reverse`），AI 訊息靠左（`flex-row`）

```tsx
onKeyDown={(e) => e.key === 'Enter' && handleSend()}
```
按 Enter 送出，`&&` 短路運算：左邊為 true 才執行右邊。

---

## 二、Eval Dataset `evals/dataset.jsonl`

### JSONL 格式

`.jsonl`（JSON Lines）：每一行是一個獨立的 JSON 物件。

**為什麼不用普通 JSON 陣列**：
- 可以一行一行讀，不用把整個檔案載進記憶體
- 容易用 `git diff` 看改了哪題
- 容易用 script append 新題目

### 每筆資料的欄位

```json
{
  "question": "受試者同意書可以由協同主持人簽名嗎？",
  "expected_answer": "可以。依第49條規定...",
  "expected_source_titles": ["醫療器材優良臨床試驗管理辦法"],
  "difficulty": "single-hop"
}
```

| 欄位 | 用途 |
|------|------|
| `question` | 問系統的問題 |
| `expected_answer` | 標準答案（人工標注），目前未用於自動評分，留給未來的 correctness metric |
| `expected_source_titles` | 正確答案應該來自哪些文件，Recall 和 MRR 靠這個判斷 |
| `difficulty` | 題型分類 |

### 三種難度

| 難度 | 說明 | 例子 |
|------|------|------|
| `single-hop` | 問題和答案直接對應文件一段 | 「試驗用醫療器材應如何標示？」 |
| `multi-hop` | 需要綜合多個段落才能完整回答 | 「受試者同意書與試驗計畫書各應載明哪些內容？」 |
| `query-rewrite` | 口語問法，RAG 系統需要「理解意圖」才能找到對的 chunk | 「兒童參加臨床試驗需要家長同意嗎？」 |

**為什麼要分難度**：知道系統在哪種題型上表現差，才能有針對性地改進。如果只看平均分，可能看不出 query-rewrite 題型特別弱。

### 目前的限制

13 題全來自同一份文件（醫療器材優良臨床試驗管理辦法）。Recall@6 = 1.00 不代表 retriever 很好，只是因為沒有干擾文件——任何查詢都只可能找到同一份文件。加入更多文件後，分數才有鑑別力。

---

## 三、Phase B — LangFuse Observability

### 為什麼需要 Observability

Eval harness 告訴你分數，但不告訴你**為什麼**分數低。比如 faithfulness 某題是 0.0：
- 是 retriever 沒找到對的 chunk？
- 還是 LLM 忽略了 context 自己編？

Trace 讓你看到完整的執行過程：送了什麼 prompt、retrieve 到什麼、LLM 看到什麼 context、回了什麼。

### LangFuse 是什麼

LangFuse 是 LLM observability 平台（類似 Datadog 但專門給 LLM 用）。每次 chat 都會記錄：
- 完整 prompt（填入 placeholder 後的最終版）
- 每個 node 的輸入/輸出
- Token 用量和花費
- 延遲（p50/p95）

### Self-host vs Cloud

我們用 self-host（Docker），不用付費也沒有資料隱私問題。Cloud free tier 也可以，但有資料量限制。

### Docker Compose 裡的兩個 service

```yaml
langfuse-db:
  image: postgres:16
  # 沒有 ports: 設定
```
langfuse-db 不對外暴露 port，只在 Docker 內部網路讓 langfuse container 連。

```yaml
langfuse:
  ports:
    - "3000:3000"
  environment:
    DATABASE_URL: postgresql://langfuse:langfuse@langfuse-db:5432/langfuse
```
- `langfuse-db` 在 URL 裡當 hostname 使用，Docker 內部 DNS 自動解析
- port 3000：LangFuse 的 web UI

### 接下來要做的事（Phase B 剩餘）

1. **LangFuse 跑起來**（UI 在 localhost:3000）
2. **建立 API key**（在 LangFuse UI 裡）→ 存進 `.env`
3. **在 `services/rag_core.py` 加 callback**，讓每次 retrieve/LLM call 都送進 LangFuse
4. **補 structlog**：結構化 logging，JSON 格式輸出，方便之後用工具分析

---

## 四、v2 Roadmap 整體脈絡

面試被問「你在這個專案做了什麼改進」的標準回答框架：

**問題**：v1 能跑，但改任何東西都不知道有沒有變好（沒有量尺）、出了問題不知道哪一步壞了（沒有 trace）、pipeline 是硬式線性的（沒辦法加 query rewrite、multi-hop）。

**解法順序**：
1. **先建量尺（Phase A）**：eval harness，Recall、MRR、LLM-as-judge。有了基準數字，後面任何改動都能用數字驗證。
2. **再加 trace（Phase B）**：LangFuse，讓每次 chat 有完整 trace，知道哪一步出問題。
3. **然後才升級 RAG（Phase C）**：基於 A 的數字，決定哪個改動 ROI 最高（reranker > chunking > hybrid search）。
4. **最後才做 agentic（Phase D）**：LangGraph state machine，讓系統能 query rewrite、multi-hop、自我判斷。

**為什麼這個順序**：沒有量尺就升級是賭博，沒有 trace 就 debug 是猜謎。先量、再看、再改。