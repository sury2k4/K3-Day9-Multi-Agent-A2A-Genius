"""Batch runner: reads every input/EC_*.json, drives the LangGraph
multi-agent pipeline, writes output/EC_*.json and logging/trace.jsonl,
and refreshes logging/metadata.json with this run's stats.

Usage:
    python main.py                # run all cases in input/
    python main.py EC_001 EC_002  # run a subset (smoke test)
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

from src.config import (
    FRAMEWORK,
    INPUT_DIR,
    LOGGING_DIR,
    MODEL_NAME,
    MODEL_PARAM_COUNT,
    MODEL_PROVIDER,
    OPENROUTER_API_KEY,
    OUTPUT_DIR,
    POLICY_VERSION,
)
from src.graph import build_graph
from src.tracing import TraceWriter, event


def fallback_output(case_id: str, reason: str) -> dict:
    return {
        "case_id": case_id,
        "assessment": {"primary_issue": "unsupported_late_claim", "case_status": "no_action", "confidence": 0.0},
        "affected_entities": {"order_ids": [], "item_ids": [], "seller_ids": [], "payment_ids": []},
        "root_cause_analysis": {"ranked_causes": [], "responsible_parties": []},
        "evidence_ids": [],
        "financial_resolution": {
            "currency": "BRL",
            "item_total_brl": 0.0,
            "freight_total_brl": 0.0,
            "payment_total_brl": 0.0,
            "recommended_refund_brl": 0.0,
        },
        "resolution_actions": ["reject_late_refund"],
        "_pipeline_error": reason,
    }


def main(argv: list[str]) -> None:
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY is empty. Fill it in .env before running.", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOGGING_DIR.mkdir(parents=True, exist_ok=True)

    if argv:
        case_files = [INPUT_DIR / f"{cid}.json" for cid in argv]
    else:
        case_files = sorted(INPUT_DIR.glob("EC_*.json"))

    if not case_files:
        print(f"No input cases found in {INPUT_DIR}", file=sys.stderr)
        sys.exit(1)

    graph = build_graph()
    trace = TraceWriter(LOGGING_DIR / "trace.jsonl")

    run_started = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    ok_count = 0
    error_count = 0

    for i, path in enumerate(case_files, start=1):
        input_case = json.loads(path.read_text(encoding="utf-8"))
        case_id = input_case["case_id"]
        print(f"[{i}/{len(case_files)}] {case_id} ...", flush=True)

        try:
            case_started = time.monotonic()
            final_state: dict = {}
            for update in graph.stream({"case_id": case_id, "input_case": input_case}, stream_mode="updates"):
                for node_name, node_output in update.items():
                    for evt in node_output.get("trace_events", []):
                        trace.log(**evt)
                    final_state.update(node_output)
                    print(f"    - {node_name} done", flush=True)
            final_output = final_state["final_output"]
            ok_count += 1
            print(f"    ({round(time.monotonic() - case_started, 1)}s)", flush=True)
        except Exception as e:  # noqa: BLE001
            error_count += 1
            trace.log(**event(case_id, "pipeline", "error", detail={"error": f"{type(e).__name__}: {e}"}))
            final_output = fallback_output(case_id, f"{type(e).__name__}: {e}")

        out_path = OUTPUT_DIR / f"{case_id}.json"
        out_path.write_text(json.dumps(final_output, ensure_ascii=False, indent=2), encoding="utf-8")

    trace.close()
    elapsed_s = round(time.monotonic() - t0, 1)

    metadata = {
        "model": {
            "name": MODEL_NAME,
            "parameter_size": MODEL_PARAM_COUNT,
            "provider": MODEL_PROVIDER,
        },
        "framework": FRAMEWORK,
        "runtime": {
            "python": sys.version.split()[0],
            "os": sys.platform,
        },
        "policy_version": POLICY_VERSION,
        "run": {
            "started_at": run_started,
            "elapsed_seconds": elapsed_s,
            "cases_total": len(case_files),
            "cases_ok": ok_count,
            "cases_error": error_count,
        },
    }
    (LOGGING_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Done. {ok_count} ok, {error_count} errors, {elapsed_s}s total.")


if __name__ == "__main__":
    main(sys.argv[1:])
