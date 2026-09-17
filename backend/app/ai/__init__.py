from app.ai.provider import AIProvider, MockAIProvider
from app.core.config import get_settings


def build_provider() -> AIProvider:
    if not get_settings().openai_api_key:
        return MockAIProvider()
    from app.ai.openai_provider import OpenAIProvider

    return OpenAIProvider()
