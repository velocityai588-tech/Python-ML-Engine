import math
import json
from collections import Counter
from app.services.llm_handler import LLMHandler
from app.models.schemas import PlanResponse

llm = LLMHandler()

def filter_top_resources(project_desc: str, employees: list, top_k: int = 20):
    """
    Ranks employees using TF-IDF and expertise weighting.
    """
    project_tokens = project_desc.lower().split()
    project_counter = Counter(project_tokens)
    num_employees = len(employees)
    
    # Calculate Document Frequency (DF) for IDF calculation
    df_counts = Counter()
    for emp in employees:
        # skills is assumed to be a list of strings
        unique_skills = set(s.lower() for s in emp.skills)
        for skill in unique_skills:
            df_counts[skill] += 1

    scored_employees = []
    
    # Proficiency multipliers based on your schema levels
    multipliers = {"advanced": 1.5, "mid": 1.2, "beginner": 1.0}

    for emp in employees:
        tfidf_score = 0.0
        emp_skills = [s.lower() for s in emp.skills]
        
        for word in set(project_tokens):
            if word in emp_skills:
                # TF (Presence) * IDF (Log-scaled uniqueness)
                idf = math.log(num_employees / (df_counts[word] + 1))
                tfidf_score += idf * project_counter[word]
        
        # Apply Expertise Multiplier (Default to 1.0 if not specified)
        # Note: This assumes 'proficiency' is available on the emp object
        level = getattr(emp, 'proficiency', 'beginner').lower()
        final_score = tfidf_score * multipliers.get(level, 1.0)
        
        scored_employees.append((final_score, emp))

    scored_employees.sort(key=lambda x: x[0], reverse=True)
    return [emp for score, emp in scored_employees[:top_k]]

async def generate_project_plan(project_desc: str, employees: list):
    # 1. PRE-FILTER: Narrow 140+ pool down to top 20 high-signal resources
    relevant_employees = filter_top_resources(project_desc, employees, top_k=20)
    
    # 2. ANONYMIZE: Map real data to temporary 'E' IDs for PII and Token safety
    id_map = {}
    compact_resources = []
    
    for i, emp in enumerate(relevant_employees):
        temp_id = f"E{i+1}"
        id_map[temp_id] = {"id": emp.id, "name": emp.name}
        
        # Positional array: [ID, Skills, Capacity]
        compact_resources.append([
            temp_id, 
            emp.skills, 
            emp.capacity_hours_per_week
        ])

    # 3. OPTIMIZED PROMPT
    prompt = f"""
    Role: Technical PM.
    Task: Decompose project and assign resources.
    
    Resources [ID, Skills, Weekly Cap]:
    {compact_resources}
    
    Project Context:
    {project_desc}
    
    Constraints: Assign by skill-fit and capacity.
    Output: JSON only.
    """

    # 4. LLM CALL
    plan_data = await llm.generate_structured(prompt, PlanResponse)

    # 5. DE-ANONYMIZE: Restore real UUIDs and Names
    for task in plan_data.suggested_tasks:
        for assignment in task.assignments:
            temp_id = assignment.real_user_id
            real_info = id_map.get(temp_id)
            
            if real_info:
                assignment.real_user_id = str(real_info["id"])
                assignment.employee_name = real_info["name"]

    return plan_data