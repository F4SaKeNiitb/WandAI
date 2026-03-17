"""
RAG Pipeline — document ingestion, chunking, ChromaDB vector storage, and semantic retrieval.
Enables agents to ground responses in user-provided documents.
"""

import os
import uuid
from datetime import datetime
from typing import Optional

from langchain.text_splitter import RecursiveCharacterTextSplitter

from core.logging import get_logger

logger = get_logger("RAG")


class RAGPipeline:
    """
    Retrieval-Augmented Generation pipeline.
    Handles document ingestion, chunking, embedding, and retrieval via ChromaDB.
    """

    def __init__(
        self,
        persist_dir: str = "./chroma_data",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        chroma_host: Optional[str] = None,
        chroma_port: Optional[int] = None,
    ):
        self.persist_dir = persist_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._client = None
        self._embeddings = None
        self._chroma_host = chroma_host
        self._chroma_port = chroma_port

    def _get_client(self):
        """Lazy-init ChromaDB client."""
        if self._client is None:
            import chromadb

            if self._chroma_host:
                self._client = chromadb.HttpClient(
                    host=self._chroma_host,
                    port=self._chroma_port or 8001,
                )
            else:
                self._client = chromadb.PersistentClient(path=self.persist_dir)
        return self._client

    def _get_embeddings(self):
        """Lazy-init embedding model."""
        if self._embeddings is None:
            from rag.embeddings import get_embeddings

            self._embeddings = get_embeddings()
        return self._embeddings

    def _collection_name(self, session_id: str) -> str:
        """Sanitize session_id into a valid ChromaDB collection name."""
        safe = session_id.replace("-", "_")[:50]
        return f"rag_{safe}"

    def _detect_and_load(self, file_bytes: bytes, filename: str) -> str:
        """Detect file type and extract text content."""
        ext = os.path.splitext(filename)[1].lower()

        if ext == ".pdf":
            from pypdf import PdfReader
            import io

            reader = PdfReader(io.BytesIO(file_bytes))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)

        elif ext == ".csv":
            text = file_bytes.decode("utf-8", errors="replace")

        elif ext in (".md", ".txt", ".text"):
            text = file_bytes.decode("utf-8", errors="replace")

        else:
            # Best-effort decode
            text = file_bytes.decode("utf-8", errors="replace")

        return text

    def ingest_document(
        self,
        file_bytes: bytes,
        filename: str,
        session_id: str,
    ) -> dict:
        """
        Ingest a document: detect type, split into chunks, embed, store in ChromaDB.

        Returns metadata dict with doc_id, chunk_count, etc.
        """
        text = self._detect_and_load(file_bytes, filename)

        if not text.strip():
            raise ValueError(f"No text content extracted from {filename}")

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        chunks = splitter.split_text(text)

        doc_id = str(uuid.uuid4())[:8]
        collection = self._get_client().get_or_create_collection(
            name=self._collection_name(session_id),
        )

        # Embed chunks
        embeddings_model = self._get_embeddings()
        embeddings = embeddings_model.embed_documents(chunks)

        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "doc_id": doc_id,
                "filename": filename,
                "chunk_index": i,
                "session_id": session_id,
            }
            for i in range(len(chunks))
        ]

        collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info(
            f"Ingested '{filename}' into session {session_id[:8]}: "
            f"{len(chunks)} chunks"
        )

        return {
            "doc_id": doc_id,
            "filename": filename,
            "chunk_count": len(chunks),
            "char_count": len(text),
            "ingested_at": datetime.now().isoformat(),
        }

    def query(
        self,
        query_text: str,
        session_id: str,
        k: int = 5,
    ) -> list[dict]:
        """
        Similarity search against uploaded documents for a session.

        Returns list of {content, metadata, distance} dicts.
        """
        client = self._get_client()
        col_name = self._collection_name(session_id)

        try:
            collection = client.get_collection(col_name)
        except Exception:
            return []

        if collection.count() == 0:
            return []

        embeddings_model = self._get_embeddings()
        query_embedding = embeddings_model.embed_query(query_text)

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, collection.count()),
        )

        docs = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else None
                docs.append(
                    {"content": doc, "metadata": meta, "distance": distance}
                )
        return docs

    def delete_collection(self, session_id: str) -> bool:
        """Delete all documents for a session."""
        client = self._get_client()
        col_name = self._collection_name(session_id)
        try:
            client.delete_collection(col_name)
            logger.info(f"Deleted collection for session {session_id[:8]}")
            return True
        except Exception:
            return False

    def list_documents(self, session_id: str) -> list[dict]:
        """List unique documents uploaded to a session."""
        client = self._get_client()
        col_name = self._collection_name(session_id)
        try:
            collection = client.get_collection(col_name)
        except Exception:
            return []

        all_meta = collection.get(include=["metadatas"])
        seen: dict[str, dict] = {}
        for meta in all_meta.get("metadatas", []):
            doc_id = meta.get("doc_id", "unknown")
            if doc_id not in seen:
                seen[doc_id] = {
                    "doc_id": doc_id,
                    "filename": meta.get("filename", "unknown"),
                    "session_id": session_id,
                }
        return list(seen.values())
