from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from database import get_db
import models
from services.rag_core import get_hybrid_retriever, rerank_documents
from services.observability import get_langfuse_handler
from schemas import ChatRequest, ChatTestRequest, ModelProvider


router = APIRouter(prefix="/api/chat", tags=["Chat"])
with open("prompts/answer.md", "r", encoding="utf-8") as f:
    ANSWER_TEMPLATE = f.read()

@router.post("/ask")
async def ask_document(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    try:
        if request.model_provider == ModelProvider.ollama:
            llm = ChatOllama(model = "llama3")
        else:
            llm = ChatOpenAI(model_name="gpt-4o", temperature=0.2)

        # 🧠 1. 喚醒記憶：從資料庫撈出最近 5 筆對話
        stmt = select(models.ChatHistory).where(
            models.ChatHistory.user_id == request.user_id
        ).order_by(models.ChatHistory.timestamp.desc()).limit(5)
        
        result = await db.execute(stmt)
        history_records = result.scalars().all()
        history_records.reverse()
        
        chat_history_str = "".join([f"User: {m.user_question}\nAI: {m.ai_response}\n\n" for m in history_records])

        # 🔍 2. 檢索資料：Hybrid Search（向量 + BM25）撈候選，Reranking 精排取前 6，
        #    手動觸發以便抓取 metadata 裡的真實標題
        langfuse_handler = get_langfuse_handler()
        retriever = get_hybrid_retriever(k=15)
        candidates = await retriever.ainvoke(request.question, config={"callbacks": [langfuse_handler]})
        docs = rerank_documents(request.question, candidates, k=6)

        context_text = "\n\n".join([f"[{d.metadata.get('title', '未知文件')}] {d.page_content}" for d in docs])
        sources = list(dict.fromkeys([d.metadata.get("title", "未知文件") for d in docs]))

        # 🗣️ 3. 升級版 Prompt
        prompt = ChatPromptTemplate.from_template(ANSWER_TEMPLATE)
        chain = prompt | llm | StrOutputParser()

        response = await chain.ainvoke({
            "chat_history": chat_history_str,
            "context": context_text,
            "input": request.question
        }, config={"callbacks": [langfuse_handler]})

        # 💾 4. 寫入新記憶
        try:
            new_chat = models.ChatHistory(
                user_id=request.user_id, user_question=request.question, ai_response=response
            )
            db.add(new_chat)
            await db.commit()
        except Exception:
            await db.rollback()

        return {"status": "success", "answer": response, "sources": sources}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/test-insert")
async def test_insert_chat(request: ChatTestRequest, db: AsyncSession = Depends(get_db)):
    try:
        new_chat = models.ChatHistory(
            user_id=request.user_id, user_question=request.question, ai_response=request.ai_response
        )
        db.add(new_chat)
        await db.commit()
        await db.refresh(new_chat) 
        return {"status": "success"}
    except Exception as e:
        await db.rollback() 
        raise HTTPException(status_code=500, detail=str(e))