from typing import Any, Callable

from pydantic import BaseModel

from app.ai.openai_provider import OpenAIProvider
from app.ai.provider import AIProvider, MockAIProvider
from app.core.config import get_settings
from app.schemas.workflows import WorkflowType

WorkflowHandler = Callable[[dict[str, Any], AIProvider], BaseModel]


class WorkflowService:
    def __init__(self, provider: AIProvider | None = None) -> None:
        settings = get_settings()
        self.provider = provider or (OpenAIProvider() if settings.openai_api_key else MockAIProvider())
        self._handlers: dict[WorkflowType, WorkflowHandler] = {}

    def register(self, workflow_type: WorkflowType, handler: WorkflowHandler) -> None:
        self._handlers[workflow_type] = handler

    def execute(self, workflow_type: str, input_payload: dict[str, Any]) -> dict[str, Any]:
        workflow = WorkflowType(workflow_type)
        handler = self._handlers.get(workflow)
        if not handler:
            raise ValueError(f"Unsupported workflow type: {workflow_type}")
        result = handler(input_payload, self.provider)
        return result.model_dump()

