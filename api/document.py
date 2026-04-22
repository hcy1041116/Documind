import os
from typing import Annotated
from fastapi import APIRouter, HTTPException, UploadFile, File
from langchain_community.document_loaders import PyPDFLoader

# 引入剛剛建好的 AI 核心
from services.rag_core import vector_db, text_splitter

router = APIRouter(prefix="/api/document", tags=["Document"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload/bulk")
async def upload_multiple_pdfs(files: Annotated[list[UploadFile], File(description="批次上傳 PDF 檔案")]):
    results = [] 
    all_chunks = []
    
    if not files:
        raise HTTPException(status_code=400, detail="請至少上傳一個檔案！")

    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            results.append({"filename": file.filename, "status": "failed", "reason": "非 PDF 格式"})
            continue

        file_path = os.path.join(UPLOAD_DIR, file.filename)

        try:
            content = await file.read()
            with open(file_path, "wb") as buffer:
                buffer.write(content)
                
            loader = PyPDFLoader(file_path)
            pages = loader.load() 
            
            # 🌟【升級】抓取第一頁文字作為真實標題
            first_page_text = pages[0].page_content.strip()
            real_title = "未知文件"
            if first_page_text:
                lines = [line.strip() for line in first_page_text.split('\n') if line.strip()]
                if lines:
                    real_title = lines[0][:40] 
                    
            chunks = text_splitter.split_documents(pages)
        
            for chunk in chunks:
                chunk.metadata["source"] = file.filename
                chunk.metadata["title"] = real_title # 寫入真實標題
                all_chunks.append(chunk)

            results.append({
                "filename": file.filename, 
                "real_title": real_title,
                "status": "success", 
                "chunks_count": len(chunks)
            })

        except Exception as e:
            results.append({"filename": file.filename, "status": "failed", "reason": str(e)})

    if all_chunks:
        try:
            vector_db.add_documents(all_chunks)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Embedding 失敗: {str(e)}")

    return {
        "status": "completed",
        "total_chunks": len(all_chunks),
        "data": results,
    }

@router.get("/stats")
async def get_vector_db_stats():
    try:
        count = vector_db._collection.count()
        return {"status": "success", "total_chunks_in_db": count}
    except Exception as e:
        return {"status": "error", "message": str(e)}