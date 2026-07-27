import os
import re
from collections import Counter
from typing import Annotated
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from langchain_community.document_loaders import PyMuPDFLoader
import fitz
import pytesseract
from pytesseract import Output
from PIL import Image
from langchain_core.documents import Document

# 引入剛剛建好的 AI 核心
from services.rag_core import vector_db, text_splitter, refresh_bm25_index

# 掃描檔常見的版面：印章、裝訂線、頁首頁尾會讓 PSM 3（全自動版面判斷）誤判。
# PSM 4（假設單欄、字級可變）對這種公文格式常常辨識得更準，但遇到真正多欄/
# 表格版面的文件又會反過來更差——沒有辦法事先判斷哪個比較好，兩個都跑，
# 用 Tesseract 自己回報的信心分數挑比較好的那份。
_OCR_PSM_CANDIDATES = (3, 4)


def _ocr_page_best_psm(img: Image.Image) -> tuple[str, float]:
    """同一張圖跑多個 PSM 設定，回傳信心分數最高的那份文字內容。"""
    best_text, best_conf = "", -1.0
    for psm in _OCR_PSM_CANDIDATES:
        config = f"--psm {psm}"
        data = pytesseract.image_to_data(img, lang="chi_tra", config=config, output_type=Output.DICT)
        confs = [c for c in data["conf"] if c != -1]
        avg_conf = sum(confs) / len(confs) if confs else 0.0
        if avg_conf > best_conf:
            best_conf = avg_conf
            best_text = pytesseract.image_to_string(img, lang="chi_tra", config=config)
    return best_text, best_conf


def ocr_pdf(file_path: str) -> tuple[list[Document], float]:
    """回傳 OCR 出來的頁面，以及整份文件的平均信心分數（0-100，供品質判斷用）。"""
    doc = fitz.open(file_path)
    pages = []
    page_confs = []
    for i, page in enumerate(doc):
        # 放大到 300 DPI（PDF 預設 72 DPI，乘以 300/72 ≈ 4.17x）
        pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        text, conf = _ocr_page_best_psm(img)
        page_confs.append(conf)
        pages.append(Document(
            page_content=text,
            metadata={"source": file_path, "page": i}
        ))
    doc.close()
    avg_confidence = sum(page_confs) / len(page_confs) if page_confs else 0.0
    return pages, avg_confidence


def _looks_like_garbage(text: str, max_repeat_ratio: float = 0.35) -> bool:
    """粗略判斷一段文字是不是亂碼：單一字元佔比過高（例如「一一一一一一」
    這種 OCR 誤判）就當作亂碼，不採用。純文字啟發式，OCR、非 OCR 文件都適用。
    """
    if not text:
        return True
    most_common_count = Counter(text).most_common(1)[0][1]
    return (most_common_count / len(text)) > max_repeat_ratio


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

    # 第二層：內文第一個「有意義」的行（跳過日期、頁碼、單字標題、OCR 亂碼等雜訊）
    first_page_text = pages[0].page_content.strip() if pages else ""
    if first_page_text:
        for line in first_page_text.split("\n"):
            line = line.strip()
            if len(line) < 4:
                continue
            if re.match(r"^(中華民國)?\d", line):
                continue
            if _looks_like_garbage(line):
                continue
            return line[:40]

    # 第三層：檔名
    return filename


QA_MARKER_RE = re.compile(r"(?m)^([一二三四五六七八九十]+、\s?)")
QUESTION_MARK_WINDOW = 70  # 題目編號後多少字內要出現問號，才算「真正的題目」


def _question_markers(full_text: str) -> list[re.Match]:
    """只留下後面緊接著問號的編號——答案內文自己也常有「一、二、三」子清單
    （例如條列款項），這些沒有問號，用這個條件把它們濾掉，避免把一組完整
    問答誤切成好幾個破碎的子清單 chunk。
    """
    markers = []
    for m in QA_MARKER_RE.finditer(full_text):
        window = full_text[m.end():m.end() + QUESTION_MARK_WINDOW]
        if "?" in window or "？" in window:
            markers.append(m)
    return markers


def looks_like_qa_doc(full_text: str) -> bool:
    """判斷是不是「問／答」對照格式的文件：開頭附近同時出現「問」「答」
    這兩個獨立欄位標題，且至少有 3 個「真正的題目」編號。
    """
    head = full_text[:300]
    return "問" in head and "答" in head and len(_question_markers(full_text)) >= 3


def split_qa_pairs(full_text: str) -> list[str]:
    """照題目編號邊界切，讓每個 chunk 剛好是一組完整問答，
    取代固定字數切塊——後者會把題目切在題號中間，檢索時常常只抓到半題。
    """
    matches = _question_markers(full_text)
    if not matches:
        return [full_text]
    blocks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        block = full_text[start:end].strip()
        if block:
            blocks.append(block)
    return blocks


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
            ocr_confidence = None
            if pages and total_chars / len(pages) < 100:
                pages, ocr_confidence = ocr_pdf(file_path)

            real_title = extract_title(pages, file.filename)
            full_text = "\n".join(p.page_content for p in pages)

            if looks_like_qa_doc(full_text):
                # 問答對照格式：照題號邊界切，避免固定字數切塊把題目切在題號中間
                chunks = [
                    Document(
                        page_content=block,
                        metadata={"source": file.filename, "title": real_title},
                    )
                    for block in split_qa_pairs(full_text)
                ]
            else:
                chunks = text_splitter.split_documents(pages)
                for chunk in chunks:
                    chunk.metadata["source"] = file.filename
                    chunk.metadata["title"] = real_title # 寫入真實標題

            all_chunks.extend(chunks)

            result_entry = {
                "filename": file.filename,
                "real_title": real_title,
                "status": "success",
                "chunks_count": len(chunks)
            }
            # OCR 信心分數低於門檻，明確標示出來，不要讓使用者以為這份文件的內容是乾淨的
            # （門檻是憑實測資料抓的粗略值，不是精算出來的，之後有更多樣本可以再調）
            if ocr_confidence is not None:
                result_entry["ocr_confidence"] = round(ocr_confidence, 1)
                if ocr_confidence < 80:
                    result_entry["warning"] = "此文件為掃描檔，OCR 辨識信心分數偏低，內容可能有辨識錯誤，建議人工核對或改用更清晰的掃描檔重新上傳"

            results.append(result_entry)

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