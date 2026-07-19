"""CRAG（Corrective RAG）state machine，用 LangGraph 官方範例架構改的。

流程：
    retrieve → grade_documents ──correct/ambiguous──► generate
                     │
                 incorrect（0 個 chunk 被判相關）
                     ▼
              transform_query → web_search → generate

跟 api/chat.py 的 /ask（純線性 pipeline）不同，這裡多了一個「評分」步驟去判斷
內部檢索到的內容夠不夠回答問題，不夠才觸發外部搜尋（Tavily MCP），而不是每次
都無腦相信 reranker 的分數——今天發現的「reranker 對不相關法條打高分」那個 bug
就是靠這個評分步驟去擋。

只有 grade 是 incorrect（撈回來的 chunk 沒有任何一個被判相關）才會去查外部；
ambiguous（部分相關）直接用篩選過的相關 chunk 生成答案，不額外查——CRAG 論文
原始設計是 ambiguous 也要內部+外部一起用，但實測下來 reranker 撈回來的東西
很少每個都 100% 精準，這樣做幾乎每次都會多觸發一次 web search，成本划不來，
所以改成比較保守的版本。
"""
import asyncio
import os
from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import StateGraph, START, END

from services.rag_core import get_hybrid_retriever, rerank_documents

with open("prompts/answer.md", "r", encoding="utf-8") as f:
    ANSWER_TEMPLATE = f.read()

grade_llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0)
rewrite_llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0)
answer_llm = ChatOpenAI(model_name="gpt-4o", temperature=0.2)


class CRAGState(TypedDict):
    question: str
    chat_history: str
    documents: list[Document]
    grade: str  # "correct" | "incorrect" | "ambiguous"
    search_query: str
    web_results: list[Document]
    answer: str
    sources: list[str]


# ── MCP tool（Tavily 搜尋）──────────────────────────────────────────
_tavily_search_tool = None


async def _get_tavily_search_tool():
    """惰性初始化：第一次真的要用到 web search 時才連 MCP server，
    避免每次啟動都要 spawn npx process。"""
    global _tavily_search_tool
    if _tavily_search_tool is None:
        client = MultiServerMCPClient({
            "tavily": {
                "command": "npx",
                "args": ["-y", "tavily-mcp@latest"],
                "transport": "stdio",
                "env": {"TAVILY_API_KEY": os.environ["TAVILY_API_KEY"]},
            }
        })
        tools = await client.get_tools()
        _tavily_search_tool = next(t for t in tools if t.name == "tavily_search")
    return _tavily_search_tool


def _extract_text(mcp_result) -> str:
    """MCP tool 回傳的是一包 content block（list of dict），把文字部分接出來。"""
    if isinstance(mcp_result, str):
        return mcp_result
    if isinstance(mcp_result, list):
        parts = []
        for block in mcp_result:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(mcp_result)


# ── 節點 ────────────────────────────────────────────────────────────

async def retrieve_node(state: CRAGState, config: RunnableConfig) -> dict:
    retriever = get_hybrid_retriever(k=15)
    candidates = await retriever.ainvoke(state["question"], config=config)
    docs = rerank_documents(state["question"], candidates, k=6)
    return {"documents": docs}


GRADE_PROMPT = ChatPromptTemplate.from_template(
    "你是嚴格的檢索品質評分員。判斷下面這段文件內容是否「明確」回答了使用者的問題。\n"
    "只要主題相關、但沒有直接給出答案，也算不相關——寧可嚴格。\n\n"
    "問題：{question}\n\n"
    "文件內容：\n{content}\n\n"
    "只回答一個字：「是」或「否」，不要其他文字。"
)


async def grade_documents_node(state: CRAGState, config: RunnableConfig) -> dict:
    docs = state["documents"]
    if not docs:
        return {"grade": "incorrect", "documents": []}

    grader = GRADE_PROMPT | grade_llm | StrOutputParser()
    verdicts = await asyncio.gather(*[
        grader.ainvoke({"question": state["question"], "content": d.page_content}, config=config)
        for d in docs
    ])
    relevant_docs = [d for d, v in zip(docs, verdicts) if "是" in v]

    if len(relevant_docs) == 0:
        grade = "incorrect"
    elif len(relevant_docs) == len(docs):
        grade = "correct"
    else:
        grade = "ambiguous"

    return {"grade": grade, "documents": relevant_docs}


REWRITE_PROMPT = ChatPromptTemplate.from_template(
    "把下面這個問題改寫成適合丟進搜尋引擎的關鍵字組合：去掉口語贅字（例如「請問」「想知道」），"
    "保留專有名詞、法規名稱、條號。只回傳改寫後的關鍵字，不要加任何說明或標點符號包裝。\n\n"
    "問題：{question}"
)


async def transform_query_node(state: CRAGState, config: RunnableConfig) -> dict:
    chain = REWRITE_PROMPT | rewrite_llm | StrOutputParser()
    rewritten = await chain.ainvoke({"question": state["question"]}, config=config)
    return {"search_query": rewritten.strip()}


async def web_search_node(state: CRAGState, config: RunnableConfig) -> dict:
    search_tool = await _get_tavily_search_tool()
    query = state.get("search_query") or state["question"]
    raw = await search_tool.ainvoke({"query": query}, config=config)
    text = _extract_text(raw)
    web_doc = Document(page_content=text, metadata={"title": "網路搜尋結果（非內部文件庫）"})
    return {"web_results": [web_doc]}


async def generate_node(state: CRAGState, config: RunnableConfig) -> dict:
    docs = state["documents"] + state.get("web_results", [])
    context_text = "\n\n".join(f"[{d.metadata.get('title', '未知文件')}] {d.page_content}" for d in docs)
    sources = list(dict.fromkeys(d.metadata.get("title", "未知文件") for d in docs))

    prompt = ChatPromptTemplate.from_template(ANSWER_TEMPLATE)
    chain = prompt | answer_llm | StrOutputParser()
    answer = await chain.ainvoke({
        "chat_history": state.get("chat_history", ""),
        "context": context_text,
        "input": state["question"],
    }, config=config)
    return {"answer": answer, "sources": sources}


def _route_after_grading(state: CRAGState) -> str:
    # 只有「完全沒有相關 chunk」才觸發 web search；ambiguous（部分相關）直接
    # 用篩選過的 relevant_docs 生成答案，避免每次 reranker 撈到一個不夠精準的
    # chunk 就多花一次 web search 的時間和 API 成本。
    return "transform_query" if state["grade"] == "incorrect" else "generate"


# ── 組裝 graph ──────────────────────────────────────────────────────

def build_crag_graph():
    graph = StateGraph(CRAGState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("grade_documents", grade_documents_node)
    graph.add_node("transform_query", transform_query_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("generate", generate_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "grade_documents")
    graph.add_conditional_edges(
        "grade_documents",
        _route_after_grading,
        {"generate": "generate", "transform_query": "transform_query"},
    )
    graph.add_edge("transform_query", "web_search")
    graph.add_edge("web_search", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


crag_graph = build_crag_graph()
