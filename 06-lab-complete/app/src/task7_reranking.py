"""
Task 7 — Reranking Module.

Chọn 1 trong các phương pháp:
    - Cross-encoder reranker: Jina Reranker v2 (multilingual) hoặc Qwen3-Reranker
    - MMR (Maximal Marginal Relevance): tự implement
    - RRF (Reciprocal Rank Fusion): tự implement

Nếu dùng MMR hoặc RRF, đảm bảo hiểu và giải thích được cơ chế.
"""

from typing import Optional





import os
from dotenv import load_dotenv
load_dotenv()


def rerank_cross_encoder(
    query: str, candidates: list[dict], top_k: int = 5
) -> list[dict]:
    """
    Rerank candidates sử dụng cross-encoder model.

    Args:
        query: Câu truy vấn
        candidates: List of {'content': str, 'score': float, 'metadata': dict}
        top_k: Số lượng kết quả sau rerank

    Returns:
        List of top_k candidates, re-scored và sorted by rerank_score descending.
    """
    if not candidates:
        return []

    jina_key = os.getenv("JINA_API_KEY", "")
    if jina_key and "xxx" not in jina_key:
        print("Using Jina Reranker API...")
        import requests
        try:
            response = requests.post(
                "https://api.jina.ai/v1/rerank",
                headers={"Authorization": f"Bearer {jina_key}"},
                json={
                    "model": "jina-reranker-v2-base-multilingual",
                    "query": query,
                    "documents": [c["content"] for c in candidates],
                    "top_n": top_k
                },
                timeout=10
            )
            response.raise_for_status()
            reranked = response.json()["results"]
            
            results = []
            for r in reranked:
                idx = r["index"]
                item = candidates[idx].copy()
                item["score"] = float(r["relevance_score"])
                results.append(item)
            return results
        except Exception as e:
            print(f"⚠ Jina Reranker API error, falling back to local Cross-Encoder: {e}")

    # Fallback to local CrossEncoder model
    print("Using local Cross-Encoder model (ms-marco-MiniLM-L-6-v2)...")
    from sentence_transformers import CrossEncoder

    model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    pairs = [[query, c["content"]] for c in candidates]
    scores = model.predict(pairs)

    # Gán điểm mới và sắp xếp
    scored_candidates = []
    for item, score in zip(candidates, scores):
        new_item = item.copy()
        new_item["score"] = float(score)
        scored_candidates.append(new_item)

    scored_candidates.sort(key=lambda x: x["score"], reverse=True)
    return scored_candidates[:top_k]



def cosine_sim(v1: list[float], v2: list[float]) -> float:
    import numpy as np
    dot_prod = np.dot(v1, v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot_prod / (norm1 * norm2))


def rerank_mmr(
    query_embedding: list[float],
    candidates: list[dict],
    top_k: int = 5,
    lambda_param: float = 0.7,
) -> list[dict]:
    """
    Maximal Marginal Relevance — chọn candidates vừa relevant vừa diverse.

    MMR = λ * sim(query, doc) - (1-λ) * max(sim(doc, selected_docs))

    Args:
        query_embedding: Vector embedding của query
        candidates: List of {'content': str, 'score': float, 'embedding': list, 'metadata': dict}
        top_k: Số lượng kết quả
        lambda_param: Trade-off giữa relevance (1.0) và diversity (0.0)

    Returns:
        List of top_k candidates selected by MMR.
    """
    if not candidates:
        return []

    # Kiểm tra xem các candidates có chứa vector embedding không.
    # Nếu không, không thể thực hiện MMR nên fallback về trả về danh sách theo thứ tự điểm ban đầu.
    for c in candidates:
        if "embedding" not in c:
            print("⚠ Chú ý: Thiếu vector embedding trong candidates. MMR chuyển sang fallback trả về top_k theo điểm ban đầu.")
            return candidates[:top_k]

    selected = []
    remaining = list(range(len(candidates)))

    for _ in range(min(top_k, len(candidates))):
        best_idx = None
        best_score = float('-inf')

        for idx in remaining:
            # Độ tương đồng ngữ nghĩa của candidate với câu truy vấn
            relevance = cosine_sim(query_embedding, candidates[idx]["embedding"])

            # Độ tương đồng lớn nhất của candidate với các tài liệu đã chọn trước đó
            max_sim_to_selected = 0.0
            for sel_idx in selected:
                sim = cosine_sim(candidates[idx]["embedding"], candidates[sel_idx]["embedding"])
                max_sim_to_selected = max(max_sim_to_selected, sim)

            # Công thức tính điểm MMR
            mmr_score = lambda_param * relevance - (1.0 - lambda_param) * max_sim_to_selected

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx

        if best_idx is not None:
            selected.append(best_idx)
            remaining.remove(best_idx)

    return [candidates[i] for i in selected]



def rerank_rrf(
    ranked_lists: list[list[dict]], top_k: int = 5, k: int = 60
) -> list[dict]:
    """
    Reciprocal Rank Fusion — gộp kết quả từ nhiều ranker.

    RRF(d) = Σ 1 / (k + rank_r(d))

    Args:
        ranked_lists: List of ranked result lists (mỗi list từ 1 ranker)
        top_k: Số lượng kết quả cuối cùng
        k: Smoothing constant (default=60, từ paper Cormack et al. 2009)

    Returns:
        List of top_k candidates sorted by RRF score descending.
    """
    rrf_scores = {}  # content -> score
    content_map = {}  # content -> full dict

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, 1):
            key = item["content"]
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in content_map:
                content_map[key] = item.copy()

    # Sắp xếp theo điểm RRF giảm dần
    sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    results = []
    for content, score in sorted_items[:top_k]:
        item = content_map[content].copy()
        item["score"] = score
        results.append(item)

    return results



# =============================================================================
# Main rerank interface
# =============================================================================

def rerank(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
    method: str = "cross_encoder",  # "cross_encoder" | "mmr" | "rrf"
) -> list[dict]:
    """
    Unified reranking interface.

    Args:
        query: Câu truy vấn
        candidates: Danh sách candidates từ retrieval
        top_k: Số lượng kết quả sau rerank
        method: Phương pháp reranking

    Returns:
        List of top_k reranked candidates.
    """
    if method == "cross_encoder":
        return rerank_cross_encoder(query, candidates, top_k)
    elif method == "mmr":
        # Cần query_embedding - embed query trước
        raise NotImplementedError("Call rerank_mmr with query_embedding")
    elif method == "rrf":
        # RRF cần nhiều ranked lists - gọi riêng
        raise NotImplementedError("Call rerank_rrf with ranked_lists")
    else:
        raise ValueError(f"Unknown rerank method: {method}")


if __name__ == "__main__":
    from task5_semantic_search import semantic_search

    query = "hình phạt cho tội tàng trữ ma tuý theo pháp luật"
    print(f"Query: {query}")

    # Bước 1: Lấy các candidates thực tế từ Weaviate bằng Semantic Search
    print("\n--- Bước 1: Retrieval (Semantic Search) ---")
    candidates = semantic_search(query, top_k=10)
    for i, c in enumerate(candidates, 1):
        print(f"  {i}. [{c['score']:.3f}] {c['content'][:80]}...")

    # Bước 2: Rerank các candidates thực tế
    print("\n--- Bước 2: Reranking (Cross-Encoder) ---")
    results = rerank(query, candidates, top_k=5)
    for i, r in enumerate(results, 1):
        print(f"  {i}. [{r['score']:.3f}] {r['content'][:80]}...")
