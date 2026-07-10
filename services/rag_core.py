import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.documents import Document
from flashrank import Ranker, RerankRequest

load_dotenv()

# 1. 初始化模型
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")


# 2. 初始化 ChromaDB
CHROMA_PATH = "chromadb_data"
vector_db = Chroma(
    collection_name="documind_law",
    embedding_function=embeddings,
    persist_directory=CHROMA_PATH
)

# 3. 設定切塊器
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separators=["\n\n", "\n", "。", "！", "？", "，", " ", ""]
)

# 4. Hybrid Search：BM25（關鍵字）+ 向量（語意）
_bm25_retriever: BM25Retriever | None = None


def refresh_bm25_index() -> None:
    """把 ChromaDB 裡目前所有的 chunk 重新拉出來建一份 BM25 索引。
    BM25 是關鍵字比對，沒有增量更新的機制，只能整包重建；
    在每次上傳文件、資料庫內容變動後呼叫一次即可。
    """
    global _bm25_retriever
    data = vector_db._collection.get(include=["documents", "metadatas"])
    docs = [
        Document(page_content=content, metadata=meta)
        for content, meta in zip(data["documents"], data["metadatas"])
    ]
    _bm25_retriever = BM25Retriever.from_documents(docs) if docs else None


def get_hybrid_retriever(k: int = 6):
    """回傳向量檢索 + BM25 關鍵字檢索的 Ensemble Retriever（各半權重）。
    向量檢索抓語意相近的內容，BM25 抓精確關鍵字（例如法規條號、專有名詞）；
    兩邊各自取分數最高的結果再依權重合併排序。
    """
    vector_retriever = vector_db.as_retriever(search_kwargs={"k": k})

    if _bm25_retriever is None:
        refresh_bm25_index()

    if _bm25_retriever is None:
        return vector_retriever

    _bm25_retriever.k = k
    return EnsembleRetriever(retrievers=[vector_retriever, _bm25_retriever], weights=[0.5, 0.5])


# 5. Reranking：本地跑輕量 cross-encoder，把 Hybrid Search 撈出來的候選重新排序
# 用 flashrank 而不是 Cohere/OpenAI 的 rerank API，是因為不用額外的 API key、不用付費、
# 模型（ONNX，多語言）跑在本機 CPU 就夠快，適合這個規模的專案。
_reranker = Ranker(model_name="ms-marco-MultiBERT-L-12", cache_dir=".flashrank_cache")


def rerank_documents(query: str, docs: list[Document], k: int = 6) -> list[Document]:
    if not docs:
        return docs

    passages = [{"id": i, "text": d.page_content} for i, d in enumerate(docs)]
    results = _reranker.rerank(RerankRequest(query=query, passages=passages))
    ordered_ids = [r["id"] for r in results]
    return [docs[i] for i in ordered_ids[:k]]