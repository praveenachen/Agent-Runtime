from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from app.ai.openai_provider import OpenAIProvider
from app.core.errors import ErrorCode, ExecutionError


def provider(create):
    instance = OpenAIProvider.__new__(OpenAIProvider)
    instance.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    instance.model = "test"
    return instance


@pytest.mark.parametrize(
    "kind, status, expected",
    [
        (RateLimitError, 429, ErrorCode.rate_limited),
        (APIStatusError, 503, ErrorCode.unavailable),
        (APIStatusError, 401, ErrorCode.validation),
        (APIStatusError, 400, ErrorCode.validation),
    ],
)
def test_sdk_status_errors_are_normalized(kind, status, expected):
    response = httpx.Response(status, request=httpx.Request("POST", "https://example.test"))
    error = kind("sensitive raw error", response=response, body={"secret": "hidden"})
    with pytest.raises(ExecutionError) as caught:
        provider(Mock(side_effect=error)).generate_json("prompt", {"text": "private"})
    assert caught.value.code == expected
    assert "sensitive" not in str(caught.value)


@pytest.mark.parametrize(
    "kind, expected",
    [(APITimeoutError, ErrorCode.provider_timeout), (APIConnectionError, ErrorCode.unavailable)],
)
def test_sdk_network_errors_are_normalized(kind, expected):
    error = kind(request=httpx.Request("POST", "https://example.test"))
    with pytest.raises(ExecutionError) as caught:
        provider(Mock(side_effect=error)).generate_json("prompt", {})
    assert caught.value.code == expected


@pytest.mark.parametrize(
    "content, reason, refusal",
    [
        ("not json", "stop", None),
        ("[]", "stop", None),
        ("{}", "length", None),
        ("{}", "stop", "refused"),
        (None, "stop", None),
    ],
)
def test_malformed_provider_response(content, reason, refusal):
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=reason, message=SimpleNamespace(content=content, refusal=refusal)
            )
        ]
    )
    with pytest.raises(ExecutionError) as caught:
        provider(Mock(return_value=response)).generate_json("prompt", {})
    assert caught.value.code == ErrorCode.structured_output
