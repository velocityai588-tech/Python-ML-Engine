from pydantic import BaseModel, Field
from typing import List, Optional

# --- STEP 1: DECOMPOSITION INPUT ---
class ProjectInput(BaseModel):
    project_description: str = Field(..., description="Raw project text to be analyzed")

# --- STEP 1: DECOMPOSITION OUTPUT ---
class TaskDecomposition(BaseModel):
    task_name: str
    description: str
    estimated_hours: int
    required_skills: List[str]

class DecompositionResponse(BaseModel):
    analysis_summary: str
    suggested_tasks: List[TaskDecomposition]

# --- STEP 2: ALLOCATION INPUT ---
class AllocationRequest(BaseModel):
    org_id: str
    task_name: str
    task_description: str
    required_skills: List[str]
    estimated_hours: int
    start_date: str # YYYY-MM-DD
    end_date: str   # YYYY-MM-DD

# --- STEP 2: ALLOCATION OUTPUT ---
class Assignment(BaseModel):
    real_user_id: str
    employee_name: str
    match_percentage: int
    justification: str

class TaskAssignmentsResponse(BaseModel):
    assignments: List[Assignment]

class TaskDetail(BaseModel):
    task_name: str
    estimated_hours: int
    required_skills: List[str] = []
    task_description: Optional[str] = "Project task"

# New Schema for the Batch Request
class BatchAllocationRequest(BaseModel):
    org_id: str
    start_date: str
    end_date: str
    tasks: List[TaskDetail]

# Output Schema for the Team Member
class TeamMemberResponse(BaseModel):
    id: str # UUID from DB
    name: str
    role: str
    match_percentage: int
    availability: int
    task_fit: List[str] # List of task names they were assigned to
    justification: str