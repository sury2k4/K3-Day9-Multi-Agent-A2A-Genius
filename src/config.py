import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

DATA_DIR = ROOT_DIR / "data"
INPUT_DIR = ROOT_DIR / "input"
OUTPUT_DIR = ROOT_DIR / "output"
LOGGING_DIR = ROOT_DIR / "logging"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Same model reused by every agent node; kept under the 10B-parameter cap
# required by the assignment. Declared here (not in .env) so it is visible
# in source for grading, and mirrored into logging/metadata.json.
MODEL_NAME = "nvidia/nemotron-nano-9b-v2:free"
MODEL_PARAM_COUNT = "9B"
MODEL_PROVIDER = "OpenRouter"
FRAMEWORK = "LangGraph"

POLICY_VERSION = "EC_POLICY_V1"
CURRENCY = "BRL"

MAX_RETRIES = 3
REQUEST_TIMEOUT_S = 25
