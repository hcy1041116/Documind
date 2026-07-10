import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, time, asyncio, subprocess
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


def get_git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def append_eval_log(mean_scores, n_questions, missing_counts):
    """每次跑完 eval 附加一行到 docs/eval_log.md，累積歷史紀錄，
    而不是像 results_ragas.csv 一樣每次覆蓋掉——這樣才有辦法看趨勢、抓 regression。
    """
    log_path = "docs/eval_log.md"
    header = (
        "# Eval Log\n\n"
        "> 每次跑 `scripts/RAGAS.py` 自動附加一行，追蹤 RAG 改動對品質分數的影響。\n"
        "> 分數是 0～1，越高越好；`missing` 是這輪有幾格分數因為連線問題拿不到（不是分數低，是根本沒評出來）。\n\n"
        "| 時間 | Commit | 題數 | Faithfulness | Answer Relevancy | Context Recall | Context Precision | Missing |\n"
        "|------|--------|------|--------------|-------------------|-----------------|--------------------|---------|\n"
    )

    if not os.path.exists(log_path):
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(header)

    row = (
        f"| {time.strftime('%Y-%m-%d %H:%M')} "
        f"| `{get_git_commit()}` "
        f"| {n_questions} "
        f"| {mean_scores['faithfulness']:.3f} "
        f"| {mean_scores['answer_relevancy']:.3f} "
        f"| {mean_scores['context_recall']:.3f} "
        f"| {mean_scores['context_precision']:.3f} "
        f"| {int(missing_counts.sum())} |\n"
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(row)
    print(f"已附加一筆紀錄到 {log_path}")


append_eval_log(df[METRIC_COLS].mean(), len(df), still_missing)
