import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.rag_core import vector_db


with open("evals/dataset.jsonl", "r", encoding="utf-8") as f:
    questions = [json.loads(line) for line in f if line.strip()]

retrieved = []
for q in questions:
    docs = vector_db.similarity_search(q["question"], k=6)
    retrieved_titles = [doc.metadata.get("title") for doc in docs]
    hit = any(t in retrieved_titles for t in q["expected_source_titles"])
    retrieved.append(hit)
recall = sum(retrieved) / len(retrieved)
print(f"Recall@6: {recall:.2f} ({sum(retrieved)}/{len(retrieved)} 題命中)")
