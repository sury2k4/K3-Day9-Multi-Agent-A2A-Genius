from __future__ import annotations

import json
import platform
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings


class TraceRecorder:
    """Writes the latest batch trace to logging/trace.jsonl without appending batches."""

    def __init__(self, logging_dir: Path):
        self.logging_dir = logging_dir
        self.trace_path = logging_dir / "trace.jsonl"
        self._lock = threading.Lock()
        self.logging_dir.mkdir(parents=True, exist_ok=True)

    def reset(self) -> None:
        self.trace_path.write_text("", encoding="utf-8")

    def event(
        self,
        *,
        trace_id: str,
        case_id: str,
        node: str,
        event: str,
        **payload: Any,
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": trace_id,
            "case_id": case_id,
            "node": node,
            "event": event,
            **payload,
        }
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with self._lock, self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def sync_root_artifacts(self) -> None:
        root_trace = self.logging_dir.parent / "trace.jsonl"
        shutil.copyfile(self.trace_path, root_trace)


def write_metadata(settings: Settings) -> dict[str, Any]:
    metadata = {
        "model": settings.openrouter_model,
        "provider": "OpenRouter",
        "parameter_size": "9B",
        "framework": "LangGraph",
        "tracing": "Langfuse Cloud",
        "embedding_model": None,
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    settings.logging_dir.mkdir(parents=True, exist_ok=True)
    logging_path = settings.logging_dir / "metadata.json"
    logging_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copyfile(logging_path, settings.logging_dir.parent / "metadata.json")
    return metadata


def langfuse_callbacks(settings: Settings) -> list[Any]:
    """Return the LangChain callback when Langfuse Cloud credentials are present."""

    if not settings.langfuse_configured:
        return []
    try:
        from langfuse.langchain import CallbackHandler

        return [CallbackHandler()]
    except Exception:  # noqa: BLE001 - local JSONL tracing must survive SDK drift
        # Local JSONL tracing remains available if the optional callback API changes.
        return []


class NodeTimer:
    def __init__(self) -> None:
        self.started = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self.started) * 1000, 3)
