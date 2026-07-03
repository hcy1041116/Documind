import os

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://documind_user:documind_pass@localhost:5432/documind_db"
)
# Railway 給的是 postgresql://，需要轉成 asyncpg driver 格式
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# 建立非同步引擎 (echo=True 可以在終端機印出底層轉換的 SQL 語法，方便 Debug)
engine = create_async_engine(DATABASE_URL, echo=True)

# 建立 Session 工廠，這是未來 API 和資料庫溝通的橋樑
AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# 這是所有 ORM 模型的基礎類別
Base = declarative_base()

# Dependency Injection (依賴注入)：讓 FastAPI 可以在每次 Request 時取得資料庫連線，結束時自動關閉
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session