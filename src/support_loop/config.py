"""Runtime settings. Model, chunking, and retrieval live here, not in `.env`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    handbook_path: Path = Path("data/support_handbook.md")
    orders_path: Path = Path("data/orders.json")
    dataset_path: Path = Path("evals/seed.jsonl")
    dataset_name: str = "alder-support"
    collection_name: str = "alder_support"
    embedding_model: str = "jinaai/jina-embeddings-v2-small-en"
    chat_model: str = "gemini-3.1-flash-lite"
    eval_model: str = "gpt-5.4-nano"
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_k: int = 4
    max_tool_rounds: int = 4
    prompt_style: str = "baseline"
    trace_tag: str = "local"
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    qdrant_url: str = os.getenv("QDRANT_URL", "")
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "")


def get_settings() -> Settings:
    return Settings()


ENV_NAMES = {
    "gemini_api_key": "GEMINI_API_KEY",
    "qdrant_url": "QDRANT_URL",
    "qdrant_api_key": "QDRANT_API_KEY",
}


def require_env(settings: Settings, *fields: str) -> None:
    missing = [ENV_NAMES.get(field, field) for field in fields if not getattr(settings, field)]
    if missing:
        names = ", ".join(missing)
        raise SystemExit(f"Missing {names}. Copy .env.example to .env and fill it in.")
