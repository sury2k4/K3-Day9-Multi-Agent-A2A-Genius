from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .config import Settings, get_settings
from .db import PostgresRepository, RunStore, ingest_csv_data
from .graph import DisputeGraph
from .schemas import CaseInput, CaseOutput
from .tracing import TraceRecorder, write_metadata


def load_cases(input_dir: Path, require_official_batch: bool = True) -> list[CaseInput]:
    files = sorted(input_dir.glob("EC_*.json")) if input_dir.exists() else []
    if require_official_batch and len(files) != 50:
        raise RuntimeError(
            f"Expected exactly 50 official case files in {input_dir}, found {len(files)}. "
            "Do not generate replacement cases."
        )
    cases: list[CaseInput] = []
    for path in files:
        try:
            cases.append(CaseInput.model_validate_json(path.read_text(encoding="utf-8")))
        except (OSError, ValidationError, ValueError) as exc:
            raise RuntimeError(f"Invalid input case {path}: {exc}") from exc
    expected_ids = [f"EC_{index:03d}" for index in range(1, 51)]
    if require_official_batch and [case.case_id for case in cases] != expected_ids:
        raise RuntimeError(
            "Official input filenames/case IDs must be EC_001 through EC_050 in order."
        )
    order_ids = [case.customer_request.claimed_order_id for case in cases]
    if len(set(order_ids)) != len(order_ids):
        raise RuntimeError("Input batch contains duplicate claimed_order_id values.")
    return cases


def clear_generated_outputs(output_dir: Path, case_ids: set[str]) -> None:
    """Remove only generated case JSONs that are not part of this run.

    Keeping stale EC_*.json files is a common source of hard-gate failures when a
    new official batch replaces an earlier development batch. Non-case files are
    intentionally left untouched.
    """

    if not output_dir.exists():
        return
    for path in output_dir.glob("EC_*.json"):
        if path.stem not in case_ids:
            path.unlink()


def run_batch(settings: Settings, require_official_batch: bool) -> int:
    cases = load_cases(settings.input_dir, require_official_batch)
    if not cases:
        raise RuntimeError(f"No case JSON files found in {settings.input_dir}")

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    clear_generated_outputs(settings.output_dir, {case.case_id for case in cases})
    write_metadata(settings)
    tracer = TraceRecorder(settings.logging_dir)
    tracer.reset()
    repository = PostgresRepository(settings.database_url)
    run_store = RunStore(settings.database_url)
    graph = DisputeGraph(repository, settings, tracer, run_store=run_store)

    completed = 0
    for case in cases:
        result = graph.run_case(case)
        tracer.event(
            trace_id=result.get("trace_id", "unknown"),
            case_id=case.case_id,
            node="batch_runner",
            event="case_complete",
            output_path=result.get("output_path"),
            fallback_used=result.get("fallback_used", False),
            valid=result.get("verification_report", {}).get("valid", False),
        )
        completed += 1
    tracer.sync_root_artifacts()
    print(f"Completed {completed} cases")
    print(f"Trace: {settings.logging_dir / 'trace.jsonl'}")
    print(f"Metadata: {settings.logging_dir / 'metadata.json'}")
    return 0


def validate_outputs(settings: Settings, require_official_batch: bool) -> int:
    files = sorted(settings.output_dir.glob("EC_*.json")) if settings.output_dir.exists() else []
    expected_ids = {f"EC_{index:03d}" for index in range(1, 51)}
    actual_ids = {path.stem for path in files}
    if require_official_batch and actual_ids != expected_ids:
        raise RuntimeError(
            "Expected exactly EC_001.json through EC_050.json in "
            f"{settings.output_dir}; found {len(files)} files with IDs "
            f"{sorted(actual_ids)}"
        )
    errors: list[str] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            output = CaseOutput.model_validate(payload)
            if path.stem != output.case_id:
                errors.append(f"{path.name}: case_id mismatch")
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            errors.append(f"{path.name}: {exc}")
    if errors:
        raise RuntimeError("Output validation failed:\n" + "\n".join(errors))
    print(f"Validated {len(files)} output files")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Olist multi-agent dispute resolver")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Create schema and load data/*.csv into PostgreSQL")
    ingest.set_defaults(command_handler="ingest")

    run = subparsers.add_parser("run", help="Run the LangGraph over input/EC_*.json")
    run.add_argument(
        "--require-official-batch",
        action="store_true",
        help="Require exactly EC_001.json through EC_050.json",
    )
    run.set_defaults(command_handler="run")

    validate = subparsers.add_parser("validate", help="Validate generated output JSON schemas")
    validate.add_argument(
        "--require-official-batch",
        action="store_true",
        help="Require exactly 50 output files",
    )
    validate.set_defaults(command_handler="validate")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    settings = get_settings()
    try:
        if args.command_handler == "ingest":
            counts = ingest_csv_data(settings.database_url, settings.data_dir)
            print(json.dumps(counts, indent=2, sort_keys=True))
            return 0
        if args.command_handler == "run":
            return run_batch(settings, args.require_official_batch)
        if args.command_handler == "validate":
            return validate_outputs(settings, args.require_official_batch)
    except Exception as exc:  # noqa: BLE001 - CLI must return a readable error
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
