from app.ai.provider import MockAIProvider
from app.schemas.workflows import ClassificationOutput, StructuredDataOutput, SummaryOutput
from app.workflows.classify import classify_message
from app.workflows.extract import extract_structured_data
from app.workflows.summarize import summarize_text


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


def test_classify_message_returns_valid_output() -> None:
    result = classify_message({"message": "The nightly workflow failed."}, MockAIProvider())

    assert isinstance(result, ClassificationOutput)
    assert 0 <= result.confidence <= 1


def test_empty_extraction_output_does_not_succeed():
    import pytest
    from pydantic import ValidationError

    class EmptyProvider(MockAIProvider):
        def generate_json(self, *args):
            return {}

    with pytest.raises(ValidationError):
        extract_structured_data({"text": "hello"}, EmptyProvider())
