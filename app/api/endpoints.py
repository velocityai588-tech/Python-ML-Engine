from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List
from app.models.schemas import (
    PredictionRequest, PredictionResponse, FeedbackRequest, BottleneckReport, AvailabilityReport,
    CapacityRequest, CapacityReport,
    SkillMatchRequest, SkillMatchResponse, SkillMatchScore,
    TimelineRequest, TimelineResponse,
    FeasibilityRequest, FeasibilityResponse,
    AIInsightRequest, AIInsightResponse, InsightTrigger,
    PTOImpactRequest, PTOImpactResponse,
    TimesheetLearningRequest, TimesheetLearningResponse,
    RecommendationEngineRequest, RecommendationEngineResponse, Recommendation,
    ReallocationRequest, ReallocationResponse,
    TeamAggregationRequest, TeamAggregationResponse,
    HistoricalTrendRequest, HistoricalTrendResponse
)
from app.services.feature_builder import FeatureBuilder
from app.services.rl_model import model_instance
from app.services.analytics import analytics_service
from app.db.supabase import supabase_client
from app.core.config import settings
import uuid
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

# ============================================================================
# MODULE #2: SKILL MATCHING
# ============================================================================

@router.post("/skill-matching", response_model=SkillMatchResponse)
async def perform_skill_matching(request: SkillMatchRequest):
    """
    Skill Matching Module (#2):
    - Skill Match Score: % of required skills the employee has
    - Assignment Score: Composite readiness for assignment
    - Reallocation Success Probability: Likelihood of successful task transition
    """
    try:
        matches = analytics_service.calculate_skill_match(request.task, request.candidates)
        
        if not matches:
            raise HTTPException(status_code=400, detail="No candidates provided")
        
        best_match = matches[0]
        
        # Determine skill gap risk
        if best_match.skill_match_percent >= 80:
            skill_gap_risk = "Low"
        elif best_match.skill_match_percent >= 50:
            skill_gap_risk = "Medium"
        elif best_match.skill_match_percent >= 20:
            skill_gap_risk = "High"
        else:
            skill_gap_risk = "Critical"
        
        return {
            "matches": matches,
            "best_candidate_id": best_match.employee_id,
            "skill_gap_risk": skill_gap_risk
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MODULE #4: TIMELINE CALCULATIONS
# ============================================================================

@router.post("/timeline-projections", response_model=TimelineResponse)
async def calculate_timelines(request: TimelineRequest):
    """
    Timeline Calculations (#4):
    - Learning Curve Factors: Adjustment for skill gaps
    - Critical Path Method (CPM): Days to completion
    - Risk of Delay: Probability of missing deadline
    """
    try:
        projections = analytics_service.calculate_timeline_projections(request.task, request.candidates)
        
        if not projections:
            raise HTTPException(status_code=400, detail="No candidates provided")
        
        # Find earliest completion
        best_candidate = min(projections, key=lambda x: x.cpm_critical_path_days)
        earliest_days = best_candidate.cpm_critical_path_days
        
        from datetime import datetime, timedelta
        today = datetime.utcnow()
        earliest_completion = (today + timedelta(days=earliest_days)).isoformat()
        
        # Latest safe start (deadline - estimated days)
        task_deadline_days = request.task.deadline_hours / 8
        latest_safe_start = (today + timedelta(days=max(0, task_deadline_days - earliest_days))).isoformat()
        
        return {
            "projections": projections,
            "earliest_completion_date": earliest_completion,
            "latest_safe_start_date": latest_safe_start,
            "recommended_candidate_id": best_candidate.employee_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MODULE #5: FEASIBILITY CALCULATIONS
# ============================================================================

@router.post("/feasibility-analysis", response_model=FeasibilityResponse)
async def analyze_feasibility(request: FeasibilityRequest):
    """
    Feasibility Calculations (#5):
    - Complete feasibility scoring across skill, timeline, capacity, learning dimensions
    - Identifies blockers
    """
    try:
        scores = analytics_service.calculate_feasibility(request.task, request.candidates, request.deadline_days)
        
        if not scores:
            raise HTTPException(status_code=400, detail="No candidates provided")
        
        # Find viable candidates (overall_feasibility > 0.5)
        viable = [s.employee_id for s in scores if s.overall_feasibility > 0.5]
        
        if viable:
            recommendation = f"Task is feasible. {len(viable)} viable candidate(s) available."
        else:
            recommendation = "CAUTION: No fully viable candidates. Consider scope reduction or timeline extension."
        
        return {
            "feasibility_scores": scores,
            "viable_candidates": viable,
            "recommendation": recommendation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MODULE #6: AI INSIGHT GENERATION
# ============================================================================

@router.post("/ai-insights", response_model=AIInsightResponse)
async def generate_insights(request: AIInsightRequest):
    """
    AI Insight Generation (#6):
    - Rule-based triggers: Overload, Timeline Risk, Underutilization, Skill Gap
    - Overall team health assessment
    """
    try:
        insights = analytics_service.generate_ai_insights(request.candidates, request.tasks_in_progress, request.overdue_tasks)
        
        # Calculate overall health
        critical_count = sum(1 for i in insights if i.severity == "Critical")
        high_count = sum(1 for i in insights if i.severity == "High")
        
        if critical_count >= 2:
            overall_health = "Critical"
        elif critical_count > 0 or high_count >= 2:
            overall_health = "Warning"
        elif high_count > 0:
            overall_health = "Caution"
        else:
            overall_health = "Healthy"
        
        # Priority actions based on insights
        priority_actions = []
        for insight in insights:
            if insight.severity in ["Critical", "High"]:
                priority_actions.append(insight.recommended_action)
        
        return {
            "insights": insights,
            "overall_health": overall_health,
            "priority_actions": priority_actions[:3]  # Top 3 actions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MODULE #8: PTO IMPACT CALCULATIONS
# ============================================================================

@router.post("/pto-impact", response_model=PTOImpactResponse)
async def calculate_pto_impact(request: PTOImpactRequest):
    """
    PTO Impact Calculations (#8):
    - Timeline impact from leave
    - Task completion probability with PTO deduction
    - Resource availability adjusted for PTO
    """
    try:
        analyses = analytics_service.calculate_pto_impact(request.task, request.candidates)
        
        if not analyses:
            raise HTTPException(status_code=400, detail="No candidates provided")
        
        # Find best candidate considering PTO
        best_candidate = max(analyses, key=lambda x: x.task_completion_probability)
        
        # Should we defer? If all have low completion probability
        avg_completion_prob = sum(a.task_completion_probability for a in analyses) / len(analyses)
        deferral_recommendation = avg_completion_prob < 0.4
        
        return {
            "impact_analysis": analyses,
            "recommended_candidate_id": best_candidate.employee_id,
            "deferral_recommendation": deferral_recommendation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MODULE #9: TIMESHEET-BASED LEARNING
# ============================================================================

@router.post("/learning-metrics", response_model=TimesheetLearningResponse)
async def calculate_learning_metrics(request: TimesheetLearningRequest):
    """
    Timesheet-Based Learning (#9):
    - Learning productive hours tracked
    - Capacity prediction accuracy
    - Skill improvement rate
    - Training gaps identification
    """
    try:
        metrics = analytics_service.calculate_timesheet_learning(request.candidates, request.days_historical)
        
        if not metrics:
            raise HTTPException(status_code=400, detail="No candidates provided")
        
        # Calculate team learning velocity
        team_velocity = sum(m.skill_improvement_rate for m in metrics) / max(1, len(metrics))
        
        # Identify training gaps
        training_gaps = []
        for m in metrics:
            if m.recommended_training_hours > 3:  # Threshold: > 3 hours needed
                training_gaps.append(f"{m.name}: {m.recommended_training_hours} hours needed")
        
        return {
            "metrics": metrics,
            "team_learning_velocity": round(team_velocity, 3),
            "training_gaps": training_gaps
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MODULE #10: RECOMMENDATION ENGINE
# ============================================================================

@router.post("/recommendations", response_model=RecommendationEngineResponse)
async def get_recommendations(request: RecommendationEngineRequest):
    """
    Recommendation Engine (#10):
    - Timeline extension
    - Hiring needs
    - Scope reduction
    - Skill training recommendations
    """
    try:
        recommendations = analytics_service.generate_recommendations(
            request.task, request.candidates, request.current_blockers, request.budget_hours
        )
        
        if not recommendations:
            # If no specific recommendations, provide default
            recommendations = [
                Recommendation(
                    recommendation_type="proceed",
                    description="Task can proceed as scheduled",
                    estimated_cost=0,
                    timeline_impact_days=0,
                    risk_mitigation_level="Low"
                )
            ]
        
        primary_rec = recommendations[0] if recommendations else None
        primary_text = f"{primary_rec.recommendation_type}: {primary_rec.description}" if primary_rec else "Proceed"
        
        # Calculate success probability (0-1.0)
        success_prob = 0.85  # Default
        if any(r.recommendation_type == "hiring" for r in recommendations):
            success_prob = 0.75
        if any(r.recommendation_type == "scope_reduction" for r in recommendations):
            success_prob = 0.70
        
        return {
            "recommendations": recommendations,
            "primary_recommendation": primary_text,
            "success_probability": success_prob
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MODULE #11: REALLOCATION IMPACT ANALYSIS
# ============================================================================

@router.post("/reallocation-impact", response_model=ReallocationResponse)
async def analyze_reallocation(request: ReallocationRequest):
    """
    Reallocation Impact Analysis (#11):
    - Cascade impact analysis
    - Risk assessment
    - Rollback cost calculation
    """
    try:
        impact = analytics_service.analyze_reallocation_impact(
            request.employee_id, request.reallocation_reason, request.current_tasks, request.all_candidates
        )
        
        # Calculate ripple effects
        ripple_effects = []
        for affected_emp_id in impact.cascade_impact_employees:
            ripple_effects.append({
                "affected_employee_id": affected_emp_id,
                "impact_type": "related_task_dependency",
                "mitigation_required": True
            })
        
        # Rollback cost: time to undo + reassign
        rollback_cost = impact.recovery_time_hours * 1.5  # Add 50% overhead
        
        return {
            "impact_analysis": impact,
            "ripple_effects": ripple_effects,
            "rollback_cost_hours": round(rollback_cost, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MODULE #13: TEAM AGGREGATIONS
# ============================================================================

@router.post("/team-metrics", response_model=TeamAggregationResponse)
async def calculate_team_metrics(request: TeamAggregationRequest):
    """
    Team Aggregations (#13):
    - Department/team rollups
    - Total productive hours
    - Utilization metrics
    - Critical skill gaps
    - Team health scoring
    """
    try:
        metrics = analytics_service.calculate_team_metrics(
            request.department_id or "general", request.candidates
        )
        
        # Performance trends (simulated)
        performance_trends = {
            "utilization_trend": "stable" if 0.4 < metrics.average_utilization < 0.9 else "concerning",
            "health_trajectory": "improving" if metrics.team_health_score > 70 else "needs_attention",
            "skill_coverage": f"{len(request.candidates)} employees, identified gaps in {len(metrics.critical_skill_gaps)} skills"
        }
        
        # Recommendations
        recs = []
        if metrics.overloaded_count >= len(request.candidates) * 0.3:
            recs.append("Redistribute workload or hire support")
        if len(metrics.critical_skill_gaps) > 2:
            recs.append("Implement cross-training program")
        if metrics.underutilized_count > 3:
            recs.append("Assign new projects to underutilized members")
        if not recs:
            recs.append("Team is performing well - maintain current trajectory")
        
        return {
            "team_metrics": metrics,
            "performance_trends": performance_trends,
            "recommendations": recs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MODULE #14: HISTORICAL TREND CALCULATIONS
# ============================================================================

@router.post("/historical-trends", response_model=HistoricalTrendResponse)
async def calculate_trends(request: HistoricalTrendRequest):
    """
    Historical Trend Calculations (#14):
    - 12-week utilization trends
    - Project velocity trends
    - Trend direction and velocity confidence
    """
    try:
        trends = analytics_service.calculate_historical_trends(request.candidates, request.weeks_back)
        
        if not trends:
            raise HTTPException(status_code=400, detail="No candidates provided")
        
        # Calculate team velocity average
        team_velocity_avg = sum(t.average_velocity for t in trends) / max(1, len(trends))
        
        # Overall team trend direction
        up_count = sum(1 for t in trends if t.trend_direction == "up")
        down_count = sum(1 for t in trends if t.trend_direction == "down")
        
        if up_count > len(trends) * 0.5:
            velocity_trend_direction = "increasing"
        elif down_count > len(trends) * 0.5:
            velocity_trend_direction = "decreasing"
        else:
            velocity_trend_direction = "stable"
        
        return {
            "trend_analysis": trends,
            "team_velocity_avg": round(team_velocity_avg, 2),
            "velocity_trend_direction": velocity_trend_direction
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))