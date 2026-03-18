"""
vector_store.py — ChromaDB persistent client with customer-scoped operations.
CRITICAL: every query filters by customer_id metadata — no global cross-customer search.
"""

import logging
import chromadb
from chromadb.config import Settings
from backend.config import CHROMA_PERSIST_DIR
from typing import Optional


logger = logging.getLogger(__name__)

# Module-level client — created once, reused across requests
_chroma_client: Optional[chromadb.PersistentClient] = None
_collection = None
COLLECTION_NAME = "interactions"


def _get_client() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        logger.info("ChromaDB client initialised at %s", CHROMA_PERSIST_DIR)
    return _chroma_client


def _get_collection():
    global _collection
    if _collection is None:
        client = _get_client()
        # get_or_create so re-imports don't duplicate the collection
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB collection '%s' ready.", COLLECTION_NAME)
    return _collection


def upsert_interaction(interaction_id: str, customer_id: str, text: str) -> None:
    """Store or update an interaction embedding keyed by interaction_id."""
    col = _get_collection()
    col.upsert(
        ids=[interaction_id],
        documents=[text],
        # customer_id stored in metadata so every query can filter on it
        metadatas=[{"customer_id": customer_id}],
    )
    logger.debug("Upserted interaction %s for customer %s", interaction_id, customer_id)


def query_similar(customer_id: str, text: str, n_results: int = 3) -> list[dict]:
    """
    Return top-N semantically similar interactions scoped to customer_id.
    Always applies a where-filter — never searches across all customers.
    Returns list of dicts with keys: id, document, distance.
    """
    col = _get_collection()

    # Count docs for this customer first to avoid query errors on empty collections
    existing = col.get(where={"customer_id": customer_id})
    if not existing["ids"]:
        logger.debug("No prior embeddings for customer %s — skipping similarity query.", customer_id)
        return []

    safe_n = min(n_results, len(existing["ids"]))

    results = col.query(
        query_texts=[text],
        n_results=safe_n,
        where={"customer_id": customer_id},  # NEVER remove this filter
    )

    if not results["ids"] or not results["ids"][0]:
        return []

    return [
        {
            "id": results["ids"][0][i],
            "document": results["documents"][0][i],
            "distance": results["distances"][0][i],
        }
        for i in range(len(results["ids"][0]))
    ]
