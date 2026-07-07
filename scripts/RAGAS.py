import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, time, asyncio
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.metrics.collections import Faithfulness, AnswerRelevancy, ContextRecall, ContextPrecision
from services.rag_core import vector_db

with open("evals/dataset.jsonl", "r", encoding="utf-8") as f:
    questions = [json.loads(line) for line in f if line.strip()]

k = 6
llm = ChatOpenAI(model_name="gpt-4o", temperature=0.2)

with open("prompts/answer.md", "r", encoding="utf-8") as f:
    answer_chain = ChatPromptTemplate.from_template(f.read()) | llm | StrOutputParser()

async def get_answer(context_text, question):
    return await answer_chain.ainvoke({
        "chat_history": "",
        "context": context_text,
        "input": question,
    })

samples = []

for q in questions:
    docs = vector_db.similarity_search(q["question"], k=k)
    contexts = [f"[{d.metadata.get('title', '未知文件')}] {d.page_content}" for d in docs]
    context_text = "\n\n".join(contexts)
    answer = asyncio.run(get_answer(context_text, q["question"]))
    samples.append(SingleTurnSample(
        user_input=q["question"],
        response=answer,
        retrieved_contexts=contexts,
        reference=q["expected_answer"]
    ))
    time.sleep(2)

result = evaluate(
    EvaluationDataset(samples=samples),
    metrics=[Faithfulness(), AnswerRelevancy(), ContextRecall(), ContextPrecision()]
)

df = result.to_pandas()
print(df[["faithfulness", "answer_relevancy", "context_recall", "context_precision"]].mean().round(3))
df.to_csv("results_ragas.csv", index=False)
