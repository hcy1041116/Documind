English | [中文](DESIGN-zh-TW.md)

# DocuMind v2 — System Design

> Status: Draft v1 · 2026-05-18
> Scope: Engineering plan for evolving from v1 (current `main`) to v2

---

## 0. Background

DocuMind is an enterprise document Q&A system. Users upload PDFs; the system chunks and embeds them into a vector store, then answers questions via RAG with conversation history.

v1 is functional but has structural gaps that make iteration difficult:

| Problem | Impact |
|---------|--------|
| No evaluation harness | Any change (chunking, reranker, prompt) is a guess |
| Prompts and retriever params hardcoded | A/B comparison requires touching source code |
| No observability | Can't see what was retrieved or what tokens were spent |
| Linear pipeline | Query rewriting, multi-hop, and tool use require a full rewrite |

**v2 goal**: make the system engineerably iterable — measure first, then upgrade; trace first, then go agentic.

---

## 1. Architecture (v1 baseline)

### Request flow

```
PDF upload                          User question
     │                                    │
     ▼                                    ▼
PyPDFLoader                     Fetch last 5 msgs from PostgreSQL
     │                                    │
     ▼                                    ▼
RecursiveCharacterTextSplitter   ChromaDB.similarity_search(k=6)
  chunk=500 / overlap=50               │
     │                                    ▼
     ▼                           Build prompt (history + context)
Write metadata.title                     │
  (first line of page 1)                 ▼
     │                           GPT-4o (temp=0.2)
     ▼                                   │
ChromaDB (collection: documind_law)      ▼
                              Answer + deduplicated sources
                                         │
                                         ▼
                              Persist to PostgreSQL chat_history
```

### Tech stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Vector store | ChromaDB (persisted) | Keeping |
| Conversation history | PostgreSQL (Docker) | Keeping |
| Embeddings | `text-embedding-3-small` (1536d) | May evaluate BGE-M3 / multilingual-e5 |
| LLM | GPT-4o or Ollama llama3 | Ollama deprioritized, UI toggle kept |
| Backend | FastAPI + LangChain 1.x | |
| Frontend | React 19 + Vite + Tailwind | Not touching in v2 |

### Known issues (v1 audit)

1. **No eval harness** — highest priority fix
2. **`sources` uses `set()`** → non-deterministic order, traces don't match source text
3. **chunk_size=500 is too small for Chinese text**; no reranker; k=6 causes fragmentation
4. **`metadata["title"]` takes first 40 chars of page 1** → breaks when cover is an image or logo
5. **`langchain_community.vectorstores.Chroma` is deprecated** → migrate to `langchain_chroma`
6. **No structured logging or tracing**
7. **Prompts hardcoded** in `api/chat.py`
8. **CORS fully open, `user_id` hardcoded** as `guest_user`

---

## 2. Goals

**Primary**: transform DocuMind from a working demo into a system that can be iterated with engineering discipline.

**Explicitly out of scope**:
- SOTA RAG benchmarks (personal project, not research)
- Frontend rewrite
- Multi-tenancy (Phase F at earliest)
- LangSmith (LangFuse self-host preferred)

**Definition of done**:
- After Phase A: any PR can run `make eval` and get retrieval + answer quality numbers
- After Phase D: complex queries (multi-hop, requiring query rewrite) measurably outperform v1
- Throughout: every chat has a full trace visible in LangFuse

---

## 3. Phased Roadmap

### Phase A — Evaluation Harness

**Why first**: upgrading RAG without a yardstick is guesswork. Every Phase B–D change needs a number to justify itself.

| Artifact | Description | Status |
|----------|-------------|--------|
| `evals/dataset.jsonl` | 20–50 QA pairs with `question`, `expected_answer`, `expected_source_titles`, `difficulty` | ✅ 13 questions |
| `prompts/judge.md` | Faithfulness judge prompt (GPT-4o) | ✅ done |
| `scripts/run_eval.py` | Retrieval metrics (Recall@k, MRR) + LLM-as-judge faithfulness · CSV + console summary | 🔄 retrieval + faithfulness done; answer relevance + CSV pending |
| `docs/eval_baseline.md` | v1 baseline numbers | ⬜ pending |

Dataset covers three difficulty tiers: single-hop factual, multi-passage synthesis, and ambiguous queries requiring rewrite. Judge model: GPT-4o prompt-based (no Ragas dependency yet).

**Done when**: `uv run python scripts/run_eval.py` completes and prints both score groups; traces visible in LangFuse.

---

### Phase B — Observability *(parallel with Phase A tail)*

1. LangFuse self-host via Docker Compose
2. Callback handler in `services/rag_core.py` — every retrieve and LLM call logged
3. Extract prompts from `api/chat.py` → `prompts/answer.md`
4. Structured logging with `structlog` (JSON output)
5. **Cost & latency as first-class metrics** — token usage per request, per-node duration, p50/p95 latency. LangFuse captures these by default; surface them in every eval report alongside quality scores.

**Why parallel with A**: eval scores alone can't tell you where a query failed (bad retrieval? LLM ignored context?). Traces are needed to debug, not just measure.

---

### Phase C — RAG Improvements *(after Phase A baseline)*

Each item is an independent PR; each PR runs `make eval` and logs the delta in `docs/eval_log.md`.

| Item | Expected gain | Priority |
|------|--------------|----------|
| Metadata fallback | Correctness fix | 1st — cheap, no eval needed |
| Reranker (BGE-reranker-base or Cohere rerank-3) | Context precision ↑ | 2nd — highest ROI |
| Chunking (500 → 800–1000, overlap 50 → 100; try SemanticChunker) | Recall ↑ for long Chinese text | 3rd |
| Hybrid search (ChromaDB dense + BM25 sparse, RRF fusion) | Recall ↑ on proper nouns | 4th |
| Embedding swap (BGE-M3 / multilingual-e5) | Chinese benchmark ↑ | Last — requires full index rebuild |

---

### Phase D — Agentic Pipeline (LangGraph)

*Prerequisite: Phase C reranker + metadata done.*

Replace the linear pipeline with a state machine that can plan, rewrite queries, and loop:

```
┌─────────────┐
│  classify   │──── small talk ────► direct answer
│ (needs RAG?)│
└──────┬──────┘
       │ needs RAG
       ▼
┌─────────────┐
│   rewrite   │  reformulate colloquial query → retrieval-friendly
└──────┬──────┘  (with conversation history)
       ▼
┌─────────────┐
│  retrieve   │  hybrid search + rerank
└──────┬──────┘
       ▼
┌─────────────┐  insufficient  ┌──────────────┐
│    judge    │───────────────►│ refine query │
│ enough ctx? │                └──────┬───────┘
└──────┬──────┘                       │
       │ sufficient                    │
       ▼                               │
┌─────────────┐                        │
│   answer    │◄───────────────────────┘
└─────────────┘
```

**Why LangGraph over CrewAI**: LangGraph is a state machine — debuggable, traceable, integrates well with LangFuse. CrewAI targets multi-role collaboration; DocuMind is single-objective QA.

Old linear pipeline stays as `?mode=simple` fallback for regression testing.

---

### Phase E — MCP Integration

Wrap DocuMind as an MCP server so Claude Desktop and other MCP clients can call:
- `documind_search(query)` → retrieved chunks
- `documind_ask(question)` → full answer + citations

*Prerequisite: Phase D stable. Packaging an unstable core exposes instability.*

---

### Phase F — Production Hardening *(optional)*

JWT auth, rate limiting, CORS restriction, env-driven DB URL, upload size limits, PDF parse timeouts.

---

## 4. Quick Wins (before Phase A)

Five changes, each under 30 minutes, that unblock all later phases:

1. `api/chat.py`: replace `set(sources)` with order-preserving dedup
2. `test.py`: add `from services.rag_core import vector_db`
3. `services/rag_core.py`: `langchain_community.vectorstores.Chroma` → `langchain_chroma.Chroma`
4. `api/document.py`: three-tier title fallback — filename → PDF metadata → first-line heuristic
5. Extract prompt string from `api/chat.py` → `prompts/answer.md`

---

## 5. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Eval dataset too small → noisy scores | Min 20 questions; LLM-as-judge averaged over 3 runs |
| LangFuse self-host fails to start | Fallback: LangFuse cloud free tier |
| LangGraph learning curve | Build a toy graph before touching production code |
| Reranker latency too high | Use BGE-reranker-base (small) or Cohere API; skip `large` variant |
| Embedding swap requires full index rebuild | Eval delta first; dual-write during transition |

---

## 6. Non-Goals

- ❌ Replace ChromaDB
- ❌ Rewrite frontend
- ❌ Optimize Ollama path
- ❌ Multi-tenancy
- ❌ Fine-tune embedding model or LLM
- ❌ LangSmith
- ❌ CrewAI
