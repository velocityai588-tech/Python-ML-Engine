from fastapi import APIRouter, HTTPException
from typing import List
from app.models.schemas import (
    ProjectInput,           # <--- NEW LIGHTWEIGHT INPUT
    DecompositionResponse,
    AllocationRequest,
    Assignment,
    BatchAllocationRequest
)
from app.services.planner_service import (
    allocate_project_team,
    decompose_project, 
    allocate_resource_for_task
)


router = APIRouter()

# ---------------------------------------------------------
# ROUTE 1: Project Decomposition (The "Task Breaker")
# ---------------------------------------------------------
@router.post("/decompose", response_model=DecompositionResponse)
async def step_one_decompose(payload: ProjectInput):
    """
    Step 1: Breaks the project description into logical technical tasks.
    Input: {"project_description": "..."}
    """
    try:
        # Pass just the string to the service
        return await decompose_project(payload.project_description)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Decomposition Error: {str(e)}")

# ---------------------------------------------------------
# ROUTE 2: Resource Allocation (The "Matchmaker")
# ---------------------------------------------------------
@router.post("/allocate", response_model=List[Assignment])
async def step_two_allocate(payload: AllocationRequest):
    """
    Step 2: Assigns employees to a specific approved task.
    Input: Full context (Org ID, Dates, Task Details)
    """
    try:
        return await allocate_resource_for_task(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Allocation Error: {str(e)}")
    
@router.post("/api/v1/planner/allocate")
async def allocate_team_endpoint(req: BatchAllocationRequest):
    team = await allocate_project_team(req)
    return {"recommended_team": team}