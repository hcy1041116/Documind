# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DocuMind is an enterprise RAG (Retrieval-Augmented Generation) document Q&A system. Users upload PDFs, which are chunked and embedded into ChromaDB. Questions are answered using retrieved context plus PostgreSQL-persisted conversation history, via OpenAI's GPT-4o.

## Running the Project

**Backend** (Python 3.12, from repo root):
```bash
uv sync                        # install dependencies
uvicorn main:app --reload      # starts on http://127.0.0.1:8000
```

**Frontend** (from `frontend/`):
```bash
npm install
npm run dev     # dev server at http://localhost:5173
npm run build   # production build
```

**Prerequisites**:
- PostgreSQL on localhost:5432 with database `documind_db`, user `documind_user`, password `documind_pass`
- `.env` file with `OPENAI_API_KEY=...`

**Test ChromaDB vector store**:
```bash
python test.py
```

## Architecture

### Request Flow

1. **Document upload** → `POST /api/document/upload/bulk`
   - PDFs saved to `uploads/`, parsed by LangChain `PyPDFLoader`
   - Split into 500-char chunks (50-char overlap) by `RecursiveCharacterTextSplitter`
   - Embedded via OpenAI `text-embedding-3-small`, stored in ChromaDB collection `documind_law`

2. **Chat** → `POST /api/chat/ask`
   - Retrieves last 5 messages for `user_id` from PostgreSQL
   - Semantic search retrieves top 3 relevant chunks from ChromaDB
   - GPT-4o (`temperature=0`) generates answer from history + document context
   - Q&A pair persisted to PostgreSQL `chat_history` table

### Module Layout

| Path | Role |
|------|------|
| `main.py` | FastAPI app: lifespan (DB connect/disconnect), CORS, router mounting |
| `database.py` | Async SQLAlchemy engine + session factory for PostgreSQL |
| `models.py` | `ChatHistory` ORM model |
| `schemas.py` | Pydantic schemas: `ChatRequest`, `ChatTestRequest` |
| `api/chat.py` | Chat endpoints with memory retrieval |
| `api/document.py` | Upload and stats endpoints |
| `services/rag_core.py` | Shared singletons: `embeddings`, `llm`, `chroma_client`, `text_splitter` |
| `frontend/src/App.tsx` | Single-component React UI: chat interface + file upload |

### Data Stores

- **PostgreSQL**: `chat_history` table — stores `user_id`, `question`, `response`, `timestamp`
- **ChromaDB**: Persistent vector store in `chromadb_data/`, collection `documind_law`
- **File system**: Raw PDFs in `uploads/`

## Key Configuration

- LLM: `gpt-4o`, temperature=0
- Embeddings: `text-embedding-3-small` (1536 dims)
- Chunk size: 500 chars, overlap: 50
- Conversation memory window: last 5 messages
- CORS: allows all origins (development setup)
- DB URL hardcoded in `database.py` — override via env if needed
