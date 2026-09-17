from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from app.ai import build_provider
from app.ai.provider import AIProvider
from app.core.errors import ErrorCode, ExecutionError
from app.schemas.workflows import INPUT_MODELS, WorkflowType

WorkflowHandler = Callable[[dict[str, Any], AIProvider], BaseModel]


class WorkflowService:
    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider or build_provider()
        self._handlers: dict[WorkflowType, WorkflowHandler] = {}

    def register(self, workflow_type: WorkflowType, handler: WorkflowHandler) -> None:
        self._handlers[workflow_type] = handler

    def execute(self, workflow_type: str, input_payload: dict[str, Any]) -> dict[str, Any]:
        try:
            workflow = WorkflowType(workflow_type)
            input_payload = INPUT_MODELS[workflow].model_validate(input_payload).model_dump()
        except (ValueError, ValidationError):
            raise ExecutionError(ErrorCode.validation) from None
        handler = self._handlers.get(workflow)
        if not handler:
            raise ExecutionError(ErrorCode.validation)
        try:
            result = handler(input_payload, self.provider)
        except ValidationError:
            raise ExecutionError(ErrorCode.structured_output) from None
        return result.model_dump()
