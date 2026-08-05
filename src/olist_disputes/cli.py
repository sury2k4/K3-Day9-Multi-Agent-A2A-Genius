import argparse
import json
import zipfile
from .config import get_settings
from .db import apply_schema
from .facts import load_order_facts
from .ingest import ingest_csvs, validate_csvs
from .policy import decide
from .runner import load_cases, run_batch
from .schemas import CaseOutput
from .verifier import verify

def main():
    parser = argparse.ArgumentParser(prog="olist-disputes")
    parser.add_argument("command", choices=["run-batch", "verify", "audit-batch", "ingest", "package-output"])
    args = parser.parse_args()
    settings = get_settings()
    if args.command == "run-batch":
        run_batch(settings)
        return
    if args.command == "ingest":
        validate_csvs(settings.data_dir)
        migration = settings.data_dir.parent / "migrations" / "001_initial_schema.sql"
        if migration.exists():
            apply_schema(settings.database_url, migration)
            ingest_csvs(settings.database_url, settings.data_dir)
        print("CSV headers validated and source rows ingested")
        return
    if args.command == "verify":
        outputs = sorted(settings.output_dir.glob("EC_*.json"))
        if len(outputs) != 50:
            raise SystemExit(f"expected 50 outputs, found {len(outputs)}")
        for output in outputs:
            json.loads(output.read_text(encoding="utf-8"))
        print("50 output JSON files found")
        return
    if args.command == "package-output":
        outputs = sorted(settings.output_dir.glob("EC_*.json"))
        expected = [settings.output_dir / f"EC_{i:03d}.json" for i in range(1, 51)]
        if outputs != expected:
            raise SystemExit("output must contain exactly EC_001.json through EC_050.json")
        with zipfile.ZipFile("submission.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for path in outputs:
                archive.write(path, path.name)
        print("created submission.zip")

if __name__ == "__main__":
    main()
