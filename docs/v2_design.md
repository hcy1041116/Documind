# DocuMind v2 Design Doc

> 狀態:draft v1 · 2026-05-20
> 範圍:從 v1(目前 main 分支)演進到 v2 的工程計畫
> 目標讀者:HCY(維護者),以及未來接手的自己

---

## 0. 為什麼寫這份

v1 已經跑得起來,但有幾個結構性問題讓「加東西」變難:

- 沒有 evaluation harness,任何改動(換 chunking、加 reranker、改 prompt)都只能用「感覺起來比較好」判斷
- prompt 寫死在 `api/chat.py`,retriever 參數寫死在 `services/rag_core.py`,要做 A/B 比較得改 code
- 沒有 observability,線上跑了什麼、retrieve 到什麼、token 花了多少都看不到
- chat 邏輯是線性 pipeline,要加 query rewriting、multi-hop、tool use 都得從頭改

v2 的目的不是「更厲害的 RAG」,是**讓系統可以被迭代**。先有量尺,再升級;先有 trace,再 agentic。

---

## 1. 架構盤點(v1 現況)

### 1.1 模組關係

```
PDF upload                          User question
     │                                    │
     ▼                                    ▼
PyPDFLoader                         撈 PG 最近 5 筆對話
     │                                    │
     ▼                                    ▼
RecursiveCharacterTextSplitter     ChromaDB.similarity_search(k=6)
(500 / 50, 中文 separators)              │
     │                                    ▼
     ▼                              組 prompt(history + context)
metadata 寫入 title(首頁首行)            │
     │                                    ▼
     ▼                              GPT-4o / Ollama llama3
ChromaDB (documind_law)                  │
                                          ▼
                                    回答 + sources(set 去重)
                                          │
                                          ▼
                                    寫回 PG chat_history
```

### 1.2 Stack 確認

| 層 | 技術 | 註記 |
|----|------|------|
| Vector store | ChromaDB(persist 在 `chromadb_data/`) | 留著 |
| Metadata / history | PostgreSQL(Docker) | 留著 |
| Embedding | `text-embedding-3-small`(1536 dims) | v2 可能評估換 BGE / multilingual-e5 |
| LLM | GPT-4o(temp=0.2)或 Ollama llama3 | Ollama 停損,UI toggle 保留 |
| Backend | FastAPI + LangChain | LangChain 1.x |
| Frontend | React 19 + Vite + Tailwind | 暫不動 |

### 1.3 v1 已知問題(audit)

按嚴重度排序:

1. **沒有 eval harness** — 改任何東西都是賭。最高優先處理。*(Phase A 進行中)*
2. ✅ **`api/chat.py` sources 用 `set()`** → 已修:改用 `dict.fromkeys()` 保序去重
3. **chunk_size=500 對中文偏小**,沒 reranker,k=6 容易碎片化 *(Phase C)*
4. **`metadata["title"]` 取首頁首行 40 字** → 部分修復:加入 `file.filename` fallback;完整解法留 Phase C
5. ✅ **`langchain_community.vectorstores.Chroma` 已 deprecated** → 已改用 `langchain_chroma`
6. ✅ **`test.py` 拿不到 `vector_db`** → 已刪除,由 eval harness 取代
7. **沒有 logging / trace**,prod 化前必須補 *(Phase B)*
8. ✅ **prompt 寫在 code 裡** → 已抽出至 `prompts/answer.md`
9. **CORS 全開、user_id hardcode `guest_user`** — Phase F 前要處理

---

## 2. v2 目標

**主目標**:讓 DocuMind 從「能跑的 demo」變成「可以被工程化迭代的系統」。

**非目標**(明確不做的事):
- 不追求 SOTA RAG 分數(這是個人專案,不是研究)
- 不重寫 frontend(toggle 留著當 feature 展示就好)
- 不做 multi-tenant(user_id 暫時 hardcode,Phase F 才考慮)
- 不導 LangSmith(優先試 LangFuse self-host)

**成功標準**:
- Phase A 結束時,任何 PR 都能跑 `make eval` 給出 retrieval 和 answer quality 的數字
- Phase D 結束時,複雜問題(multi-hop、需要 query rewrite 的)準確率明顯優於 v1
- 全程在 LangFuse 看得到每一次 chat 的完整 trace

---

## 3. Phase 計畫

### Phase A — Evaluation harness(先做這個)

**為什麼先做**:在沒有量尺前升級 RAG,等於在黑暗中換零件。Phase B 以後的每一個改動都要靠 A 的數字證明值得做。

**內容**:
1. 建一個小型測試集(20–50 題)
   - 從現有上傳的 PDF 出發,人工標 ground truth answer + ground truth chunks
   - 涵蓋三種難度:單跳事實題、需要綜合多段、需要 query rewrite 的模糊題
   - 存成 `evals/dataset.jsonl`,每筆:`{question, expected_answer, expected_source_titles, difficulty}`

2. Metrics 兩層:
   - **Retrieval**:Recall@k、MRR、context precision(retrieve 到的有多少真的相關)
   - **Answer**:LLM-as-judge(faithfulness、answer relevance),用 GPT-4o 當 judge,先 prompt-based 不上 Ragas

3. `scripts/run_eval.py`:吃 dataset → 跑現在的 pipeline → 出報告(CSV + console summary)

4. 接上 LangFuse:每一次 eval run 都進 LangFuse 一個 dataset,可以對比 run-to-run

**deliverables**:
- `evals/dataset.jsonl`(至少 20 題)
- `evals/metrics.py`
- `scripts/run_eval.py`
- `docs/eval_baseline.md`(v1 跑出來的數字,當基準)

**怎麼算完成**:`uv run python scripts/run_eval.py` 能跑完,印出 retrieval + answer 兩組分數,LangFuse 看得到 trace。

---

### Phase B — Observability(可以和 A 並行,後段)

**內容**:
1. LangFuse self-host(Docker compose)
2. 在 `services/rag_core.py` 包 callback handler,讓每次 retrieve / LLM call 都進 LangFuse
3. 把 prompt 從 `api/chat.py` 抽出來,改用 LangFuse prompt management(或先用本地 `prompts/*.md`,LangFuse 之後再上)
4. 補基本 logging:`structlog` 或 std `logging`,結構化 JSON 輸出
5. **Cost 與 latency 列為第一級指標** — token 用量、各 node 耗時、p50/p95 延遲,LangFuse 預設會收,需在每份 eval 報告與品質分數並列

**deliverables**:
- `docker-compose.yml` 加 LangFuse service
- `services/observability.py`(callback wiring)
- `prompts/answer.md`、`prompts/query_rewrite.md`
- `.env.example` 加 LangFuse keys

---

### Phase C — RAG 升級(基於 A 的數字才做)

**前置條件**:Phase A 跑完,有 baseline 數字。

**候選改動**(每個都是一個獨立 PR,各自跑 eval):

1. **修 chunking** — chunk_size 500 → 800/1000,overlap 50 → 100;試 `SemanticChunker`
2. **加 reranker** — retrieve top-20 → BGE-reranker 或 Cohere rerank-3 → top-5 進 prompt
3. **hybrid search** — ChromaDB dense + BM25 sparse,RRF 融合
4. **metadata 修補** — 三層 fallback:檔名 → PDF metadata title → 首頁啟發式;加 `page_number`
5. **embedding 換不換?** — BGE-M3 / multilingual-e5 中文更強,但要重建整庫,eval 先量

**順序建議**:4 → 2 → 1 → 3 → 5

每改一項都要跑 `make eval` 對比 baseline,寫進 `docs/eval_log.md`。

---

### Phase D — Agentic(LangGraph)

**前置條件**:Phase C 至少做完 reranker + metadata 修補。

**第一版 graph**:

```
   ┌─────────────┐
   │ classify    │ ─── 是閒聊 ───► 直接回答
   │ (是否需 RAG)│
   └──────┬──────┘
          │ 需要 RAG
          ▼
   ┌─────────────┐
   │ rewrite     │ 把口語問題改成檢索友善的 query
   └──────┬──────┘
          ▼
   ┌─────────────┐
   │ retrieve    │ hybrid + rerank
   └──────┬──────┘
          ▼
   ┌─────────────┐ 不夠 ┌─────────────┐
   │ judge       │─────►│ refine query│
   │ 夠不夠回答？│      └──────┬──────┘
   └──────┬──────┘             │
          │ 夠                  │
          ▼                     │
   ┌─────────────┐              │
   │ answer      │◄─────────────┘
   └─────────────┘
```

**為什麼 LangGraph 不選 CrewAI**:LangGraph 是 state machine,debug 清楚;DocuMind 是單一目標 QA,不需要多角色協作。

**deliverables**:
- `services/graph.py`
- `api/chat.py` 改用 graph,舊 linear pipeline 留 `?mode=simple` fallback
- eval dataset 加一批需要 query rewrite / multi-hop 的題

---

### Phase E — MCP integration

把 DocuMind 包成 MCP server:
- `documind_search(query)` → retrieve 結果
- `documind_ask(question)` → 完整 answer + citations

前置條件:Phase D 穩定後再封裝。技術選擇:`mcp` Python SDK,複用 `services/`。

---

### Phase F — production hardening(可選)

user_id / JWT、rate limiting、CORS 收緊、連線字串從 env 讀、上傳大小限制、PDF 解析超時。

---

## 4. 立刻可以做的小事(Phase A 之前) — ✅ 全部完成

1. ✅ **修 `api/chat.py` 的 `sources`**:改用 `dict.fromkeys()` 保序去重
2. ✅ **`test.py`**:已刪除(由 eval harness 取代)
3. ✅ **`Chroma` import**:已換成 `langchain_chroma.Chroma`
4. ✅ **`metadata["title"]` 加檔名 fallback**:首頁文字為空時 fallback 至 `file.filename`
5. ✅ **抽出 `prompts/answer.md`**:prompt 已從 `api/chat.py` 移出

---

## 5. 風險和取捨

| 風險 | 應對 |
|------|------|
| eval dataset 太小,分數 noisy | 至少 20 題,LLM-as-judge 跑 3 次取平均 |
| LangFuse self-host 跑不起來 | fallback:LangFuse cloud free tier |
| LangGraph 學習曲線 | Phase D 前先寫 toy graph 練手 |
| reranker 跑太慢 | BGE-reranker-base 或 Cohere API |
| embedding 換了要重建整庫 | eval 對比後再決定;dual-write 過渡 |

---

## 6. 不做的事

- ❌ 換掉 ChromaDB
- ❌ 重寫 frontend
- ❌ Ollama 優化
- ❌ multi-tenant
- ❌ 自訓 embedding / 微調 LLM
- ❌ LangSmith
- ❌ CrewAI

---

## 7. 下一步

1. ✅ §4 的五個小事全部完成
2. Phase A 進行中:
   - ✅ `evals/dataset.jsonl`:13 題(single-hop、multi-hop、query-rewrite),來源為醫療器材優良臨床試驗管理辦法
   - ✅ `scripts/run_eval.py`:retrieval eval 可跑,Recall@6: 1.00、MRR@6: 1.00(目前只有一份文件,加入更多文件後數字才有意義)
   - ✅ `scripts/run_eval.py`:完整 eval 可跑，Recall@6: 1.00 / MRR@6: 1.00 / Faithfulness: 0.92 / Relevance: 0.92
   - ✅ `prompts/judge_faithfulness.md`:faithfulness judge prompt
   - ✅ `prompts/judge_relevance.md`:answer relevance judge prompt
   - ✅ `docs/eval_baseline.md`:v1 基準數字（本地，gitignored）
   - ✅ `results.csv`:每題逐筆分數輸出（每次跑會覆蓋，不進 git）
3. Phase A 期間平行起 LangFuse(Phase B 前段)

每跑完一個 Phase 回來更新 §5 風險表。
