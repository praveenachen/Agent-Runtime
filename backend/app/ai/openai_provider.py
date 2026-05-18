import json
from typing import Any

from openai import OpenAI

from app.ai.provider import AIProvider
from app.core.config import get_settings


class OpenAIProvider(AIProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

