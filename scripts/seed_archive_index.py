"""
EPM Note Engine - Archive Index Seeder

Populate ChromaDB archive_index with past articles and snippets from PostgreSQL.

Usage:
    python scripts/seed_archive_index.py

Options:
    --dry-run        Count documents without inserting
    --prune-missing  Delete documents whose DB records no longer exist
"""

import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
import sys
sys.path.insert(0, str(project_root))

from src.database.connection import get_session
from src.database.models import Article, Snippet
from src.repositories.rag_service import RAGService


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Split text into chunks with overlap."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            for sep in ["。\n", "。", "\n\n", "\n", ".", " "]:
                last_sep = text[start:end].rfind(sep)
                if last_sep > chunk_size // 2:
                    end = start + last_sep + len(sep)
                    break
        chunks.append(text[start:end].strip())
        start = end - overlap

    return [c for c in chunks if c]


def build_article_text(article: dict) -> str:
    """Build searchable text for an article (dict-based)."""
    title = article.get("title") or ""
    if not title:
        return ""

    parts = [f"# {title}"]
    if article.get("target_persona"):
        parts.append(f"ターゲット: {article.get('target_persona')}")
    if article.get("seo_keywords"):
        parts.append(f"SEOキーワード: {article.get('seo_keywords')}")
    if article.get("hook_statement"):
        parts.append(f"フック: {article.get('hook_statement')}")
    if article.get("content_outline"):
        parts.append(f"見出し案: {article.get('content_outline')}")
    if article.get("research_summary"):
        parts.append("リサーチサマリー:")
        parts.append(article.get("research_summary") or "")

    content = article.get("final_content_md") or article.get("draft_content_md") or ""
    if content:
        parts.append(content)

    return "\n\n".join(parts).strip()


def seed_archive_index(dry_run: bool = False, prune_missing: bool = False) -> dict:
    """Seed archive_index collection from DB articles and snippets."""
    stats = {
        "articles": 0,
        "snippets": 0,
        "chunks_created": 0,
        "errors": 0,
    }

    if not dry_run:
        rag_service = RAGService()

    # Load data as plain dicts to avoid detached instance issues
    articles = []
    snippets = []
    with get_session() as session:
        for article in session.query(Article).all():
            articles.append({
                "id": str(article.id),
                "week_id": article.week_id,
                "title": article.title,
                "target_persona": article.target_persona,
                "seo_keywords": article.seo_keywords,
                "hook_statement": article.hook_statement,
                "content_outline": article.content_outline,
                "research_summary": article.research_summary,
                "draft_content_md": article.draft_content_md,
                "final_content_md": article.final_content_md,
            })
        for snippet in session.query(Snippet).all():
            snippets.append({
                "id": str(snippet.id),
                "article_id": str(snippet.article_id),
                "category": str(snippet.category),
                "content": snippet.content,
            })

    current_keys = set()
    for article in articles:
        current_keys.add(("article", article["id"]))
    for snippet in snippets:
        current_keys.add(("snippet", snippet["id"]))

    if not dry_run and prune_missing:
        existing = rag_service.get_all_documents("archive_index")
        existing_keys = set()
        for meta in existing.get("metadatas", []) or []:
            if not meta:
                continue
            if meta.get("source_type") == "article" and meta.get("article_id"):
                existing_keys.add(("article", meta.get("article_id")))
            if meta.get("source_type") == "snippet" and meta.get("snippet_id"):
                existing_keys.add(("snippet", meta.get("snippet_id")))

        stale_keys = existing_keys - current_keys
        for source_type, source_id in stale_keys:
            if source_type == "article":
                rag_service.delete_by_metadata("archive_index", {"source_type": "article", "article_id": source_id})
            else:
                rag_service.delete_by_metadata("archive_index", {"source_type": "snippet", "snippet_id": source_id})

    # Insert articles
    for article in articles:
        try:
            text = build_article_text(article)
            if not text:
                continue

            chunks = chunk_text(text)
            stats["articles"] += 1
            stats["chunks_created"] += len(chunks)

            if not dry_run:
                rag_service.delete_by_metadata("archive_index", {"source_type": "article", "article_id": article["id"]})

                doc_ids = [f"article_{article['id']}_{i:03d}" for i in range(len(chunks))]
                metadatas = [{
                    "source_type": "article",
                    "article_id": article["id"],
                    "week_id": article["week_id"],
                    "title": article["title"],
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                } for i in range(len(chunks))]

                rag_service.add_documents(
                    collection_name="archive_index",
                    document_ids=doc_ids,
                    contents=chunks,
                    metadatas=metadatas,
                )
        except Exception as e:
            print(f"[ERROR] article_id={article.get('id')} title={article.get('title')}: {e}")
            stats["errors"] += 1

    # Insert snippets
    for snippet in snippets:
        try:
            content = snippet.get("content") or ""
            if not content:
                continue
            stats["snippets"] += 1
            stats["chunks_created"] += 1

            if not dry_run:
                rag_service.delete_by_metadata("archive_index", {"source_type": "snippet", "snippet_id": snippet["id"]})

                rag_service.add_document(
                    collection_name="archive_index",
                    document_id=f"snippet_{snippet['id']}",
                    content=content,
                    metadata={
                        "source_type": "snippet",
                        "snippet_id": snippet["id"],
                        "article_id": snippet["article_id"],
                        "category": snippet.get("category", ""),
                    },
                )
        except Exception as e:
            print(f"[ERROR] snippet_id={snippet.get('id')}: {e}")
            stats["errors"] += 1

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed archive_index from DB")
    parser.add_argument("--dry-run", action="store_true", help="Count without inserting")
    parser.add_argument("--prune-missing", action="store_true", help="Delete missing records")
    args = parser.parse_args()

    print("=" * 60)
    print("EPM Note Engine - Archive Index Seeder")
    print("=" * 60)

    stats = seed_archive_index(dry_run=args.dry_run, prune_missing=args.prune_missing)

    print("\nSummary:")
    print(f"  Articles processed: {stats['articles']}")
    print(f"  Snippets processed: {stats['snippets']}")
    print(f"  Chunks created: {stats['chunks_created']}")
    print(f"  Errors: {stats['errors']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
