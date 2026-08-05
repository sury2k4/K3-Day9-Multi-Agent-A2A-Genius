"""Source-controlled model selection required by the assignment."""

from pathlib import Path

import yaml

from src.errors import ConfigurationError

OPENROUTER_MODEL_ID = "qwen/qwen-2.5-7b-instruct"
OPENROUTER_MODEL_PARAMETER_COUNT_B = 7.61
OPENROUTER_PROVIDER = "OpenRouter"
LLM_TEMPERATURE = 0.1
MAX_MODEL_PARAMETER_COUNT_B = 10.0


def validate_model_configuration(registry_path: Path | None = None) -> None:
    """Fail fast when source constants and the audited registry disagree."""
    if OPENROUTER_MODEL_PARAMETER_COUNT_B <= 0:
        raise ConfigurationError("Model parameter count must be known and positive")
    if OPENROUTER_MODEL_PARAMETER_COUNT_B > MAX_MODEL_PARAMETER_COUNT_B:
        raise ConfigurationError("Configured model exceeds the 10B parameter limit")

    path = registry_path or Path(__file__).resolve().parents[2] / "config" / "model_registry.yaml"
    try:
        registry = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Cannot read model registry: {path}") from exc

    if registry.get("model_id") != OPENROUTER_MODEL_ID:
        raise ConfigurationError("Model registry slug does not match source configuration")
    if float(registry.get("parameter_count_b", 0)) != OPENROUTER_MODEL_PARAMETER_COUNT_B:
        raise ConfigurationError(
            "Model registry parameter count does not match source configuration"
        )
