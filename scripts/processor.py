"""
processor.py

Handles chunking, embedding and vector storage using FAISS.
Tracks which user owns which chunks AND which file each chunk belongs to.
Supports per-file semantic search for isolated knowledge bases.
"""

import os
import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from scripts.log import get_logger

logger = get_logger("Processor")

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
VECTOR_DIR = os.path.join(PROJECT_ROOT, "vectorstore")
os.makedirs(VECTOR_DIR, exist_ok=True)

INDEX_PATH = os.path.join(VECTOR_DIR, "faiss.index")
CHUNKS_PATH = os.path.join(VECTOR_DIR, "chunks.json")

EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
EMBED_DIMENSION = 384


class Processor:

    def __init__(self):
        self.logger = get_logger("Processor")
        self.chunks = []
        self.index = None
        self._load()
        self.logger.info("Processor ready")

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------
    def chunk_text(self, text, chunk_size=500, overlap=100):
        if not text or not text.strip():
            return []

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end].strip()

            if chunk:
                chunks.append(chunk)

            start = start + chunk_size - overlap

        return chunks

    # ------------------------------------------------------------------
    # Process a document — tagged with both user_id and file_id
    # ------------------------------------------------------------------
    def process(self, file_name, text, user_id, file_id=None):
        if not text or not text.strip():
            self.logger.warning(f"Empty text for {file_name}, skipping")
            return 0

        self.logger.info(f"Processing: {file_name} for user_id={user_id}, file_id={file_id}")

        # Step 1: Chunk
        text_chunks = self.chunk_text(text)
        self.logger.info(f"Created {len(text_chunks)} chunks")

        if not text_chunks:
            return 0

        # Step 2: Embed
        embeddings = EMBED_MODEL.encode(text_chunks)
        self.logger.info(f"Created {len(embeddings)} embeddings")

        # Step 3: Store chunks with user_id AND file_id
        for i, chunk in enumerate(text_chunks):
            self.chunks.append({
                "text":        chunk,
                "source":      file_name,
                "user_id":     user_id,
                "file_id":     file_id,
                "chunk_index": i
            })

        # Step 4: Add to FAISS
        embeddings_np = np.array(embeddings).astype("float32")

        if self.index is None:
            self.index = faiss.IndexFlatL2(EMBED_DIMENSION)

        self.index.add(embeddings_np)
        self.logger.info(f"Total chunks in store: {len(self.chunks)}")

        # Step 5: Save
        self._save()
        return len(text_chunks)   # return chunk count so caller can store it

    # ------------------------------------------------------------------
    # Search — optionally scoped to a specific file
    # ------------------------------------------------------------------
    def search(self, query, user_id, top_k=5, file_id=None):
        """
        Search for relevant chunks.
        - file_id given  -> search only within that specific file
        - file_id None   -> search across all of user chunks
        """
        if self.index is None or len(self.chunks) == 0:
            self.logger.warning("No documents processed yet")
            return []

        search_k = top_k * 10

        query_embedding = EMBED_MODEL.encode([query])
        query_np = np.array(query_embedding).astype("float32")

        distances, indices = self.index.search(query_np, search_k)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx >= len(self.chunks):
                continue

            chunk = self.chunks[idx]
            chunk_user_id = chunk.get("user_id")
            chunk_file_id = chunk.get("file_id")

            if chunk_user_id != user_id:
                continue

            if file_id is not None and chunk_file_id != file_id:
                continue

            results.append({
                "text":    chunk["text"],
                "source":  chunk["source"],
                "file_id": chunk_file_id,
                "score":   float(distances[0][i])
            })

            if len(results) >= top_k:
                break

        scope = f"file_id={file_id}" if file_id else "all files"
        self.logger.info(f"Found {len(results)} results for user_id={user_id} [{scope}]")
        return results

    # ------------------------------------------------------------------
    # Clear all data for a specific file
    # ------------------------------------------------------------------
    def clear_file(self, user_id, file_id):
        """Remove all chunks for a specific file and rebuild index."""
        old_count = len(self.chunks)
        remaining = [
            c for c in self.chunks
            if not (c.get("user_id") == user_id and c.get("file_id") == file_id)
        ]
        removed = old_count - len(remaining)
        self.logger.info(f"Removing {removed} chunks for user_id={user_id}, file_id={file_id}")
        self._rebuild(remaining)

    # ------------------------------------------------------------------
    # Clear all data for a specific user
    # ------------------------------------------------------------------
    def clear_user(self, user_id):
        """Remove all chunks for a specific user and rebuild index."""
        old_count = len(self.chunks)
        remaining = [c for c in self.chunks if c.get("user_id") != user_id]
        removed = old_count - len(remaining)
        self.logger.info(f"Removing {removed} chunks for user_id={user_id}")
        self._rebuild(remaining)

    # ------------------------------------------------------------------
    # Rebuild index from a given chunk list
    # ------------------------------------------------------------------
    def _rebuild(self, remaining_chunks):
        self.chunks = remaining_chunks
        self.index = None
        if self.chunks:
            texts = [c["text"] for c in self.chunks]
            embeddings = EMBED_MODEL.encode(texts)
            embeddings_np = np.array(embeddings).astype("float32")
            self.index = faiss.IndexFlatL2(EMBED_DIMENSION)
            self.index.add(embeddings_np)
        self._save()
        self.logger.info(f"Remaining chunks after rebuild: {len(self.chunks)}")

    # ------------------------------------------------------------------
    # Clear everything
    # ------------------------------------------------------------------
    def clear(self):
        self.chunks = []
        self.index = None

        if os.path.exists(INDEX_PATH):
            os.remove(INDEX_PATH)
        if os.path.exists(CHUNKS_PATH):
            os.remove(CHUNKS_PATH)

        self.logger.info("Vector store cleared")

    # ------------------------------------------------------------------
    # Save and Load
    # ------------------------------------------------------------------
    def _save(self):
        if self.index is not None:
            faiss.write_index(self.index, INDEX_PATH)

        with open(CHUNKS_PATH, "w") as f:
            json.dump(self.chunks, f)

        self.logger.debug("Saved to disk")

    def _load(self):
        if os.path.exists(INDEX_PATH) and os.path.exists(CHUNKS_PATH):
            self.index = faiss.read_index(INDEX_PATH)

            with open(CHUNKS_PATH, "r") as f:
                self.chunks = json.load(f)

            self.logger.info(f"Loaded {len(self.chunks)} chunks from disk")
        else:
            self.logger.info("No existing vector store found")


# ------------------------------------------------------------------
# Singleton instance - ensures one shared processor across the app
# ------------------------------------------------------------------
_processor_instance = None

def get_processor():
    """Get the shared processor instance."""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = Processor()
    return _processor_instance