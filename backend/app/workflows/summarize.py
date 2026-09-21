from app.ai.provider import AIProvider
from app.schemas.workflows import SummarizeInput, SummaryOutput

SYSTEM_PROMPT = """
You are a workflow engine step that summarizes text for an operations dashboard.
Return JSON with:
- summary: concise summary under 120 words
- key_points: 3 to 5 short bullet-style strings
"""


def summarize_text(input_payload: dict, provider: AIProvider) -> SummaryOutput:
    validated_input = SummarizeInput.model_validate(input_payload)
    raw_output = provider.generate_structured(
        SYSTEM_PROMPT, validated_input.model_dump(), output_model=SummaryOutput
    )
    return SummaryOutput.model_validate(raw_output)
