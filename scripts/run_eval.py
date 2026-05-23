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

k = 6
llm = ChatOpenAI(model_name="gpt-4o", temperature=0.2)

with open("prompts/answer.md", "r", encoding="utf-8") as f:
    answer_chain = ChatPromptTemplate.from_template(f.read()) | llm | StrOutputParser()

with open("prompts/judge_faithfulness.md", "r", encoding="utf-8") as f:
    faithfulness_chain = ChatPromptTemplate.from_template(f.read()) | llm | StrOutputParser()

with open("prompts/judge_relevance.md", "r", encoding="utf-8") as f:
    relevance_chain = ChatPromptTemplate.from_template(f.read()) | llm | StrOutputParser()


async def get_answer(context, question):
    return await answer_chain.ainvoke({
        "chat_history": "",
        "context": context,
        "input": question,
    })

async def get_faithfulness(context, answer):
    return await faithfulness_chain.ainvoke({
        "context": context,
        "answer": answer,
    })

async def get_relevance(question, answer):
    return await relevance_chain.ainvoke({
        "question": question,
        "answer": answer,
    })


recall_hits = []
reciprocal_ranks = []
faithfulness_scores = []
relevance_scores = []

for q in questions:
    docs = vector_db.similarity_search(q["question"], k=k)
    retrieved_titles = [doc.metadata.get("title") for doc in docs]
    context = "\n\n".join([f"[{d.metadata.get('title', '未知文件')}] {d.page_content}" for d in docs])

    hit = any(t in retrieved_titles for t in q["expected_source_titles"])
    recall_hits.append(hit)

    rr = 0
    for i, title in enumerate(retrieved_titles):
        if title in q["expected_source_titles"]:
            rr = 1 / (i + 1)
            break
    reciprocal_ranks.append(rr)

    answer = asyncio.run(get_answer(context, q["question"]))
    faithfulness_scores.append(float(asyncio.run(get_faithfulness(context, answer)).strip()))
    relevance_scores.append(float(asyncio.run(get_relevance(q["question"], answer)).strip()))
    time.sleep(3)

print(f"Recall@{k}:    {sum(recall_hits) / len(recall_hits):.2f} ({sum(recall_hits)}/{len(recall_hits)} 題命中)")
print(f"MRR@{k}:       {sum(reciprocal_ranks) / len(reciprocal_ranks):.2f}")
print(f"Faithfulness:  {sum(faithfulness_scores) / len(faithfulness_scores):.2f} (avg over {len(faithfulness_scores)} questions)")
print(f"Relevance:     {sum(relevance_scores) / len(relevance_scores):.2f} (avg over {len(relevance_scores)} questions)")