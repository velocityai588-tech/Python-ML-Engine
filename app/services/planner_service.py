from app.services.llm_handler import LLMHandler
from app.models.schemas import PlanResponse
import json

llm = LLMHandler()

async def generate_project_plan(project_desc: str, employees: list):
    # 1. ANONYMIZATION: Create a Map (ID -> Temp Name)
    id_map = {}
    anonymized_employees = []
    
    for i, emp in enumerate(employees):
        temp_id = f"EMP_{i+1:02}"
        # Store metadata to map back later
        id_map[temp_id] = {"id": emp.id, "name": emp.name}
        
        anonymized_employees.append({
            "temp_id": temp_id,
            "skills": emp.skills,
            "capacity": emp.capacity_hours_per_week
        })

    # 2. SYSTEM PROMPT
    prompt = f"""
    Act as a Technical Project Manager. 
    Project Description: {project_desc}
    
    Available Resources: {json.dumps(anonymized_employees)}
    
    Task:
    1. Break down the project into logical technical tasks.
    2. Assign resources based on skill fit and capacity.
    3. Calculate match_percentage (0-100).
    4. Provide a brief justification for each choice.
    """

    # 3. CALL LLM (Uses the schema we defined in Step 1)
    # The 'response_schema' in LLMHandler ensures this returns a PlanResponse object
    plan_data = await llm.generate_structured(prompt, PlanResponse)

    # 4. DE-ANONYMIZATION: Replace Temp IDs with real data
    for task in plan_data.suggested_tasks:
        for assignment in task.assignments:
            # Look up the real info using the temp_id (EMP_01, etc)
            temp_id = assignment.real_user_id # Gemini used temp_id here initially
            real_info = id_map.get(temp_id)
            
            if real_info:
                assignment.real_user_id = real_info["id"]
                assignment.employee_name = real_info["name"]

    return plan_data