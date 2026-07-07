# DocuMind 學習筆記

---

## LLM 的無狀態特性與記憶架構

**LLM API 是無狀態的**：每次 API call 對 GPT-4o 來說都是全新的，它完全不記得上一次對話。

現在的架構是「假記憶」：
- 每次請求從 PostgreSQL 撈最近 5 筆 chat_history
- 把歷史對話拼成字串塞進 prompt
- LLM 「看到」歷史，給出有上下文的回答
- 回答完再把這筆存回 PostgreSQL

用圖示理解：
```
理想（真正的 context window）：aAbBcCdD
現實（每次重新注入）         ：aAaAbBaAbBcC
```

**為何 limit(5)**：prompt 有 token 上限，歷史太長會超限，所以只取最近 5 筆。
缺點：超過 5 輪的對話會遺失記憶。

**改進方向**：ConversationSummaryBufferMemory（超過一定長度就把舊對話壓縮成摘要）

---

## 模型切換設計

**為何要改 rag_core.py**：原本 llm 在 module 載入時就 hardcoded 初始化，無法動態切換。

**LLM 物件 vs 對話狀態**：
- LLM 物件（`ChatOpenAI(...)`）：只是一個「設定好的 API 客戶端」，本身不存任何對話內容
- 對話內容：存在 PostgreSQL，用 user_id 隔離

**為何每次請求都重建 LLM 物件，不用 cache**：
- 多人系統中，User A 選 OpenAI、User B 選 Ollama，global cache 會互相覆蓋
- LLM 物件初始化成本很低（只是建一個 Python 物件），不需要 cache

**Embedding 和 LLM 是獨立的**：
- 換 LLM → 不影響 ChromaDB，隨時可換
- 換 Embedding 模型 → ChromaDB 裡的向量和查詢向量語言不同，相似度搜尋會亂掉，必須重新 index 所有文件

**Enum 好過字串比對**：
```python
# 不好：打錯字不會報錯
if request.model_provider == "openai":

# 好：IDE 可以找到所有使用點，改名時不會漏
if request.model_provider == ModelProvider.openai:
```

**Factory Pattern**：LangChain 的所有 LLM class（`ChatOpenAI`、`ChatOllama`）都實作同一個介面（`BaseChatModel`），呼叫端只要換掉初始化的物件，其他程式碼完全不用改。

---

## ChromaDB

- collection ≈ SQL 的 table
- 每筆資料固定有：`ids`、`documents`（原始文字）、`embeddings`（向量）、`metadatas`（自訂欄位）
- `metadatas` 裡的欄位（`source`、`title`）是我們自己定義的，不是 ChromaDB 規定的
- `get()` → 撈資料（不做相似度搜尋）；`include=["metadatas"]` 只回傳 metadata，省記憶體
- `query()` → 向量相似度搜尋

---

## Docker 概念

**為何用 Docker 跑 PostgreSQL**：WSL2 重啟後 PostgreSQL 服務不會自動啟動，資料也可能消失，用 Docker + named volume 比較穩定。

**image vs container**：
- image = 食譜（不可變的模板）
- container = 按食譜做出來的料理（可執行的實例）

**docker-compose up 流程**：
1. 去 Docker Hub pull image（本機沒有的話）
2. 用 image 啟動 container，套用 environment / volumes 設定
3. **不會產生 Dockerfile**，直接用現成的官方 image

**volume**：
- container 預設「用完即丟」，停掉就失去資料
- named volume（`postgres_data:`）由 Docker 管理，container 刪掉重建資料還在
- service 底下的 `volumes` = 「掛載到哪」；最底層的 `volumes:` 宣告 = 「跟 Docker 登記這個 volume 存在」

**`POSTGRES_USER` 的陷阱**：設了 `POSTGRES_USER: documind_user` 後，預設的 `postgres` superuser 不會被建立，要用 `documind_user` 登入。

**Dockerfile layer**：每行 `RUN`、`COPY`、`ADD` 都會產生一個 layer，layer 多會讓 image 肥大，所以慣例是合併：
```dockerfile
# 好：一個 layer
RUN apt-get update && apt-get install -y curl && apt-get clean
```

---

## Eval Metrics：Recall@k 與 MRR

**Recall@k**：前 k 筆結果裡，有沒有包含正確來源。只回答「有沒有」，不管排第幾。

**MRR（Mean Reciprocal Rank）**：正確來源第一次出現在第幾名的倒數，再取平均。
- 排第 1 → RR = 1.0
- 排第 3 → RR = 0.33
- 沒找到 → RR = 0

**為何 MRR 比 Recall 更有意義**：LLM 讀 context 有位置偏差（Lost in the Middle），排越前面的 chunk 被引用機率越高。Recall 看不出這個差距，MRR 可以。

**實作重點**：
- 用 `enumerate(retrieved_titles)` 找第一個符合的 index
- `_rr = 0` 放 loop 之前當預設值，loop 裡找到就更新並 `break`
- MRR = `sum(rr) / len(rr)`

**為何 MRR break 在第一個符合**：MRR 只關心「第一次拿到有用的東西是第幾名」，不需要繼續找後面的相關來源（那是 Average Precision 的事）。

---

## Async vs Sync

**Sync（同步）**：每行跑完才跑下一行，遇到網路等待就卡住。

**Async（非同步）**：遇到等待操作時，Python 可以先做別的事，等結果回來再繼續。FastAPI endpoint 用 `async def` 是因為要同時服務很多 request，不能讓一個人的等待卡住所有人。

**`await` 的限制**：只能在 `async def` 函式裡用。

**在 sync 腳本裡執行 async function**：用 `asyncio.run()`——它建一個 event loop、跑一次 async function、然後關掉：
```python
result = asyncio.run(some_async_function())
```

---

## LLM-as-Judge：Faithfulness

RAG 的 answer 品質有兩個維度：
- **Faithfulness**：回答的內容在 retrieved context 裡有沒有依據（防幻覺）
- **Answer Relevance**：回答有沒有真正回應問題

**Faithfulness 的做法**：第二次呼叫 GPT-4o 當 judge，輸入 context + answer，讓它打 0~1 分。這個 judge call 只存在 eval 腳本裡，不影響 production prompt。

**重要：judge 和 production 是分開的**：
- `prompts/answer.md` = production 用，讓 RAG 回答問題
- judge prompt = 只在 `scripts/run_eval.py` 裡，評估回答品質

**現成工具**：RAGAS 把這些 metric 全部包好，但先自己寫一次才知道黑盒子裡在算什麼。

---

## csv.DictWriter

Python 內建 `csv` module，`DictWriter` 讓你用 dict 寫每一行，key = 欄位名稱：

```python
import csv
with open("output.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["question", "score"])
    writer.writeheader()
    writer.writerow({"question": "...", "score": 0.92})
```

`newline=""` 是 Windows 避免多餘空行的慣例寫法。

**`zip` vs `enumerate`**：把多個 list 逐一配對時，`zip` 不需要 index 直接解包，`enumerate` 用 index 去取其他 list 的值——兩種都對，`zip` 更 Pythonic。

---

## Git 觀念

**node_modules 不放 git**：體積大，任何人 clone 後跑 `npm install` 就能重建，`package.json` 已記錄所有依賴。

**git rm --cached**：把已追蹤的檔案從 git 移除，但不刪實際檔案（用來修正「不該追蹤但已 commit」的情況）。

**SSH multi-account**：見 `~/.claude/CLAUDE.md`，用 alias `github-hcy` 區分帳號。

