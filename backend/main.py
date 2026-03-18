"""
main.py — FastAPI application with three API routes.
All business logic lives in agent.py and db.py; routes are thin adapters.
"""

import logging
from contextlib import asynccontextmanager

from datetime import datetime as _datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.db import ensure_indexes, get_interactions, get_commitments
from backend.models import AddInteractionRequest, UpdateCommitmentRequest
from backend.agent import run_pipeline

# Configure logging once at the application entry point
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup hook — create MongoDB indexes before accepting requests."""
    ensure_indexes()
    logger.info("ContextFlow API ready.")
    yield


app = FastAPI(
    title="ContextFlow API",
    description="Follow-up & Context Intelligence Agent for sales/support/ops",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow Streamlit (and other front-ends) to call the API from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the vanilla HTML/CSS/JS frontend."""
    return FileResponse("static/index.html")


# ─────────────────────────────── POST /add-interaction ────────────────────────

@app.post("/add-interaction")
async def add_interaction(body: AddInteractionRequest) -> dict:
    """
    Ingest a raw interaction note and run the full 5-step ContextFlow pipeline.
    Returns structured output and all open commitments for the customer.
    """
    # Edge case 6 — reject empty or gibberish input before touching the LLM
    if not body.raw_input or len(body.raw_input.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="raw_input must be at least 10 non-whitespace characters.",
        )
    if not body.customer_id or not body.customer_id.strip():
        raise HTTPException(status_code=400, detail="customer_id is required.")

    try:
        result = run_pipeline(
            customer_id=body.customer_id.strip(),
            customer_name=body.customer_name.strip() if body.customer_name else "",
            raw_input=body.raw_input.strip(),
        )

        # Append all current commitments (including newly created) to the response
        all_commitments = list(
            get_commitments().find(
                {"customer_id": body.customer_id.strip()},
                {"_id": 0},
            ).sort("created_at", -1)
        )
        # Serialise datetime objects to strings
        for c in all_commitments:
            for k in ("created_at", "updated_at"):
                if hasattr(c.get(k), "isoformat"):
                    c[k] = c[k].isoformat()

        return {**result, "all_commitments": all_commitments}

    except Exception as exc:
        logger.error("Pipeline error for customer %s: %s", body.customer_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(exc)}")


# ─────────────────────────────── GET /get-customer/{customer_id} ──────────────

@app.get("/get-customer/{customer_id}")
async def get_customer(customer_id: str) -> dict:
    """Return all interactions and commitments for a customer, chronologically."""
    interactions = list(
        get_interactions()
        .find({"customer_id": customer_id}, {"_id": 0})
        .sort("timestamp", 1)
    )
    commitments = list(
        get_commitments()
        .find({"customer_id": customer_id}, {"_id": 0})
        .sort("created_at", -1)
    )

    # Serialise datetime objects
    for doc in interactions + commitments:
        for k in ("timestamp", "created_at", "updated_at"):
            if hasattr(doc.get(k), "isoformat"):
                doc[k] = doc[k].isoformat()

    return {
        "customer_id": customer_id,
        "interactions": interactions,
        "commitments": commitments,
    }


# ─────────────────────────────── POST /update-commitment ──────────────────────

VALID_STATUSES = {"pending", "fulfilled", "overdue", "cancelled", "vague"}


@app.post("/update-commitment")
async def update_commitment(body: UpdateCommitmentRequest) -> dict:
    """Manually override the status of a commitment."""
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )

    result = get_commitments().update_one(
        {"commitment_id": body.commitment_id},
        {"$set": {"status": body.status, "updated_at": __import__("datetime").datetime.utcnow()}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Commitment {body.commitment_id} not found.")

    logger.info("Commitment %s manually updated to '%s'.", body.commitment_id, body.status)
    return {"commitment_id": body.commitment_id, "status": body.status, "updated": True}


# ─────────────────────────────── GET /customers ───────────────────────────────

@app.get("/customers")
async def list_customers() -> list:
    """Return all unique customers (id + name) from the interactions collection."""
    pipeline = [
        {"$group": {"_id": "$customer_id", "customer_name": {"$first": "$customer_name"}}},
        {"$sort": {"customer_name": 1}},
    ]
    results = list(get_interactions().aggregate(pipeline))
    return [
        {"customer_id": r["_id"], "customer_name": r.get("customer_name", "Unknown")}
        for r in results
    ]


# ─────────────────────────────── GET /pending-commitments ─────────────────────

@app.get("/pending-commitments")
async def pending_commitments() -> list:
    """Return all pending/overdue/vague commitments across all customers."""
    docs = list(
        get_commitments()
        .find(
            {"status": {"$in": ["pending", "overdue", "vague"]}},
            {"_id": 0},
        )
        .sort("created_at", -1)
    )
    # Look up customer names from the interactions collection
    customer_ids = list({d.get("customer_id") for d in docs if d.get("customer_id")})
    name_map = {}
    if customer_ids:
        for cid in customer_ids:
            record = get_interactions().find_one({"customer_id": cid}, {"customer_name": 1})
            if record:
                name_map[cid] = record.get("customer_name", cid)
    for doc in docs:
        doc["customer_name"] = name_map.get(doc.get("customer_id"), doc.get("customer_id", "Unknown"))
        for k in ("created_at", "updated_at"):
            if hasattr(doc.get(k), "isoformat"):
                doc[k] = doc[k].isoformat()
    return docs


# ─────────────────────────────── Health Check ─────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "ContextFlow API"}
