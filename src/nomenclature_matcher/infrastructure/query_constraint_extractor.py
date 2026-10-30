from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI

from ..domain.constraints import QueryConstraints

DEFAULT_QUERY_CONSTRAINTS_PROMPT = (
    Path(__file__).resolve().parent.parent / "prompts" / "query_constraints_system.md"
)


class DeepSeekQueryConstraintExtractor:
    """Infrastructure adapter for model-backed constraint extraction."""

    def __init__(self, settings, client=None, prompt_path: str | Path | None = None):
        self.settings = settings
        self.prompt_path = (
            Path(prompt_path) if prompt_path else DEFAULT_QUERY_CONSTRAINTS_PROMPT
        )
        self.system_prompt = self.prompt_path.read_text(encoding="utf-8").strip()
        self.client = client or OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            timeout=settings.deepseek_timeout_seconds,
        )

    def extract(self, query: str) -> QueryConstraints:
        response = self.client.chat.completions.create(
            model=self.settings.deepseek_model,
            temperature=0,
            response_format={"type": "json_object"},
            extra_body={"thinking": {"type": "disabled"}},
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"QUERY:\n{query}"},
            ],
        )
        content = response.choices[0].message.content or "{}"
        return QueryConstraints.model_validate(json.loads(content))
