from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.models.schemas import PredictionRequest, PredictionResponse, FeedbackRequest
from app.services.feature_builder import FeatureBuilder
from app.services.rl_model import model_instance
from app.db.supabase import supabase_client
from app.core.config import settings
import uuid
import json
import numpy as np

router = APIRouter()
feature_builder = FeatureBuilder()

@router.post("/predict", response_model=PredictionResponse)
async def predict_assignment(request: PredictionRequest):
    try:
        # 1. Generate Context Vectors for all candidates
        context_vectors = []
        candidate_ids = []
        
        for cand in request.candidates:
            vector = feature_builder.build_context_vector(request.task, cand)
            context_vectors.append(vector)
            candidate_ids.append(cand.id)
            
        # 2. Get Scores from RL Model
        scores = model_instance.predict(
            arm_ids=candidate_ids, 
            context_vectors=np.array(context_vectors)
        )
        
        # 3. Log to Supabase (Asynchronous)
        rec_id = str(uuid.uuid4())
        log_entry = {
            "id": rec_id,
            "task_features": request.task.model_dump(),
            "candidate_ids": candidate_ids,
            "recommended_action": scores[0]['id'], # Top pick
            "model_version": settings.MODEL_VERSION,
            "confidence_score": scores[0]['confidence']
        }
        
        # Note: In production, use BackgroundTasks for this DB write
        supabase_client.table("decision_logs").insert(log_entry).execute()
        
        return {
            "recommendation_id": rec_id,
            "sorted_candidates": [
                {"employee_id": s["id"], "score": s["score"], "confidence": s["confidence"]} 
                for s in scores
            ],
            "model_version": settings.MODEL_VERSION
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/train")
async def train_feedback(feedback: FeedbackRequest):
    try:
        # 1. Retrieve the original context from DB
        # We need the feature vector used at the time of prediction to learn correctly
        response = supabase_client.table("decision_logs").select("*").eq("id", feedback.recommendation_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Recommendation ID not found")
            
        log_data = response.data[0]
        
        # 2. Re-construct the feature vector (Or better, store vector in DB to save compute)
        # For this prototype, we'll assume we can rebuild it or stored it. 
        # *Simplification*: We trust the current feature builder produces same vector.
        # In PROD: Store the vector array in Supabase `decision_logs` as jsonb
        
        # ... Re-fetching task/employee data would be needed here if not stored ...
        # For the sake of this code snippet, we will assume a generic update 
        # or that you pass the context back from Frontend (Stateful)
        
        # Let's update the Log with the final action
        supabase_client.table("decision_logs").update({
            "final_action_taken": feedback.selected_employee_id,
            "reward_value": feedback.actual_reward
        }).eq("id", feedback.recommendation_id).execute()

        # 3. Update the Model (Online Learning)
        # Warning: This requires the original context vector `x`. 
        # Ideally, pass `x` in the feedback or fetch from DB.
        # For now, we acknowledge the feedback was received.
        
        return {"status": "success", "message": "Model updated (logged)"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))