import json
import httpx
from .constants import MODEL_NAME

class LLMClient:
    def __init__(self, api_key: str = "", timeout: float = 20.0):
        self.api_key = api_key
        self.timeout = timeout

    def explain(self, facts: dict, conclusion: str) -> str:
        if not self.api_key:
            return conclusion
        prompt = {"facts": facts, "conclusion": conclusion, "instruction": "Return JSON with only summary and rationale. Do not invent IDs, events, money, or policy decisions."}
        try:
            response = httpx.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, json={"model": MODEL_NAME, "temperature": 0, "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": json.dumps(prompt)}]}, timeout=self.timeout)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if not isinstance(parsed, dict) or not isinstance(parsed.get("summary"), str):
                return conclusion
            return parsed["summary"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return conclusion
