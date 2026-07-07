# DocuMind 完整技術筆記

> 面試準備版。涵蓋架構、每個檔案的作用、每段語法的解釋。

---

## 一、整體架構

### 系統是在做什麼

使用者上傳 PDF → 系統把 PDF 切成小塊、向量化存進 ChromaDB → 使用者問問題 → 系統從 ChromaDB 找出最相關的幾段文字 → 把文字 + 問題 + 對話歷史一起送給 GPT-4o → 回傳答案。

這個架構叫 **RAG（Retrieval-Augmented Generation）**：先「Retrieve」相關文件，再「Generate」回答。

### 為什麼需要 RAG？

GPT-4o 本身不知道你上傳的 PDF 內容。你可以把整份 PDF 塞進 prompt，但 PDF 如果很長會超過 token 上限，而且每次都送全文很貴。RAG 的做法是只送「跟這個問題最相關的幾段」，既省 token 又準確。

### Request Flow

```
PDF 上傳
  │
  ▼
PyPDFLoader        ← 解析 PDF，每頁變成一個 Document 物件
  │
  ▼
RecursiveCharacterTextSplitter  ← 把每頁切成 500 字的 chunk，重疊 50 字
  │
  ▼
OpenAIEmbeddings   ← 每個 chunk 送給 OpenAI，轉成 1536 維的數字向量
  │
  ▼
ChromaDB           ← 向量存進資料庫（chromadb_data/ 資料夾）
```

```
使用者問問題
  │
  ▼
PostgreSQL         ← 撈最近 5 筆對話歷史
  │
  ▼
ChromaDB.similarity_search(k=6)  ← 把問題也向量化，找出最接近的 6 個 chunk
  │
  ▼
組 Prompt          ← 把 context + 歷史 + 問題拼成 prompt
  │
  ▼
GPT-4o             ← 生成回答
  │
  ▼
PostgreSQL         ← 把這次對話存起來
  │
  ▼
回傳 {answer, sources}
```

### 技術選型

| 層 | 技術 | 為什麼這個 |
|----|------|-----------|
| 向量資料庫 | ChromaDB | 輕量、本機跑、不需要額外服務 |
| 對話歷史 | PostgreSQL | 關聯式資料，支援 SQL 查詢 |
| Embedding | text-embedding-3-small | OpenAI 的，跟 GPT-4o 同生態系，1536 維 |
| LLM | GPT-4o | 目前最強的商業模型，中文也很好 |
| 後端 | FastAPI | async 支援好，自動產生 API 文件 |
| 前端 | React + Vite + Tailwind | 現代前端標配 |

### 資料流圖

```
uploads/           ← PDF 原始檔
chromadb_data/     ← ChromaDB 向量資料（persistent）
PostgreSQL         ← chat_history table（對話記錄）
```

---

## 二、目錄結構

```
DocuMind/
├── main.py              ← FastAPI app 入口，掛載 router、設定 lifespan
├── database.py          ← PostgreSQL 連線設定、Session 工廠
├── models.py            ← ORM 模型（ChatHistory table 定義）
├── schemas.py           ← Pydantic 請求格式定義
├── docker-compose.yml   ← PostgreSQL + LangFuse 的 Docker 設定
├── .env                 ← OPENAI_API_KEY（不進 git）
│
├── api/
│   ├── chat.py          ← /api/chat/ask endpoint（RAG 主流程）
│   └── document.py      ← /api/document/upload/bulk endpoint
│
├── services/
│   └── rag_core.py      ← Embedding、ChromaDB、TextSplitter 初始化（shared singletons）
│
├── prompts/
│   ├── answer.md            ← 回答用的 prompt template
│   ├── judge_faithfulness.md ← eval 用的 faithfulness judge prompt
│   └── judge_relevance.md   ← eval 用的 relevance judge prompt
│
├── evals/
│   └── dataset.jsonl    ← eval 測試集（13 題）
│
├── scripts/
│   └── run_eval.py      ← eval 腳本，跑出 Recall/MRR/Faithfulness/Relevance
│
└── chromadb_data/       ← ChromaDB 持久化資料（不進 git）
```

---

## 三、Docker Compose

```yaml
services:
  postgres:
    image: postgres:16
```
`image: postgres:16`：從 Docker Hub 拉 postgres 官方映像，版本 16。

```yaml
    environment:
      POSTGRES_USER: documind_user
      POSTGRES_PASSWORD: documind_pass
      POSTGRES_DB: documind_db
```
容器啟動時設定的環境變數。這三個 PostgreSQL 官方映像會自動讀取，建立指定的 user 和 database。注意：設了 `POSTGRES_USER` 之後，預設的 `postgres` superuser **不會**被建立。

```yaml
    ports:
      - "5432:5432"
```
`本機port:容器port`。讓本機的 `localhost:5432` 連到容器裡的 PostgreSQL。

```yaml
    volumes:
      - postgres_data:/var/lib/postgresql/data
```
Named volume：容器刪掉重建，資料仍保留在 Docker 管理的 volume 裡。`/var/lib/postgresql/data` 是 PostgreSQL 在容器內存資料的路徑。

```yaml
  langfuse:
    image: langfuse/langfuse:2
    depends_on:
      - langfuse-db
```
`depends_on`：告訴 Docker 先把 langfuse-db 跑起來，再啟動 langfuse。不過這只保證「先啟動」，不保證 langfuse-db 已經 ready。

```yaml
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse@langfuse-db:5432/langfuse
```
`langfuse-db` 是同一個 compose 裡的 service 名稱，容器之間可以用 service 名當 hostname。

```yaml
      NEXTAUTH_SECRET: local-dev-secret
      SALT: local-dev-salt
```
LangFuse 用來加密 session 的 secret。local 開發隨便填，production 要用真正的隨機字串。

```yaml
volumes:
  postgres_data:
  langfuse_data:
```
最底層的 `volumes:` 是「向 Docker 登記這些 named volume 存在」。上面 service 裡的 `volumes:` 是「掛載到哪個路徑」。兩個都需要。

---

## 四、`main.py`

```python
from contextlib import asynccontextmanager
```
Python 標準庫，`asynccontextmanager` 讓你把一個 async generator function 變成 async context manager（可以用 `async with` 的東西）。

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield
    # shutdown
    await engine.dispose()
```
`lifespan` 是 FastAPI 的生命週期鉤子：
- `yield` 之前的程式碼在 **伺服器啟動時**執行（建立 table）
- `yield` 之後的程式碼在 **伺服器關閉時**執行（釋放資料庫連線）
- `engine.begin()` 開一個 transaction，`run_sync` 是把同步的 `create_all` 包成可在 async 環境執行
- `create_all` 讀取所有繼承自 `Base` 的 model，如果 table 不存在就建立（存在就跳過）

```python
app = FastAPI(title="DocuMind API", lifespan=lifespan)
```
建立 FastAPI 實例，把 lifespan 傳進去。

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    ...
)
```
CORS（Cross-Origin Resource Sharing）：瀏覽器的安全機制，不同 domain 的請求預設會被擋。`allow_origins=["*"]` 讓所有來源都能訪問 API，這在 dev 方便但 production 要收緊。

```python
app.include_router(chat.router)
app.include_router(document.router)
```
把 `api/chat.py` 和 `api/document.py` 裡定義的 router 掛上去。FastAPI 的 router 讓你把不同功能的 endpoint 拆到不同檔案，最後統一 include。

---

## 五、`database.py`

```python
DATABASE_URL = "postgresql+asyncpg://documind_user:documind_pass@localhost:5432/documind_db"
```
連線字串格式：`driver://user:password@host:port/dbname`
- `postgresql+asyncpg`：用 asyncpg 這個 async 驅動（而不是預設的同步 psycopg2）
- 為什麼 async：FastAPI 是 async 框架，如果用同步的 DB driver，等待 DB 回應時會卡住整個程式

```python
engine = create_async_engine(DATABASE_URL, echo=True)
```
- `engine`：SQLAlchemy 的連線池管理器，所有 DB 操作都透過它
- `echo=True`：把底層執行的 SQL 印到 console，debug 很有用，production 要關掉

```python
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)
```
Session 工廠：
- `bind=engine`：指定這個 factory 用哪個 engine
- `expire_on_commit=False`：commit 後不要讓 ORM 物件失效（預設 True 的話，commit 後再讀物件屬性會重新查資料庫）
- 這個 factory 每次呼叫都產生一個新的 Session（像是一次資料庫的「工作階段」）

```python
Base = declarative_base()
```
所有 ORM model 都要繼承這個 Base，SQLAlchemy 才能把它們納入管理。

```python
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```
**Dependency Injection（依賴注入）**：
- FastAPI 看到 endpoint 的參數有 `Depends(get_db)`，就會自動呼叫這個 generator
- `yield session` 把 session 傳給 endpoint 使用
- endpoint 跑完後，`async with` 的 `__aexit__` 自動關閉 session
- 好處：每個 request 自動拿到新的 session，用完自動關，不用手動管理

---

## 六、`models.py`

```python
from sqlalchemy import Column, Integer, String, Text, DateTime, func
```
SQLAlchemy 的欄位型別：
- `Integer`：整數，用於 primary key
- `String(50)`：有長度限制的字串，對應 SQL VARCHAR(50)
- `Text`：無長度限制的字串，對應 SQL TEXT，用於長文字（問題、回答）
- `DateTime(timezone=True)`：帶時區的時間
- `func`：SQL 函式，這裡用 `func.now()` 讓資料庫在 insert 時自動填入當下時間

```python
class ChatHistory(Base):
    __tablename__ = "chat_history"
```
繼承 `Base` 代表這個 class 對應到一張 table。`__tablename__` 指定 table 名稱。

```python
    id = Column(Integer, primary_key=True, index=True)
```
- `primary_key=True`：這欄是主鍵，PostgreSQL 自動做 auto increment
- `index=True`：建立索引，用 id 查詢會更快

```python
    user_id = Column(String(50), nullable=False, index=True)
```
- `nullable=False`：不允許 NULL，insert 時一定要有值
- `index=True`：因為常常用 `WHERE user_id = ?` 查詢，建索引讓查詢更快

```python
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
```
`server_default=func.now()`：讓 **PostgreSQL**（不是 Python）在 insert 時填入當下時間。好處是時間由 DB server 產生，不受 Python 程式時區影響。

---

## 七、`schemas.py`

```python
from pydantic import BaseModel
```
Pydantic 是 FastAPI 使用的資料驗證庫。繼承 `BaseModel` 的 class 會自動驗證欄位型別，型別不對會回傳 422 錯誤。

```python
class ModelProvider(Enum):
    openai = "openai"
    ollama = "ollama"
```
用 Enum 而不是 string 的好處：
- IDE 可以找到所有使用點
- 改名時不會漏掉
- 打錯字會報錯而不是靜默錯誤

```python
class ChatRequest(BaseModel):
    model_provider: ModelProvider = ModelProvider.openai
    question: str
    user_id: str = "guest_user"
```
- `= ModelProvider.openai`：有預設值，POST body 不送這個欄位時用預設值
- `user_id: str = "guest_user"`：hardcode 預設值，Phase F 才換成真正的 JWT

---

## 八、`services/rag_core.py`

這個檔案在 **module 載入時**（import 的那一刻）就初始化所有 AI 相關的物件。

```python
from dotenv import load_dotenv
load_dotenv()
```
讀取 `.env` 檔案，把裡面的 `OPENAI_API_KEY=...` 載入成環境變數。之後 OpenAI SDK 自動讀取 `OPENAI_API_KEY` 這個環境變數。

```python
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
```
Embedding 模型的客戶端。每次呼叫它，就是送一個字串到 OpenAI API，拿回一個 1536 維的浮點數向量。

**為什麼是 singleton（只初始化一次）**：Embedding 物件本身不存任何資料，只是一個「設定好的 API 客戶端」，建一次讓所有 request 共用就好，不需要每次 request 重建。

```python
vector_db = Chroma(
    collection_name="documind_law",
    embedding_function=embeddings,
    persist_directory=CHROMA_PATH
)
```
- `collection_name`：ChromaDB 裡的 collection（類似 SQL 的 table）
- `embedding_function`：告訴 ChromaDB 做 similarity search 時，問題要用哪個模型轉成向量
- `persist_directory`：資料存到硬碟的哪裡，重啟後資料還在

```python
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separators=["\n\n", "\n", "。", "！", "？", "，", " ", ""]
)
```
- `chunk_size=500`：每個 chunk 最多 500 個字元
- `chunk_overlap=50`：相鄰 chunk 重疊 50 個字元，避免句子在邊界被截斷導致語意斷裂
- `separators`：切割的優先順序，先試雙換行，不行再試單換行，以此類推，最後才是逐字切
- 為什麼有中文標點：英文預設的 separators 沒有中文標點，加上去讓中文文件切得更自然

---

## 九、`api/document.py`

```python
router = APIRouter(prefix="/api/document", tags=["Document"])
```
- `prefix`：這個 router 下所有 endpoint 的路徑前綴，`/upload/bulk` 實際是 `/api/document/upload/bulk`
- `tags`：API 文件（/docs）裡的分組標籤

```python
os.makedirs(UPLOAD_DIR, exist_ok=True)
```
`exist_ok=True`：目錄已存在也不報錯。如果沒有這個參數，目錄存在時會拋 `FileExistsError`。

```python
async def upload_multiple_pdfs(files: Annotated[list[UploadFile], File(...)]):
```
- `UploadFile`：FastAPI 的上傳檔案型別，有 `.filename`、`.read()` 等屬性
- `list[UploadFile]`：接受多個檔案
- `Annotated[..., File(...)]`：讓 FastAPI 知道這個參數來自 form data（不是 JSON body）

```python
content = await file.read()
with open(file_path, "wb") as buffer:
    buffer.write(content)
```
- `await file.read()`：async 讀取上傳的 bytes
- `"wb"`：write binary，寫入二進位資料（PDF 是 binary）

```python
loader = PyPDFLoader(file_path)
pages = loader.load()
```
LangChain 的 PDF loader，把每一頁解析成一個 `Document` 物件，`Document.page_content` 是頁面文字，`Document.metadata` 包含 `page`（頁碼）、`source`（檔案路徑）。

```python
first_page_text = pages[0].page_content.strip()
real_title = file.filename
if first_page_text:
    lines = [line.strip() for line in first_page_text.split('\n') if line.strip()]
    if lines:
        real_title = lines[0][:40]
```
三層 fallback 邏輯（由內而外）：
1. 如果第一頁有文字，用第一頁第一行前 40 字當 title
2. 如果第一頁是空的（掃描版 PDF），fallback 到 `file.filename`
3. 這個 `real_title` 之後存進每個 chunk 的 `metadata["title"]`，答案裡的 sources 欄位就靠它

```python
chunks = text_splitter.split_documents(pages)
for chunk in chunks:
    chunk.metadata["source"] = file.filename
    chunk.metadata["title"] = real_title
    all_chunks.append(chunk)
```
切塊完後手動把 metadata 寫進每個 chunk，之後存進 ChromaDB 的時候一起存。

```python
if all_chunks:
    vector_db.add_documents(all_chunks)
```
把所有 PDF 的所有 chunk 一次送給 ChromaDB（不是一個一個送）。`add_documents` 內部會：
1. 把每個 chunk 的文字送給 embedding model 轉向量
2. 把（向量、文字、metadata）一起存進 ChromaDB

---

## 十、`api/chat.py`

```python
with open("prompts/answer.md", "r", encoding="utf-8") as f:
    ANSWER_TEMPLATE = f.read()
```
在 **module 載入時**讀一次 prompt 檔案，存成 module-level 變數。不放在 endpoint 裡是因為每次 request 都讀檔案沒必要，讀一次共用就好。

```python
async def ask_document(request: ChatRequest, db: AsyncSession = Depends(get_db)):
```
- `request: ChatRequest`：FastAPI 自動從 POST body 解析成 `ChatRequest` pydantic model
- `db: AsyncSession = Depends(get_db)`：Dependency Injection，FastAPI 自動呼叫 `get_db()` 取得 session

```python
if request.model_provider == ModelProvider.ollama:
    llm = ChatOllama(model="llama3")
else:
    llm = ChatOpenAI(model_name="gpt-4o", temperature=0.2)
```
Factory Pattern：根據請求選擇 LLM 實作。`ChatOpenAI` 和 `ChatOllama` 都實作了 LangChain 的 `BaseChatModel` 介面，之後 `chain` 的呼叫方式完全一樣，不用再判斷。

**為什麼每次 request 都重建 LLM 物件**：多使用者同時使用時，User A 選 OpenAI、User B 選 Ollama，用 global cache 會互相覆蓋。LLM 物件只是 API 客戶端，建立成本很低。

```python
stmt = select(models.ChatHistory).where(
    models.ChatHistory.user_id == request.user_id
).order_by(models.ChatHistory.timestamp.desc()).limit(5)
result = await db.execute(stmt)
history_records = result.scalars().all()
history_records.reverse()
```
- `select(...).where(...).order_by(...).limit(5)`：SQLAlchemy 的 ORM 查詢語法，最終轉成 SQL：`SELECT * FROM chat_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5`
- `.desc()`：降冪排列（最新的在前）
- `.scalars().all()`：把 query result 轉成 Python list
- `.reverse()`：拿到的是最新 5 筆（降冪），reverse 後變成時間順序（讓 LLM 讀到正確的對話脈絡）

```python
chat_history_str = "".join([f"User: {m.user_question}\nAI: {m.ai_response}\n\n" for m in history_records])
```
把對話歷史格式化成字串，拼進 prompt 的 `{chat_history}` 位置。

```python
retriever = vector_db.as_retriever(search_kwargs={"k": 6})
docs = await retriever.ainvoke(request.question)
```
- `as_retriever`：把 ChromaDB 包成 LangChain 的 retriever 介面
- `search_kwargs={"k": 6}`：每次搜尋回傳最相似的 6 個 chunk
- `ainvoke`：async 版的 invoke，內部把問題轉向量，再找最近的 k 個

```python
context_text = "\n\n".join([f"[{d.metadata.get('title', '未知文件')}] {d.page_content}" for d in docs])
```
把 6 個 chunk 格式化成一個字串，每個前面加 `[文件名稱]`，用雙換行分隔，塞進 prompt 的 `{context}`。

```python
sources = list(dict.fromkeys([d.metadata.get("title", "未知文件") for d in docs]))
```
`dict.fromkeys()`：保序去重。
- 為什麼不用 `set()`：set 不保證順序，`dict.fromkeys()` 保留第一次出現的順序
- 結果是去重後的來源清單，回傳給前端顯示「這個答案來自哪些文件」

```python
prompt = ChatPromptTemplate.from_template(ANSWER_TEMPLATE)
chain = prompt | llm | StrOutputParser()
response = await chain.ainvoke({...})
```
LangChain 的 LCEL（LangChain Expression Language）：
- `prompt | llm | StrOutputParser()`：pipe 語法，資料從左到右流
- `prompt`：把 dict 填入 template 的 `{chat_history}`、`{context}`、`{input}`，產生最終 prompt
- `llm`：把 prompt 送給 GPT-4o，拿回 `AIMessage` 物件
- `StrOutputParser()`：把 `AIMessage` 轉成純字串
- `ainvoke`：async 執行整條 chain

```python
new_chat = models.ChatHistory(
    user_id=request.user_id, user_question=request.question, ai_response=response
)
db.add(new_chat)
await db.commit()
```
建立 ORM 物件 → 加進 session → commit 寫入資料庫。

```python
except Exception:
    await db.rollback()
```
如果寫入失敗，rollback 避免資料庫處於不一致狀態。

---

## 十一、`scripts/run_eval.py`

### 為什麼需要 eval harness

改 chunking、換 prompt、加 reranker——怎麼知道改了之後更好還是更差？用感覺判斷不可靠。Eval harness 讓每個改動都有數字可以對比。

### Metrics

| Metric | 量的是什麼 | 輸入 |
|--------|-----------|------|
| Recall@k | 前 k 個結果裡有沒有正確來源 | retrieved titles vs expected titles |
| MRR@k | 正確來源第一次出現在第幾名（倒數） | 同上，看排名 |
| Faithfulness | 回答有沒有依據 context（防幻覺） | context + answer |
| Answer Relevance | 回答有沒有真的回應問題 | question + answer |

### 程式碼解釋

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```
把專案根目錄加進 Python 的 module 搜尋路徑。`__file__` 是當前腳本的路徑，`dirname` 兩層往上是根目錄。沒有這行，`from services.rag_core import vector_db` 會找不到 module。

```python
with open("prompts/answer.md", "r", encoding="utf-8") as f:
    answer_chain = ChatPromptTemplate.from_template(f.read()) | llm | StrOutputParser()
```
讀 prompt 檔案 + 建 chain，一行完成。`with` 確保檔案讀完後自動關閉。

```python
async def get_answer(context, question):
    return await answer_chain.ainvoke({
        "chat_history": "",
        "context": context,
        "input": question,
    })
```
- `chat_history` 給空字串：eval 每題獨立，不需要對話歷史
- `await`：等 OpenAI API 回應，這是 I/O 等待，所以用 async

```python
recall_hits = []
reciprocal_ranks = []
```
`recall_hits`：每題是否命中（True/False）的 list
`reciprocal_ranks`：每題的 reciprocal rank（1/rank）的 list

```python
hit = any(t in retrieved_titles for t in q["expected_source_titles"])
```
`any()`：只要 expected titles 裡有任何一個出現在 retrieved titles 就算命中。`for t in q["expected_source_titles"]` 是 generator expression，惰性求值，找到第一個就停。

```python
rr = 0
for i, title in enumerate(retrieved_titles):
    if title in q["expected_source_titles"]:
        rr = 1 / (i + 1)
        break
```
- 預設 0（找不到）
- `enumerate` 同時取 index 和值
- `i + 1`：`enumerate` 從 0 開始，rank 從 1 開始，所以 +1
- `break`：MRR 只關心第一個符合的位置，找到就停

```python
answer = asyncio.run(get_answer(context, q["question"]))
```
`asyncio.run()`：在 sync 環境執行 async function 的標準做法，內部建一個 event loop 跑一次再關掉。eval 腳本是 sync 的（沒有 `async def`），所以用這個。

```python
faithfulness_scores.append(float(asyncio.run(get_faithfulness(context, answer)).strip()))
```
- `get_faithfulness` 回傳字串（如 `"0.85"`）
- `.strip()`：移除可能的頭尾空白或換行
- `float()`：轉成浮點數才能做 `sum()`

```python
time.sleep(3)
```
OpenAI API 有 rate limit（每分鐘 token 上限）。每題之間等 3 秒避免 429 錯誤。

---

## 十二、Prompts

### `prompts/answer.md`

```
根據以下提供的【參考文件】內容...
【歷史對話紀錄】{chat_history}
【參考文件】{context}
Question: {input}
```
`{chat_history}`、`{context}`、`{input}` 是 placeholder，`ChatPromptTemplate.from_template()` 讀到這個檔案後，在 `ainvoke({"chat_history": ..., "context": ..., "input": ...})` 時自動替換。

### `prompts/judge_faithfulness.md`

```
Context: {context}
Answer: {answer}
請判斷 Answer 中每個聲明是否在 Context 中有依據...
只回傳 0.0 到 1.0 的數字
```
Judge prompt 只在 eval 裡用，不在 production 裡出現。Judge 不需要知道問題是什麼，只看 context 和 answer 的一致性。

### `prompts/judge_relevance.md`

```
Question: {question}
Answer: {answer}
請判斷 Answer 是否真的回答了 Question...
```
Relevance 不需要 context，只看問題和回答的對應關係。一個有依據但答非所問的回答，faithfulness 高但 relevance 低。

---

## 十三、關鍵概念整理

### Embedding 是什麼

把文字轉成一個數字向量（1536 個浮點數）。語意相似的文字，它們的向量在高維空間裡距離很近。ChromaDB 的 `similarity_search` 就是在高維空間裡找「距離最近的 k 個向量」。

### 為什麼換 Embedding 模型需要重建整個索引

現有的向量是用 `text-embedding-3-small` 算的。如果換成另一個 embedding 模型，問題會用新模型轉成向量，但資料庫裡存的是舊模型的向量——兩個「語言」不同，similarity search 結果會亂。所以換模型就要重新把所有文件 embed 一遍。

### LLM 是無狀態的

每次呼叫 GPT-4o API 對它來說都是全新的，它完全不記得上一次對話。DocuMind 的「記憶」是假的——每次從 PostgreSQL 撈最近 5 筆歷史，拼成字串塞進 prompt，讓 LLM「看到」歷史。

### Faithfulness vs Relevance vs Correctness

- **Faithfulness**：回答有沒有依據 context（context ↔ answer）
- **Relevance**：回答有沒有回應問題（question ↔ answer）
- **Correctness**：回答跟 ground truth 一不一樣（answer ↔ expected_answer）——我們目前沒實作這個，因為它需要 semantic similarity 或 LLM 比對，比前兩個複雜

### dict.fromkeys() 保序去重

```python
list(dict.fromkeys(["A", "B", "A", "C"]))  # → ["A", "B", "C"]
```
`set()` 去重但不保序，`dict.fromkeys()` 保留第一次出現的順序。Sources 清單用這個是因為順序代表相關程度（最相關的 chunk 排前面）。

### Dependency Injection

FastAPI 的 `Depends(get_db)` 讓你把「取得資源」的邏輯抽出來，endpoint 只宣告「我需要一個 db session」，FastAPI 負責建立和回收。好處是所有 endpoint 共用同一套 session 管理邏輯，不用各自寫。

---

## 十四、面試可能被問的問題

**Q: RAG 跟直接把文件塞進 prompt 有什麼差別？**
A: 直接塞全文的問題：文件太長超過 token 上限、token 費用貴、LLM 讀長 context 容易漏掉重點。RAG 只送最相關的幾段，省 token 又讓 LLM focus 在對的地方。

**Q: ChromaDB 和 PostgreSQL 各存什麼？**
A: ChromaDB 存向量（chunks 的 embedding）和對應的文字/metadata，用來做相似度搜尋。PostgreSQL 存對話歷史（chat_history table），用來做 SQL 查詢和持久化對話記憶。

**Q: 為什麼 chunk 要 overlap？**
A: 避免一個句子或概念被切在兩個 chunk 的邊界，50 字的重疊讓前後 chunk 都包含邊界的語意。

**Q: 你怎麼評估 RAG 系統的品質？**
A: 兩層：Retrieval（Recall@k、MRR，量能不能找到對的文件、排名高不高）和 Answer（Faithfulness 量有沒有幻覺、Answer Relevance 量有沒有答非所問），用 GPT-4o 當 LLM-as-judge。

**Q: 如果 faithfulness 很低代表什麼？**
A: LLM 回答的內容在 retrieved context 裡找不到依據，可能是 LLM 用了自身知識在「幻覺」，或 retrieved context 根本和問題無關。要去看那次的 trace 才能判斷哪一步出問題。

**Q: async/await 是什麼，為什麼 FastAPI 用 async？**
A: async 讓程式在等待 I/O（資料庫查詢、API 呼叫）時不卡住，可以先去處理其他 request。FastAPI 是高並發 web server，如果用同步 I/O，每個 request 在等 DB 的期間，其他 request 都要排隊等。
