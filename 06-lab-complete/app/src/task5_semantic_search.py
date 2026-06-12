"""
Task 5 — Semantic Search Module.

Viết module tìm kiếm ngữ nghĩa (dense retrieval) trên vector store.

Yêu cầu:
    - Input: query string + top_k
    - Output: danh sách chunks có score, sorted descending
    - Phải tương thích với embedding model và vector store ở Task 4
"""




import os
from dotenv import load_dotenv
from task4_chunking_indexing import VECTOR_STORE, EMBEDDING_MODEL

load_dotenv()


def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    """
    Tìm kiếm ngữ nghĩa sử dụng vector similarity.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,      # Nội dung chunk
            'score': float,      # Cosine similarity score
            'metadata': dict     # source, doc_type, chunk_index
        }
        Sorted by score descending.
    """
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or "xxx" in api_key:
        raise ValueError("OPENAI_API_KEY chưa được thiết lập trong file .env")

    # Bước 1: Embed query bằng cùng model ở Task 4
    client = OpenAI(api_key=api_key)
    response = client.embeddings.create(
        input=[query],
        model=EMBEDDING_MODEL
    )
    query_embedding = response.data[0].embedding

    # Bước 2 & 3: Query vector store và trả về kết quả
    if VECTOR_STORE == "weaviate":
        import weaviate
        from weaviate.classes.init import Auth
        from weaviate.classes.query import MetadataQuery

        weaviate_url = os.getenv("WEAVIATE_URL", "")
        weaviate_api_key = os.getenv("WEAVIATE_API_KEY", "")

        if not weaviate_url or "xxx" in weaviate_url:
            client = weaviate.connect_to_local()
        else:
            client = weaviate.connect_to_weaviate_cloud(
                cluster_url=weaviate_url,
                auth_credentials=Auth.api_key(weaviate_api_key)
            )

        try:
            collection = client.collections.get("DrugLawDocs")
            results = collection.query.near_vector(
                near_vector=query_embedding,
                limit=top_k,
                return_metadata=MetadataQuery(distance=True)
            )

            search_results = []
            for obj in results.objects:
                # distance = 1 - cosine_similarity trong Weaviate
                distance = obj.metadata.distance if obj.metadata.distance is not None else 1.0
                score = 1.0 - distance
                search_results.append({
                    "content": obj.properties.get("content", ""),
                    "score": score,
                    "metadata": {
                        "source": obj.properties.get("source", ""),
                        "type": obj.properties.get("doc_type", ""),
                        "chunk_index": obj.properties.get("chunk_index", 0)
                    }
                })
            return search_results
        finally:
            client.close()

    elif VECTOR_STORE == "chromadb":
        import chromadb
        from pathlib import Path

        persist_dir = Path(__file__).parent.parent / "data" / "chromadb"
        client = chromadb.PersistentClient(path=str(persist_dir))
        collection = client.get_collection("DrugLawDocs")

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )

        search_results = []
        if results and 'documents' in results and results['documents']:
            documents = results['documents'][0]
            distances = results['distances'][0] if 'distances' in results else [0.0] * len(documents)
            metadatas = results['metadatas'][0] if 'metadatas' in results else [{}] * len(documents)

            for doc, dist, meta in zip(documents, distances, metadatas):
                # distance = L2 hoặc Cosine distance trong Chroma. Đối với Cosine: score = 1.0 - distance
                score = 1.0 - dist
                search_results.append({
                    "content": doc,
                    "score": score,
                    "metadata": meta
                })
        return search_results

    else:
        raise ValueError(f"Unknown vector store: {VECTOR_STORE}")



if __name__ == "__main__":
    # Test
    results = semantic_search("hình phạt cho tội tàng trữ ma tuý", top_k=5)
    for r in results:
        print(f"[{r['score']:.3f}] {r['content'][:100]}...")
