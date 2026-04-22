# schemas.py
from pydantic import BaseModel
from enum import Enum

class ModelProvider(Enum):
    openai = "openai"
    ollama = "ollama"

# 1. 問答 API 的請求格式
class ChatRequest(BaseModel):
    model_provider: ModelProvider = ModelProvider.openai
    question: str
    user_id: str = "guest_user"

# 2. 測試寫入 API 的請求格式
class ChatTestRequest(BaseModel):
    user_id: str
    user_question: str
    ai_response: str

