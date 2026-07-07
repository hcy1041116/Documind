# Eval Baseline — v1

> 日期：2026-05-24
> 文件：醫療器材優良臨床試驗管理辦法（單一文件）
> 腳本：`scripts/run_eval.py`，k=6，judge model: GPT-4o

---

## 數字

| Metric | Score | 備註 |
|--------|-------|------|
| Recall@6 | 1.00 | 13/13 題命中 |
| MRR@6 | 1.00 | 正確來源均排第 1 |
| Faithfulness | 0.92 | avg over 13 questions |
| Answer Relevance | 0.92 | avg over 13 questions |

---

## 注意事項

- **單文件情境**：ChromaDB 目前只有一份文件，retrieval 分數 1.00 不代表系統真的很好——沒有干擾來源，retriever 不可能失手。加入更多文件後數字才有鑑別力。
- **Faithfulness 0.0 異常題**：「使用安慰劑的人算是受試者嗎？」judge 評為完全無依據，推測 LLM 用了自身知識而非 retrieved context 回答。
- **Relevance 0.5 題**：「倫委會每年審查幾次？」與「嚴重不良事件包含哪些情形？」回答只有部分切中問題。

---

## 下一步比較點

Phase C 每個 PR 都要跑 `make eval`，將 delta 記錄在 `docs/eval_log.md`，與這份 baseline 對比。

重點觀察：
1. 加入更多文件後 Recall 和 MRR 會下降多少？
2. reranker 能不能把 MRR 拉回來？
3. faithfulness 異常題在換 chunking 後是否改善？