from app.ai.provider import AIProvider
from app.schemas.workflows import ExtractInput, StructuredDataOutput

SYSTEM_PROMPT = """
Extract structured operational data from the provided text.
Return JSON with:
- title: short descriptive title or null
- entities: array of objects with name, type, value
- dates: array of date strings found or inferred from the text
- action_items: array of clear follow-up tasks
"""


def extract_structured_data(input_payload: dict, provider: AIProvider) -> StructuredDataOutput:
    validated_input = ExtractInput.model_validate(input_payload)
    raw_output = provider.generate_json(SYSTEM_PROMPT, validated_input.model_dump())
    return StructuredDataOutput.model_validate(raw_output)

