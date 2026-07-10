[English](DESIGN.md) | 中文

# DocuMind v2 — 系統設計文件

> 狀態：Draft v1 · 2026-05-18
> 範圍：從 v1（目前 `main` 分支）演進到 v2 的工程計畫

---

## 0. 背景

DocuMind 是一套企業文件問答系統。使用者上傳 PDF，系統將內容切塊嵌入向量資料庫，並以 RAG 架構結合對話歷史回答自然語言問題。

v1 已可運作，但有幾個結構性問題讓「加東西」變得困難：

| 問題 | 影響 |
|------|------|
| 沒有 evaluation harness | 任何改動（換 chunking、加 reranker、改 prompt）都只能憑感覺判斷 |
| Prompt 與 retriever 參數寫死在程式碼裡 | 做 A/B 比較必須直接改 source code |
| 沒有 observability | 看不到 retrieve 了什麼、花了多少 token |
| 線性 pipeline | 要加 query rewriting、multi-hop、tool use 都得從頭重寫 |

**v2 目標**：讓系統從「能跑的 demo」變成「可以被工程化迭代的系統」。先有量尺再升級；先有 trace 再 agentic。

---

## 1. 架構（v1 現況）

### Request flow

```
PDF 上傳                              使用者提問
     │                                    │
     ▼                                    ▼
PyPDFLoader                     從 PostgreSQL 撈最近 5 筆對話
     │                                    │
     ▼                                    ▼
RecursiveCharacterTextSplitter   ChromaDB.similarity_search(k=6)
  chunk=500 / overlap=50               │
     │                                    ▼
     ▼                           組 prompt（history + context）
寫入 metadata.title                      │
  （首頁首行前 40 字）                    ▼
     │                           GPT-4o（temp=0.2）
     ▼                                   │
ChromaDB（collection: documind_law）     ▼
                              回答 + 去重後的來源清單
                                         │
                                         ▼
                              寫回 PostgreSQL chat_history
```

### 技術選型

| 層 | 技術 | 備註 |
|----|------|------|
| 向量資料庫 | ChromaDB（持久化） | 保留 |
| 對話歷史 | PostgreSQL（Docker） | 保留 |
| Embedding | `text-embedding-3-small`（1536 維） | 評估換 BGE-M3 / multilingual-e5 |
| LLM | GPT-4o 或 Ollama llama3 | Ollama 已停損，UI toggle 保留 |
| 後端 | FastAPI + LangChain 1.x | |
| 前端 | React 19 + Vite + Tailwind | v2 不動 |

### v1 已知問題

1. **沒有 eval harness** — 最高優先處理
2. **`sources` 用 `set()`** → 順序不穩定，trace 對不上原文
3. **chunk_size=500 對中文偏小**；沒有 reranker；k=6 容易碎片化
4. **`metadata["title"]` 取首頁首行** → 封面是圖或 logo 時會出錯，需加 fallback
5. **`langchain_community.vectorstores.Chroma` 已 deprecated** → 改用 `langchain_chroma`
6. **沒有結構化 logging 或 tracing**
7. **Prompt 寫死在 `api/chat.py`**
8. **CORS 全開，`user_id` hardcode 為 `guest_user`**

---

## 2. 目標

**主目標**：讓 DocuMind 從「能跑的 demo」變成「可以被工程化迭代的系統」。

**明確不做的事**：
- 不追求 SOTA RAG 分數（個人專案，非學術研究）
- 不重寫前端
- 不做 multi-tenant（Phase F 才考慮）
- 不導入 LangSmith（改用 LangFuse；self-host 測試過，後來改接 LangFuse Cloud）

**完成標準**：
- Phase A 結束：任何 PR 都能跑 `make eval`，輸出 retrieval 與 answer quality 數字
- Phase D 結束：複雜問題（multi-hop、需要 query rewrite）的準確率明顯優於 v1
- 全程：每一次 chat 在 LangFuse 都有完整 trace

---

## 3. Phase 計畫

### Phase A — Evaluation Harness（先做這個）

**為什麼先做**：沒有量尺就升級 RAG，等於在黑暗中換零件。Phase B 以後的每個改動都要靠 A 的數字來驗證。

| 產出物 | 說明 | 狀態 |
|--------|------|------|
| `evals/dataset.jsonl` | 20–50 題，每筆含 `question`、`expected_answer`、`expected_source_titles`、`difficulty` | ✅ 15 題（2026-07-11 擴充，加入 QA 文件來源的題目與多重來源標記） |
| `prompts/judge_faithfulness.md` / `judge_relevance.md` | 手刻 judge prompt（GPT-4o） | ⚠️ 已被 RAGAS 內建 judge 取代，檔案還在但目前未使用 |
| ~~`scripts/run_eval.py`~~ | Recall@k、MRR、faithfulness、relevance | 🗄️ 已封存，改用下一列 |
| `scripts/RAGAS.py` | 改用 RAGAS 框架：Faithfulness、Answer Relevancy、Context Recall、Context Precision | ✅ 完成（2026 年中遷移），⚠️ 但可靠度有已知問題——長時間跑會有連線失敗、部分分數拿不到，細節見內部筆記 |
| `notes/eval_baseline.md` | v1 基準（單一文件情境）— Recall 1.00 / MRR 1.00 / Faithfulness 0.92 / Relevance 0.92 | ✅ 完成（本地，gitignored；已是舊 pipeline 的基準，非目前 RAGAS 數字的對照） |

測試集涵蓋三種難度：單跳事實題、需綜合多段、需要 query rewrite 的模糊題。Judge 模型：改用 RAGAS 框架（取代原本手刻的 prompt-based judge）。

**怎麼算完成**：`uv run python scripts/RAGAS.py` 跑完並印出四組分數；LangFuse 看得到 trace。

---

### Phase B — Observability（可與 Phase A 後段並行）✅ 大致完成

1. ~~LangFuse self-host（Docker Compose）~~ → ✅ 改用 LangFuse Cloud（self-host container 還留著但已停用）
2. ✅ 在 `services/rag_core.py`／`api/chat.py` 加 callback handler，每次 retrieve 與 LLM call 都進 LangFuse
3. ✅ 將 prompt 從 `api/chat.py` 抽出 → `prompts/answer.md`
4. ⬜ 補結構化 logging：`structlog`，JSON 輸出（未做）
5. ⬜ **Cost 與 latency 列為第一級指標**（未做）— LangFuse 預設有收，但還沒有整理進 eval 報告跟品質分數並列呈現

**為什麼與 A 並行**：光看分數無法知道哪一步出問題（retrieve 沒抓到？還是 LLM 沒用好 context？），trace 是 debug 的必要條件。

---

### Phase C — RAG 升級（基於 Phase A 的數字才做）

每個項目各為一個獨立 PR；每個 PR 都跑 `make eval` 並將 delta 記錄在 `docs/eval_log.md`。

| 項目 | 預期效益 | 優先序 | 狀態 |
|------|---------|--------|------|
| Metadata fallback | 正確性修復 | 第 1 — 成本低，不需要 eval | ✅ 完成（2026-07-10，三層 fallback：PDF metadata → 首行 → 檔名） |
| Reranker（原規劃 BGE-reranker-base 或 Cohere rerank-3） | Context precision ↑ | 第 2 — ROI 最高 | ✅ 完成（2026-07-10，實際改用 flashrank 本機多語言 cross-encoder，不需要額外 API key） |
| Chunking（500 → 800–1000，overlap 50 → 100；試 SemanticChunker） | 中文長文 Recall ↑ | 第 3 | ⬜ 未做——已發現兩欄「問／答」版面 PDF 的 chunk 邊界問題（見 `notes/todo.md` Backlog），跟這項高度相關 |
| Hybrid search（ChromaDB dense + BM25 sparse，RRF fusion） | 專有名詞 Recall ↑ | 第 4 | ✅ 完成（2026-07-10，`EnsembleRetriever`，向量 + BM25） |
| Embedding 替換（BGE-M3 / multilingual-e5） | 中文 benchmark ↑ | 最後 — 需重建整個索引 | ⬜ 未做 |

---

### Phase D — Agentic Pipeline（LangGraph）

*前置條件：Phase C 的 reranker + metadata 修補完成。*

將線性 pipeline 改為能 plan、能 query rewrite、能多輪迴圈的 state machine：

```
┌─────────────┐
│   分類      │──── 閒聊 ────► 直接回答
│（需要 RAG?）│
└──────┬──────┘
       │ 需要 RAG
       ▼
┌─────────────┐
│   改寫      │  將口語問題改成檢索友善的 query
└──────┬──────┘  （帶入對話歷史）
       ▼
┌─────────────┐
│   檢索      │  hybrid search + rerank
└──────┬──────┘
       ▼
┌─────────────┐  不足  ┌──────────────┐
│   判斷      │───────►│  精煉 query  │
│ 夠不夠回答？│        └──────┬───────┘
└──────┬──────┘               │
       │ 足夠                  │
       ▼                       │
┌─────────────┐                │
│   回答      │◄───────────────┘
└─────────────┘
```

**為什麼選 LangGraph 不選 CrewAI**：LangGraph 是 state machine，debug 清楚、與 LangFuse 整合好。CrewAI 適合多角色協作；DocuMind 是單一目標 QA，不需要。

舊的線性 pipeline 保留為 `?mode=simple` fallback，用於迴歸測試。

---

### Phase E — MCP Integration

將 DocuMind 包裝成 MCP server，讓 Claude Desktop 與其他 MCP client 可以呼叫：
- `documind_search(query)` → 檢索結果
- `documind_ask(question)` → 完整回答 + citations

*前置條件：Phase D 穩定後才封裝，否則等於把不穩定的核心暴露出去。*

---

### Phase F — Production Hardening（選做）

JWT 認證、rate limiting、CORS 收緊、連線字串從 env 讀取、上傳大小限制、PDF 解析超時。

---

## 4. 立刻可以做的小事（Phase A 之前）✅ 全部完成

五個改動，每個不超過 30 分鐘，卻能讓後續所有 Phase 都更順：

1. ✅ `api/chat.py`：`set(sources)` 改為保序去重
2. ✅ `test.py`：加入 `from services.rag_core import vector_db`
3. ✅ `services/rag_core.py`：`langchain_community.vectorstores.Chroma` → `langchain_chroma.Chroma`
4. ✅ `api/document.py`：三層 title fallback（實際版本：PDF metadata → 首行啟發式 → 檔名，跟原規劃順序略有不同）
5. ✅ 將 prompt 字串從 `api/chat.py` 移出 → `prompts/answer.md`

---

## 5. 風險與應對

| 風險 | 應對 |
|------|------|
| eval dataset 太小，分數 noisy | 至少 20 題；LLM-as-judge 跑 3 次取平均 |
| LangFuse self-host 無法啟動 | fallback：LangFuse cloud free tier |
| LangGraph 學習曲線 | Phase D 前先寫 toy graph 練手 |
| Reranker 延遲過高 | 用 BGE-reranker-base（小）或 Cohere API；不上 large 版 |
| 換 embedding 需重建整個索引 | eval 先量 delta；用 dual-write 過渡 |

---

## 6. 明確不做的事

- ❌ 替換 ChromaDB
- ❌ 重寫前端
- ❌ Ollama 路徑優化
- ❌ Multi-tenancy
- ❌ 自訓 embedding 或微調 LLM
- ❌ LangSmith
- ❌ CrewAI
