import pytest

from app.ai.provider import AIProvider, MockAIProvider
from app.core.errors import ErrorCode, ExecutionError
from app.schemas.workflows import ClassificationOutput, StructuredDataOutput, SummaryOutput
from app.services.workflow_service import WorkflowService
from app.workflows.classify import classify_message
from app.workflows.extract import extract_structured_data
from app.workflows.summarize import summarize_text


class StaticProvider(AIProvider):
    def __init__(self, output: dict) -> None:
        self.output = output
        self.output_model = None

    def generate_structured(self, system_prompt, user_payload, output_model):
        self.output_model = output_model
        return self.output


def test_summarize_text_returns_valid_output() -> None:
    result = summarize_text({"text": "First point. Second point. Third point."}, MockAIProvider())

    assert isinstance(result, SummaryOutput)
    assert result.summary
    assert result.key_points


def test_extract_structured_data_returns_valid_output() -> None:
    result = extract_structured_data(
        {"text": "Acme needs a follow-up by Friday."}, MockAIProvider()
    )

    assert isinstance(result, StructuredDataOutput)
    assert result.action_items == []


def test_extract_structured_data_validates_nested_entities_and_string_lists() -> None:
    provider = StaticProvider(
        {
            "title": "CSV export issue for Northstar Analytics",
            "entities": [
                {
                    "name": "Maya Chen",
                    "type": "customer",
                    "value": "maya.chen@example.com",
                },
                {"name": "Northstar Analytics", "type": "company", "value": None},
            ],
            "dates": ["September 16, 2026", "Friday at 3 PM"],
            "action_items": ["Investigate the CSV export failure before Friday at 3 PM"],
        }
    )

    result = extract_structured_data({"text": "Customer report"}, provider)

    assert provider.output_model is StructuredDataOutput
    assert result.entities[0].name == "Maya Chen"
    assert result.entities[1].value is None
    assert result.dates == ["September 16, 2026", "Friday at 3 PM"]
    assert result.action_items == ["Investigate the CSV export failure before Friday at 3 PM"]


def test_classify_message_returns_valid_output() -> None:
    result = classify_message({"message": "The nightly workflow failed."}, MockAIProvider())

    assert isinstance(result, ClassificationOutput)
    assert 0 <= result.confidence <= 1


def test_mock_provider_is_deterministic() -> None:
    payload = {"text": "First point. Second point."}
    provider = MockAIProvider()

    assert summarize_text(payload, provider) == summarize_text(payload, provider)


def test_empty_extraction_output_does_not_succeed():
    from pydantic import ValidationError

    class EmptyProvider(MockAIProvider):
        def generate_structured(self, *args, **kwargs):
            return {}

    with pytest.raises(ValidationError):
        extract_structured_data({"text": "hello"}, EmptyProvider())


def test_malformed_extraction_is_structured_output_failure() -> None:
    service = WorkflowService(StaticProvider({}))
    service.register("extract_structured_data", extract_structured_data)

    with pytest.raises(ExecutionError) as caught:
        service.execute("extract_structured_data", {"text": "hello"})

    assert caught.value.code == ErrorCode.structured_output
