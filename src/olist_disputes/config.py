from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

from .constants import MODEL_NAME

@dataclass(frozen=True)
class Settings:
    database_url: str
    openrouter_api_key: str
    langfuse_host: str
    langfuse_public_key: str
    langfuse_secret_key: str
    data_dir: Path
    input_dir: Path
    output_dir: Path
    trace_path: Path
    metadata_path: Path
    model: str = MODEL_NAME

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openrouter_api_key)

def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql+psycopg://olist:olist@localhost:5432/olist_disputes"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        langfuse_host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
        langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
        langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
        data_dir=Path(os.getenv("DATA_DIR", "data")),
        input_dir=Path(os.getenv("INPUT_DIR", "input")),
        output_dir=Path(os.getenv("OUTPUT_DIR", "output")),
        trace_path=Path(os.getenv("TRACE_PATH", "trace.jsonl")),
        metadata_path=Path(os.getenv("METADATA_PATH", "metadata.json")),
    )
