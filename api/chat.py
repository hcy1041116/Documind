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
from services.rag_core import vector_db
from schemas import ChatRequest, ChatTestRequest, ModelProvider


router = APIRouter(prefix="/api/chat", tags=["Chat"])


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

        # 🔍 2. 檢索資料：手動觸發以便抓取 metadata 裡的真實標題
        retriever = vector_db.as_retriever(search_kwargs={"k": 3})
        docs = await retriever.ainvoke(request.question)
        
        context_text = "\n\n".join([f"[{d.metadata.get('title', '未知文件')}] {d.page_content}" for d in docs])
        sources = list(set([d.metadata.get("title", "未知文件") for d in docs]))

        # 🗣️ 3. 升級版 Prompt
        template = """根據以下提供的【參考文件】內容，以及我們之前的【歷史對話紀錄】，來回答使用者的問題。
        
        【歷史對話紀錄】
        {chat_history}
        
        【參考文件】
        {context}
        
        Question: {input}
        """
        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | llm | StrOutputParser()
        
        response = await chain.ainvoke({
            "chat_history": chat_history_str,
            "context": context_text,
            "input": request.question
        })

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