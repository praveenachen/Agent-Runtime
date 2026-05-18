from app.services.workflow_service import WorkflowService


def build_workflow_service() -> WorkflowService:
    return WorkflowService()

