from pydantic import BaseModel, Field
from typing import List, Optional

# What the Node.js backend sends TO Python
class EmployeeInput(BaseModel):
    id: str  # The UUID from Supabase
    name: str
    skills: List[str]
    capacity_hours_per_week: int

class PlanRequest(BaseModel):
    project_description: str
    employees: List[EmployeeInput]

# What Python sends BACK to Node.js
class Assignment(BaseModel):
    real_user_id: str
    employee_name: str
    match_percentage: int
    justification: str

class TaskOutput(BaseModel):
    task_name: str
    description: str
    required_skills: List[str]
    assignments: List[Assignment]

class PlanResponse(BaseModel):
    analysis_summary: str
    suggested_tasks: List[TaskOutput]