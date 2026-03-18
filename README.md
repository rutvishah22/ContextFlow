# ContextFlow

> A production-grade Follow-up & Context Intelligence Agent for sales, support, and operations workflows.

## The Problem

In real-world business workflows, customer interactions happen across time, context gets lost between calls, follow-ups are missed, and risk signals go unnoticed. CRM tools store data but don't reason over it. ContextFlow fixes this — it ingests messy interaction notes, extracts structured insights, maintains context over time, tracks commitments with state, and surfaces risks and next steps automatically.

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
│  └────────┬─────────┘  (always returns English)                 │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────────────────────────┐                       │
│  │  Step 2  TWO-PASS CONTEXT RETRIEVAL  │                       │
│  │  Pass 1: MongoDB  ──► chronological  │                       │
│  │          history for this customer   │                       │
│  │  Pass 2: ChromaDB ──► semantic rank  │                       │
│  │          ALWAYS filtered by          │                       │
│  │          customer_id (no bleed)      │                       │
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
│  │  Streamlit UI    │   (HTTP calls only — zero business logic) │
│  └──────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### Two-Pass Retrieval — Preventing Customer Context Bleed
Step 2 deliberately runs two passes. Pass 1 retrieves the full chronological history from MongoDB for the specific `customer_id`. Pass 2 uses ChromaDB's semantic similarity, but **always filtered by `customer_id` metadata** — never a global vector search. This prevents a specific production bug where semantic similarity across customers could surface another customer's context, causing incorrect insights and potential data leakage.

### Commitment State Machine — Why `vague` is a Real State
A simple "done / not done" list loses nuance. In real sales workflows, "we'll reconnect" and "will send a firm PO by Friday" are not the same. The `vague` status — with a mandatory `vague_reason` and `confidence_score < 0.5` — forces the agent to be explicit about what it doesn't know, rather than silently treating ambiguous language as a real commitment.

### ChromaDB over FAISS
ChromaDB is persistent with zero setup — data survives restarts without serialisation code. FAISS is faster at scale, but requires manual index persistence. For this use case (thousands of interactions per tenant, not billions), ChromaDB's operational simplicity wins.

### MongoDB over SQLite
Interaction data is naturally nested (extracted fields, lists of objections, commitment arrays). MongoDB's document model stores this without normalisation overhead. SQLite would require JOIN-heavy schemas for the same data. MongoDB Atlas also provides a hosted option with minimal ops burden.

### Streamlit over React
The agent logic, commitment state machine, and retrieval pipeline are the product. Streamlit delivers a functional, styled frontend in a single file, enabling evaluation against business logic — not UI engineering. The frontend is fully decoupled and only makes HTTP calls.

---

## How to Run Locally

### 1. Clone & Install

```bash
git clone <repo_url>
cd contextflow
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in GROQ_API_KEY and MONGODB_URI
```

### 3. Start the Backend

```bash
# From the contextflow/ directory
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Load Sample Data (run once)

```bash
# From the contextflow/ directory
python -m sample_data.preload
```

This inserts two fictional customers — Priya Sharma (sales) and Rahul Mehta (support) — with pre-existing interactions and commitments. Re-running is safe; it performs a duplicate check before inserting.

### 5. Start the Frontend

```bash
# From the contextflow/ directory
streamlit run frontend/app.py
```

Open [http://localhost:8501](http://localhost:8501).

---

## API Reference

| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/add-interaction` | Run 5-step pipeline on a raw interaction note |
| `GET` | `/get-customer/{customer_id}` | Fetch all interactions + commitments |
| `POST` | `/update-commitment` | Manually override commitment status |
| `GET` | `/health` | Health check |

**POST /add-interaction body:**
```json
{
  "customer_id": "cust_xyz",
  "customer_name": "Jane Doe",
  "raw_input": "Had a call with Jane. She loved the demo but pricing is high..."
}
```

---

## Deployment — Hugging Face Spaces

1. Create a new Space with **Docker** runtime (to run both FastAPI + Streamlit).
2. Or create two Spaces: one for the FastAPI backend (Python runtime) and one for Streamlit.
3. Set environment secrets: `GROQ_API_KEY`, `MONGODB_URI`.
4. For the Streamlit Space, set `BACKEND_URL` in `app.py` to point to your deployed FastAPI URL.
5. ChromaDB will use `/data/chroma_store` (persistent disk) on HF Spaces — update `CHROMA_PERSIST_DIR` in `config.py` accordingly.

---

## Edge Cases Handled

| Edge Case | Handling |
|-----------|----------|
| Missing customer name | Extraction returns "Unknown"; pipeline continues |
| Vague commitments | `status: vague`, `confidence_score < 0.5`, `vague_reason` always populated |
| Hinglish / Hindi input | Extraction prompt explicitly normalises all output to English |
| First interaction / no history | Steps 3 & 4 degrade gracefully with empty context |
| Conflicting intent | Flagged as `intent_shift: true` with description |
| Empty / gibberish input | 400 validation error before LLM is called |
| Malformed LLM JSON | `try/except` in `call_llm()`, logs raw output, returns structured fallback dict |
