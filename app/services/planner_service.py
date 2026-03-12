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
    Takes a project description and returns a professional engineering roadmap.
    """
    prompt = f"""
    ### ROLE
    You are a Senior Technical Program Manager and System Architect. Your goal is to take a high-level project vision and turn it into a concrete, executable engineering roadmap.

    ### TASK
    Analyze the project description provided and break it down into logical, sequential engineering tasks.
    - Focus on technical milestones (e.g., API design, Database schema, Frontend components) rather than vague goals.
    - Each task should be sized between 4 to 24 hours. If a task is larger, break it down further.
    - Ensure tasks are "MECE" (Mutually Exclusive, Collectively Exhaustive).
    
    ### PROJECT DESCRIPTION
    {project_description}

    ### OUTPUT FORMAT & QUALITY STANDARDS
    You must return a JSON object following the `DecompositionResponse` schema. 
    Each task in `suggested_tasks` must adhere to these descriptive standards:

    1. **task_name**: Use action-oriented, professional titles (e.g., "Implement JWT Authentication").
    2. **description**: Provide 2-3 sentences explaining the technical scope and expected deliverables.
    3. **estimated_hours**: Realistic integer (UI tweaks: 2-4h, CRUD APIs: 6-12h, Complex Logic: 16-24h).
    4. **required_skills**: List 2-4 specific technologies (e.g., 'TypeScript', 'PostgreSQL').

    Ensure the `analysis_summary` provides a high-level technical architectural overview.
    """
    
    response = await llm.generate_structured(prompt, DecompositionResponse)
    return response


# ==========================================
# STEP 2: ALLOCATION LOGIC (Helper Functions)
# ==========================================
def filter_top_resources(task_context: str, employees: list, top_k: int = 15):
    """
    Ranks employees based on Skill/Role Match and Capacity using TF-IDF.
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
        
        if score == 0.0: score += 0.1 
            
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
    Allocates an entire project team in a single call to prevent 429 errors.
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

    if not all_employees: return []

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

    prompt = f"""
    ### ROLE
    You are an AI Resource Manager specialized in technical team optimization.

    ### OBJECTIVE
    Match the provided list of tasks to the most qualified engineers. Maximize project quality while balancing workload.

    ### ALLOCATION HIERARCHY
    1. **Proven Expertise:** Prioritize engineers with successful Jira history matching the task.
    2. **Technical Alignment:** Match 'required_skills' to engineer 'skills'.
    3. **Role Validation:** Use 'role' as a proxy if skills data is sparse.
    4. **Load Balancing:** Distribute tasks fairly. Do not exceed 40 hours for a single engineer.

    ### DATA
    TASKS: {json.dumps([t.model_dump() for t in request.tasks])}
    RESOURCES: {json.dumps(compact_resources)}

    ### OUTPUT FORMAT & JUSTIFICATION STANDARDS
    Return a JSON object with a list of `assignments`. Guidelines:
    1. **match_percentage**: 90-100% (Perfect expertise match), 70-89% (Strong role match), <70% (Fallback).
    2. **justification**: Professional, evidence-based sentence. E.g., "Assigned to {{name}} due to 3 successful API deliveries and current 12h bandwidth."
    """

    class BatchAssignment(BaseModel):
        task_name: str
        real_user_id: str
        match_percentage: int
        justification: str

    class BatchResponse(BaseModel):
        assignments: List[BatchAssignment]

    response = await llm.generate_structured(prompt, BatchResponse)
    
    team_roster = {}
    for asn in response.assignments:
        temp_id = asn.real_user_id
        real_info = id_map.get(temp_id)
        
        if not real_info: continue
        
        user_uuid = str(real_info['id'])

        # --- DYNAMIC AVAILABILITY CALCULATION ---
        # Find the original employee record from all_employees to get capacity/leave
        emp_record = next((e for e in all_employees if str(e['id']) == user_uuid), {})
        
        base_capacity = emp_record.get('capacity_hours_per_week', 40)
        leave_status = emp_record.get('leave_status', 'Available')
        
        # Calculate availability percentage
        # If they are on leave, availability is 0. 
        # Otherwise, we calculate based on their capacity.
        if leave_status != 'Available' and leave_status is not None:
            calculated_availability = 0
        else:
            # For now, we assume availability is high, but you could subtract 
            # hours already assigned to other projects here if your RPC returns 'current_load'
            current_load = emp_record.get('current_load_hours', 0)
            calculated_availability = max(0, min(100, int(((base_capacity - current_load) / base_capacity) * 100)))

        if user_uuid not in team_roster:
            team_roster[user_uuid] = {
                "id": user_uuid,
                "name": real_info['name'],
                "role": real_info['role'],
                "match_percentage": asn.match_percentage,
                "availability": calculated_availability, # <--- NOW DYNAMIC
                "task_fit": [asn.task_name],
                "justification": asn.justification,
                "avatar": real_info['name'][:2].upper()
            }
        else:
            team_roster[user_uuid]["task_fit"].append(asn.task_name)
            
    return list(team_roster.values())


async def allocate_resource_for_task(request: AllocationRequest):
    """
    Legacy/Single task allocation logic with high-density system prompt.
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

    if not all_employees: return []

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
    Senior AI Resource Manager.
    
    ### HIERARCHY OF EVIDENCE
    1. Jira History (Proven Track Record)
    2. Technical Skills
    3. Role Proxy (Logical Fallback)
    4. Availability

    ### DATA
    TASK: {request.task_name}
    RESOURCES: {json.dumps(compact_resources)}

    ### OUTPUT FORMAT
    Return JSON structure: {{ "assignments": [ {{ "real_user_id": "E1", "match_percentage": 95, "justification": "Evidence-based justification." }} ] }}
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