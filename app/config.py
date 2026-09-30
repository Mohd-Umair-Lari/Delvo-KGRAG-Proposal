"""Application configuration loaded from environment and optional .env."""
from pathlib import Path
import os
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass
def _env(name: str, default: str = "") -> str:
    # Accept values copied into .env with optional surrounding quotes/spaces.
    return os.getenv(name, default).strip().strip('"').strip("'")

GROQ_API_KEY = _env("GROQ_API_KEY")
GROQ_MODEL = _env("GROQ_MODEL") or _env("LLM_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL = _env("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_MODEL_MIGRATIONS = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "llama-3.1-8b-instant": "openai/gpt-oss-20b",
}
GROQ_REQUEST_MODEL = GROQ_MODEL_MIGRATIONS.get(GROQ_MODEL, GROQ_MODEL)
