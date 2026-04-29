# DocuMind

企業級 RAG 文件問答系統。上傳 PDF，用自然語言提問，AI 根據文件內容回答。

## 功能

- PDF 批次上傳，自動切塊向量化存入 ChromaDB
- 語意搜尋找出相關段落，GPT-4o 生成回答
- 對話記憶（PostgreSQL 存最近 5 筆）
- 支援切換 LLM 模型（OpenAI / Ollama）

## 技術架構

| 層 | 技術 |
|----|------|
| 前端 | React + Vite + TypeScript + Tailwind |
| 後端 | FastAPI + Python 3.12 |
| LLM | GPT-4o / Ollama（可切換）|
| Embedding | text-embedding-3-small |
| 向量資料庫 | ChromaDB |
| 關聯式資料庫 | PostgreSQL |

## 啟動方式

**PostgreSQL（Docker）**
```bash
docker compose up -d
```

**後端**
```bash
uv sync
uv run uvicorn main:app --reload
```

**前端**
```bash
cd frontend
npm install
npm run dev
```

| 服務 | 位置 |
|------|------|
| 後端 API | http://127.0.0.1:8000 |
| API 文件 | http://127.0.0.1:8000/docs |
| 前端 UI | http://localhost:5173 |

## 環境需求

`.env` 檔案（放在專案根目錄）：
```
OPENAI_API_KEY=your_key_here
```

## Request Flow

```
PDF 上傳
  → PyPDFLoader 解析
  → RecursiveCharacterTextSplitter 切塊（500字，50字重疊）
  → OpenAI Embedding 轉向量
  → ChromaDB 儲存

使用者提問
  → PostgreSQL 撈最近 5 筆對話
  → ChromaDB 語意搜尋（top-3 相關段落）
  → GPT-4o 生成回答
  → 結果存回 PostgreSQL
```
