from enum import StrEnum

from pydantic import BaseModel, Field


class WorkflowType(StrEnum):
    summarize_text = "summarize_text"
    extract_structured_data = "extract_structured_data"
    classify_message = "classify_message"


class SummarizeInput(BaseModel):
    text: str = Field(..., min_length=1)


class ExtractInput(BaseModel):
    text: str = Field(..., min_length=1)


class ClassifyInput(BaseModel):
    message: str = Field(..., min_length=1)


class SummaryOutput(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)


class ExtractedEntity(BaseModel):
    name: str
    type: str
    value: str | None = None


class StructuredDataOutput(BaseModel):
    title: str | None = None
    entities: list[ExtractedEntity] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)


class ClassificationOutput(BaseModel):
    category: str
    priority: str
    sentiment: str
    confidence: float = Field(..., ge=0, le=1)

