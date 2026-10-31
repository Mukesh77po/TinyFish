"""All config comes from env vars (see .env.example)."""
import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://tenderhawk:tenderhawk@localhost:5432/tenderhawk")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))
# Browser origins allowed to call the API (the Next.js dashboard). Comma-separated; "*" allows any.
WEB_ORIGINS = [o.strip().rstrip("/") for o in
               os.getenv("WEB_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]


def fallback_mode() -> bool:
    return os.getenv("FALLBACK_MODE", "false").lower() in ("1", "true", "yes")
