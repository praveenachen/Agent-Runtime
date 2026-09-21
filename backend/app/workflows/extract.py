from app.ai.provider import AIProvider
from app.schemas.workflows import ExtractInput, StructuredDataOutput

SYSTEM_PROMPT = """
Extract structured operational data from the provided text.
Return JSON with:
- title: a string containing a short descriptive title, or null
- entities: an array of objects, each containing name (string), type (string), and value
  (string or null)
- dates: an array of strings containing dates found or inferred from the text
- action_items: an array of strings containing clear follow-up tasks
"""


def extract_structured_data(input_payload: dict, provider: AIProvider) -> StructuredDataOutput:
    validated_input = ExtractInput.model_validate(input_payload)
    raw_output = provider.generate_structured(
        SYSTEM_PROMPT, validated_input.model_dump(), output_model=StructuredDataOutput
    )
    return StructuredDataOutput.model_validate(raw_output)
