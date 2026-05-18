from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    @abstractmethod
    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        """Return a JSON-serializable response for a workflow prompt."""


class MockAIProvider(AIProvider):
    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        text = str(user_payload.get("text") or user_payload.get("message") or "")
        if "summary" in system_prompt.lower():
            words = text.split()
            return {
                "summary": " ".join(words[:35]) or "No text provided.",
                "key_points": [sentence.strip() for sentence in text.split(".")[:3] if sentence.strip()],
            }
        if "extract" in system_prompt.lower():
            return {
                "title": text[:60] or None,
                "entities": [],
                "dates": [],
                "action_items": [],
            }
        return {
            "category": "general",
            "priority": "normal",
            "sentiment": "neutral",
            "confidence": 0.72,
        }

