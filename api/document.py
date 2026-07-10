import os
import re
from typing import Annotated
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from langchain_community.document_loaders import PyMuPDFLoader
import fitz
import pytesseract
from PIL import Image
from langchain_core.documents import Document

# 引入剛剛建好的 AI 核心
from services.rag_core import vector_db, text_splitter, refresh_bm25_index

def ocr_pdf(file_path: str) -> list[Document]:
    doc = fitz.open(file_path)
    pages = []
    for i, page in enumerate(doc):
        # 放大到 300 DPI（PDF 預設 72 DPI，乘以 300/72 ≈ 4.17x）
        pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        text = pytesseract.image_to_string(img, lang="chi_tra")
        pages.append(Document(
            page_content=text,
            metadata={"source": file_path, "page": i}
        ))
    doc.close()
    return pages


def extract_title(pages: list[Document], filename: str) -> str:
    """三層 fallback：PDF metadata title → 內文首個有意義的行 → 檔名"""
    # 第一層：PDF 內嵌的 metadata title（常見於 Word 匯出的 PDF）
    pdf_title = (pages[0].metadata.get("title") or "").strip() if pages else ""
    pdf_title = re.sub(r"^Microsoft\s+Word\s*-\s*", "", pdf_title, flags=re.IGNORECASE)
    pdf_title = re.sub(r"\.(docx?|xlsx?|pptx?|odt|ods|odp|pdf|rtf|txt)$", "", pdf_title, flags=re.IGNORECASE).strip()
    # 排除像 "0001-2" 這種內部檔名代號：沒有中文字也沒有空白的短字串通常不是真標題
    looks_like_real_title = pdf_title and (re.search(r"[一-鿿]", pdf_title) or " " in pdf_title)
    if looks_like_real_title and pdf_title.lower() not in {"untitled", "unknown"}:
        return pdf_title[:40]

    # 第二層：內文第一個「有意義」的行（跳過日期、頁碼、單字標題等雜訊）
    first_page_text = pages[0].page_content.strip() if pages else ""
    if first_page_text:
        for line in first_page_text.split("\n"):
            line = line.strip()
            if len(line) < 4:
                continue
            if re.match(r"^(中華民國)?\d", line):
                continue
            return line[:40]

    # 第三層：檔名
    return filename


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
                
            # 第一步：先用 PyMuPDF 試
            loader = PyMuPDFLoader(file_path)
            pages = loader.load()

            # 第二步：算平均每頁字數，太少就走 OCR
            total_chars = sum(len(p.page_content) for p in pages)
            if pages and total_chars / len(pages) < 100:
                pages = ocr_pdf(file_path)

            
            real_title = extract_title(pages, file.filename)

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
            refresh_bm25_index()
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
@router.get("/download/{filename}")
async def download_document(filename: str):
    safe_name = os.path.basename(filename)
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="檔案不存在")

    return FileResponse(file_path, filename=safe_name, media_type="application/pdf")

@router.get("/list")
async def list_uploaded_documents():
    try:
        _filenames = vector_db._collection.get(include=["metadatas"])
        filenames = set()
        for filename in _filenames["metadatas"]:
            filenames.add(filename["source"])
        return {"status": "success", "filenames": list(filenames)}
    except Exception as e:
        return {"status": "error", "message": str(e)}