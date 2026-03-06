from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date
# --- INPUT SCHEMAS (From Node.js/Frontend to Python) ---

class PlanRequest(BaseModel):
    """
    Requested project parameters. 
    Python uses org_id to fetch employees and Jira/Leave data internally.
    """
    org_id: str = Field(..., description="The UUID of the organization")
    project_description: str = Field(..., description="The PRD or task list to analyze")
    start_date: date = Field(..., description="Project start date")
    end_date: date = Field(..., description="Project end date")


# --- OUTPUT SCHEMAS (From Python back to Node.js) ---

class Assignment(BaseModel):
    """
    The AI's specific mapping of a real user to a task.
    """
    real_user_id: str
    employee_name: str
    match_percentage: int
    justification: str

class TaskOutput(BaseModel):
    """
    A logical technical task decomposed from the project description.
    """
    task_name: str
    description: str
    required_skills: List[str]
    assignments: List[Assignment]

class PlanResponse(BaseModel):
    """
    The full AI-generated planning document.
    """
    analysis_summary: str
    suggested_tasks: List[TaskOutput]