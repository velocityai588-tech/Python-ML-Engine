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
    You are an expert Technical Program Manager. 
    Analyze the following project description and break it down into logical, sequential engineering tasks.

    For each task, provide:
    1. A concise task name.
    2. A brief description of the work.
    3. An estimated time to complete in hours.
    4. A list of exact technical skills required (e.g., ["React", "Node.js", "SQL"]).

    Project Description:
    {project_description}
    """
    
    response = await llm.generate_structured(prompt, DecompositionResponse)
    return response

# ==========================================
# STEP 2: ALLOCATION LOGIC (Helper Functions)
# ==========================================
def filter_top_resources(task_context: str, employees: list, top_k: int = 10):
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
    Loops through all project tasks and returns an aggregated team roster.
    """
    team_roster = {}

    for task in request.tasks:
        single_req = AllocationRequest(
            org_id=request.org_id,
            task_name=task.task_name,
            task_description=task.task_description or task.task_name,
            required_skills=task.required_skills,
            estimated_hours=task.estimated_hours,
            start_date=request.start_date,
            end_date=request.end_date
        )
        
        assignments = await allocate_resource_for_task(single_req)
        
        for asn in assignments:
            user_id = asn.real_user_id
            
            if user_id not in team_roster:
                team_roster[user_id] = {
                    "id": user_id,
                    "name": asn.employee_name,
                    "role": "Engineer", 
                    "match_percentage": asn.match_percentage,
                    "availability": 100, 
                    "task_fit": [task.task_name],
                    "justification": asn.justification, # Fixed: was asn.reason
                    "avatar": asn.employee_name[:2].upper() if asn.employee_name else "AI"
                }
            else:
                team_roster[user_id]["task_fit"].append(task.task_name)
                
    return list(team_roster.values())

async def allocate_resource_for_task(request: AllocationRequest):
    """
    Assigns the best employee to a single task using the Gemini Matchmaker.
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
            "history": (emp.get('jira_history') or [])[:3],
            "leave": emp.get('leave_status') or "Available"
        })

    prompt = f"""
    You are a Technical Program Manager. Assign engineering tasks to resources.
    TASK: {request.task_name} ({request.estimated_hours}h)
    RESOURCES: {compact_resources}
    
    RULES:
    1. Prioritize Jira History.
    2. Fallback to Role match if history/skills are missing.
    3. Tie-break with highest capacity.
    
    OUTPUT JSON:
    {{ "assignments": [ {{ "real_user_id": "E1", "employee_name": "", "match_percentage": 90, "justification": "..." }} ] }}
    """
    
    class AllocationResponseWrapper(BaseModel):
        assignments: List[Assignment]

    response = await llm.generate_structured(prompt, AllocationResponseWrapper)
    
    final_assignments = response.assignments
    for asn in final_assignments:
        real_info = id_map.get(asn.real_user_id)
        if real_info:
            asn.real_user_id = str(real_info['id'])
            asn.employee_name = real_info['name']
            
    return final_assignments