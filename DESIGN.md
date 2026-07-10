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
- LangSmith (using LangFuse instead; self-host was tried, later switched to LangFuse Cloud)

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
| `evals/dataset.jsonl` | 20–50 QA pairs with `question`, `expected_answer`, `expected_source_titles`, `difficulty` | ✅ 15 questions (expanded 2026-07-11 with QA-document-sourced questions and multi-source labels) |
| `prompts/judge_faithfulness.md` / `judge_relevance.md` | Hand-rolled judge prompts (GPT-4o) | ⚠️ Superseded by RAGAS's built-in judges; files remain but are currently unused |
| ~~`scripts/run_eval.py`~~ | Recall@k, MRR, faithfulness, relevance | 🗄️ Archived, replaced by the row below |
| `scripts/RAGAS.py` | Migrated to the RAGAS framework: Faithfulness, Answer Relevancy, Context Recall, Context Precision | ✅ done (mid-2026 migration), ⚠️ but has known reliability issues — long runs hit connection failures and some scores come back missing; see internal notes |
| `notes/eval_baseline.md` | v1 baseline (single-document setup) — Recall 1.00 / MRR 1.00 / Faithfulness 0.92 / Relevance 0.92 | ✅ done (local, gitignored); this baseline predates the current RAGAS pipeline and multi-document setup |

Dataset covers three difficulty tiers: single-hop factual, multi-passage synthesis, and ambiguous queries requiring rewrite. Judge model: migrated to the RAGAS framework (replacing the original hand-rolled prompt-based judge).

**Done when**: `uv run python scripts/RAGAS.py` completes and prints all four score groups; traces visible in LangFuse.

---

### Phase B — Observability *(parallel with Phase A tail)* ✅ mostly done

1. ~~LangFuse self-host via Docker Compose~~ → ✅ switched to LangFuse Cloud (self-host container still exists locally but is stopped/unused)
2. ✅ Callback handler in `services/rag_core.py`/`api/chat.py` — every retrieve and LLM call logged
3. ✅ Extract prompts from `api/chat.py` → `prompts/answer.md`
4. ⬜ Structured logging with `structlog` (JSON output) — not done
5. ⬜ **Cost & latency as first-class metrics** — not done. LangFuse captures these by default, but they haven't been surfaced in eval reports alongside quality scores yet.

**Why parallel with A**: eval scores alone can't tell you where a query failed (bad retrieval? LLM ignored context?). Traces are needed to debug, not just measure.

---

### Phase C — RAG Improvements *(after Phase A baseline)*

Each item is an independent PR; each PR runs `make eval` and logs the delta in `docs/eval_log.md`.

| Item | Expected gain | Priority | Status |
|------|--------------|----------|--------|
| Metadata fallback | Correctness fix | 1st — cheap, no eval needed | ✅ done (2026-07-10, three-tier fallback: PDF metadata → first line → filename) |
| Reranker (originally planned: BGE-reranker-base or Cohere rerank-3) | Context precision ↑ | 2nd — highest ROI | ✅ done (2026-07-10, actually used flashrank — a local multilingual cross-encoder, no API key needed) |
| Chunking (500 → 800–1000, overlap 50 → 100; try SemanticChunker) | Recall ↑ for long Chinese text | 3rd | ⬜ not done — closely related to a known issue with two-column "Q/A" layout PDFs causing bad chunk boundaries (see Backlog in `notes/todo.md`) |
| Hybrid search (ChromaDB dense + BM25 sparse, RRF fusion) | Recall ↑ on proper nouns | 4th | ✅ done (2026-07-10, `EnsembleRetriever`, vector + BM25) |
| Embedding swap (BGE-M3 / multilingual-e5) | Chinese benchmark ↑ | Last — requires full index rebuild | ⬜ not done |

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

## 4. Quick Wins (before Phase A) ✅ all done

Five changes, each under 30 minutes, that unblock all later phases:

1. ✅ `api/chat.py`: replace `set(sources)` with order-preserving dedup
2. ✅ `test.py`: add `from services.rag_core import vector_db`
3. ✅ `services/rag_core.py`: `langchain_community.vectorstores.Chroma` → `langchain_chroma.Chroma`
4. ✅ `api/document.py`: three-tier title fallback (actual order ended up: PDF metadata → first-line heuristic → filename, slightly different from the original plan)
5. ✅ Extract prompt string from `api/chat.py` → `prompts/answer.md`

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
