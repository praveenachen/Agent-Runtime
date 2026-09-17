from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class WorkflowType(StrEnum):
    summarize_text = "summarize_text"
    extract_structured_data = "extract_structured_data"
    classify_message = "classify_message"


class SummarizeInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)


class ExtractInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)


class ClassifyInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=100_000)


class SummaryOutput(BaseModel):
    summary: str = Field(min_length=1)
    key_points: list[str] = Field(default_factory=list)


class ExtractedEntity(BaseModel):
    name: str
    type: str
    value: str | None = None


class StructuredDataOutput(BaseModel):
    title: str | None
    entities: list[ExtractedEntity]
    dates: list[str]
    action_items: list[str]


class ClassificationOutput(BaseModel):
    category: Literal["support", "sales", "incident", "feedback", "general"]
    priority: Literal["low", "normal", "high", "urgent"]
    sentiment: Literal["negative", "neutral", "positive"]
    confidence: float = Field(..., ge=0, le=1)


INPUT_MODELS = {
    WorkflowType.summarize_text: SummarizeInput,
    WorkflowType.extract_structured_data: ExtractInput,
    WorkflowType.classify_message: ClassifyInput,
}
