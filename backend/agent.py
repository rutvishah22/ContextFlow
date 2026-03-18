"""
agent.py — ContextFlow's 5-step LLM pipeline.

All Groq API calls funnel through a single call_llm() function.
Every LLM response is JSON-parsed inside try/except — the pipeline never crashes on bad output.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from groq import Groq

from backend.config import GROQ_API_KEY, GROQ_MODEL
from backend.db import get_interactions, get_commitments
from backend.vector_store import upsert_interaction, query_similar

logger = logging.getLogger(__name__)

# Single shared Groq client
_groq_client = Groq(api_key=GROQ_API_KEY)


# ─────────────────────────────── Core LLM Helper ──────────────────────────────

def call_llm(prompt: str) -> dict:
    """
    Single entry-point for all Groq LLM calls.
    Instructs the model to return JSON, parses response safely.
    On failure: logs raw output & returns a structured error dict.
    """
    try:
        response = _groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a JSON-only response engine. "
                        "Always return valid, parsable JSON with no markdown fences, "
                        "no extra commentary, and no trailing text outside the JSON object."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2048,
        )
        raw = response.choices[0].message.content.strip()
        # Strip accidental markdown fences the model may still emit
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned non-JSON output. Raw: %s | Error: %s", raw, exc)
        return {"_error": "JSON parse failure", "_raw": raw}
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return {"_error": str(exc)}


# ─────────────────────────────── Step 1: Extraction ───────────────────────────

def step1_extract(raw_input: str) -> dict:
    """Extract structured fields from raw interaction text."""
    prompt = f"""
You are an expert sales/support interaction analyser.

Extract the following fields from the interaction note below.
CRITICAL: Regardless of input language (English, Hindi, Hinglish, or mixed), ALL extracted fields
must be returned in English. Translate and normalise any non-English content before returning.

Return ONLY a JSON object with these exact keys:
{{
  "customer_name": "string — the customer's name, or 'Unknown' if not found",
  "intent": "one of: interested | neutral | not_interested",
  "objections": ["list of objections raised, in English, empty list if none"],
  "sentiment": "one of: positive | neutral | negative",
  "language_detected": "one of: english | hinglish | hindi | other",
  "raw_commitments": ["every promise, follow-up, or next-step mentioned, word-for-word translated to English, empty list if none"]
}}

Interaction note:
\"\"\"
{raw_input}
\"\"\"
"""
    result = call_llm(prompt)
    # Populate safe defaults if extraction partially failed
    defaults = {
        "customer_name": "Unknown",
        "intent": "neutral",
        "objections": [],
        "sentiment": "neutral",
        "language_detected": "other",
        "raw_commitments": [],
    }
    for key, val in defaults.items():
        result.setdefault(key, val)
    return result


# ─────────────────────────────── Step 2: Context Retrieval ────────────────────

def step2_retrieve_context(customer_id: str, raw_input: str) -> dict:
    """
    Two-pass retrieval — structured history from MongoDB + semantic ranking from ChromaDB.
    Always scoped to customer_id; never a global ChromaDB search.
    """
    # Pass 1 — full chronological history from MongoDB
    raw_history = list(
        get_interactions()
        .find({"customer_id": customer_id}, {"_id": 0})
        .sort("timestamp", 1)
    )

    if not raw_history:
        logger.info("No prior interactions found for customer %s.", customer_id)
        return {"structured_history": [], "similar_interactions": [], "pending_commitments": []}

    # Pass 2 — semantic ranking within this customer's documents only
    similar_ids = {doc["id"] for doc in query_similar(customer_id, raw_input, n_results=3)}

    # Annotate history docs with similarity flag for the reasoning step
    structured = []
    similar_interactions = []
    for doc in raw_history:
        entry = {
            "interaction_id": doc.get("interaction_id"),
            "timestamp": str(doc.get("timestamp", "")),
            "raw_input": doc.get("raw_input", ""),
            "extracted": doc.get("extracted", {}),
        }
        structured.append(entry)
        if doc.get("interaction_id") in similar_ids:
            similar_interactions.append(entry)

    # Fetch all pending commitments for this customer
    pending = list(
        get_commitments().find(
            {"customer_id": customer_id, "status": {"$in": ["pending", "vague", "overdue"]}},
            {"_id": 0},
        )
    )
    # Convert datetime fields to strings for JSON serialisation
    for c in pending:
        for k in ("created_at", "updated_at"):
            if isinstance(c.get(k), datetime):
                c[k] = c[k].isoformat()

    return {
        "structured_history": structured,
        "similar_interactions": similar_interactions,
        "pending_commitments": pending,
    }


# ─────────────────────────────── Step 3: Context Reasoning ────────────────────

def step3_reason_context(extracted: dict, context: dict) -> dict:
    """Identify risks, patterns, and intent shifts by reasoning over history."""
    history_json = json.dumps(context.get("structured_history", []), indent=2)
    similar_json = json.dumps(context.get("similar_interactions", []), indent=2)
    commitments_json = json.dumps(context.get("pending_commitments", []), indent=2)
    current_json = json.dumps(extracted, indent=2)

    prompt = f"""
You are a senior account intelligence analyst reviewing a customer's full interaction history.

Current interaction (already extracted):
{current_json}

Chronological interaction history (oldest first):
{history_json}

Most semantically similar past interactions:
{similar_json}

Open / pending commitments for this customer:
{commitments_json}

Analyse the above and return ONLY a JSON object with these exact keys:
{{
  "repeated_objections": ["objections that appeared in more than one interaction"],
  "unresolved_issues": ["issues raised in past interactions not yet addressed"],
  "intent_shift": true | false,
  "intent_shift_description": "describe the shift if true, else null",
  "risk_signals": ["specific signals that this deal or relationship is at risk"],
  "risk_level": "one of: low | medium | high"
}}

CRITICAL RULES:
- The CURRENT interaction's sentiment and intent carry the MOST weight for risk assessment.
- If the current interaction indicates positive resolution (e.g., project completed, client satisfied, issues resolved),
  then risk_level MUST be "low" unless there is an explicit new concern raised IN THIS INTERACTION.
- Do NOT list issues as "unresolved" if the current interaction explicitly states they have been resolved or completed.
- If the customer's current sentiment is positive and intent is interested, past negative history should be noted as context
  but should NOT inflate the risk_level. Past issues that are now resolved reduce risk, they do not increase it.
- intent_shift should reflect the DIRECTION of the shift (e.g., "negative to positive" is a POSITIVE shift).
- If there is no past context, return empty arrays and risk_level: "low". Do not error.
"""
    result = call_llm(prompt)
    defaults = {
        "repeated_objections": [],
        "unresolved_issues": [],
        "intent_shift": False,
        "intent_shift_description": None,
        "risk_signals": [],
        "risk_level": "low",
    }
    for key, val in defaults.items():
        result.setdefault(key, val)
    return result


# ─────────────────────────────── Step 4: Commitment Tracking ──────────────────

def step4_track_commitments(extracted: dict, context: dict) -> dict:
    """
    Classify new commitments and check if existing ones are resolved.
    Vague commitments (confidence < 0.5) always get a vague_reason.
    """
    raw_commitments = extracted.get("raw_commitments", [])
    pending = context.get("pending_commitments", [])

    prompt = f"""
You are a commitment-tracking engine for a sales/support workflow.

Current interaction text context (for understanding what was discussed):
{json.dumps(extracted.get("raw_commitments", []), indent=2)}

Full current interaction extracted data:
{json.dumps(extracted, indent=2)}

Existing open commitments for this customer:
{json.dumps(pending, indent=2)}

Rules:
1. For each NEW commitment:
   - CRITICAL: If the interaction describes something as ALREADY COMPLETED or DONE (e.g., "project completed",
     "delivered successfully", "issue resolved", "task finished"), its status should be "fulfilled" with
     confidence_score: 0.8–1.0. Do NOT mark completed items as "pending".
   - If it is a future action that is clear and time-bound → status: "pending", confidence_score: 0.7–1.0
   - If it is vague (no timeline, no specifics, no clear owner) → status: "vague",
     confidence_score: 0.0–0.49, and populate vague_reason.
   - Determine owner: "rep" if the sales/support rep made the promise, "customer" if the customer did.
   - Include due_date if explicitly mentioned, else null.
   Examples of vague commitments: "follow up soon", "we'll think about it", "let's reconnect",
   "sometime next week", "will get back to you", "maybe later".

2. For EXISTING commitments:
   - Mark as "fulfilled" if the current interaction contains evidence of completion, resolution, or success.
     This includes general positive signals like "project completed", "everything is working", "client is happy",
     "issue has been fixed", etc. Be reasonably generous — if the interaction suggests overall resolution,
     related open commitments should likely be marked fulfilled.
   - Mark as "cancelled" if the commitment is no longer relevant.
   - Leave unchanged only if truly uncertain.

Return ONLY a JSON object:
{{
  "new_commitments": [
    {{
      "description": "string",
      "owner": "rep | customer",
      "status": "pending | vague | fulfilled",
      "confidence_score": 0.0–1.0,
      "vague_reason": "string or null",
      "due_date": "string or null"
    }}
  ],
  "updated_commitments": [
    {{
      "commitment_id": "string",
      "new_status": "fulfilled | cancelled | overdue"
    }}
  ]
}}
"""
    result = call_llm(prompt)
    result.setdefault("new_commitments", [])
    result.setdefault("updated_commitments", [])
    return result


# ─────────────────────────────── Step 5: Output Generation ────────────────────

def step5_generate_output(
    extracted: dict,
    context: dict,
    reasoning: dict,
    commitments_result: dict,
    all_pending_actions: list,
) -> dict:
    """Synthesise everything into a final, actionable output for the rep."""
    prompt = f"""
You are preparing a post-interaction brief for a sales/support representative.

Based on the following data, produce a final structured JSON output.
Every field must be concrete and actionable — no generic filler advice.

Extracted interaction:
{json.dumps(extracted, indent=2)}

Context reasoning:
{json.dumps(reasoning, indent=2)}

All open commitments:
{json.dumps(all_pending_actions, indent=2)}

Rules:
- summary: 2–3 sentences describing what happened in THIS interaction. The summary MUST accurately reflect
  the CURRENT interaction's tone and outcome. If the interaction is positive (e.g., project completed, client happy),
  the summary must be positive. Do NOT let past negative history override a clearly positive current interaction.
- context_insights: max 4 bullet points. These should reflect the CURRENT state of the relationship.
  If past issues have been resolved, acknowledge the positive recovery. Do not only list past negatives
  when the current situation is positive. Insights should be balanced and forward-looking.
- pending_actions: list of all GENUINELY unresolved commitments. Do NOT include commitments that have been
  fulfilled or resolved. Only include items that still need action.
- risk_level: one of low | medium | high. CRITICAL: base this on the CURRENT state of the relationship,
  not just historical patterns. If the current interaction is positive and issues are resolved, risk should be "low"
  even if there was past friction. Past negative history that has been addressed REDUCES risk.
- risk_reason: one concise sentence explaining the risk level based on the current state.
- recommended_next_steps: exactly 2–3 specific, forward-looking actions. If the relationship is now positive,
  focus on maintaining momentum, deepening the relationship, or exploring expansion — NOT on rehashing
  previously resolved issues.

Return ONLY this JSON:
{{
  "summary": "string",
  "context_insights": ["bullet 1", "bullet 2", ...],
  "pending_actions": [
    {{
      "commitment_id": "string",
      "description": "string",
      "owner": "rep | customer",
      "due_date": "string or null",
      "status": "string",
      "confidence_score": 0.0,
      "is_vague": true | false,
      "vague_reason": "string or null"
    }}
  ],
  "risk_level": "low | medium | high",
  "risk_reason": "string",
  "recommended_next_steps": ["step 1", "step 2", "step 3"]
}}
"""
    result = call_llm(prompt)
    # Safe defaults so the API always returns a well-formed response
    result.setdefault("summary", "Interaction processed.")
    result.setdefault("context_insights", [])
    result.setdefault("pending_actions", all_pending_actions)
    result.setdefault("risk_level", reasoning.get("risk_level", "low"))
    result.setdefault("risk_reason", "Insufficient history to assess risk.")
    result.setdefault("recommended_next_steps", [])
    return result


# ─────────────────────────────── Main Pipeline ────────────────────────────────

def run_pipeline(customer_id: str, customer_name: str, raw_input: str) -> dict:
    """
    Execute the full 5-step ContextFlow pipeline.
    Returns a dict ready to be serialised as the API response.
    """
    interaction_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    logger.info("Pipeline start — customer_id=%s interaction_id=%s", customer_id, interaction_id)

    # ── Step 1: Extract ───────────────────────────────────────────────────────
    extracted = step1_extract(raw_input)
    # Use provided name preferentially; fall back to what LLM found
    resolved_name = customer_name if customer_name.strip() else extracted.get("customer_name", "Unknown")
    extracted["customer_name"] = resolved_name

    # ── Step 2: Retrieve context ──────────────────────────────────────────────
    context = step2_retrieve_context(customer_id, raw_input)

    # ── Step 3: Reason over context ───────────────────────────────────────────
    reasoning = step3_reason_context(extracted, context)

    # ── Step 4: Track commitments ─────────────────────────────────────────────
    commitment_result = step4_track_commitments(extracted, context)

    # Persist new commitments to MongoDB
    new_commitment_docs = []
    for nc in commitment_result.get("new_commitments", []):
        doc = {
            "commitment_id": str(uuid.uuid4()),
            "customer_id": customer_id,
            "description": nc.get("description", ""),
            "owner": nc.get("owner", "rep"),
            "status": nc.get("status", "pending"),
            "confidence_score": float(nc.get("confidence_score", 0.5)),
            "vague_reason": nc.get("vague_reason"),
            "due_date": nc.get("due_date"),
            "created_at": now,
            "updated_at": now,
            "source_interaction_id": interaction_id,
        }
        get_commitments().insert_one(doc)
        new_commitment_docs.append(doc)

    # Apply status updates from the LLM to existing commitments
    for uc in commitment_result.get("updated_commitments", []):
        get_commitments().update_one(
            {"commitment_id": uc["commitment_id"]},
            {"$set": {"status": uc["new_status"], "updated_at": now}},
        )

    # Build flat list of all pending actions for Step 5
    all_pending = [
        {
            "commitment_id": c["commitment_id"],
            "description": c["description"],
            "owner": c["owner"],
            "due_date": c.get("due_date"),
            "status": c["status"],
            "confidence_score": float(c["confidence_score"]),
            "is_vague": c["status"] == "vague",
            "vague_reason": c.get("vague_reason"),
        }
        for c in new_commitment_docs
    ] + [
        {
            "commitment_id": c["commitment_id"],
            "description": c["description"],
            "owner": c.get("owner", "rep"),
            "due_date": c.get("due_date"),
            "status": c["status"],
            "confidence_score": float(c.get("confidence_score", 0.5)),
            "is_vague": c["status"] == "vague",
            "vague_reason": c.get("vague_reason"),
        }
        for c in context.get("pending_commitments", [])
    ]

    # ── Step 5: Generate output ───────────────────────────────────────────────
    final_output = step5_generate_output(extracted, context, reasoning, commitment_result, all_pending)

    # ── Persist interaction to MongoDB ────────────────────────────────────────
    interaction_doc = {
        "interaction_id": interaction_id,
        "customer_id": customer_id,
        "customer_name": resolved_name,
        "timestamp": now,
        "raw_input": raw_input,
        "extracted": {
            "intent": extracted.get("intent", "neutral"),
            "objections": extracted.get("objections", []),
            "sentiment": extracted.get("sentiment", "neutral"),
            "language_detected": extracted.get("language_detected", "other"),
        },
    }
    get_interactions().insert_one(interaction_doc)

    # ── Index in ChromaDB for future semantic retrieval ───────────────────────
    upsert_interaction(interaction_id, customer_id, raw_input)

    logger.info("Pipeline complete — interaction_id=%s", interaction_id)

    return {
        "interaction_id": interaction_id,
        "customer_id": customer_id,
        "customer_name": resolved_name,
        "timestamp": now.isoformat(),
        "extracted": extracted,
        "context_reasoning": reasoning,
        "final_output": final_output,
    }
