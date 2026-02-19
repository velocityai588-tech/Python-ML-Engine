from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict

# --- CORE ENTITIES ---

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
    
    # --- CAPACITY FIELDS ---
    base_productive_hours: float = 40.0  # Default 40, or learned average
    pto_hours_this_week: float = 0.0
    holiday_hours_this_week: float = 0.0

# --- ANALYSIS MODELS ---

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

# --- CAPACITY ---

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

# --- SKILL MATCHING MODULE (#2) ---

class SkillMatchScore(BaseModel):
    employee_id: str
    name: str
    skill_match_percent: float  # 0-100%
    missing_skills: List[str]
    excess_skills: List[str]
    assignment_score: float  # Composite score for assignment readiness
    reallocation_success_probability: float  # 0-1.0

class SkillMatchRequest(BaseModel):
    task: TaskFeatures
    candidates: List[EmployeeCandidate]

class SkillMatchResponse(BaseModel):
    matches: List[SkillMatchScore]
    best_candidate_id: str
    skill_gap_risk: str  # "Low", "Medium", "High", "Critical"

# --- TIMELINE CALCULATIONS (#4) ---

class TimelineProjection(BaseModel):
    employee_id: str
    name: str
    estimated_completion_hours: float
    learning_curve_factor: float  # 0.8 - 1.5 (1.0 = baseline)
    cpm_critical_path_days: float  # Critical Path Method calculation
    risk_of_delay_percent: float  # 0-100%

class TimelineRequest(BaseModel):
    task: TaskFeatures
    candidates: List[EmployeeCandidate]
    project_dependencies: List[str] = []  # Task IDs this depends on

class TimelineResponse(BaseModel):
    projections: List[TimelineProjection]
    earliest_completion_date: str  # ISO format
    latest_safe_start_date: str  # ISO format
    recommended_candidate_id: str

# --- FEASIBILITY CALCULATIONS (#5) ---

class FeasibilityScore(BaseModel):
    employee_id: str
    name: str
    skill_feasibility: float  # 0-1.0
    timeline_feasibility: float  # 0-1.0
    capacity_feasibility: float  # 0-1.0
    learning_feasibility: float  # 0-1.0 (How quickly can they learn?)
    overall_feasibility: float  # Average of above
    blocker_flags: List[str]  # Critical constraints

class FeasibilityRequest(BaseModel):
    task: TaskFeatures
    candidates: List[EmployeeCandidate]
    deadline_days: int = 5  # Project deadline in days

class FeasibilityResponse(BaseModel):
    feasibility_scores: List[FeasibilityScore]
    viable_candidates: List[str]  # Employee IDs that are feasible
    recommendation: str  # Why the task should/shouldn't proceed

# --- AI INSIGHT GENERATION (#6) ---

class InsightTrigger(BaseModel):
    trigger_type: str  # "Overload", "Timeline Risk", "Underutilization", "Skill Gap"
    severity: str  # "Low", "Medium", "High", "Critical"
    affected_employee_ids: List[str]
    description: str
    recommended_action: str

class AIInsightRequest(BaseModel):
    candidates: List[EmployeeCandidate]
    tasks_in_progress: int = 0
    overdue_tasks: int = 0

class AIInsightResponse(BaseModel):
    insights: List[InsightTrigger]
    overall_health: str  # "Healthy", "Caution", "Warning", "Critical"
    priority_actions: List[str]

# --- PTO IMPACT CALCULATIONS (#8) ---

class PTOImpactAnalysis(BaseModel):
    employee_id: str
    name: str
    initial_available_hours: float
    pto_deduction_hours: float
    net_available_after_pto: float
    timeline_impact_days: float  # How many days delay if assigned
    task_completion_probability: float  # 0-1.0

class PTOImpactRequest(BaseModel):
    task: TaskFeatures
    candidates: List[EmployeeCandidate]
    start_date: str  # ISO format

class PTOImpactResponse(BaseModel):
    impact_analysis: List[PTOImpactAnalysis]
    recommended_candidate_id: str
    deferral_recommendation: bool  # Should we defer the task?

# --- TIMESHEET-BASED LEARNING (#9) ---

class TimesheetLearningMetric(BaseModel):
    employee_id: str
    name: str
    productive_hours_tracked: float  # From timesheet
    learning_hours_invested: float  # Training/upskilling
    capacity_prediction_accuracy: float  # 0-1.0
    skill_improvement_rate: float  # Skills per week
    recommended_training_hours: float

class TimesheetLearningRequest(BaseModel):
    candidates: List[EmployeeCandidate]
    days_historical: int = 84  # 12-week window

class TimesheetLearningResponse(BaseModel):
    metrics: List[TimesheetLearningMetric]
    team_learning_velocity: float  # Skills/week avg
    training_gaps: List[str]

# --- RECOMMENDATION ENGINE (#10) ---

class Recommendation(BaseModel):
    recommendation_type: str  # "timeline_extension", "hiring", "scope_reduction", "skill_training"
    description: str
    estimated_cost: Optional[float] = None  # In hours or currency
    timeline_impact_days: Optional[float] = None
    risk_mitigation_level: str  # "Low", "Medium", "High"

class RecommendationEngineRequest(BaseModel):
    task: TaskFeatures
    candidates: List[EmployeeCandidate]
    current_blockers: List[str] = []
    budget_hours: Optional[float] = None

class RecommendationEngineResponse(BaseModel):
    recommendations: List[Recommendation]
    primary_recommendation: str
    success_probability: float  # 0-1.0

# --- REALLOCATION IMPACT ANALYSIS (#11) ---

class ReallocationImpact(BaseModel):
    employee_id: str
    name: str
    current_tasks: List[str]  # Task IDs currently assigned
    cascade_impact_employees: List[str]  # Downstream affected employees
    risk_score: float  # 0-100
    recovery_time_hours: float

class ReallocationRequest(BaseModel):
    employee_id: str
    reallocation_reason: str  # "workload", "skill_match", "timeline"
    current_tasks: List[str]
    all_candidates: List[EmployeeCandidate]

class ReallocationResponse(BaseModel):
    impact_analysis: ReallocationImpact
    ripple_effects: List[Dict]  # Tasks/employees affected
    rollback_cost_hours: float

# --- TEAM AGGREGATIONS (#13) ---

class TeamMetrics(BaseModel):
    department_id: str
    department_name: str
    total_employees: int
    total_productive_hours: float
    average_utilization: float  # 0-1.0
    overloaded_count: int
    underutilized_count: int
    critical_skill_gaps: List[str]
    team_health_score: float  # 0-100

class TeamAggregationRequest(BaseModel):
    department_id: Optional[str] = None
    candidates: List[EmployeeCandidate]

class TeamAggregationResponse(BaseModel):
    team_metrics: TeamMetrics
    performance_trends: Dict  # Can hold various trend data
    recommendations: List[str]

# --- HISTORICAL TREND CALCULATIONS (#14) ---

class UtilizationTrend(BaseModel):
    week_number: int
    utilization_percent: float
    tasks_completed: int
    average_completion_time: float

class TrendAnalysis(BaseModel):
    employee_id: str
    name: str
    utilization_trend_12week: List[UtilizationTrend]
    average_velocity: float  # Tasks/week
    trend_direction: str  # "up", "down", "stable"
    velocity_confidence: float  # 0-1.0

class HistoricalTrendRequest(BaseModel):
    candidates: List[EmployeeCandidate]
    weeks_back: int = 12

class HistoricalTrendResponse(BaseModel):
    trend_analysis: List[TrendAnalysis]
    team_velocity_avg: float
    velocity_trend_direction: str