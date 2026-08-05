import json
import os
from pathlib import Path
from .schemas import CaseOutput

def write_atomic(output_dir: Path, output: CaseOutput):
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{output.case_id}.json"
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(output.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, target)
