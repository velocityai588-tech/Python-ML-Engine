import math
from collections import Counter
from app.services.llm_handler import LLMHandler
from app.models.schemas import PlanResponse
from app.db.supabase import supabase

llm = LLMHandler()

def filter_top_resources(project_desc: str, employees: list, top_k: int = 20):
    """
    Ranks employees using TF-IDF logic and proficiency multipliers.
    """
    project_tokens = project_desc.lower().split()
    project_counter = Counter(project_tokens)
    num_employees = len(employees)
    
    df_counts = Counter()
    for emp in employees:
        unique_skills = set(s.lower() for s in (emp.get('skills') or []))
        for skill in unique_skills:
            df_counts[skill] += 1

    scored_employees = []
    # Weighted by role from your schema
    multipliers = {"admin": 1.5, "manager": 1.3, "employee": 1.0}

    for emp in employees:
        tfidf_score = 0.0
        emp_skills = [s.lower() for s in (emp.get('skills') or [])]
        
        for word in set(project_tokens):
            if word in emp_skills:
                idf = math.log(num_employees / (df_counts[word] + 1))
                tfidf_score += idf * project_counter[word]
        
        role = (emp.get('role') or 'employee').lower()
        final_score = tfidf_score * multipliers.get(role, 1.0)
        scored_employees.append((final_score, emp))

    scored_employees.sort(key=lambda x: x[0], reverse=True)
    return [emp for score, emp in scored_employees[:top_k]]

async def generate_project_plan(project_desc: str, org_id: str, start_date: str, end_date: str):
    # 1. FETCH CONTEXT: One call to our custom Supabase RPC function
    # This replaces multiple separate table queries
    rpc_response = supabase.rpc('get_project_context', {
        'org_uuid': org_id,
        'start_dt': start_date,
        'end_dt': end_date
    }).execute()

    all_employees = rpc_response.data
    
    # 2. PRE-FILTER: Select top 20 resources locally before LLM pass
    relevant_employees = filter_top_resources(project_desc, all_employees, top_k=20)
    
    # 3. ANONYMIZE & TOKEN OPTIMIZE: Prepare positional array
    id_map = {}
    compact_resources = []
    
    for i, emp in enumerate(relevant_employees):
        temp_id = f"E{i+1}"
        id_map[temp_id] = {"id": emp['id'], "name": emp['name']}
        
        # Pull history and leave status directly from the RPC result
        past_tasks = (emp.get('jira_history') or [])[:3]
        leave_info = emp.get('leave_status') or "Available"
        
        # Positional array [ID, Skills, Capacity, Jira_History, Leave_Status]
        compact_resources.append([
            temp_id, 
            emp['skills'], 
            emp['capacity_hours_per_week'],
            past_tasks,
            leave_info
        ])

    # 4. SYSTEM PROMPT
    prompt = f"""
    Act as a Technical PM. Decompose the project and assign resources.
    Project Dates: {start_date} to {end_date}
    
    Resources [ID, Skills, Weekly Cap, Proven Jira History, Leave Status]:
    {compact_resources}
    
    Project Context:
    {project_desc}
    
    Constraints:
    - Match by Skills vs Proven Jira History.
    - Check 'Leave Status' conflicts for Project Dates.
    - Return JSON only.
    """

    # 5. LLM ORCHESTRATION
    plan_data = await llm.generate_structured(prompt, PlanResponse)

    # 6. DE-ANONYMIZE
    for task in plan_data.suggested_tasks:
        for assignment in task.assignments:
            temp_id = assignment.real_user_id
            real_info = id_map.get(temp_id)
            if real_info:
                assignment.real_user_id = str(real_info["id"])
                assignment.employee_name = real_info["name"]

    return plan_data