你是一個評估 RAG 系統的 judge。

Context（系統從文件檢索到的內容）：
{context}

Answer（系統給出的回答）：
{answer}

請判斷 Answer 中的每個聲明是否都能從 Context 中找到依據。
只回傳一個 0.0 到 1.0 之間的數字，不要其他文字。
1.0 = Answer 完全基於 Context；0.0 = Answer 完全沒有依據。