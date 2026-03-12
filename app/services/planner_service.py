import math
import json
from collections import Counter
from typing import List
from pydantic import BaseModel
from app.services.llm_handler import LLMHandler
from app.models.schemas import (
    DecompositionResponse, 
    AllocationRequest, 
    Assignment,
    ProjectInput,
    BatchAllocationRequest
)
from app.db.supabase import supabase

llm = LLMHandler()

# ==========================================
# STEP 1: DECOMPOSITION LOGIC
# ==========================================
async def decompose_project(project_description: str) -> DecompositionResponse:
    """
    Takes a project description, analyzes it via LLM, and returns structured tasks.
    """
    prompt = f"""
    ### ROLE
    You are a Senior Technical Program Manager and System Architect. Your goal is to take a high-level project vision and turn it into a concrete, executable engineering roadmap.

    ### TASK
    Analyze the project description provided and break it down into logical, sequential engineering tasks.
    - Focus on technical milestones (e.g., API design, Database schema, Frontend components).
    - Each task should be sized between 4 to 24 hours.
    - 'required_skills' must use industry-standard naming (e.g., 'PostgreSQL', 'React').
    - Ensure tasks are "MECE" (Mutually Exclusive, Collectively Exhaustive).
    - Focus on technical milestones (API design, Database schema, Frontend components) rather than vague goals.
    - Each task should be sized between 4 to 24 hours. If a task is larger, break it down further.
    
    ### PROJECT DESCRIPTION
    {project_description}

    ### OUTPUT FORMAT & QUALITY STANDARDS
    You must return a JSON object following the `DecompositionResponse` schema. 
    Each task in `suggested_tasks` must adhere to these descriptive standards:

    1. **task_name**: Use action-oriented, professional titles (e.g., "Implement JWT Authentication" instead of "Login stuff").
    2. **description**: Provide 2-3 sentences explaining the technical scope, specific endpoints to be created, or database tables to be modified. It should be clear enough for a developer to start work.
    3. **estimated_hours**: Provide a realistic estimate. 
        - Small UI tweaks: 2-4h
        - CRUD APIs: 6-12h
        - Complex Logic/Integrations: 16-24h
    4. **required_skills**: List 2-4 specific technologies. Avoid generic terms like "Programming". Use "TypeScript", "Tailwind CSS", "Redis", etc.

    Ensure the `analysis_summary` provides a high-level technical architectural overview of the approach you've chosen.
    """
    
    response = await llm.generate_structured(prompt, DecompositionResponse)
    return response


# ==========================================
# STEP 2: ALLOCATION LOGIC (Helper Functions)
# ==========================================
def filter_top_resources(task_context: str, employees: list, top_k: int = 15):
    """
    Ranks employees based on Skill/Role Match, Fallback Baseline, and Capacity.
    """
    tokens = task_context.lower().split()
    if not tokens or not employees:
        return employees[:top_k]

    token_counts = Counter(tokens)
    num_employees = len(employees)
    
    df_counts = Counter()
    for emp in employees:
        skills_list = emp.get('skills') or []
        role_words = str(emp.get('role', '')).lower().split()
        unique_terms = set(str(s).lower() for s in skills_list).union(role_words)
        for term in unique_terms:
            df_counts[term] += 1

    scored_employees = []
    for emp in employees:
        score = 0.0
        skills_list = emp.get('skills') or []
        emp_skills = [str(s).lower() for s in skills_list]
        role = str(emp.get('role', 'employee')).lower()
        role_words = role.split()
        
        for word in set(tokens):
            if word in emp_skills or word in role_words:
                idf = math.log(num_employees / (df_counts[word] + 1))
                weight = 1.5 if word in role_words else 1.0 
                score += idf * token_counts[word] * weight
        
        if score == 0.0:
            score += 0.1 
            
        capacity = emp.get('capacity_hours_per_week', 0)
        capacity_boost = (capacity / 100.0) 
        
        final_score = score + capacity_boost
        scored_employees.append((final_score, emp))

    scored_employees.sort(key=lambda x: x[0], reverse=True)
    return [emp for score, emp in scored_employees[:top_k]]


# ==========================================
# STEP 2: ALLOCATION LOGIC (Main Functions)
# ==========================================

async def allocate_project_team(request: BatchAllocationRequest) -> List[dict]:
    """
    Allocates an entire project team in a single LLM call to prevent 429 errors.
    """
    # 1. FETCH ALL EMPLOYEES ONCE
    try:
        rpc_response = supabase.rpc('get_project_context', {
            'org_uuid': request.org_id,
            'start_dt': request.start_date,
            'end_dt': request.end_date
        }).execute()
        all_employees = rpc_response.data
    except Exception as e:
        print(f"Supabase RPC Error: {e}")
        return []

    if not all_employees:
        return []

    # 2. PREPARE COLLECTIVE CONTEXT
    # Flatten all tasks to find the best pool of candidates for the whole project
    all_task_text = " ".join([f"{t.task_name} {' '.join(t.required_skills)}" for t in request.tasks])
    relevant_employees = filter_top_resources(all_task_text, all_employees, top_k=15)
    
    compact_resources = []
    id_map = {}
    for i, emp in enumerate(relevant_employees):
        temp_id = f"E{i+1}"
        id_map[temp_id] = {"id": emp['id'], "name": emp['name'], "role": emp.get('role', 'Engineer')}
        compact_resources.append({
            "id": temp_id,
            "role": emp.get('role', 'Unknown Role'),
            "skills": emp.get('skills', []),
            "capacity": emp.get('capacity_hours_per_week', 40),
            "history": (emp.get('jira_history') or [])[:3]
        })

    # 3. CONSTRUCT BATCH PROMPT
    prompt = f"""
    ### ROLE
    You are an AI Resource Manager specialized in technical team optimization.

    ### OBJECTIVE
    Match the provided list of tasks to the most qualified engineers. Maximize project quality while balancing workload.

    ### ALLOCATION HIERARCHY
    1. **Proven Expertise:** Prioritize engineers with successful Jira history matching the task.
    2. **Technical Alignment:** Match 'required_skills' to engineer 'skills'.
    3. **Role Validation:** Use 'role' as a proxy if skills data is sparse (e.g., Backend Dev for API tasks).
    4. **Load Balancing:** Distribute tasks fairly. Do not exceed an engineer's weekly capacity.

    ### DATA
    TASKS: {json.dumps([t.model_dump() for t in request.tasks])}
    RESOURCES: {json.dumps(compact_resources)}

    ### OUTPUT FORMAT & JUSTIFICATION STANDARDS
Return a JSON object with a list of `assignments`. Each assignment must follow these descriptive guidelines:

1. **match_percentage**: 
    - 90-100%: Perfect match between history, role, and skills.
    - 70-89%: Strong role/skill match but lacks specific Jira history for this task.
    - <70%: Assigned based on availability and role fallback only.
2. **justification**: This must be a professional, evidence-based sentence. 
    - **BAD**: "He knows React."
    - **GOOD**: "Assigned to {name} because their Jira history shows 3 successful deliveries of similar API integrations, and they currently have the 12h of bandwidth required this week."
3. **Load Balancing**: If one resource is the "best" for all tasks, you MUST distribute the load. Do not assign more than 40 hours of work to a single 'real_user_id'. Use the next best available match to ensure the project timeline is met.
    """

    # Internal schemas for structured output
    class BatchAssignment(BaseModel):
        task_name: str
        real_user_id: str
        match_percentage: int
        justification: str

    class BatchResponse(BaseModel):
        assignments: List[BatchAssignment]

    # 4. SINGLE LLM CALL (Eliminates 429 errors)
    response = await llm.generate_structured(prompt, BatchResponse)
    
    # 5. AGGREGATE RESULTS FOR FRONTEND
    team_roster = {}
    for asn in response.assignments:
        temp_id = asn.real_user_id
        real_info = id_map.get(temp_id)
        
        if not real_info:
            continue
        
        user_uuid = str(real_info['id'])
        if user_uuid not in team_roster:
            team_roster[user_uuid] = {
                "id": user_uuid,
                "name": real_info['name'],
                "role": real_info['role'],
                "match_percentage": asn.match_percentage,
                "availability": 100, 
                "task_fit": [asn.task_name],
                "justification": asn.justification,
                "avatar": real_info['name'][:2].upper()
            }
        else:
            # If user is already in roster, add this task to their fit list
            team_roster[user_uuid]["task_fit"].append(asn.task_name)
            # Use the higher match percentage or average? Let's take the latest for simplicity
            team_roster[user_uuid]["match_percentage"] = (team_roster[user_uuid]["match_percentage"] + asn.match_percentage) // 2
            
    return list(team_roster.values())


async def allocate_resource_for_task(request: AllocationRequest):
    """
    Legacy fallback for single task allocation if needed.
    """
    try:
        rpc_response = supabase.rpc('get_project_context', {
            'org_uuid': request.org_id,
            'start_dt': request.start_date,
            'end_dt': request.end_date
        }).execute()
        all_employees = rpc_response.data
    except Exception as e:
        print(f"Supabase RPC Error: {e}")
        return []

    if not all_employees:
        return []

    task_context = f"{request.task_name} {request.task_description} {' '.join(request.required_skills)}"
    relevant_employees = filter_top_resources(task_context, all_employees, top_k=10)
    
    compact_resources = []
    id_map = {}
    for i, emp in enumerate(relevant_employees):
        temp_id = f"E{i+1}"
        id_map[temp_id] = {"id": emp['id'], "name": emp['name']}
        compact_resources.append({
            "id": temp_id,
            "role": emp.get('role', 'Unknown Role'),
            "skills": emp.get('skills', []),
            "capacity": emp.get('capacity_hours_per_week', 40),
            "history": (emp.get('jira_history') or [])[:3]
        })

    prompt = f"""
### ROLE
You are a Senior AI Resource Manager specialized in high-performance engineering team optimization. Your goal is to maximize project success by matching tasks to the most qualified engineers based on empirical data.

### OBJECTIVE
Analyze the provided TASK and the list of AVAILABLE RESOURCES. Select the single best candidate for the job based on the Hierarchy of Evidence.

### DATA INPUTS
1. **TASK**: {request.task_name} (Estimated: {request.estimated_hours} hours).
2. **RESOURCES**: {json.dumps(compact_resources)}

### THE HIERARCHY OF EVIDENCE (Strict Priority)
1. **Proven Track Record (Jira History):** If a resource has 'Successfully Completed' tasks of a similar nature in their history, they are the primary choice. Past performance is the strongest predictor of success.
2. **Technical Alignment (Skills):** Match the 'required_skills' of the task against the engineer's 'skills' array.
3. **Role Proxy:** If history and skills are sparse (common for new hires), evaluate the candidate's 'role' (e.g., a 'Frontend Developer' is a logical fallback for a 'CSS' task even if 'CSS' isn't explicitly listed in their skills).
4. **Availability & Capacity:** You MUST NOT assign a task if the duration overlaps with the candidate's 'leave_status'. If multiple candidates are equally qualified, the tie-breaker is the highest remaining 'capacity'.

### OUTPUT QUALITY STANDARDS
You must return a JSON object containing an `assignments` list. Each assignment must meet these descriptive requirements:

1. **match_percentage**: 
    - **90-100%**: Expert match; has both the exact skills and a proven Jira history of similar tasks.
    - **70-89%**: Strong match; has the skills or role alignment but lacks specific recorded history for this exact task type.
    - **Below 70%**: Fallback match; selected based on availability and role-relevance because no better candidate exists.

2. **justification**: Write a professional, data-driven sentence for the Project Manager.
    - **Format**: "Selected [Name] due to [Evidence]. [Capacity Note]."
    - **Example**: "Selected E1 due to their proven history with 3 successful React-based API integrations and their high current availability (40h)."
    - **Note**: Mention if you are using 'Role Fallback' because they are a new hire.

### OUTPUT FORMAT
Provide only valid JSON following this structure:
{{
  "assignments": [
    {{
      "real_user_id": "E1",
      "employee_name": "Leave blank",
      "match_percentage": 95,
      "justification": "Descriptive string here"
    }}
  ]
}}
"""
    
    class AllocationResponseWrapper(BaseModel):
        assignments: List[Assignment]

    response = await llm.generate_structured(prompt, AllocationResponseWrapper)
    
    for asn in response.assignments:
        real_info = id_map.get(asn.real_user_id)
        if real_info:
            asn.real_user_id = str(real_info['id'])
            asn.employee_name = real_info['name']
            
    return response.assignments