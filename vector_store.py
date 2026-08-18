"""
vector_store.py
Embeds text chunks and stores them in a local ChromaDB collection.

Free-tier only:
- Chroma's built-in embedding function (ONNX MiniLM-L6-v2) -> embeddings
  computed LOCALLY, no API key, no per-call cost. This replaces
  OpenAIEmbeddings from the paid version, and is lighter than
  sentence-transformers since it doesn't need PyTorch.
- ChromaDB persistent client -> stored on disk, no signup, no API key
"""

from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from ingestion import Chunk


class VectorStoreManager:
    """Wraps Chroma + a local embedding model behind a simple interface."""

    def __init__(self, persist_dir: str = "./chroma_db", collection_name: str = "documents"):
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        # Local ONNX embedding model (all-MiniLM-L6-v2 under the hood).
        # Downloads once (~80MB) then runs fully offline, no torch needed.
        self.embedder = embedding_functions.DefaultEmbeddingFunction()

        # Chroma's PersistentClient writes to disk so your data survives
        # between runs -- no separate DB server to manage.
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedder,
        )

    def add_chunks(self, chunks: list[Chunk], user_id: str) -> int:
        """Embed a list of Chunks and add them, tagged to a specific user."""
        if not chunks:
            return 0

        texts = [c.content for c in chunks]

        # Prefix every id with user_id -- without this, two different
        # users uploading a file with the same name would collide and
        # overwrite each other's chunks (upsert treats matching ids as
        # "update", so this is a real isolation bug if skipped).
        ids = [
            f"{user_id}::{c.source}::{c.metadata.get('chunk', i)}"
            for i, c in enumerate(chunks)
        ]
        metadatas = [
            {
                "source": c.source,
                "doc_type": c.doc_type,
                "filename": c.metadata.get("filename", ""),
                "user_id": user_id,
            }
            for c in chunks
        ]

        self.collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
        )
        return len(chunks)

    def search(self, query: str, user_id: str, k: int = 5) -> list[dict]:
        """Semantic search, scoped to only this user's chunks.

        The `where` filter runs at the database level -- Chroma never
        even considers another user's vectors as candidates, rather than
        fetching everything and filtering results afterward.
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=k,
            where={"user_id": {"$eq": user_id}},
        )

        hits = []
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]

        for doc, meta, dist in zip(docs, metas, dists):
            hits.append({
                "content": doc,
                "source": meta.get("source"),
                "doc_type": meta.get("doc_type"),
                "distance": dist,
            })
        return hits

    def source_exists(self, filename: str, user_id: str) -> bool:
        """Has this user already ingested a file with this name?"""
        existing = self.collection.get(
            where={
                "$and": [
                    {"filename": {"$eq": filename}},
                    {"user_id": {"$eq": user_id}},
                ]
            }
        )
        return len(existing["ids"]) > 0

    def count(self, user_id: str | None = None) -> int:
        """Total chunks stored, or just this user's if user_id is given."""
        if user_id is None:
            return self.collection.count()
        existing = self.collection.get(where={"user_id": {"$eq": user_id}})
        return len(existing["ids"])