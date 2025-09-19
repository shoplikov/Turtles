from typing import Optional, Dict, Any
from pydantic import BaseModel


class InstructionRequest(BaseModel):
    instruction: str
    project_key: Optional[str] = "PROJ"


class TaskResponse(BaseModel):
    success: bool
    task_key: Optional[str] = None
    message: str
    details: Optional[Dict[str, Any]] = None


