"""一次性 migration：幫既有的 chat_history 表補上 sources / model_provider 兩個欄位。

為什麼需要這支腳本：main.py 的 lifespan 只用 SQLAlchemy 的
`Base.metadata.create_all()`，這個只會建「不存在的表」，不會幫「已經存在的表」
補新欄位。chat_history 這張表在本機／production 都已經存在，所以新欄位要手動
ALTER TABLE 補上去，不然 models.py 定義的欄位跟資料庫實際 schema 會對不上，
一跑就噴 UndefinedColumnError。

用 IF NOT EXISTS，可以放心重複執行。
"""
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine


async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS sources JSONB"
        ))
        await conn.execute(text(
            "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS model_provider VARCHAR(20)"
        ))
    print("✅ chat_history 已補上 sources / model_provider 欄位")


if __name__ == "__main__":
    asyncio.run(migrate())
