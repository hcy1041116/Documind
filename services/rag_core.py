import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

# 1. 初始化模型
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")


# 2. 初始化 ChromaDB
CHROMA_PATH = "chromadb_data"
vector_db = Chroma(
    collection_name="documind_law",
    embedding_function=embeddings,
    persist_directory=CHROMA_PATH
)

# 3. 設定切塊器
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,       
    chunk_overlap=50,     
    separators=["\n\n", "\n", "。", "！", "？", "，", " ", ""]
)