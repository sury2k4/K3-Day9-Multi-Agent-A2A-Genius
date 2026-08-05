import json
from pathlib import Path

from .config import Settings, get_settings
from .constants import POLICY_VERSION
from .graph import run_case
from .llm import LLMClient
from .observability import TraceWriter
from .schemas import CaseInput
from .writers import write_atomic

def load_cases(input_dir: Path) -> list[CaseInput]:
    expected = [f"EC_{i:03d}.json" for i in range(1, 51)]
    actual = sorted(p.name for p in input_dir.glob("*.json"))
    if actual != expected:
        raise RuntimeError(f"input must contain exactly 50 cases; found {len(actual)}")
    cases = []
    for name in expected:
        try:
            raw = json.loads((input_dir / name).read_text(encoding="utf-8"))
            case = CaseInput.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid input case: {name}: {exc}") from exc
        if case.case_id != Path(name).stem or case.policy_version != POLICY_VERSION:
            raise ValueError(f"invalid case identity or policy: {name}")
        cases.append(case)
    return cases

def run_batch(settings: Settings | None = None):
    settings = settings or get_settings()
    cases = load_cases(settings.input_dir)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    existing = list(settings.output_dir.glob("EC_*.json"))
    if existing:
        raise RuntimeError("output directory must be empty before batch run")
    trace = TraceWriter(settings.trace_path)
    llm = LLMClient(settings.openrouter_api_key)
    for case in cases:
        output = run_case(case, settings.data_dir, llm=llm, trace=trace)
        write_atomic(settings.output_dir, output)
    trace.flush()
