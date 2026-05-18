from app.services.workflow_service import WorkflowService
from app.schemas.workflows import WorkflowType
from app.workflows.summarize import summarize_text


def build_workflow_service() -> WorkflowService:
    service = WorkflowService()
    service.register(WorkflowType.summarize_text, summarize_text)
    return service
