import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import time
import asyncio

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from services.rag_core import vector_db



with open("evals/dataset.jsonl", "r", encoding="utf-8") as f:
    questions = [json.loads(line) for line in f if line.strip()]

#eval (recall@k, MRR@k)
k=6
retrieved = []
rr = []
for q in questions:
    docs = vector_db.similarity_search(q["question"], k=k)
    retrieved_titles = [doc.metadata.get("title") for doc in docs]
    hit = any(t in retrieved_titles for t in q["expected_source_titles"])
    retrieved.append(hit)

    _rr = 0
    for i, title in enumerate(retrieved_titles):
        if title in q["expected_source_titles"]:
            _rr = 1 / (i + 1)
            break
    rr.append(_rr)

recall = sum(retrieved) / len(retrieved)
print(f"Recall@{k}: {recall:.2f} ({sum(retrieved)}/{len(retrieved)} 題命中)")
print(f"MRR@{k}: {sum(rr) / len(rr):.2f}")

#faithfulness (manual check)
with open("prompts/answer.md", "r", encoding="utf-8") as f:
    ANSWER_TEMPLATE = f.read()
with open("prompts/judge.md", "r", encoding="utf-8") as f:
    JUDGE_TEMPLATE = f.read()

llm = ChatOpenAI(model_name="gpt-4o", temperature=0.2)
prompt = ChatPromptTemplate.from_template(ANSWER_TEMPLATE)
chain = prompt | llm | StrOutputParser()

judge_prompt = ChatPromptTemplate.from_template(JUDGE_TEMPLATE)
judge_chain = judge_prompt | llm | StrOutputParser()

async def run_answer(chain, context_text, question):
    return await chain.ainvoke({
    "chat_history": '',
    "context": context_text,
    "input": question
})
async def run_judge(judge_chain, context, answer):
    return await judge_chain.ainvoke({
    "context": context,
    "answer": answer
})

faithfulness_scores = []
for q in questions:
    docs = vector_db.similarity_search(q["question"], k=k) 
    context_text = "\n\n".join([f"[{d.metadata.get('title', '未知文件')}] {d.page_content}" for d in docs])
    response = asyncio.run(run_answer(chain, context_text, q["question"]))
    judge = asyncio.run(run_judge(judge_chain, context_text, response))
    faithfulness_scores.append(judge)
    time.sleep(3) 

print(f"Faithfulness: {sum(float(score) for score in faithfulness_scores) / len(faithfulness_scores):.2f} (average score over {len(faithfulness_scores)} questions)")
