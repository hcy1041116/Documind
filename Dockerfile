FROM python:3.12-slim

# tesseract OCR + 繁體中文語言包
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-tra \
    && rm -rf /var/lib/apt/lists/*

# 官方 uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 先複製依賴宣告，讓 Docker 可以 cache 這層
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN mkdir -p uploads chromadb_data

EXPOSE 8000

# Railway 會注入 PORT 環境變數
CMD uv run uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
