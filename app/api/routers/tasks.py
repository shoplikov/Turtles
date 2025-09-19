from fastapi import APIRouter, HTTPException

from app.models.schemas import InstructionRequest, TaskResponse
from app.services.llm import parse_instruction_with_llm
from app.services.jira import get_jira_client


router = APIRouter(prefix="", tags=["tasks"])


@router.post("/create-jira-task", response_model=TaskResponse)
async def create_jira_task(request: InstructionRequest) -> TaskResponse:
    try:
        task_data = parse_instruction_with_llm(request.instruction, request.project_key)

        jira_client = get_jira_client()
        jira_response = await jira_client.create_issue(
            project_key=request.project_key,
            summary=task_data.get("summary"),
            description=task_data.get("description"),
            issue_type=task_data.get("issue_type", "Task"),
            priority=task_data.get("priority", "Medium"),
            labels=task_data.get("labels", []),
            components=task_data.get("components", []),
            assignee=task_data.get("assignee"),
        )

        issue_key = jira_response.get("key")

        return TaskResponse(
            success=True,
            task_key=issue_key,
            message=f"Successfully created Jira task: {issue_key}",
            details={
                "parsed_data": task_data,
                "jira_response": jira_response,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        return TaskResponse(
            success=False,
            message=f"Failed to create task: {str(e)}",
            details={"error": str(e)},
        )


