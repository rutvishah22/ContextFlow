"""
preload.py — load two sample customers with two interactions each into MongoDB and ChromaDB.
Run this once; re-running is safe — duplicate check prevents double-insertion.

Usage (from project root):
    python -m sample_data.preload
"""

import sys
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta

# Allow running from project root without installing the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.config import GROQ_API_KEY, MONGODB_URI  # validates env vars early
from backend.db import get_interactions, get_commitments, ensure_indexes
from backend.vector_store import upsert_interaction

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def _iso(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


# ─────────────────────────────── Sample Data ──────────────────────────────────

CUSTOMERS = [
    {
        "customer_id": "cust_priya_001",
        "customer_name": "Priya Sharma",
        "interactions": [
            {
                "days_ago": 14,
                "raw_input": (
                    "Had an introductory call with Priya from TechNova. She was very enthusiastic "
                    "about our product — asked for a detailed demo next week. Her main concern was "
                    "whether we support SSO integration. I promised to send the pricing deck and "
                    "schedule a demo by Friday. She confirmed her budget is approved."
                ),
                "extracted": {
                    "intent": "interested",
                    "objections": ["SSO integration support unclear"],
                    "sentiment": "positive",
                    "language_detected": "english",
                },
                "commitments": [
                    {
                        "description": "Send pricing deck to Priya by Friday",
                        "owner": "rep",
                        "status": "fulfilled",
                        "confidence_score": 0.9,
                        "vague_reason": None,
                        "due_date": "Friday",
                    },
                    {
                        "description": "Schedule a product demo for next week",
                        "owner": "rep",
                        "status": "pending",
                        "confidence_score": 0.85,
                        "vague_reason": None,
                        "due_date": "Next week",
                    },
                ],
            },
            {
                "days_ago": 7,
                "raw_input": (
                    "Follow-up call with Priya. She said the pricing is on the higher side — "
                    "comparing us with a competitor. She mentioned SSO still feels risky. "
                    "She said 'I need to think about it, will reconnect with my team and let you know.' "
                    "Did not commit to a specific date. Mood seemed less excited than before."
                ),
                "extracted": {
                    "intent": "neutral",
                    "objections": ["pricing too high", "SSO integration concern persists", "competitor comparison"],
                    "sentiment": "neutral",
                    "language_detected": "english",
                },
                "commitments": [
                    {
                        "description": "Will reconnect after discussing with team — no specific date given",
                        "owner": "customer",
                        "status": "vague",
                        "confidence_score": 0.3,
                        "vague_reason": "No timeline specified; customer said 'let you know' without a date or concrete next step.",
                        "due_date": None,
                    },
                ],
            },
        ],
    },
    {
        "customer_id": "cust_rahul_002",
        "customer_name": "Rahul Mehta",
        "interactions": [
            {
                "days_ago": 10,
                "raw_input": (
                    "Rahul from FastMove Logistics reported a critical bug — their API integration "
                    "keeps throwing 503 errors during peak load. They process 5000+ shipments daily "
                    "and this is costing them money. I told him our engineering team will investigate "
                    "and push a fix within 48 hours. He accepted but said this is urgent."
                ),
                "extracted": {
                    "intent": "neutral",
                    "objections": ["critical API integration bug causing 503 errors"],
                    "sentiment": "negative",
                    "language_detected": "english",
                },
                "commitments": [
                    {
                        "description": "Engineering team to fix API 503 errors within 48 hours",
                        "owner": "rep",
                        "status": "overdue",
                        "confidence_score": 0.95,
                        "vague_reason": None,
                        "due_date": "48 hours from 10 days ago",
                    },
                ],
            },
            {
                "days_ago": 2,
                "raw_input": (
                    "Rahul called back very frustrated. The API bug is STILL not fixed. He said "
                    "'You promised 48 hours and it's been over a week. This is unacceptable. "
                    "I'm evaluating other vendors now.' He demanded a call with a senior engineer "
                    "today or he will escalate to his CTO."
                ),
                "extracted": {
                    "intent": "not_interested",
                    "objections": [
                        "repeated broken promise on API fix",
                        "considering switching vendors",
                        "demanding senior engineer escalation",
                    ],
                    "sentiment": "negative",
                    "language_detected": "english",
                },
                "commitments": [
                    {
                        "description": "Escalate to senior engineer and set up call with Rahul today",
                        "owner": "rep",
                        "status": "pending",
                        "confidence_score": 0.92,
                        "vague_reason": None,
                        "due_date": "Today",
                    },
                ],
            },
        ],
    },
]


# ─────────────────────────────── Loader ───────────────────────────────────────

def load():
    ensure_indexes()
    interactions_col = get_interactions()
    commitments_col = get_commitments()

    for customer in CUSTOMERS:
        cid = customer["customer_id"]
        cname = customer["customer_name"]

        for idx, interaction in enumerate(customer["interactions"]):
            ts = _iso(interaction["days_ago"])

            # Duplicate check — skip if an interaction with same customer_id and timestamp already exists
            existing = interactions_col.find_one({"customer_id": cid, "timestamp": ts})
            if existing:
                logger.info("Skipping duplicate interaction for %s (index %d).", cname, idx)
                continue

            iid = str(uuid.uuid4())

            # Insert interaction
            interaction_doc = {
                "interaction_id": iid,
                "customer_id": cid,
                "customer_name": cname,
                "timestamp": ts,
                "raw_input": interaction["raw_input"],
                "extracted": interaction["extracted"],
            }
            interactions_col.insert_one(interaction_doc)
            logger.info("Inserted interaction %s for %s.", iid, cname)

            # Index in ChromaDB
            upsert_interaction(iid, cid, interaction["raw_input"])

            # Insert commitments linked to this interaction
            for commitment in interaction.get("commitments", []):
                # Duplicate check on commitment description + customer_id
                existing_c = commitments_col.find_one(
                    {"customer_id": cid, "description": commitment["description"]}
                )
                if existing_c:
                    logger.info("Skipping duplicate commitment for %s.", cname)
                    continue

                commitment_doc = {
                    "commitment_id": str(uuid.uuid4()),
                    "customer_id": cid,
                    "description": commitment["description"],
                    "owner": commitment["owner"],
                    "status": commitment["status"],
                    "confidence_score": commitment["confidence_score"],
                    "vague_reason": commitment.get("vague_reason"),
                    "due_date": commitment.get("due_date"),
                    "created_at": ts,
                    "updated_at": ts,
                    "source_interaction_id": iid,
                }
                commitments_col.insert_one(commitment_doc)
                logger.info(
                    "Inserted commitment '%s' (status=%s) for %s.",
                    commitment["description"][:50],
                    commitment["status"],
                    cname,
                )

    logger.info("Sample data load complete.")


if __name__ == "__main__":
    load()
