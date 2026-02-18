from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional

# --- CORE ENTITIES ---
from pydantic import BaseModel
from typing import List

class EmployeeCandidate(BaseModel):
    id: str
    name: str
    current_load: int
    skills: List[str]
    role_level: str
    avg_completion_time: float
    efficiency_score: float = 1.0
    
    # --- NEW CAPACITY FIELDS ---
    base_productive_hours: float = 40.0  # Default 40, or learned average
    pto_hours_this_week: float = 0.0
    holiday_hours_this_week: float = 0.0
class TaskFeatures(BaseModel):
    title: str = "Untitled Task"
    priority: str          # "High", "Medium", "Low", "Critical"
    complexity: int        # 1-10
    deadline_hours: int    # Hours until deadline
    skills_required: List[str] # Derived from Project SRS

class EmployeeCandidate(BaseModel):
    id: str                # UUID from Supabase
    name: str              # Needed for reporting
    current_load: int      # Number of active tasks
    skills: List[str]
    role_level: str        # e.g., "Junior", "Senior"
    avg_completion_time: float # Historical metric
    efficiency_score: float = 1.0 # 0.0 - 2.0 (1.0 is average), derived from history

# --- ANALYSIS MODELS (NEW) ---

class BottleneckReport(BaseModel):
    overloaded_skills: List[str]  # Skills where Demand > Supply
    at_risk_employees: List[str]  # Employees with > 120% load
    system_strain_score: float    # 0-100% (Overall team capacity usage)
    recommendation: str           # e.g. "Hire more React devs"

class AvailabilityReport(BaseModel):
    employee_id: str
    name: str
    is_eligible: bool             # Matches SRS hard constraints?
    availability_score: float     # 0.0 (Busy) to 1.0 (Free)
    match_reason: str             # "Perfect Skill Match" or "Skill Mismatch"

# --- API REQUESTS/RESPONSES ---

class PredictionRequest(BaseModel):
    task: TaskFeatures
    candidates: List[EmployeeCandidate]

class CandidateScore(BaseModel):
    employee_id: str
    score: float
    confidence: float

class PredictionResponse(BaseModel):
    # Fixes the "model_" namespace warning from Pydantic
    model_config = ConfigDict(protected_namespaces=()) 
    
    recommendation_id: str
    sorted_candidates: List[CandidateScore]
    model_version: str
    bottleneck_warning: Optional[str] = None # Alert if system is strained

# --- FEEDBACK ---

class FeedbackRequest(BaseModel):
    recommendation_id: str
    selected_employee_id: str
    actual_reward: float    # 1.0 (Accepted), 0.0 (Rejected)


class CapacityRequest(BaseModel):
    candidates: List[EmployeeCandidate]

class CapacityReport(BaseModel):
    employee_id: str
    name: str
    base_productive_hours: float
    pto_hours_this_week: float
    holiday_hours_this_week: float
    net_available_hours: float
    status: str  # "Available", "At Capacity", or "Overloaded"