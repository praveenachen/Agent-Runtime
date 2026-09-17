from app.ai.provider import AIProvider
from app.schemas.workflows import ClassificationOutput, ClassifyInput

SYSTEM_PROMPT = """
Classify an incoming operational message.
Return JSON with:
- category: one of support, sales, incident, feedback, general
- priority: one of low, normal, high, urgent
- sentiment: one of negative, neutral, positive
- confidence: number from 0 to 1
"""


def classify_message(input_payload: dict, provider: AIProvider) -> ClassificationOutput:
    validated_input = ClassifyInput.model_validate(input_payload)
    raw_output = provider.generate_json(SYSTEM_PROMPT, validated_input.model_dump())
    return ClassificationOutput.model_validate(raw_output)
