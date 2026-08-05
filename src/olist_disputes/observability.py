import json
from datetime import datetime, timezone
from pathlib import Path
from .constants import MODEL_NAME

class TraceWriter:
    def __init__(self, path: Path):
        self.path = path
        self.events: list[dict] = []

    def event(self, case_id: str, run_id: str, node: str, status: str = "ok", order_id: str | None = None):
        self.events.append({"case_id": case_id, "run_id": run_id, "order_id": order_id, "node": node, "status": status, "model": MODEL_NAME, "timestamp": datetime.now(timezone.utc).isoformat()})

    def flush(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            for event in self.events:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
