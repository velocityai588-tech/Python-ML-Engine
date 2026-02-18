from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List  # <--- ADDED THIS IMPORT
from app.models.schemas import PredictionRequest, PredictionResponse, FeedbackRequest, BottleneckReport, AvailabilityReport
from app.services.feature_builder import FeatureBuilder
from app.services.rl_model import model_instance
from app.services.analytics import analytics_service
from app.db.supabase import supabase_client
from app.core.config import settings
import uuid
from app.models.schemas import CapacityRequest, CapacityReport
import numpy as np

router = APIRouter()
feature_builder = FeatureBuilder()

@router.post("/predict", response_model=PredictionResponse)
async def predict_assignment(request: PredictionRequest):
    """
    Auto-Assignment:
    1. Filter out ineligible employees (SRS Mismatch).
    2. Score remaining employees using RL Model.
    3. Check for bottlenecks.
    """
    try:
        # 1. Eligibility Check (Hard Constraints)
        availability_reports = analytics_service.check_eligibility(request.task, request.candidates)
        eligible_candidates = [c for c in request.candidates if next((r.is_eligible for r in availability_reports if r.employee_id == c.id), False)]
        
        if not eligible_candidates:
             # Fallback: If no one matches, return everyone but with low confidence
             eligible_candidates = request.candidates

        # 2. RL Inference
        context_vectors = []
        candidate_ids = []
        for cand in eligible_candidates:
            vector = feature_builder.build_context_vector(request.task, cand)
            context_vectors.append(vector)
            candidate_ids.append(cand.id)
            
        scores = model_instance.predict(candidate_ids, np.array(context_vectors))
        
        # 3. Bottleneck Warning
        bottleneck = analytics_service.analyze_bottlenecks(request.candidates, 0)
        warning = None
        if bottleneck.system_strain_score > 80:
            warning = f"System Strain {bottleneck.system_strain_score}%: Consider delaying task."

        # 4. Log to Supabase
        rec_id = str(uuid.uuid4())
        log_entry = {
            "id": rec_id,
            "task_id": str(uuid.uuid4()),
            "task_features": request.task.model_dump(),
            "candidate_ids": candidate_ids,
            # Add this line to satisfy the database constraint
            "candidate_features": [c.model_dump() for c in eligible_candidates], 
            "recommended_action": scores[0]['id'] if scores else "NONE",
            "model_version": settings.MODEL_VERSION,
            "confidence_score": scores[0]['confidence'] if scores else 0.0
        }
        supabase_client.table("decision_logs").insert(log_entry).execute()
        
        return {
            "recommendation_id": rec_id,
            "sorted_candidates": [
                {"employee_id": s["id"], "score": s["score"], "confidence": s["confidence"]} 
                for s in scores
            ],
            "bottleneck_warning": warning,
            "model_version": settings.MODEL_VERSION
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze/bottlenecks", response_model=BottleneckReport)
async def get_bottlenecks(request: PredictionRequest):
    """Returns system health and skill shortages."""
    return analytics_service.analyze_bottlenecks(request.candidates, 1)

@router.post("/analyze/availability", response_model=List[AvailabilityReport])
async def check_availability(request: PredictionRequest):
    """Returns raw eligibility based on Project SRS."""
    return analytics_service.check_eligibility(request.task, request.candidates)

@router.post("/train")
async def train_feedback(feedback: FeedbackRequest):
    """Learns from Manager Feedback."""
    try:
        # Update Log
        supabase_client.table("decision_logs").update({
            "final_action_taken": feedback.selected_employee_id,
            "reward_value": feedback.actual_reward
        }).eq("id", feedback.recommendation_id).execute()

        # Update Model
        # In a real system, you'd fetch the original context vector here.
        # For prototype, we acknowledge receipt.
        return {"status": "success", "message": "Feedback recorded."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze/capacity", response_model=List[CapacityReport])
async def check_team_capacity(request: CapacityRequest):
    """
    NEW ENDPOINT: Calculates the true available hours for the team based on 
    base capacity, PTO, and holidays. Does not affect the ML model.
    """
    reports = []
    
    for emp in request.candidates:
        # The Math: Productive - PTO - Holiday
        net_hours = (
            emp.base_productive_hours 
            - emp.pto_hours_this_week 
            - emp.holiday_hours_this_week
        )
        
        # Prevent negative hours
        net_hours = max(0.0, net_hours)
        
        # Determine human-readable status
        if net_hours == 0:
            status = "Overloaded / Out of Office"
        elif net_hours < 10:
            status = "At Capacity"
        else:
            status = "Available"

        reports.append(CapacityReport(
            employee_id=emp.id,
            name=emp.name,
            base_productive_hours=emp.base_productive_hours,
            pto_hours_this_week=emp.pto_hours_this_week,
            holiday_hours_this_week=emp.holiday_hours_this_week,
            net_available_hours=net_hours,
            status=status
        ))
        
    # Sort by who has the most time available
    return sorted(reports, key=lambda x: x.net_available_hours, reverse=True)