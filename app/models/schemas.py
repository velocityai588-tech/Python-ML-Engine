from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# --- INPUTS ---
from pydantic import BaseModel, ConfigDict

class PredictionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())  # Add this line
    
    recommendation_id: str
    sorted_candidates: list
    model_version: str  # This field name was causing the warning
    
class TaskFeatures(BaseModel):
    priority: str          # e.g., "High", "Medium", "Low"
    complexity: int        # 1-10
    deadline_hours: int    # Hours until deadline
    skills_required: List[str]

class EmployeeCandidate(BaseModel):
    id: str                # UUID from Supabase
    current_load: int      # Number of active tasks
    skills: List[str]
    role_level: str        # e.g., "Junior", "Senior"
    avg_completion_time: float # Historical metric

class PredictionRequest(BaseModel):
    task: TaskFeatures
    candidates: List[EmployeeCandidate]

# --- OUTPUTS ---

class CandidateScore(BaseModel):
    employee_id: str
    score: float
    confidence: float

class PredictionResponse(BaseModel):
    recommendation_id: str  # UUID for logging
    sorted_candidates: List[CandidateScore]
    model_version: str

# --- FEEDBACK ---

class FeedbackRequest(BaseModel):
    recommendation_id: str
    selected_employee_id: str
    actual_reward: float    # 1.0 (Accepted), 0.0 (Rejected), or calculated metric