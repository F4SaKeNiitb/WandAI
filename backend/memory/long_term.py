"""
Cross-session agent memory — agents recall past interactions and reference
historical context for improved task completion.
Uses ChromaDB for vector-based semantic search across past interactions.
"""

import uuid
from datetime import datetime
from typing import Optional

from core.logging import get_logger

logger = get_logger("MEMORY")


class AgentMemory:
    """
    Long-term vector memory for agents.
    Stores past interaction summaries and allows semantic recall.
    """

    COLLECTION_NAME = "agent_memory"

    def __init__(
        self,
        persist_dir: str = "./chroma_data",
        chroma_host: Optional[str] = None,
        chroma_port: Optional[int] = None,
        max_recall_results: int = 3,
    ):
        self.persist_dir = persist_dir
        self._client = None
        self._embeddings = None
        self._chroma_host = chroma_host
        self._chroma_port = chroma_port
        self.max_recall_results = max_recall_results

    def _get_client(self):
        if self._client is None:
            try:
                import chromadb

                if self._chroma_host:
                    self._client = chromadb.HttpClient(
                        host=self._chroma_host,
                        port=self._chroma_port or 8001,
                    )
                else:
                    self._client = chromadb.PersistentClient(path=self.persist_dir)
            except Exception as e:
                logger.warning(f"Failed to initialize ChromaDB client: {e}")
                return None
        return self._client

    def _get_embeddings(self):
        if self._embeddings is None:
            from rag.embeddings import get_embeddings

            self._embeddings = get_embeddings()
        return self._embeddings

    def _get_collection(self):
        try:
            client = self._get_client()
            if client is None:
                return None
            return client.get_or_create_collection(name=self.COLLECTION_NAME)
        except Exception as e:
            logger.warning(f"Failed to get ChromaDB collection: {e}")
            return None

    def store_interaction(
        self,
        session_id: str,
        agent_type: str,
        task: str,
        result: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Store an agent interaction for future recall.

        Returns the memory_id.
        """
        memory_id = str(uuid.uuid4())[:12]
        text = f"Task: {task}\nResult: {str(result)[:2000]}"

        try:
            embeddings_model = self._get_embeddings()
            embedding = embeddings_model.embed_query(text)

            meta = {
                "session_id": session_id,
                "agent_type": agent_type,
                "task_preview": task[:200],
                "stored_at": datetime.now().isoformat(),
            }
            if metadata:
                meta.update({k: str(v)[:200] for k, v in metadata.items()})

            collection = self._get_collection()
            collection.add(
                ids=[memory_id],
                documents=[text],
                embeddings=[embedding],
                metadatas=[meta],
            )

            logger.debug(
                f"Stored memory {memory_id} for agent={agent_type}, "
                f"session={session_id[:8]}"
            )
        except Exception as e:
            logger.warning(f"Failed to store interaction in memory: {e}")
        return memory_id

    def recall(
        self,
        query: str,
        agent_type: Optional[str] = None,
        k: Optional[int] = None,
    ) -> list[dict]:
        """
        Semantic search across past interactions.

        Args:
            query: search query
            agent_type: optional filter by agent type
            k: max results (defaults to self.max_recall_results)
        """
        k = k or self.max_recall_results
        try:
            collection = self._get_collection()

            if collection.count() == 0:
                return []

            embeddings_model = self._get_embeddings()
            query_embedding = embeddings_model.embed_query(query)

            where_filter = {"agent_type": agent_type} if agent_type else None

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(k, collection.count()),
                where=where_filter,
            )

            memories = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    dist = results["distances"][0][i] if results["distances"] else None
                    memories.append({
                        "content": doc,
                        "metadata": meta,
                        "relevance_score": 1.0 - (dist or 0.0),
                    })
            return memories
        except Exception as e:
            logger.warning(f"Failed to recall from memory: {e}")
            return []

    def get_session_summary(self, session_id: str) -> list[dict]:
        """Get all stored interactions for a session."""
        collection = self._get_collection()
        if collection.count() == 0:
            return []

        results = collection.get(
            where={"session_id": session_id},
            include=["documents", "metadatas"],
        )

        summaries = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                summaries.append({"content": doc, "metadata": meta})
        return summaries

    def clear_all(self) -> bool:
        """Clear all agent memory."""
        try:
            client = self._get_client()
            client.delete_collection(self.COLLECTION_NAME)
            logger.info("Cleared all agent memory")
            return True
        except Exception:
            return False
