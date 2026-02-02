"""
EPM Note Engine - RAG Service

ChromaDB-based vector store service for knowledge retrieval.
Uses OpenAI text-embedding-3-small for high-quality Japanese embeddings.
"""

import logging
from dataclasses import dataclass
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions

from src.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Result from a vector similarity search."""

    id: str
    content: str
    metadata: dict[str, Any]
    distance: float


class RAGService:
    """
    Vector store service using ChromaDB for RAG operations.

    Uses OpenAI text-embedding-3-small for embeddings (high Japanese accuracy).

    Manages two collections:
    - knowledge_base: Internal documents (PDFs, markdown files)
    - archive_index: Past articles and snippets
    """

    KNOWLEDGE_BASE_COLLECTION = "knowledge_base_v2"  # New collection with OpenAI embeddings
    ARCHIVE_INDEX_COLLECTION = "archive_index_v2"

    def __init__(self, persist_directory: str | None = None) -> None:
        """
        Initialize RAG service with ChromaDB and OpenAI embeddings.

        Args:
            persist_directory: Optional path to persist data.
                             Defaults to settings.chroma_persist_directory.
        """
        settings = get_settings()
        persist_path = persist_directory or settings.chroma_persist_directory

        # Ensure directory exists
        from pathlib import Path
        Path(persist_path).mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=persist_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # Initialize OpenAI embedding function
        self._embedding_function = self._create_embedding_function(settings)

        # Initialize collections with OpenAI embeddings
        self._knowledge_base = self.client.get_or_create_collection(
            name=self.KNOWLEDGE_BASE_COLLECTION,
            metadata={
                "description": "Internal knowledge documents",
                "embedding_model": "text-embedding-3-small",
            },
            embedding_function=self._embedding_function,
        )
        self._archive_index = self.client.get_or_create_collection(
            name=self.ARCHIVE_INDEX_COLLECTION,
            metadata={
                "description": "Past articles and snippets",
                "embedding_model": "text-embedding-3-small",
            },
            embedding_function=self._embedding_function,
        )

    def _create_embedding_function(self, settings):
        """Create the embedding function based on available API keys."""
        if settings.openai_api_key:
            logger.info("Using OpenAI text-embedding-3-small for embeddings")
            return embedding_functions.OpenAIEmbeddingFunction(
                api_key=settings.openai_api_key,
                model_name="text-embedding-3-small",
            )
        else:
            logger.warning("OpenAI API key not found, using default embeddings (lower Japanese accuracy)")
            return embedding_functions.DefaultEmbeddingFunction()

    @property
    def knowledge_base(self):
        """Get knowledge base collection."""
        return self._knowledge_base

    @property
    def archive_index(self):
        """Get archive index collection."""
        return self._archive_index

    def add_document(
        self,
        collection_name: str,
        document_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Add a document to a collection.

        Args:
            collection_name: Name of the collection (knowledge_base or archive_index).
            document_id: Unique identifier for the document.
            content: Text content to store and embed.
            metadata: Optional metadata dictionary.
        """
        if not isinstance(content, str) or not content.strip():
            logger.warning("Skipping empty/non-string document: %s", document_id)
            return

        collection = self._get_collection(collection_name)
        collection.upsert(
            ids=[document_id],
            documents=[content],
            metadatas=[metadata or {}],
        )

    def add_documents(
        self,
        collection_name: str,
        document_ids: list[str],
        contents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        Add multiple documents to a collection (with batching for API limits).

        Args:
            collection_name: Name of the collection.
            document_ids: List of unique identifiers.
            contents: List of text contents.
            metadatas: Optional list of metadata dictionaries.
        """
        # Filter invalid contents to avoid embedding errors
        filtered = []
        for doc_id, content, meta in zip(document_ids, contents, metadatas or [{}] * len(document_ids)):
            if isinstance(content, str) and content.strip():
                filtered.append((doc_id, content, meta))
            else:
                logger.warning("Skipping empty/non-string document: %s", doc_id)

        if not filtered:
            return

        doc_ids = [d[0] for d in filtered]
        contents = [d[1] for d in filtered]
        metas = [d[2] for d in filtered]

        collection = self._get_collection(collection_name)

        # Batch in chunks of 100 to avoid API rate limits
        batch_size = 100
        total = len(document_ids)

        for i in range(0, total, batch_size):
            end = min(i + batch_size, total)
            batch_ids = doc_ids[i:end]
            batch_contents = contents[i:end]
            batch_metas = metas[i:end]

            logger.info(f"Inserting batch {i//batch_size + 1}/{(total + batch_size - 1)//batch_size} ({len(batch_ids)} documents)")

            collection.upsert(
                ids=batch_ids,
                documents=batch_contents,
                metadatas=batch_metas,
            )

    def search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        Search for similar documents in a collection.

        Args:
            collection_name: Name of the collection to search.
            query: Search query text.
            top_k: Number of results to return.
            where: Optional metadata filter.

        Returns:
            List of SearchResult objects.
        """
        collection = self._get_collection(collection_name)

        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
        )

        search_results = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                search_results.append(
                    SearchResult(
                        id=doc_id,
                        content=results["documents"][0][i] if results["documents"] else "",
                        metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                        distance=results["distances"][0][i] if results["distances"] else 0.0,
                    )
                )

        return search_results

    def search_knowledge_base(
        self,
        query: str,
        top_k: int = 5,
        document_type: str | None = None,
    ) -> list[SearchResult]:
        """
        Search the knowledge base collection.

        Args:
            query: Search query text.
            top_k: Number of results to return.
            document_type: Optional filter by document type.

        Returns:
            List of SearchResult objects.
        """
        where = {"document_type": document_type} if document_type else None
        return self.search(self.KNOWLEDGE_BASE_COLLECTION, query, top_k, where)

    def search_archive(
        self,
        query: str,
        top_k: int = 5,
        article_id: str | None = None,
    ) -> list[SearchResult]:
        """
        Search the archive index collection.

        Args:
            query: Search query text.
            top_k: Number of results to return.
            article_id: Optional filter by article ID.

        Returns:
            List of SearchResult objects.
        """
        where = {"article_id": article_id} if article_id else None
        return self.search(self.ARCHIVE_INDEX_COLLECTION, query, top_k, where)

    def delete_document(self, collection_name: str, document_id: str) -> None:
        """
        Delete a document from a collection.

        Args:
            collection_name: Name of the collection.
            document_id: ID of the document to delete.
        """
        collection = self._get_collection(collection_name)
        collection.delete(ids=[document_id])

    def delete_by_metadata(self, collection_name: str, where: dict[str, Any]) -> None:
        """
        Delete documents from a collection by metadata filter.

        Args:
            collection_name: Name of the collection.
            where: Metadata filter for deletion.
        """
        collection = self._get_collection(collection_name)
        # Chroma expects a single operator at the top level (e.g., $and).
        # Normalize simple dict filters into operator form.
        if not where:
            return

        if len(where) == 1:
            key, value = next(iter(where.items()))
            normalized = {key: value} if isinstance(value, dict) else {key: {"$eq": value}}
        else:
            normalized = {
                "$and": [
                    {k: v} if isinstance(v, dict) else {k: {"$eq": v}}
                    for k, v in where.items()
                ]
            }

        collection.delete(where=normalized)

    def get_all_documents(self, collection_name: str) -> dict[str, Any]:
        """
        Get all document IDs and metadata from a collection.

        Returns:
            Raw collection.get response with ids and metadatas.
        """
        collection = self._get_collection(collection_name)
        # ids are always returned by Chroma; include only metadatas to avoid validation errors
        return collection.get(include=["metadatas"])

    def get_document(
        self,
        collection_name: str,
        document_id: str,
    ) -> SearchResult | None:
        """
        Get a specific document by ID.

        Args:
            collection_name: Name of the collection.
            document_id: ID of the document.

        Returns:
            SearchResult or None if not found.
        """
        collection = self._get_collection(collection_name)
        result = collection.get(ids=[document_id])

        if result["ids"]:
            return SearchResult(
                id=result["ids"][0],
                content=result["documents"][0] if result["documents"] else "",
                metadata=result["metadatas"][0] if result["metadatas"] else {},
                distance=0.0,
            )
        return None

    def get_collection_count(self, collection_name: str) -> int:
        """
        Get the number of documents in a collection.

        Args:
            collection_name: Name of the collection.

        Returns:
            Number of documents.
        """
        collection = self._get_collection(collection_name)
        return collection.count()

    def _get_collection(self, collection_name: str):
        """Get collection by name."""
        if collection_name == self.KNOWLEDGE_BASE_COLLECTION:
            return self._knowledge_base
        elif collection_name == self.ARCHIVE_INDEX_COLLECTION:
            return self._archive_index
        # Support old collection names for backwards compatibility
        elif collection_name == "knowledge_base":
            return self._knowledge_base
        elif collection_name == "archive_index":
            return self._archive_index
        else:
            raise ValueError(f"Unknown collection: {collection_name}")

    def clear_collection(self, collection_name: str) -> None:
        """
        Clear all documents from a collection.

        Args:
            collection_name: Name of the collection to clear.
        """
        # Map old names to new names
        if collection_name == "knowledge_base":
            collection_name = self.KNOWLEDGE_BASE_COLLECTION
        elif collection_name == "archive_index":
            collection_name = self.ARCHIVE_INDEX_COLLECTION

        # Delete and recreate collection
        try:
            self.client.delete_collection(collection_name)
        except Exception as e:
            logger.warning(f"Collection {collection_name} not found: {e}")

        if collection_name == self.KNOWLEDGE_BASE_COLLECTION:
            self._knowledge_base = self.client.create_collection(
                name=self.KNOWLEDGE_BASE_COLLECTION,
                metadata={
                    "description": "Internal knowledge documents",
                    "embedding_model": "text-embedding-3-small",
                },
                embedding_function=self._embedding_function,
            )
        elif collection_name == self.ARCHIVE_INDEX_COLLECTION:
            self._archive_index = self.client.create_collection(
                name=self.ARCHIVE_INDEX_COLLECTION,
                metadata={
                    "description": "Past articles and snippets",
                    "embedding_model": "text-embedding-3-small",
                },
                embedding_function=self._embedding_function,
            )

    def get_embedding_info(self) -> dict:
        """Get information about the embedding model being used."""
        is_openai = "OpenAI" in type(self._embedding_function).__name__
        return {
            "model": "text-embedding-3-small" if is_openai else "default",
            "provider": "OpenAI" if is_openai else "Local",
            "knowledge_base_count": self.get_collection_count(self.KNOWLEDGE_BASE_COLLECTION),
            "archive_count": self.get_collection_count(self.ARCHIVE_INDEX_COLLECTION),
        }
