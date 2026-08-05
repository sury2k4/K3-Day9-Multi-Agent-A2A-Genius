from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class TraceWriter:
    """Writes one JSON line per agent step. Opened fresh (mode 'w') at the
    start of each full batch run so trace.jsonl always reflects only the
    latest run, per the assignment's "khong append" requirement."""

    def __init__(self, path: Path):
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "w", encoding="utf-8")

    def log(self, **fields) -> None:
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), **fields}
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def event(
    case_id: str,
    agent: str,
    action: str,
    detail: dict | None = None,
    llm_call: dict | None = None,
) -> dict:
    record = {"case_id": case_id, "agent": agent, "action": action}
    if detail is not None:
        record["detail"] = detail
    if llm_call is not None:
        record["llm"] = {
            "model": llm_call.get("model"),
            "ok": llm_call.get("ok"),
            "latency_ms": llm_call.get("latency_ms"),
            "usage": llm_call.get("usage"),
            "error": llm_call.get("error"),
        }
    return record
