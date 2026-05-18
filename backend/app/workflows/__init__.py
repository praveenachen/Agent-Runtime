from app.services.workflow_service import WorkflowService
from app.schemas.workflows import WorkflowType
from app.workflows.classify import classify_message
from app.workflows.extract import extract_structured_data
from app.workflows.summarize import summarize_text


def build_workflow_service() -> WorkflowService:
    service = WorkflowService()
    service.register(WorkflowType.summarize_text, summarize_text)
    service.register(WorkflowType.extract_structured_data, extract_structured_data)
    service.register(WorkflowType.classify_message, classify_message)
    return service
