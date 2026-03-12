from fastapi import APIRouter, HTTPException
from typing import List
from app.models.schemas import (
    ProjectInput,          
    DecompositionResponse,
    BatchAllocationRequest
)
from app.services.planner_service import (
    allocate_project_team,
    decompose_project
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
# ROUTE 2: Resource Allocation (The "Batch Matchmaker")
# ---------------------------------------------------------
@router.post("/allocate")
async def allocate_team_endpoint(req: BatchAllocationRequest):
    """
    Step 2: Receives an array of tasks and assigns the best team members.
    """
    try:
        team = await allocate_project_team(req)
        return {"recommended_team": team}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Allocation Error: {str(e)}")