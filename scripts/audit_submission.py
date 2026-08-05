#!/usr/bin/env python3
"""Audit the 50-case workspace and ZIP hard-gate requirements."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from zipfile import ZipFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas import CaseInput, CaseOutput

EXPECTED_IDS = {f"EC_{index:03d}" for index in range(1, 51)}


def audit_json_directory(directory: Path, model: type[CaseInput | CaseOutput]) -> list[str]:
    errors: list[str] = []
    files = sorted(directory.glob("EC_*.json")) if directory.exists() else []
    actual_ids = {path.stem for path in files}
    if actual_ids != EXPECTED_IDS:
        errors.append(
            f"{directory}: expected EC_001..EC_050, found {len(files)} files"
        )
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            parsed = model.model_validate(payload)
            if parsed.case_id != path.stem:
                errors.append(f"{path}: case_id does not match filename")
        except Exception as exc:  # noqa: BLE001 - audit must report every bad file
            errors.append(f"{path}: {exc}")
    return errors


def audit_archive(archive: Path) -> list[str]:
    errors: list[str] = []
    expected_names = {f"output/EC_{index:03d}.json" for index in range(1, 51)}
    try:
        with ZipFile(archive) as zip_file:
            names = set(zip_file.namelist())
            if names != expected_names:
                errors.append(
                    "archive must contain exactly output/EC_001.json through "
                    f"output/EC_050.json; found {len(names)} entries"
                )
            if zip_file.testzip() is not None:
                errors.append("archive contains a corrupted entry")
            for name in sorted(names & expected_names):
                try:
                    payload = json.loads(zip_file.read(name).decode("utf-8"))
                    parsed = CaseOutput.model_validate(payload)
                    if parsed.case_id != Path(name).stem:
                        errors.append(f"{name}: case_id does not match filename")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{name}: {exc}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{archive}: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("input"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--archive", type=Path, default=Path("output.zip"))
    args = parser.parse_args()

    errors = audit_json_directory(args.input_dir, CaseInput)
    errors.extend(audit_json_directory(args.output_dir, CaseOutput))
    errors.extend(audit_archive(args.archive))
    if errors:
        print("SUBMISSION AUDIT FAILED")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(json.dumps({"status": "ok", "cases": 50, "archive_entries": 50}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
