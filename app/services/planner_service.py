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

# ... (Keep your decompose_project function exactly as it is) ...

# ==========================================
# STEP 2: ALLOCATION LOGIC (Helper Functions)
# ==========================================
def filter_top_resources(task_context: str, employees: list, top_k: int = 10):
    """
    Ranks employees based on: 
    1. Skill/Role Match (TF-IDF)
    2. Fallback Baseline (for empty profiles)
    3. Capacity Boost (Tie-breaker)
    """
    tokens = task_context.lower().split()
    if not tokens or not employees:
        return employees[:top_k]

    token_counts = Counter(tokens)
    num_employees = len(employees)
    
    # Calculate Document Frequency across both SKILLS and ROLES
    df_counts = Counter()
    for emp in employees:
        skills_list = emp.get('skills') or []
        role_words = str(emp.get('role', '')).lower().split()
        
        # Combine skills and role words to build our dictionary
        unique_terms = set(str(s).lower() for s in skills_list).union(role_words)
        for term in unique_terms:
            df_counts[term] += 1

    scored_employees = []

    for emp in employees:
        score = 0.0
        
        # Extract employee data safely
        skills_list = emp.get('skills') or []
        emp_skills = [str(s).lower() for s in skills_list]
        role = str(emp.get('role', 'employee')).lower()
        role_words = role.split()
        
        # 1. TF-IDF Scoring for Skills AND Role
        for word in set(tokens):
            if word in emp_skills or word in role_words:
                idf = math.log(num_employees / (df_counts[word] + 1))
                # Give a 50% higher weight if the word is specifically in their Job Title
                weight = 1.5 if word in role_words else 1.0 
                score += idf * token_counts[word] * weight
        
        # 2. Fallback Baseline (If score is 0, give them a tiny bump so they aren't eliminated)
        if score == 0.0:
            score += 0.1 
            
        # 3. Capacity Boost (Tie-breaker & Prioritize availability)
        # e.g., 40 hours = +0.40 score, 10 hours = +0.10 score
        capacity = emp.get('capacity_hours_per_week', 0)
        capacity_boost = (capacity / 100.0) 
        
        final_score = score + capacity_boost
        scored_employees.append((final_score, emp))

    # Sort descending by final score
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

    # 2. FILTER CANDIDATES (Now resilient to sparse data)
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
            "role": emp.get('role', 'Unknown Role'), # Added role for LLM context
            "skills": emp.get('skills', []),
            "capacity": emp.get('capacity_hours_per_week', 40),
            "history": (emp.get('jira_history') or [])[:3],
            "leave": emp.get('leave_status') or "Available"
        })

    # 4. CONSTRUCT PROMPT (Updated with Sparse Data Instructions)
    prompt = f"""
    You are a Technical Program Manager responsible for assigning engineering tasks to internal resources.

    Your job is to analyze a task and allocate the most suitable candidate(s) from the provided resource list.

    --------------------------------------------------

    TASK DETAILS

    Task Name: {request.task_name}
    Description: {request.task_description}
    Required Skills: {request.required_skills}
    Est. Hours: {request.estimated_hours}
    Task Duration: {request.start_date} → {request.end_date}

    --------------------------------------------------

    AVAILABLE RESOURCES (Anonymized)

    {compact_resources}

    --------------------------------------------------

    ASSIGNMENT RULES (Handling Sparse Data)

    Evaluate candidates using this priority order. You MUST account for missing data (new employees).

    1. **Relevant Jira History:** If a candidate has successfully completed similar tasks, prioritize them.
    2. **Skill Match:** If history is missing, look at their specific 'skills' array.
    3. **Role Fallback:** If BOTH history and skills are empty, evaluate if their 'role' logically aligns with the task. Do NOT penalize candidates solely for missing history; they may be new hires.
    4. **Availability & Capacity:** - Candidate must NOT have overlapping leave during the task duration.
       - If candidates are equally matched, prioritize the one with the highest available capacity.
    5. **Task Splitting:** Assign to ONE candidate when possible. Use TWO only if estimated hours exceed single capacity.

    --------------------------------------------------

    OUTPUT FORMAT

    Return ONLY structured JSON. 
    The 'reason' string must briefly explain why they were chosen, referencing their capacity, history, or role.

    {{
      "assignments": [
        {{
          "real_user_id": "Candidate ID (e.g., E1)",
          "employee_name": "Leave blank",
          "match_percentage": 95,
          "justification": "Selected because their role matches the requirement and they have 40 hours of capacity."
        }}
      ]
    }}
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