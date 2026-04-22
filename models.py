from sqlalchemy import Column, Integer, String, Text, DateTime, func
from database import Base

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=False, index=True) # 預留給未來的 JWT 驗證
    user_question = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    # 讓資料庫自動填入當下時間
    timestamp = Column(DateTime(timezone=True), server_default=func.now())