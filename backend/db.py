"""
db.py — MongoDB connection, collection handles, and index setup.
Call ensure_indexes() on application startup.
"""

import logging
from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection
from backend.config import MONGODB_URI, MONGO_DB_NAME, MONGO_INTERACTIONS_COL, MONGO_COMMITMENTS_COL

logger = logging.getLogger(__name__)

# Module-level client — reused across requests (pymongo is thread-safe)
_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
        logger.info("MongoDB client initialised.")
    return _client


def get_interactions() -> Collection:
    return get_client()[MONGO_DB_NAME][MONGO_INTERACTIONS_COL]


def get_commitments() -> Collection:
    return get_client()[MONGO_DB_NAME][MONGO_COMMITMENTS_COL]


def ensure_indexes() -> None:
    """Create indexes on customer_id for fast per-customer retrieval."""
    interactions = get_interactions()
    commitments = get_commitments()

    # Create index only if it doesn't exist — idempotent
    interactions.create_index([("customer_id", ASCENDING)], name="idx_interactions_customer_id")
    commitments.create_index([("customer_id", ASCENDING)], name="idx_commitments_customer_id")
    logger.info("MongoDB indexes ensured.")
