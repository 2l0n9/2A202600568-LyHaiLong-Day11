"""
Task 6 — Lexical Search Module (BM25).

Mặc định sử dụng BM25. Nếu dùng phương pháp khác (TF-IDF, Elasticsearch,
Weaviate BM25 built-in), hãy giải thích cơ chế trong buổi demo → +5 bonus.

Cài đặt:
    pip install rank-bm25

BM25 hoạt động thế nào:
    - Term Frequency (TF): từ xuất hiện nhiều trong document → điểm cao
    - Inverse Document Frequency (IDF): từ hiếm → quan trọng hơn
    - Document length normalization: document dài không bị ưu tiên quá mức
    - Formula: score(q,d) = Σ IDF(qi) * (tf(qi,d) * (k1+1)) / (tf(qi,d) + k1*(1-b+b*|d|/avgdl))
    - k1=1.5 (term saturation), b=0.75 (length normalization)
"""

from pathlib import Path


from task4_chunking_indexing import load_documents, chunk_documents

# Load corpus và chunk để tạo cùng tập dữ liệu phân đoạn với Task 4 & 5
try:
    _docs = load_documents()
    CORPUS: list[dict] = chunk_documents(_docs)
except Exception as e:
    print(f"⚠ Không thể tải corpus: {e}")
    CORPUS = []



bm25_index = None


def build_bm25_index(corpus: list[dict]):
    """
    Xây dựng BM25 index từ corpus.

    Args:
        corpus: List of {'content': str, 'metadata': dict}
    """
    global bm25_index
    from rank_bm25 import BM25Okapi

    # Tách từ đơn giản bằng khoảng trắng sau khi chuyển về viết thường
    tokenized_corpus = [doc["content"].lower().split() for doc in corpus]
    bm25_index = BM25Okapi(tokenized_corpus)
    return bm25_index


# Tự động build index khi load module nếu corpus đã sẵn sàng
if CORPUS:
    build_bm25_index(CORPUS)



def lexical_search(query: str, top_k: int = 10) -> list[dict]:
    """
    Tìm kiếm từ khóa sử dụng BM25.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,
            'score': float,      # BM25 score
            'metadata': dict
        }
        Sorted by score descending.
    """
    global bm25_index
    if not CORPUS:
        print("⚠ Corpus rỗng, không thể tìm kiếm từ khoá.")
        return []

    if bm25_index is None:
        build_bm25_index(CORPUS)

    tokenized_query = query.lower().split()
    scores = bm25_index.get_scores(tokenized_query)

    # Lấy ra các chỉ mục có điểm cao nhất
    import numpy as np
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        if scores[idx] > 0:
            results.append({
                "content": CORPUS[idx]["content"],
                "score": float(scores[idx]),
                "metadata": CORPUS[idx]["metadata"]
            })
    return results



if __name__ == "__main__":
    # Test
    results = lexical_search("Điều 248 tàng trữ trái phép chất ma tuý", top_k=5)
    for r in results:
        print(f"[{r['score']:.3f}] {r['content'][:100]}...")
