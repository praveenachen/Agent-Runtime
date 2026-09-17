import json
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.ai.provider import AIProvider
from app.core.config import get_settings
from app.core.errors import ErrorCode, ExecutionError


class OpenAIProvider(AIProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.provider_timeout_seconds,
            max_retries=0,
        )
        self.model = settings.openai_model

    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload)},
                ],
            )
        except RateLimitError:
            raise ExecutionError(ErrorCode.rate_limited) from None
        except APITimeoutError:
            raise ExecutionError(ErrorCode.provider_timeout) from None
        except APIConnectionError:
            raise ExecutionError(ErrorCode.unavailable) from None
        except APIStatusError as exc:
            code = ErrorCode.unavailable if exc.status_code >= 500 else ErrorCode.validation
            raise ExecutionError(code) from None
        try:
            choice = response.choices[0]
            if choice.finish_reason != "stop" or choice.message.refusal:
                raise ValueError("Incomplete or refused output")
            output = json.loads(choice.message.content or "")
            if not isinstance(output, dict):
                raise ValueError("Expected object")
            return output
        except (ValueError, IndexError, TypeError):
            raise ExecutionError(ErrorCode.structured_output) from None
