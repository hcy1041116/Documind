
# 取得資料庫中前 1 筆資料的完整內容 (包含向量)
res = vector_db.get(include=["embeddings", "documents", "metadatas"], limit=1)

print("🆔 ID:", res["ids"][0])
print("📝 文字片段:", res["documents"][0][:50], "...")
print("🔢 向量前 5 個數字:", res["embeddings"][0][:5]) 
print("📊 向量總長度:", len(res["embeddings"][0])) # 應該要是 1536