"""
config.py — centralised settings loaded from environment variables.
All other modules import from here; dotenv is loaded once.
"""

import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY: str = os.environ["GROQ_API_KEY"]
MONGODB_URI: str = os.environ["MONGODB_URI"]

# Groq model name — single source of truth
GROQ_MODEL: str = "llama-3.3-70b-versatile"

# ChromaDB persistence directory (relative to project root at runtime)
CHROMA_PERSIST_DIR: str = "./chroma_store"

# MongoDB database and collection names
MONGO_DB_NAME: str = "contextflow"
MONGO_INTERACTIONS_COL: str = "interactions"
MONGO_COMMITMENTS_COL: str = "commitments"
