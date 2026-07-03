import os
from fastapi import Header, HTTPException


async def verify_access_code(x_access_code: str | None = Header(None)):
    access_code = os.environ.get("ACCESS_CODE")
    if not access_code:
        return  # 本地開發模式，未設定環境變數則放行
    if x_access_code != access_code:
        raise HTTPException(status_code=401, detail="Invalid or missing access code")
