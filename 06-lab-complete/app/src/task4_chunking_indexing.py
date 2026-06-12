"""
Task 4 — Chunking & Indexing vào Vector Store.

Hướng dẫn:
    1. Đọc toàn bộ markdown files từ data/standardized/
    2. Chọn 1 chunking strategy (giải thích lý do)
    3. Chọn 1 embedding model (giải thích lý do)
    4. Index vào vector store (Weaviate khuyến cáo)

Chunking options (langchain-text-splitters):
    - RecursiveCharacterTextSplitter: an toàn, phổ biến
    - MarkdownHeaderTextSplitter: tốt cho file có heading
    - SemanticChunker: dùng embedding để tách (nâng cao)

Embedding model options:
    - sentence-transformers/all-MiniLM-L6-v2 (384 dim, nhẹ)
    - BAAI/bge-m3 (1024 dim, multilingual, tốt cho tiếng Việt)
    - OpenAI text-embedding-3-small (1536 dim, API)

Vector store options:
    - Weaviate (khuyến cáo: hỗ trợ hybrid search built-in)
    - ChromaDB (đơn giản, local)
    - FAISS (chỉ dense search)

Cài đặt:
    pip install langchain-text-splitters sentence-transformers weaviate-client
"""

from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()


STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"


# =============================================================================
# CONFIGURATION — Giải thích lựa chọn của bạn trong comment
# =============================================================================

# Chọn RecursiveCharacterTextSplitter để tách văn bản linh hoạt theo thứ tự ưu tiên:
# đoạn (\n\n), dòng (\n), câu (. ), từ ( ) nhằm giữ nguyên cấu trúc ngữ nghĩa của văn bản luật và báo chí.
# CHUNK_SIZE = 500 ký tự giúp các phân đoạn đủ nhỏ để tránh mất ngữ cảnh cụ thể (lost in the middle) 
# nhưng đủ lớn để chứa trọn vẹn một ý hoặc một điều khoản ngắn.
# CHUNK_OVERLAP = 50 ký tự đảm bảo các thông tin nằm ở biên phân đoạn không bị ngắt quãng mất ý.
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
CHUNKING_METHOD = "recursive"

# Chọn model text-embedding-3-small từ OpenAI (1536 dimensions) để tối ưu hoá chi phí và tốc độ,
# đồng thời biểu diễn chính xác văn bản tiếng Việt mà không cần download model dung lượng lớn về máy.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# Lựa chọn Weaviate làm Vector Store chính vì có hỗ trợ Hybrid Search built-in cực tốt và hỗ trợ Weaviate Cloud.
VECTOR_STORE = "weaviate"




# =============================================================================
# IMPLEMENTATION
# =============================================================================

def load_documents() -> list[dict]:
    """
    Đọc toàn bộ markdown files từ data/standardized/.

    Returns:
        List of {'content': str, 'metadata': {'source': str, 'type': str}}
    """
    documents = []
    if not STANDARDIZED_DIR.exists():
        print(f"⚠ Thư mục {STANDARDIZED_DIR} không tồn tại!")
        return documents

    for md_file in STANDARDIZED_DIR.rglob("*.md"):
        if md_file.is_file():
            try:
                content = md_file.read_text(encoding="utf-8")
                doc_type = "legal" if "legal" in md_file.parts else "news"
                documents.append({
                    "content": content,
                    "metadata": {"source": md_file.name, "type": doc_type}
                })
            except Exception as e:
                print(f"  ✗ Lỗi khi đọc file {md_file.name}: {e}")
    return documents


def chunk_documents(documents: list[dict]) -> list[dict]:
    """
    Chunk documents theo strategy đã chọn.

    Returns:
        List of {'content': str, 'metadata': dict} — mỗi item là 1 chunk
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""]
    )

    chunks = []
    for doc in documents:
        splits = splitter.split_text(doc["content"])
        for i, chunk_text in enumerate(splits):
            chunks.append({
                "content": chunk_text,
                "metadata": {
                    "source": doc["metadata"]["source"],
                    "type": doc["metadata"]["type"],
                    "chunk_index": i
                }
            })
    return chunks


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Embed toàn bộ chunks bằng model đã chọn (OpenAI).

    Returns:
        Mỗi chunk dict được thêm key 'embedding': list[float]
    """
    from openai import OpenAI
    import os

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or "xxx" in api_key:
        raise ValueError("OPENAI_API_KEY chưa được thiết lập trong file .env")

    print(f"Connecting to OpenAI API for model: {EMBEDDING_MODEL}...")
    client = OpenAI(api_key=api_key)

    texts = [c["content"] for c in chunks]
    print(f"Generating embeddings for {len(texts)} chunks via OpenAI...")

    # Chia nhỏ thành các batch (tối đa 100 texts mỗi batch) để gửi API
    batch_size = 100
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        response = client.embeddings.create(
            input=batch_texts,
            model=EMBEDDING_MODEL
        )
        embeddings.extend([item.embedding for item in response.data])

    for chunk, emb in zip(chunks, embeddings):
        chunk["embedding"] = emb
    return chunks



def index_to_vectorstore(chunks: list[dict]):
    """
    Lưu chunks vào vector store đã chọn.
    """
    if VECTOR_STORE == "weaviate":
        import weaviate
        from weaviate.classes.config import Configure, Property, DataType
        from weaviate.classes.init import Auth

        weaviate_url = os.getenv("WEAVIATE_URL", "")
        weaviate_api_key = os.getenv("WEAVIATE_API_KEY", "")

        if not weaviate_url or "xxx" in weaviate_url:
            print("Connecting to local Weaviate...")
            client = weaviate.connect_to_local()
        else:
            print(f"Connecting to Weaviate Cloud at {weaviate_url}...")
            client = weaviate.connect_to_weaviate_cloud(
                cluster_url=weaviate_url,
                auth_credentials=Auth.api_key(weaviate_api_key)
            )

        try:
            collection_name = "DrugLawDocs"
            if client.collections.exists(collection_name):
                print(f"Collection '{collection_name}' already exists. Deleting it to re-index...")
                client.collections.delete(collection_name)

            print(f"Creating collection '{collection_name}'...")
            collection = client.collections.create(
                name=collection_name,
                vectorizer_config=Configure.Vectorizer.none(),
                vector_index_config=Configure.VectorIndex.hfresh(),
                properties=[
                    Property(name="content", data_type=DataType.TEXT),
                    Property(name="source", data_type=DataType.TEXT),
                    Property(name="doc_type", data_type=DataType.TEXT),
                    Property(name="chunk_index", data_type=DataType.INT),
                ]
            )

            print(f"Indexing {len(chunks)} chunks into Weaviate...")
            with collection.batch.dynamic() as batch:
                for chunk in chunks:
                    properties = {
                        "content": chunk["content"],
                        "source": chunk["metadata"]["source"],
                        "doc_type": chunk["metadata"]["type"],
                        "chunk_index": int(chunk["metadata"]["chunk_index"]),
                    }
                    batch.add_object(
                        properties=properties,
                        vector=chunk["embedding"]
                    )

            failed = collection.batch.failed_objects
            if failed:
                print(f"⚠ Failed to index {len(failed)} objects. Example error: {failed[0].message}")
            else:
                print("✓ Successfully indexed all chunks to Weaviate.")
        finally:
            client.close()
            print("Weaviate connection closed.")

    elif VECTOR_STORE == "chromadb":
        import chromadb

        persist_dir = Path(__file__).parent.parent / "data" / "chromadb"
        persist_dir.mkdir(parents=True, exist_ok=True)

        print(f"Connecting to persistent ChromaDB at {persist_dir}...")
        client = chromadb.PersistentClient(path=str(persist_dir))

        collection_name = "DrugLawDocs"
        try:
            client.delete_collection(name=collection_name)
            print(f"Deleted existing collection '{collection_name}' for re-indexing...")
        except Exception:
            pass

        collection = client.create_collection(name=collection_name)

        print(f"Indexing {len(chunks)} chunks into ChromaDB...")
        ids = [f"chunk_{i:04d}" for i in range(len(chunks))]
        documents = [c["content"] for c in chunks]
        embeddings = [c["embedding"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]

        collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas
        )
        print("✓ Successfully indexed all chunks to ChromaDB.")



def run_pipeline():
    """Chạy toàn bộ pipeline: load → chunk → embed → index."""
    print("=" * 50)
    print("Task 4: Chunking & Indexing")
    print(f"  Chunking: {CHUNKING_METHOD} (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")
    print(f"  Embedding: {EMBEDDING_MODEL} (dim={EMBEDDING_DIM})")
    print(f"  Vector Store: {VECTOR_STORE}")
    print("=" * 50)

    docs = load_documents()
    print(f"\n✓ Loaded {len(docs)} documents")

    chunks = chunk_documents(docs)
    print(f"✓ Created {len(chunks)} chunks")

    chunks = embed_chunks(chunks)
    print(f"✓ Embedded {len(chunks)} chunks")

    index_to_vectorstore(chunks)
    print("✓ Indexed to vector store")


if __name__ == "__main__":
    run_pipeline()
