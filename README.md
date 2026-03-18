---
title: ContextFlow
emoji: 🧠
colorFrom: indigo
colorTo: purple
sdk: docker
pinned: false
---

# ContextFlow

A Follow-up & Context Intelligence Agent for sales, support, and operations workflows.

## The Problem

Customer interactions happen across time. Context gets lost between calls, follow-ups are missed, and risk signals go unnoticed. CRMs store data but don't reason over it. ContextFlow ingests messy interaction notes, extracts structured insights, maintains context over time, tracks commitments with state, and surfaces risks and next steps automatically.

---

## Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                     CONTEXTFLOW PIPELINE                        │
│                                                                 │
│  Raw Input (text, Hinglish, transcript)                         │
│        │                                                        │
│        ▼                                                        │
│  ┌──────────────────┐                                           │
│  │  Step 1          │  LLM extracts: intent, objections,        │
│  │  EXTRACTION      │  sentiment, language, raw_commitments     │
│  └────────┬─────────┘  (always normalised to English)          │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────────────────────────┐                       │
│  │  Step 2  TWO-PASS CONTEXT RETRIEVAL  │                       │
│  │  Pass 1: MongoDB  ──► chronological  │                       │
│  │          history for this customer   │                       │
│  │  Pass 2: ChromaDB ──► semantic rank  │                       │
│  │          filtered by customer_id     │                       │
│  │          (no cross-customer bleed)   │                       │
│  └────────┬─────────────────────────────┘                       │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────┐                                           │
│  │  Step 3          │  LLM identifies: repeated objections,     │
│  │  CONTEXT         │  unresolved issues, intent shift,         │
│  │  REASONING       │  risk signals, risk_level                 │
│  └────────┬─────────┘                                           │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────┐  Classifies each commitment:              │
│  │  Step 4          │  pending   → confidence 0.7–1.0           │
│  │  COMMITMENT      │  vague     → confidence 0.0–0.49          │
│  │  TRACKING        │  + vague_reason always populated          │
│  │  (state machine) │  Updates existing commitments             │
│  └────────┬─────────┘                                           │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────┐                                           │
│  │  Step 5          │  summary, context_insights,               │
│  │  OUTPUT          │  pending_actions, risk_level,             │
│  │  GENERATION      │  recommended_next_steps                   │
│  └────────┬─────────┘                                           │
│           │                                                     │
│  ┌────────▼─────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │   FastAPI API    │   │   MongoDB    │   │   ChromaDB     │  │
│  │   (3 routes)     │──►│  (structured)│   │  (embeddings)  │  │
│  └──────────────────┘   └──────────────┘   └────────────────┘  │
│           │                                                     │
│  ┌────────▼─────────┐                                           │
│  │  Vanilla HTML/   │  (HTTP calls only — zero business logic)  │
│  │  CSS/JS Frontend │                                           │
│  └──────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Stack

- **Backend:** Python, FastAPI
- **LLM:** Groq API — `llama-3.3-70b-versatile`
- **Vector store:** ChromaDB (persistent)
- **Database:** MongoDB Atlas
- **Frontend:** Vanilla HTML/CSS/JS, served via FastAPI StaticFiles
- **Deployment:** Hugging Face Spaces (Docker)

---

## Key Design Decisions

### Two-pass retrieval — preventing context bleed
Step 2 runs two passes. Pass 1 fetches the full chronological interaction history from MongoDB scoped strictly to the current `customer_id`. Pass 2 runs ChromaDB semantic similarity, but always filtered by `customer_id` metadata — never a global vector search. Without this, semantic similarity can surface another customer's context, producing incorrect insights and potential data leakage. This is a real production bug that a naive single-pass implementation would introduce silently.

### Commitment state machine — `vague` as a first-class state
A binary done/pending model loses real-world nuance. "We'll reconnect sometime" and "sending the PO by Friday" are not the same type of commitment. The `vague` status — with a mandatory `vague_reason` and `confidence_score < 0.5` — forces the agent to be explicit about what it doesn't know rather than silently treating ambiguous language as a trackable commitment. This distinction matters operationally: a vague commitment requires clarification, a pending one requires follow-through.

### ChromaDB over FAISS
ChromaDB persists without serialisation code — the index survives restarts out of the box. FAISS requires manual index save/load logic and offers no metadata filtering natively. For this scale, ChromaDB's operational simplicity is the right trade-off.

### Single `call_llm()` entry point
All four LLM calls go through one function in `agent.py`. Every response is parsed as JSON inside a try/except — raw output is logged on failure and a structured fallback dict is returned. The pipeline never crashes on a malformed LLM response. Centralising this means retry logic, logging, and error handling only need to exist in one place.

---

## How to Run Locally

### 1. Clone and install
```bash
git clone <repo_url>
cd contextflow
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in GROQ_API_KEY and MONGODB_URI
```

### 3. Start the backend
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Load sample data (run once)
```bash
python -m sample_data.preload
```

Inserts two fictional customers — Priya Sharma (sales) and Rahul Mehta (support) — with pre-existing interactions and commitments. Safe to re-run; duplicate check is in place.

### 5. Open the app

Navigate to `http://localhost:8000`. The frontend is served directly by FastAPI.

---

## API Reference

| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/add-interaction` | Run full 5-step pipeline on a raw interaction note |
| `GET` | `/get-customer/{customer_id}` | Fetch all interactions and commitments for a customer |
| `POST` | `/update-commitment` | Manually override a commitment's status |

**POST /add-interaction — request body:**
```json
{
  "customer_id": "cust_xyz",
  "customer_name": "Jane Doe",
  "raw_input": "Had a call with Jane. She loved the demo but said pricing is too high..."
}
```

---

## Edge Cases Handled

| Edge Case | Handling |
|-----------|----------|
| Missing customer name | Extraction returns "Unknown", pipeline continues |
| Vague commitments | `status: vague`, `confidence_score < 0.5`, `vague_reason` always populated |
| Hinglish / Hindi input | Extraction prompt normalises all output to English |
| First interaction / no history | Steps 3 and 4 degrade gracefully with empty context |
| Conflicting intent across interactions | Flagged as `intent_shift: true` with description |
| Empty or invalid input | 400 validation error before LLM is called |
| Malformed LLM JSON | Caught in `call_llm()`, raw response logged, structured fallback returned |

---

## Deployment

Deployed on Hugging Face Spaces using Docker. Environment secrets (`GROQ_API_KEY`, `MONGODB_URI`) are set via Space settings — not committed to the repository.