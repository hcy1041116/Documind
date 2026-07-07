# TODO

## Feature 1 - 模型切換（進行中）
- [x] 前端：model 切換下拉選單（openai / ollama）
- [x] 前端：已上傳檔案清單（NotebookLM 風格，呼叫 /api/document/list）
- [x] k 值調大（3→6）+ prompt 加嚴格限制
- [ ] 前端：上傳成功後自動更新檔案清單
- [ ] 前端：知識庫檔案可下載（需後端 /api/document/download 端點）
- [ ] RAG：Hybrid Search（向量 + BM25）
- [ ] RAG：Reranking（Hybrid 之後）
- [ ] AI 引用文件時自稱「參考文件1」問題（prompt 控制）
- [ ] start.sh：啟動前檢查 5432 port 是否被 WSL PostgreSQL 占用

## Feature 2 - LLMOps Dashboard
- [ ] 接 LangSmith tracing
- [ ] RAGAS 評估框架

## Feature 3 - AI Agent
- [ ] Tool Calling
- [ ] ReAct Agent
- [ ] Multi-agent（CrewAI / LangGraph）
