from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

OutputModel = TypeVar("OutputModel", bound=BaseModel)


class AIProvider(ABC):
    @abstractmethod
    def generate_structured(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_model: type[OutputModel],
    ) -> dict[str, Any]:
        """Return output constrained to the workflow's expected Pydantic model."""


class MockAIProvider(AIProvider):
    def generate_structured(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_model: type[OutputModel],
    ) -> dict[str, Any]:
        text = str(user_payload.get("text") or user_payload.get("message") or "")
        if "summary" in system_prompt.lower():
            words = text.split()
            output = {
                "summary": " ".join(words[:35]) or "No text provided.",
                "key_points": [
                    sentence.strip() for sentence in text.split(".")[:3] if sentence.strip()
                ],
            }
        elif "extract" in system_prompt.lower():
            output = {
                "title": text[:60] or None,
                "entities": [],
                "dates": [],
                "action_items": [],
            }
        else:
            output = {
                "category": "general",
                "priority": "normal",
                "sentiment": "neutral",
                "confidence": 0.72,
            }
        return output_model.model_validate(output).model_dump(mode="json")
