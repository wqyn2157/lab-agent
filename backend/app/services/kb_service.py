from chromadb.api.models.Collection import Collection
from regex import T
from app.config import BASE_DIR
import chromadb
from chromadb.utils import embedding_functions
from threading import Lock
from app.services.text_splitter import split_text

_kb_lock = Lock()

KB_DIR = BASE_DIR / "data" / "kb"
CHROMA_DIR = BASE_DIR / "data" / "chroma"
EMBINDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"

_collection = None

_embedding_fn = None


def get_embedding_fn():
    global _embedding_fn
    if _embedding_fn is not None:
        return _embedding_fn
    _embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBINDING_MODEL_NAME
    )
    return _embedding_fn


def get_collection() -> Collection:
    """复用向量库连接，每次使用前同步本地文档。"""
    global _collection

    with _kb_lock:
        if not KB_DIR.is_dir():
            raise RuntimeError("知识库目录不存在，请检查配置")

        # 连接只初始化一次，但文档同步每次都执行
        if _collection is None:
            CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            _collection = client.get_or_create_collection(
                name="lab_kb",
                embedding_function=get_embedding_fn(),
            )

        col = _collection

        # 读取库里已有的文档，建立 ID -> 原文的对应关系
        stored = col.get(include=["documents"])
        old_docs = dict(zip(stored["ids"], stored["documents"] or []))

        active_ids = set()
        ids, docs, metas = [], [], []

        for path in sorted(KB_DIR.glob("*.md")):
            text = path.read_text(encoding="utf-8-sig").strip()
            if not text:
                continue

            chunks = split_text(text)

            for chunk_index, chunk in enumerate(chunks):
                doc_id = f"{path.stem}::chunk::{chunk_index}"
                active_ids.add(doc_id)

                # 片段内容没变，就不重新生成向量
                if old_docs.get(doc_id) == chunk:
                    continue

                ids.append(doc_id)
                docs.append(chunk)
                metas.append(
                    {
                        "source": path.name,
                        "chunk_index": chunk_index,
                    }
                )

        # ID 不存在则新增，已存在则更新原文和向量
        if ids:
            col.upsert(
                ids=ids,
                documents=docs,
                metadatas=metas,
            )

        # 本地已删除或清空的文档，也从向量库移除
        deleted_ids = list(set(old_docs) - active_ids)
        if deleted_ids:
            col.delete(ids=deleted_ids)

        return col


def warmup():
    """启动时初始化向量库 启动预热"""
    col = get_collection()
    if col.count() > 0:
        col.query(query_texts=["预热"], n_results=1)


def search(query: str):
    """根据关键字检索向量库"""
    col = get_collection()
    if col.count() == 0:
        return ""

    limit = min(5, col.count())
    res = col.query(query_texts=[query], n_results=limit)
    docs = (res.get("documents") or [[]])[0]  # [list]
    metas = (res.get("metadatas") or [[]])[0]  # [list]
    distances = (res.get("distances") or [[]])[0]
    """
    以下是检索出来的资料：
    [预约规则.md · 片段 2]

    # 实验室预约规则...


    [安全规则.md]

    # 安全规范...

    """
    score_parts = []

    for doc, meta, dist in zip(docs, metas, distances):
        score = 1 / (1 + dist)
        if score < 0.5:
            continue
        name = meta.get("source") or "未知来源"
        chunk_no = meta.get("chunk_index", 0) + 1

        score_parts.append(
            {
                "score": score,
                "content": f"[{name} · 片段 {chunk_no}]\n{doc}",
            }
        )
    print(f"检索出来的 score_parts: {score_parts}")
    score_parts.sort(key=lambda x: x["score"], reverse=True)
    final_parts = [item["content"] for item in score_parts[:2]]
    return "\n\n".join(final_parts)
