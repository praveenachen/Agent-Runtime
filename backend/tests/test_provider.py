from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from app.ai.openai_provider import OpenAIProvider
from app.core.errors import ErrorCode, ExecutionError
from app.schemas.workflows import SummaryOutput


def provider(create):
    instance = OpenAIProvider.__new__(OpenAIProvider)
    instance.client = SimpleNamespace(
        beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=create)))
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
        provider(Mock(side_effect=error)).generate_structured(
            "prompt", {"text": "private"}, SummaryOutput
        )
    assert caught.value.code == expected
    assert "sensitive" not in str(caught.value)


@pytest.mark.parametrize(
    "kind, expected",
    [(APITimeoutError, ErrorCode.provider_timeout), (APIConnectionError, ErrorCode.unavailable)],
)
def test_sdk_network_errors_are_normalized(kind, expected):
    error = kind(request=httpx.Request("POST", "https://example.test"))
    with pytest.raises(ExecutionError) as caught:
        provider(Mock(side_effect=error)).generate_structured("prompt", {}, SummaryOutput)
    assert caught.value.code == expected


@pytest.mark.parametrize(
    "parsed, reason, refusal",
    [
        (None, "stop", None),
        ({}, "stop", None),
        (SummaryOutput(summary="ok"), "length", None),
        (SummaryOutput(summary="ok"), "stop", "refused"),
    ],
)
def test_malformed_provider_response(parsed, reason, refusal):
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=reason, message=SimpleNamespace(parsed=parsed, refusal=refusal)
            )
        ]
    )
    with pytest.raises(ExecutionError) as caught:
        provider(Mock(return_value=response)).generate_structured("prompt", {}, SummaryOutput)
    assert caught.value.code == ErrorCode.structured_output


def test_expected_model_is_passed_to_sdk_structured_output_parser():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    parsed=SummaryOutput(summary="Done", key_points=["One"]), refusal=None
                ),
            )
        ]
    )
    create = Mock(return_value=response)

    output = provider(create).generate_structured("prompt", {"text": "private"}, SummaryOutput)

    assert output == {"summary": "Done", "key_points": ["One"]}
    assert create.call_args.kwargs["response_format"] is SummaryOutput
