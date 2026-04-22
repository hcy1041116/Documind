from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine
import models
from api import chat, document

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("⏳ 正在連線 PostgreSQL 並確認資料表...")
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    print("✅ 資料表確認完畢！伺服器啟動中...")
    yield 
    print("🛑 正在關閉資料庫連線...")
    await engine.dispose()

app = FastAPI(
    title="DocuMind API",
    description="企業級智能文件問答系統",
    lifespan=lifespan 
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "message": "DocuMind 伺服器與資料庫就緒！"}

# 🚀 把剛剛拆分的部門掛載上來
app.include_router(chat.router)
app.include_router(document.router)