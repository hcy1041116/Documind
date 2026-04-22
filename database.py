from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# 這裡的連線字串使用了 postgresql+asyncpg，代表使用非同步驅動
# 格式：postgresql+asyncpg://使用者:密碼@主機:埠號/資料庫名稱
DATABASE_URL = "postgresql+asyncpg://documind_user:documind_pass@localhost:5432/documind_db"

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