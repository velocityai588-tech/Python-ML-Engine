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
    ProjectInput
)
from app.db.supabase import supabase

llm = LLMHandler()

# ==========================================
# STEP 1: DECOMPOSITION LOGIC
# ==========================================
async def decompose_project(project_desc: str):
    """
    Uses Gemini to break a project description into technical tasks.
    """
    # Safe prompt construction using f-string with escaped curly braces for JSON examples
    prompt = f"""
    You are a Technical Project Manager responsible for decomposing software projects into clear engineering tasks.

    Your goal is to convert the provided project description into a structured list of technical tasks that an engineering team can execute.

    -------------------------------------
    PROJECT DESCRIPTION
    {project_desc}
    -------------------------------------

    TASK DECOMPOSITION RULES
    Break the project into logical engineering tasks.
    Each task must:
    • Represent a concrete engineering activity  
    • Be implementable by a single engineer  
    • Be small enough to complete within **4–16 hours**

    Include tasks for:
    - Architecture / setup
    - Backend development
    - Frontend development
    - Database design
    - API implementation
    - Testing

    OUTPUT REQUIREMENTS
    Return ONLY valid JSON.
    The output must match this structure:

    {{
      "suggested_tasks": [
        {{
          "task_name": "Task Title",
          "description": "Technical details...",
          "estimated_hours": 8,
          "required_skills": ["React", "Node.js"]
        }}
      ]
    }}

    Rules:
    - Return between **5 and 15 tasks**
    - Do not include explanations outside JSON
    - Do not include markdown
    """
    
    return await llm.generate_structured(prompt, DecompositionResponse)


# ==========================================
# STEP 2: ALLOCATION LOGIC (Helper Functions)
# ==========================================
def filter_top_resources(task_context: str, employees: list, top_k: int = 10):
    """
    Ranks employees based on skill match (TF-IDF) + Role Weight.
    """
    tokens = task_context.lower().split()
    if not tokens or not employees:
        return employees[:top_k]

    token_counts = Counter(tokens)
    num_employees = len(employees)
    
    df_counts = Counter()
    for emp in employees:
        # Safe get for skills (handled by SQL aggregation now)
        skills_list = emp.get('skills') or []
        unique_skills = set(str(s).lower() for s in skills_list)
        for skill in unique_skills:
            df_counts[skill] += 1

    scored_employees = []
    # Boost Managers/Admins slightly for complex tasks
    multipliers = {"admin": 1.2, "manager": 1.1, "employee": 1.0}

    for emp in employees:
        score = 0.0
        skills_list = emp.get('skills') or []
        emp_skills = [str(s).lower() for s in skills_list]
        
        for word in set(tokens):
            if word in emp_skills:
                # Add +1 smoothing to avoid division by zero
                idf = math.log(num_employees / (df_counts[word] + 1))
                score += idf * token_counts[word]
        
        role = (emp.get('role') or 'employee').lower()
        final_score = score * multipliers.get(role, 1.0)
        scored_employees.append((final_score, emp))

    scored_employees.sort(key=lambda x: x[0], reverse=True)
    return [emp for score, emp in scored_employees[:top_k]]


# ==========================================
# STEP 2: ALLOCATION LOGIC (Main Function)
# ==========================================
async def allocate_resource_for_task(request: AllocationRequest):
    """
    Assigns the best employee to a single task approved by the manager.
    """
    # 1. FETCH CONTEXT
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

    # 2. FILTER CANDIDATES
    task_context = f"{request.task_name} {request.task_description} {' '.join(request.required_skills)}"
    relevant_employees = filter_top_resources(task_context, all_employees, top_k=10)
    
    # 3. PREPARE ANONYMIZED DATA FOR LLM
    compact_resources = []
    id_map = {}
    
    for i, emp in enumerate(relevant_employees):
        temp_id = f"E{i+1}"
        id_map[temp_id] = {"id": emp['id'], "name": emp['name']}
        
        compact_resources.append({
            "id": temp_id,
            "skills": emp.get('skills', []),
            "capacity": emp.get('capacity_hours_per_week', 40),
            "history": (emp.get('jira_history') or [])[:3],
            "leave": emp.get('leave_status') or "Available"
        })

    # 4. CONSTRUCT PROMPT
    prompt = f"""
    Act as a Technical PM. Assign the best resource for the task: '{request.task_name}'.
    
    Task Description: {request.task_description}
    Required Skills: {request.required_skills}
    Est. Hours: {request.estimated_hours}
    Dates: {request.start_date} to {request.end_date}

    Candidates (Anonymized):
    {compact_resources}

    Assignment Rules:
    1. Match Required Skills.
    2. Check 'history' for similar past work.
    3. Check 'leave' for conflicts.
    4. Return a list of assignments.
    """
    
    # 5. DEFINE WRAPPER MODEL LOCALLY
    class AllocationResponseWrapper(BaseModel):
        assignments: List[Assignment]

    # 6. CALL LLM
    response = await llm.generate_structured(prompt, AllocationResponseWrapper)
    
    # 7. DE-ANONYMIZE
    final_assignments = response.assignments
    for asn in final_assignments:
        real_info = id_map.get(asn.real_user_id)
        if real_info:
            asn.real_user_id = str(real_info['id'])
            asn.employee_name = real_info['name']
            
    return final_assignments