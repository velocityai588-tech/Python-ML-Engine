from fastapi import APIRouter, HTTPException
from app.models.schemas import PlanRequest, PlanResponse
from app.services.planner_service import generate_project_plan

router = APIRouter()

@router.post("/generate", response_model=PlanResponse)
async def create_plan(payload: PlanRequest):
    try:
        # Pass the data to the service layer
        plan = await generate_project_plan(
            payload.project_description, 
            payload.employees
        )
        return plan
    except Exception as e:
        # Standardize error reporting
        raise HTTPException(status_code=500, detail=f"Planning Error: {str(e)}")