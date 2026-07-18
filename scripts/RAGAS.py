import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, time, asyncio
import pandas as pd
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from ragas import EvaluationDataset, SingleTurnSample, evaluate, RunConfig
from ragas.metrics import Faithfulness, AnswerRelevancy, ContextRecall, ContextPrecision
from services.rag_core import get_hybrid_retriever, rerank_documents

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

retriever = get_hybrid_retriever(k=15)
samples = []

for q in questions:
    candidates = retriever.invoke(q["question"])
    docs = rerank_documents(q["question"], candidates, k=k)
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

judge_llm = ChatOpenAI(model_name="gpt-4o", temperature=0)
judge_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

METRIC_COLS = ["faithfulness", "answer_relevancy", "context_recall", "context_precision"]
RUN_CONFIG = RunConfig(timeout=300, max_retries=15, max_wait=90, max_workers=4)


def run_eval(eval_samples):
    return evaluate(
        EvaluationDataset(samples=eval_samples),
        metrics=[Faithfulness(), AnswerRelevancy(), ContextRecall(), ContextPrecision()],
        llm=judge_llm,
        embeddings=judge_embeddings,
        run_config=RUN_CONFIG,
    ).to_pandas()


df = run_eval(samples)

# ragas 的 executor 長時間跑會偶爾因連線問題把個別 job 打成 NaN（不是分數真的是 0，
# 是那題根本沒跑成功）。只針對還缺分數的樣本重跑，而不是整批重來。
MAX_ATTEMPTS = 3
for attempt in range(1, MAX_ATTEMPTS + 1):
    nan_rows = df[df[METRIC_COLS].isna().any(axis=1)].index.tolist()
    if not nan_rows:
        break
    print(f"[retry {attempt}/{MAX_ATTEMPTS}] {len(nan_rows)} 筆樣本有缺分數，重跑中...")
    retry_df = run_eval([samples[i] for i in nan_rows])
    for pos, idx in enumerate(nan_rows):
        for col in METRIC_COLS:
            if pd.isna(df.at[idx, col]) and not pd.isna(retry_df.at[pos, col]):
                df.at[idx, col] = retry_df.at[pos, col]

still_missing = df[METRIC_COLS].isna().sum()
if still_missing.sum() > 0:
    print("重跑後仍缺分數（視為該題真的評不出來，不是連線問題）：")
    print(still_missing)

print(df[METRIC_COLS].mean().round(3))
df.to_csv("results_ragas.csv", index=False)
