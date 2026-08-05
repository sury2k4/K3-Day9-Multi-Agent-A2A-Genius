# K3 Day 09 — Multi-Agent E-commerce Dispute Resolution

Pipeline resolves Olist disputes with deterministic source joins, policy, evidence and verification. LangGraph separates Coordinator, Order/Seller, Payment, Delivery, Policy, Verifier and Writer nodes. Qwen 2.5 7B only writes optional grounded explanations; it never owns amounts, refunds, IDs, evidence or policy decisions.

## Current state

Official `input/EC_001.json` through `input/EC_050.json` are not committed yet. Runner refuses to create outputs until all 50 valid cases exist. It never synthesizes missing cases.

## Requirements

- Docker Desktop with Compose
- Python 3.11+ for local tests
- OpenRouter key is optional for deterministic execution; add it to local `.env`

## Configuration

`.env` is ignored and created locally with empty `OPENROUTER_API_KEY=`. Copy `.env.example` when setting up another machine. Model is hard-coded in `src/olist_disputes/constants.py`:

`qwen/qwen-2.5-7b-instruct`

Never commit keys or place them in trace/output.

## Run

```bash
docker compose up -d --build
# load migration automatically on first Postgres volume creation
docker compose run --rm app python -m olist_disputes.cli run-batch
```

Batch preflight requires exactly 50 files named `EC_001.json` ... `EC_050.json`, matching `case_id` and `EC_POLICY_V1`. Missing or malformed input stops before output creation.

Local Python:

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[test]"
pytest
python -m olist_disputes.cli run-batch
```

## Artifacts

- `output/EC_NNN.json`: verified output per case
- root `trace.jsonl`: latest run, overwritten each batch
- root `metadata.json`: model/runtime declaration
- `architecture.md`: roles, handoffs and policy contract

Output submission must contain exactly 50 JSON files:

```bash
zip -j submission.zip output/EC_*.json
```

Do not put source, `.env`, trace, metadata or audit files inside submission ZIP.

## Deterministic policy

Rules run by priority: paid canceled, paid unavailable, late seller handoff, late logistics delivery, valid split payment, then supported on-time delivery. Money uses `Decimal`, rounds to two decimals, and reconciles payments against item plus freight within `0.10 BRL`. Evidence IDs come only from source rows and policy codes.
