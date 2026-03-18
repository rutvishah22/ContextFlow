"""
models.py — all Pydantic request/response schemas.
No inline dicts in route handlers; everything is typed here.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────── Request Bodies ───────────────────────────────

class AddInteractionRequest(BaseModel):
    customer_id: str
    customer_name: str
    raw_input: str


class UpdateCommitmentRequest(BaseModel):
    commitment_id: str
    status: str  # pending | fulfilled | overdue | cancelled | vague


# ─────────────────────────────── Extracted Fields ─────────────────────────────

class ExtractedData(BaseModel):
    intent: str                        # interested | neutral | not_interested
    objections: List[str]
    sentiment: str                     # positive | neutral | negative
    language_detected: str             # english | hinglish | hindi | other
    raw_commitments: List[str]


# ─────────────────────────────── Context Reasoning ────────────────────────────

class ContextReasoning(BaseModel):
    repeated_objections: List[str]
    unresolved_issues: List[str]
    intent_shift: bool
    intent_shift_description: Optional[str] = None
    risk_signals: List[str]
    risk_level: str                    # low | medium | high


# ─────────────────────────────── Commitment ───────────────────────────────────

class NewCommitment(BaseModel):
    description: str
    owner: str                         # rep | customer
    status: str                        # pending | vague
    confidence_score: float
    vague_reason: Optional[str] = None
    due_date: Optional[str] = None


class UpdatedCommitment(BaseModel):
    commitment_id: str
    new_status: str


class CommitmentTrackingResult(BaseModel):
    new_commitments: List[NewCommitment]
    updated_commitments: List[UpdatedCommitment]


# ─────────────────────────────── Pending Action (output) ──────────────────────

class PendingAction(BaseModel):
    commitment_id: str
    description: str
    owner: str
    due_date: Optional[str]
    status: str
    confidence_score: float
    is_vague: bool
    vague_reason: Optional[str]


# ─────────────────────────────── Final Output ─────────────────────────────────

class FinalOutput(BaseModel):
    summary: str
    context_insights: List[str]
    pending_actions: List[PendingAction]
    risk_level: str
    risk_reason: str
    recommended_next_steps: List[str]


class InteractionResponse(BaseModel):
    interaction_id: str
    customer_id: str
    customer_name: str
    timestamp: datetime
    extracted: ExtractedData
    context_reasoning: ContextReasoning
    final_output: FinalOutput


# ─────────────────────────────── Customer History ─────────────────────────────

class CustomerHistoryResponse(BaseModel):
    customer_id: str
    interactions: List[dict]
    commitments: List[dict]
