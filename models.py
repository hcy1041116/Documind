from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from database import Base

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=False, index=True) # 預留給未來的 JWT 驗證
    user_question = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    # 這次問答引用了哪些文件（title 清單），給 Grafana 做「文件引用排行」用；舊資料沒有這欄，補為 NULL
    sources = Column(JSONB, nullable=True)
    # openai / ollama，給 Grafana 做「模型使用比例」用；舊資料沒有這欄，補為 NULL
    model_provider = Column(String(20), nullable=True)
    # 讓資料庫自動填入當下時間
    timestamp = Column(DateTime(timezone=True), server_default=func.now())