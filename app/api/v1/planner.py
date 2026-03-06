from fastapi import APIRouter, HTTPException
from app.models.schemas import PlanRequest, PlanResponse
from app.services.planner_service import generate_project_plan

router = APIRouter()

@router.post("/generate", response_model=PlanResponse)
async def create_plan(payload: PlanRequest):
    """
    Endpoint to trigger the AI planning engine. 
    Fetches real-time Jira history and leave status from Supabase.
    """
    try:
        # Validate that the project window is provided
        if not payload.start_date or not payload.end_date:
            raise HTTPException(
                status_code=400, 
                detail="Project start_date and end_date are required for leave conflict checks."
            )

        # Pass the context-heavy parameters to the service layer
        # Note: we no longer pass payload.employees; we fetch from the DB using org_id
        plan = await generate_project_plan(
            project_desc=payload.project_description,
            org_id=payload.org_id,
            start_date=payload.start_date,
            end_date=payload.end_date
        )
        
        return plan

    except Exception as e:
        # Log the internal error details for debugging
        print(f"Server Error in /planner/generate: {str(e)}")
        
        raise HTTPException(
            status_code=500, 
            detail=f"Planning Error: {str(e)}"
        )