import json
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
    OpenAI,
    RateLimitError,
)
from pydantic import ValidationError

from app.ai.provider import AIProvider, OutputModel
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

    def generate_structured(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_model: type[OutputModel],
    ) -> dict[str, Any]:
        try:
            response = self.client.beta.chat.completions.parse(
                model=self.model,
                response_format=output_model,
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
        except (ContentFilterFinishReasonError, LengthFinishReasonError):
            raise ExecutionError(ErrorCode.structured_output) from None
        try:
            choice = response.choices[0]
            if choice.finish_reason != "stop" or choice.message.refusal:
                raise ValueError("Incomplete or refused output")
            parsed = choice.message.parsed
            if parsed is None:
                raise ValueError("Expected parsed output")
            return output_model.model_validate(parsed).model_dump(mode="json")
        except (AttributeError, IndexError, TypeError, ValidationError, ValueError):
            raise ExecutionError(ErrorCode.structured_output) from None
