"""
Task 8 — PageIndex Vectorless RAG.

Đăng ký tài khoản tại: https://pageindex.ai/
SDK & sample code: https://github.com/VectifyAI/PageIndex

PageIndex cho phép RAG mà không cần vector store — sử dụng
structural understanding của document thay vì embedding.

Cài đặt:
    pip install pageindex

Hướng dẫn:
    1. Đăng ký account tại pageindex.ai
    2. Lấy API key
    3. Upload documents
    4. Query sử dụng PageIndex API
"""

import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()


PAGEINDEX_API_KEY = os.getenv("PAGEINDEX_API_KEY", "")
STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"
PDF_DIR = Path(__file__).parent.parent / "data" / "pdf"


def convert_md_to_pdf(md_path: Path, pdf_path: Path):
    """
    Chuyển đổi file Markdown sang PDF sử dụng Playwright (Chromium print-to-pdf).
    """
    from markdown_it import MarkdownIt
    from playwright.sync_api import sync_playwright

    print(f"  Converting {md_path.name} -> {pdf_path.name}...")
    content = md_path.read_text(encoding="utf-8")
    
    # Render markdown to HTML
    md = MarkdownIt()
    html_content = md.render(content)

    # Basic styled HTML document
    styled_html = f"""
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 40px;
            color: #333;
        }}
        h1, h2, h3, h4, h5, h6 {{
            color: #111;
            margin-top: 20px;
        }}
        pre {{
            background: #f4f4f4;
            padding: 10px;
            border: 1px solid #ddd;
            overflow-x: auto;
        }}
        code {{
            font-family: Consolas, Monaco, monospace;
            background: #f4f4f4;
            padding: 2px 4px;
            border-radius: 3px;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin-top: 15px;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background-color: #f2f2f2;
        }}
    </style>
    </head>
    <body>
    {html_content}
    </body>
    </html>
    """

    # Ensure output folder exists
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(styled_html)
        # In thành PDF
        page.pdf(path=str(pdf_path))
        browser.close()


def upload_documents():
    """
    Convert và upload toàn bộ documents dưới dạng PDF lên PageIndex.
    """
    if not PAGEINDEX_API_KEY:
        print("PAGEINDEX_API_KEY is not set.")
        return

    from pageindex import PageIndexClient
    client = PageIndexClient(api_key=PAGEINDEX_API_KEY)

    # Lấy danh sách tài liệu hiện tại để tránh upload trùng
    try:
        existing_docs = client.list_documents().get("documents", [])
        existing_names = {d.get("name") for d in existing_docs}
    except Exception as e:
        print(f"Warning: Failed to list existing documents: {e}")
        existing_names = set()

    for md_file in STANDARDIZED_DIR.rglob("*.md"):
        # Đường dẫn PDF đích tương ứng
        pdf_file = PDF_DIR / md_file.parent.relative_to(STANDARDIZED_DIR) / (md_file.stem + ".pdf")
        
        if pdf_file.name in existing_names:
            print(f"  ✓ Already uploaded: {pdf_file.name}")
            continue

        # Convert sang PDF nếu chưa có
        if not pdf_file.exists():
            try:
                convert_md_to_pdf(md_file, pdf_file)
            except Exception as e:
                print(f"  ✗ Failed to convert {md_file.name} to PDF: {e}")
                continue

        print(f"Uploading: {pdf_file.name}...")
        try:
            res = client.submit_document(str(pdf_file))
            doc_id = res.get("doc_id")
            if doc_id:
                print(f"  ✓ Uploaded: {pdf_file.name} (Doc ID: {doc_id})")
                # Poll until ready
                import time
                start_time = time.time()
                while time.time() - start_time < 90:  # Tăng thời gian chờ lên 90s do PDF processing lâu hơn
                    if client.is_retrieval_ready(doc_id):
                        print(f"  READY: Retrieval ready for {pdf_file.name}")
                        break
                    time.sleep(3)
                else:
                    print(f"  WARNING: Timeout waiting for {pdf_file.name} to be ready.")
            else:
                print(f"  ERROR: Failed to upload {pdf_file.name}: No doc_id returned.")
        except Exception as e:
            print(f"  ERROR: Failed to upload {pdf_file.name}: {e}")


def pageindex_search(query: str, top_k: int = 5) -> list[dict]:
    """
    Vectorless retrieval sử dụng PageIndex.
    Dùng làm fallback khi hybrid search không có kết quả tốt.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,
            'score': float,
            'metadata': dict,
            'source': 'pageindex'   # Đánh dấu nguồn retrieval
        }
    """
    if not PAGEINDEX_API_KEY:
        print("PAGEINDEX_API_KEY is not set.")
        return []

    from pageindex import PageIndexClient
    import time
    client = PageIndexClient(api_key=PAGEINDEX_API_KEY)

    try:
        # Lấy danh sách các tài liệu hiện có
        docs = client.list_documents().get("documents", [])
    except Exception as e:
        print(f"Error listing documents in pageindex_search: {e}")
        return []

    if not docs:
        print("No documents found in PageIndex.")
        return []

    all_results = []
    for d in docs:
        doc_id = d.get("id")
        doc_name = d.get("name", "")
        status = d.get("status")
        if status != "completed" and not client.is_retrieval_ready(doc_id):
            print(f"Skipping {doc_name} because it is not ready (Status: {status})")
            continue

        try:
            print(f"Querying document (id {doc_id}) ...")
            # Submit query
            res = client.submit_query(doc_id, query)
            retrieval_id = res.get("retrieval_id")
            if not retrieval_id:
                continue

            # Poll for retrieval results
            start_time = time.time()
            ret_res = None
            while time.time() - start_time < 30:  # 30s timeout per document query
                ret_res = client.get_retrieval(retrieval_id)
                if ret_res.get("status") in ["completed", "success"]:
                    break
                time.sleep(1)

            if ret_res and ret_res.get("status") in ["completed", "success"]:
                results_list = ret_res.get("retrieved_nodes", []) or ret_res.get("results", []) or ret_res.get("data", [])
                for idx, r in enumerate(results_list):
                    node_contents = []
                    relevant_contents = r.get("relevant_contents", [])
                    if isinstance(relevant_contents, list):
                        for group in relevant_contents:
                            if isinstance(group, list):
                                for item in group:
                                    if isinstance(item, dict) and "relevant_content" in item:
                                        node_contents.append(item["relevant_content"])
                            elif isinstance(group, dict) and "relevant_content" in group:
                                node_contents.append(group["relevant_content"])
                    
                    if not node_contents:
                        content = r.get("text") or r.get("content") or r.get("title") or ""
                    else:
                        content = "\n\n".join(node_contents)
                    
                    # PageIndex does not return a direct score, so we use rank-based scoring starting at 1.0
                    score = r.get("score")
                    if score is None:
                        score = max(0.1, 1.0 - (idx * 0.1))
                    
                    metadata = {
                        "document_name": doc_name,
                        "doc_id": doc_id,
                        "node_id": r.get("id"),
                        "title": r.get("title", "")
                    }
                    all_results.append({
                        "content": content,
                        "score": float(score),
                        "metadata": metadata,
                        "source": "pageindex"
                    })
            else:
                print(f"Query to {doc_name} timed out or failed. status: {ret_res.get('status') if ret_res else 'None'}")
        except Exception as e:
            print(f"Error querying document (id {doc_id}): {e}")

    # Sắp xếp tất cả kết quả theo score giảm dần
    all_results.sort(key=lambda x: x["score"], reverse=True)

    # Trả về top_k kết quả
    return all_results[:top_k]


if __name__ == "__main__":
    if not PAGEINDEX_API_KEY:
        print("WARNING: Set PAGEINDEX_API_KEY in .env")
        print("  Đăng ký tại: https://pageindex.ai/")
    else:
        print("Uploading documents...")
        upload_documents()

        print("\nTest query:")
        results = pageindex_search("hình phạt sử dụng ma tuý", top_k=3)
        for r in results:
            print(f"[{r['score']:.3f}] {r['content'][:100]}...")
