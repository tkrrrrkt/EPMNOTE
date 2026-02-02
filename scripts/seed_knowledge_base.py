"""
EPM Note Engine - Knowledge Base Seeder

91_RefDoc/ 配下の資料をChromaDBのknowledge_baseコレクションに投入する。

使い方:
    python scripts/seed_knowledge_base.py

対応形式:
    - .md (Markdown)
    - .txt (テキスト)
    - .json (JSON - DeepResearch結果など)

フォルダ構造による自動カテゴリ分け:
    91_RefDoc/01_参考サイト/   → document_type: "web_reference"
    91_RefDoc/02_生成AIとのやりとり履歴/ → document_type: "ai_conversation"
    91_RefDoc/03_本/           → document_type: "book_note"
    91_RefDoc/04_DeepResearch/ → document_type: "deep_research"
    91_RefDoc/その他/          → document_type: "general"
"""

import hashlib
import json
import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.repositories.rag_service import RAGService

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


# カテゴリマッピング
FOLDER_TO_DOCTYPE = {
    "01_": "web_reference",
    "02_": "ai_conversation",
    "03_": "book_note",
    "04_": "deep_research",
    "05_": "article_candidate",
}


def sanitize_text(text: str) -> str:
    """Remove control characters that can break embeddings."""
    if not isinstance(text, str):
        text = str(text)
    # Remove null bytes and non-printable control chars (keep \n, \r, \t)
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)


def get_document_type(file_path: Path) -> str:
    """ファイルパスからドキュメントタイプを推定する。"""
    path_str = str(file_path)
    for prefix, doc_type in FOLDER_TO_DOCTYPE.items():
        if prefix in path_str:
            return doc_type
    return "general"


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """
    テキストをチャンクに分割する。

    Args:
        text: 分割するテキスト
        chunk_size: チャンクの最大文字数
        overlap: チャンク間のオーバーラップ文字数

    Returns:
        チャンクのリスト
    """
    text = sanitize_text(text)
    if len(text) <= chunk_size:
        return [text.strip()]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size

        # 文の途中で切らないように調整
        if end < len(text):
            # 句点、改行で区切る
            for sep in ["。\n", "。", "\n\n", "\n", ".", " "]:
                last_sep = text[start:end].rfind(sep)
                if last_sep > chunk_size // 2:
                    end = start + last_sep + len(sep)
                    break

        chunks.append(text[start:end].strip())
        start = end - overlap

    return [c for c in chunks if c and c.strip()]  # 空のチャンクを除去


def read_text_with_fallback(file_path: Path) -> str:
    """Read text with UTF-8 fallback to CP932 for Windows docs."""
    try:
        return sanitize_text(file_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return sanitize_text(file_path.read_text(encoding="cp932", errors="ignore"))


def read_markdown(file_path: Path) -> tuple[str, dict]:
    """Markdownファイルを読み込む。"""
    content = read_text_with_fallback(file_path)

    # タイトルを抽出
    title_match = re.match(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1) if title_match else file_path.stem

    metadata = {
        "title": title,
        "source_path": str(file_path),
        "file_type": "markdown",
    }

    return content, metadata


def read_text(file_path: Path) -> tuple[str, dict]:
    """テキストファイルを読み込む。"""
    content = read_text_with_fallback(file_path)

    metadata = {
        "title": file_path.stem,
        "source_path": str(file_path),
        "file_type": "text",
    }

    return content, metadata


def read_json(file_path: Path) -> tuple[str, dict]:
    """JSONファイルを読み込む（DeepResearch結果など）。"""
    data = json.loads(read_text_with_fallback(file_path))

    # JSON構造に応じてテキスト化
    if isinstance(data, dict):
        # よくある形式: {"content": "...", "summary": "..."}
        content_parts = []
        for key in ["content", "summary", "text", "body", "result"]:
            if key in data and isinstance(data[key], str):
                content_parts.append(data[key])

        if not content_parts:
            # フォールバック: 全体をJSON文字列として
            content = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            content = "\n\n".join(content_parts)

        title = data.get("title", data.get("query", file_path.stem))
    else:
        content = json.dumps(data, ensure_ascii=False, indent=2)
        title = file_path.stem

    metadata = {
        "title": title,
        "source_path": str(file_path),
        "file_type": "json",
    }

    return content, metadata


def read_pdf(file_path: Path) -> tuple[str, dict]:
    """PDFファイルを読み込む。"""
    if PdfReader is None:
        raise ValueError("pypdf is not installed")

    reader = PdfReader(str(file_path))
    pages_text = []
    for page in reader.pages:
        try:
            pages_text.append(page.extract_text() or "")
        except Exception:
            continue

    content = sanitize_text("\n\n".join([t for t in pages_text if t and t.strip()]))
    metadata = {
        "title": file_path.stem,
        "source_path": str(file_path),
        "file_type": "pdf",
        "page_count": len(reader.pages),
    }

    return content, metadata


def process_file(file_path: Path, ref_doc_dir: Path) -> list[tuple[str, str, dict]]:
    """
    ファイルを処理してチャンクのリストを返す。

    Returns:
        (document_id, content, metadata) のタプルのリスト
    """
    suffix = file_path.suffix.lower()

    try:
        if suffix == ".md":
            content, metadata = read_markdown(file_path)
        elif suffix == ".txt":
            content, metadata = read_text(file_path)
        elif suffix == ".json":
            content, metadata = read_json(file_path)
        elif suffix == ".pdf":
            content, metadata = read_pdf(file_path)
        else:
            return []

        # ドキュメントタイプを追加
        metadata["document_type"] = get_document_type(file_path)
        metadata["source_rel_path"] = str(file_path.relative_to(ref_doc_dir))
        metadata["file_hash"] = hashlib.sha256(file_path.read_bytes()).hexdigest()

        # チャンクに分割
        chunks = chunk_text(content)

        results = []
        for i, chunk in enumerate(chunks):
            rel_hash = hashlib.sha1(str(metadata["source_rel_path"]).encode("utf-8")).hexdigest()[:12]
            doc_id = f"{rel_hash}_{i:03d}"
            chunk_metadata = {
                **metadata,
                "chunk_index": i,
                "total_chunks": len(chunks),
            }
            results.append((doc_id, chunk, chunk_metadata))

        return results

    except Exception as e:
        print(f"  Error processing {file_path}: {e}")
        return []


def seed_knowledge_base(ref_doc_dir: Path, dry_run: bool = False, prune_missing: bool = False) -> dict:
    """
    91_RefDoc/ 配下のファイルをknowledge_baseに投入する。

    Args:
        ref_doc_dir: 91_RefDoc ディレクトリのパス
        dry_run: Trueの場合、実際には投入せずカウントのみ

    Returns:
        統計情報の辞書
    """
    if not ref_doc_dir.exists():
        print(f"Error: Directory not found: {ref_doc_dir}")
        return {}

    print(f"Scanning: {ref_doc_dir}")

    # 対象ファイルを収集
    supported_extensions = {".md", ".txt", ".json", ".pdf"}
    files = [
        f for f in ref_doc_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in supported_extensions
    ]

    print(f"Found {len(files)} files to process")

    if not dry_run:
        rag_service = RAGService()
        if prune_missing:
            existing = rag_service.get_all_documents("knowledge_base")
            existing_paths = set()
            for meta in existing.get("metadatas", []) or []:
                if meta and meta.get("source_path"):
                    existing_paths.add(meta.get("source_path"))
            current_paths = set(str(f) for f in files)
            stale_paths = existing_paths - current_paths
            for stale_path in stale_paths:
                rag_service.delete_by_metadata("knowledge_base", {"source_path": stale_path})
        # 既存のknowledge_baseをクリア（オプション）
        # rag_service.clear_collection("knowledge_base")

    stats = {
        "files_processed": 0,
        "chunks_created": 0,
        "by_document_type": {},
        "errors": 0,
    }

    all_documents = []

    for file_path in files:
        print(f"  Processing: {file_path.relative_to(ref_doc_dir)}")

        chunks = process_file(file_path, ref_doc_dir)
        if chunks:
            if not dry_run:
                rag_service.delete_by_metadata("knowledge_base", {"source_path": str(file_path)})
            all_documents.extend(chunks)
            stats["files_processed"] += 1
            stats["chunks_created"] += len(chunks)

            doc_type = chunks[0][2].get("document_type", "unknown")
            stats["by_document_type"][doc_type] = stats["by_document_type"].get(doc_type, 0) + len(chunks)
        else:
            stats["errors"] += 1

    # バッチで投入
    if not dry_run and all_documents:
        print(f"\nInserting {len(all_documents)} chunks into ChromaDB...")

        doc_ids = [d[0] for d in all_documents]
        contents = [d[1] for d in all_documents]
        metadatas = [d[2] for d in all_documents]

        rag_service.add_documents(
            collection_name="knowledge_base",
            document_ids=doc_ids,
            contents=contents,
            metadatas=metadatas,
        )

        print(f"Successfully inserted {len(all_documents)} chunks")

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Seed knowledge base from 91_RefDoc")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count files without actually inserting",
    )
    parser.add_argument(
        "--prune-missing",
        action="store_true",
        help="Delete documents whose source files no longer exist",
    )
    parser.add_argument(
        "--ref-doc-dir",
        type=Path,
        default=project_root / "91_RefDoc",
        help="Path to reference documents directory",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("EPM Note Engine - Knowledge Base Seeder")
    print("=" * 60)

    if args.dry_run:
        print("DRY RUN MODE - No data will be inserted")

    stats = seed_knowledge_base(
        args.ref_doc_dir,
        dry_run=args.dry_run,
        prune_missing=args.prune_missing,
    )

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Files processed: {stats.get('files_processed', 0)}")
    print(f"  Chunks created: {stats.get('chunks_created', 0)}")
    print(f"  Errors: {stats.get('errors', 0)}")
    print("\nBy document type:")
    for doc_type, count in stats.get("by_document_type", {}).items():
        print(f"  {doc_type}: {count} chunks")
    print("=" * 60)


if __name__ == "__main__":
    main()
