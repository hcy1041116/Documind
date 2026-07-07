# DocuMind Product Requirements Document

**Version**: 1.0  
**Author**: HCY  
**Status**: In Progress  
**Last Updated**: 2026-06

---

## 1. Background & Problem Statement

### 1.1 Context

Enterprise employees increasingly rely on internal documents — compliance manuals, regulation PDFs, technical specs — to do their jobs. In regulated industries such as medical devices and finance, these documents are dense, frequently updated, and legally consequential.

**The current workflow is broken:**

- Employees spend 20–40 minutes searching through 50–200 page PDFs to find one relevant clause
- Search-by-keyword misses semantically related content
- Asking a colleague "where does it say X" creates interruptions and is not scalable
- No one reads compliance documents proactively; they react to audits

### 1.2 Problem Statement

> Knowledge workers cannot efficiently extract specific answers from large internal document repositories, leading to wasted time, compliance risk, and decision-making delays.

### 1.3 Why Now

- LLM-based RAG (Retrieval-Augmented Generation) has become production-ready in 2024–2025
- Enterprise demand for internal knowledge Q&A is accelerating
- OpenAI's embedding APIs have reduced the cost of semantic search to near-zero
- There is no lightweight, self-hostable RAG tool suited for SMEs in regulated industries

---

## 2. Goals & Non-Goals

### Goals

| # | Goal | Success Metric |
|---|------|----------------|
| G1 | Reduce time to find a specific answer in a document | < 30 seconds per query vs. 20+ min manual |
| G2 | Support multi-document knowledge bases | Users can upload and query across 10+ PDFs |
| G3 | Maintain answer faithfulness to source material | Faithfulness score ≥ 0.85 (RAGAS) |
| G4 | Work with real-world enterprise PDFs including protected files | OCR fallback handles copy-protected PDFs |

### Non-Goals

- This is not a document management system (no version control, access permissions — Phase F)
- This is not a general-purpose chatbot (answers are grounded in uploaded documents only)
- This is not a multi-tenant SaaS product at launch (single-org deployment)

---

## 3. User Stories

| ID | As a... | I want to... | So that... | Priority |
|----|---------|--------------|------------|----------|
| US-01 | Compliance Officer | Upload multiple PDFs at once | I can build a complete knowledge base in one step | Must Have |
| US-02 | Any user | Ask a question in natural language | I get a direct answer without reading the full document | Must Have |
| US-03 | Any user | See which document the answer came from | I can verify the source and cite it in my work | Must Have |
| US-04 | Any user | Ask follow-up questions in the same session | I can dig deeper without repeating context | Should Have |
| US-05 | Admin | Upload copy-protected PDFs and still get answers | Regulated-industry documents are often DRM-protected | Should Have |
| US-06 | Any user | Switch between AI models (cloud vs. local) | I can control cost and data privacy as needed | Could Have |
| US-07 | Admin | See how many documents and chunks are indexed | I know the current state of the knowledge base | Could Have |

---

## 4. Feature Requirements

### 4.1 Document Ingestion (Must Have)

| Requirement | Detail |
|-------------|--------|
| Multi-file upload | Accept multiple PDFs in a single request |
| Text extraction | PyMuPDF parser; fallback to OCR (Tesseract) for copy-protected or image-based PDFs |
| Chunking | 500-char chunks, 50-char overlap, Chinese-aware separators |
| Metadata tagging | Each chunk tagged with source filename and extracted title |
| Embedding | OpenAI `text-embedding-3-small` (1536 dims), stored in ChromaDB |

**Constraint discovered in development**: Government and compliance PDFs frequently use owner-password DRM that blocks text extraction. Standard PDF parsers return near-empty content silently. Solution: detect low char-per-page ratio (< 100) and route to OCR pipeline automatically.

### 4.2 Question Answering (Must Have)

| Requirement | Detail |
|-------------|--------|
| Semantic retrieval | Top-6 chunks retrieved by cosine similarity |
| Conversation memory | Last 5 exchanges stored in PostgreSQL, injected into prompt |
| Answer grounding | System prompt instructs model to answer only from retrieved context |
| Source citation | Response includes list of source document titles |
| LLM options | GPT-4o (default) or Ollama local model (toggle via UI) |

### 4.3 Observability (Should Have)


| Requirement | Detail |
|-------------|--------|
| Trace logging | Every retrieval and LLM call traced in LangFuse |
| Eval pipeline | RAGAS-based eval script; measures Faithfulness, Answer Relevancy, Context Recall, Context Precision |

---

### 4.4 Planned Features (Next Phase)

| Feature | Product Requirement | Priority |
|---------|-------------------|----------|
| Hybrid retrieval | Support exact keyword matching alongside semantic search; improves accuracy for regulation article numbers and proper nouns | Should Have |
| Relevance reranking | Re-score retrieved results before generating answer; reduces noise in context window | Should Have |
| Automated eval quality gate | Block deployments when answer quality drops below defined thresholds; prevent silent regressions | Should Have |
| Agentic query handling | Detect ambiguous queries and automatically rewrite them before retrieval; improves multi-hop question performance | Could Have |

---

## 5. Technical Constraints & Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector store | ChromaDB (self-hosted) | No external API dependency; easy local dev |
| Embedding model | text-embedding-3-small | Cost-effective; 1536 dims sufficient for document QA |
| LLM | GPT-4o (temperature=0.2) | Best reasoning quality for compliance context; low temp reduces hallucination |
| Database | PostgreSQL | Reliable async ORM; conversation history is relational data |
| Chunking | RecursiveCharacterTextSplitter | Respects Chinese sentence boundaries; preserves semantic units |

---

## 6. Out of Scope (v1)

- User authentication and role-based access control
- Document versioning or update tracking
- Multi-language UI
- Real-time document monitoring (auto-ingest on file change)
- Answer correctness scoring against ground truth (requires labelled dataset expansion)

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Answer Faithfulness | ≥ 0.85 | RAGAS eval on test set |
| Context Recall | ≥ 0.80 | RAGAS eval on test set |
| Query latency (p50) | < 5 seconds | LangFuse trace latency |
| Upload success rate | ≥ 95% (incl. protected PDFs) | Upload API response logs |
| Eval regression gate | No metric drops > 5% vs. baseline | CI/CD pipeline (planned) |
