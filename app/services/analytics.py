from typing import List, Dict, Tuple
from app.models.schemas import (
    EmployeeCandidate, TaskFeatures, BottleneckReport, AvailabilityReport,
    SkillMatchScore, TimelineProjection, FeasibilityScore, InsightTrigger,
    PTOImpactAnalysis, TimesheetLearningMetric, Recommendation, ReallocationImpact,
    TeamMetrics, UtilizationTrend, TrendAnalysis
)
import math
from datetime import datetime, timedelta

def calculate_available_hours(employee: EmployeeCandidate) -> float:
    """
    Calculates true available hours for the week based on base capacity, PTO, and holidays.
    Formula: Productive Hours - PTO - Holidays
    """
    available_hours = (
        employee.base_productive_hours 
        - employee.pto_hours_this_week 
        - employee.holiday_hours_this_week
    )
    
    return max(0.0, available_hours)
class AnalyticsService:
    def analyze_bottlenecks(self, employees: List[EmployeeCandidate], active_tasks_count: int) -> BottleneckReport:
        """
        Identifies system constraints and overloaded resources.
        """
        # 1. Identify At-Risk Employees (Load > 5 is arbitrary threshold for 'High')
        overloaded = [e.name for e in employees if e.current_load >= 5]
        
        # 2. Skill Supply vs Demand (Simple Heuristic)
        # In a real system, you'd pass all active tasks to calculate exact demand.
        # Here we approximate based on who is overloaded.
        skill_pressure = {}
        for emp in employees:
            if emp.current_load >= 5:
                for skill in emp.skills:
                    skill_pressure[skill] = skill_pressure.get(skill, 0) + 1
        
        # If more than 2 employees with the same skill are overloaded, it's a bottleneck.
        critical_skills = [skill for skill, count in skill_pressure.items() if count >= 2]
        
        # 3. System Strain
        total_capacity = len(employees) * 5 # Assume max 5 tasks per person
        total_load = sum(e.current_load for e in employees)
        strain = (total_load / total_capacity) * 100 if total_capacity > 0 else 100

        rec = "Workload Balanced"
        if strain > 80: rec = "CRITICAL: Hiring or Outsourcing needed immediately."
        elif len(critical_skills) > 0: rec = f"Bottleneck in {', '.join(critical_skills)}. Cross-train staff."

        return BottleneckReport(
            overloaded_skills=critical_skills,
            at_risk_employees=overloaded,
            system_strain_score=round(strain, 1),
            recommendation=rec
        )

    def check_eligibility(self, task: TaskFeatures, employees: List[EmployeeCandidate]) -> List[AvailabilityReport]:
        """
        Filters employees based on Project SRS (Hard Constraints) & Availability.
        """
        reports = []
        for emp in employees:
            # 1. Hard Constraint: Skills
            # Logic: Employee must have at least 1 of the required skills (or ALL, depending on policy)
            # Here: We require at least 50% skill overlap
            required_set = set(task.skills_required)
            emp_set = set(emp.skills)
            overlap = len(required_set.intersection(emp_set))
            
            is_eligible = overlap > 0 # Loose constraint for now
            
            # 2. Availability Score (Inverse of Load)
            # Load 0 -> 1.0 (Free)
            # Load 5 -> 0.0 (Busy)
            availability = max(0.0, 1.0 - (emp.current_load / 5.0))
            
            reason = "Skill Mismatch"
            if is_eligible:
                if availability < 0.2: reason = "Eligible but Overloaded"
                else: reason = f"Eligible ({overlap} skills matched)"

            reports.append(AvailabilityReport(
                employee_id=emp.id,
                name=emp.name,
                is_eligible=is_eligible,
                availability_score=round(availability, 2),
                match_reason=reason if not is_eligible else reason
            ))
            
        return sorted(reports, key=lambda x: x.availability_score, reverse=True)

    # --- SKILL MATCHING MODULE (#2) ---
    def calculate_skill_match(self, task: TaskFeatures, employees: List[EmployeeCandidate]) -> List[SkillMatchScore]:
        """
        Calculates Skill Match Score, Assignment Score, and Reallocation Success Probability.
        """
        matches = []
        task_skills_set = set(task.skills_required)
        
        for emp in employees:
            emp_skills_set = set(emp.skills)
            
            # 1. Skill Match Percent (0-100%)
            if len(task_skills_set) == 0:
                skill_match_percent = 100.0
            else:
                overlap = len(task_skills_set.intersection(emp_skills_set))
                skill_match_percent = (overlap / len(task_skills_set)) * 100
            
            # 2. Missing and Excess Skills
            missing_skills = list(task_skills_set - emp_skills_set)
            excess_skills = list(emp_skills_set - task_skills_set)
            
            # 3. Assignment Score (combination of skill match, availability, and efficiency)
            availability = max(0.0, 1.0 - (emp.current_load / 5.0))
            efficiency_factor = emp.efficiency_score  # 0.0-2.0
            skill_factor = skill_match_percent / 100.0
            assignment_score = (skill_factor * 0.4 + availability * 0.4 + (efficiency_factor / 2.0) * 0.2)
            
            # 4. Reallocation Success Probability (0-1.0)
            # Lower load and fewer missing skills = higher probability
            load_factor = 1.0 - (emp.current_load / 10.0)  # Normalize to 0-1
            missing_skill_count = len(missing_skills)
            learning_factor = 1.0 / (1.0 + missing_skill_count)  # Fewer missing = higher
            real_success_prob = (load_factor * 0.5 + learning_factor * 0.5)
            
            matches.append(SkillMatchScore(
                employee_id=emp.id,
                name=emp.name,
                skill_match_percent=round(skill_match_percent, 2),
                missing_skills=missing_skills,
                excess_skills=excess_skills,
                assignment_score=round(assignment_score, 2),
                reallocation_success_probability=round(max(0.0, min(1.0, real_success_prob)), 2)
            ))
        
        return sorted(matches, key=lambda x: x.assignment_score, reverse=True)

    # --- TIMELINE CALCULATIONS (#4) ---
    def calculate_timeline_projections(self, task: TaskFeatures, employees: List[EmployeeCandidate]) -> List[TimelineProjection]:
        """
        Calculates Learning Curve Factors, Critical Path Method, and risk of delay.
        """
        projections = []
        task_skills_set = set(task.skills_required)
        
        for emp in employees:
            emp_skills_set = set(emp.skills)
            
            # 1. Learning Curve Factor (0.8-1.5)
            missing_skills = task_skills_set - emp_skills_set
            learning_penalty = 1.0 + (len(missing_skills) * 0.15)  # +15% per missing skill
            learning_curve_factor = min(1.5, max(0.8, learning_penalty / emp.efficiency_score))
            
            # 2. Estimated Completion Hours
            base_hours = task.complexity * 8  # Rough: complexity * 8 hours
            adjusted_hours = base_hours * learning_curve_factor / emp.efficiency_score
            estimated_completion_hours = max(1.0, adjusted_hours)
            
            # 3. Critical Path Method (CPM) - Days until completion
            available_hours_per_day = calculate_available_hours(emp) / 5.0  # Assume 5-day week
            if available_hours_per_day > 0:
                cpm_days = estimated_completion_hours / available_hours_per_day
            else:
                cpm_days = estimated_completion_hours / 8.0  # Fallback to standard 8-hour day
            
            # 4. Risk of Delay Percent (0-100%)
            # Risk increases with: task complexity, missing skills, employee load
            load_risk = (emp.current_load / 5.0) * 30  # Max 30% from load
            complexity_risk = (task.complexity / 10.0) * 25  # Max 25% from complexity
            skill_risk = (len(missing_skills) / max(1, len(task_skills_set))) * 30  # Max 30% from skills
            deadline_risk = (task.deadline_hours / (cpm_days * 8)) * 15  # Max 15% from tight deadline
            risk_of_delay = min(100.0, load_risk + complexity_risk + skill_risk + deadline_risk)
            
            projections.append(TimelineProjection(
                employee_id=emp.id,
                name=emp.name,
                estimated_completion_hours=round(estimated_completion_hours, 2),
                learning_curve_factor=round(learning_curve_factor, 2),
                cpm_critical_path_days=round(cpm_days, 2),
                risk_of_delay_percent=round(risk_of_delay, 1)
            ))
        
        return sorted(projections, key=lambda x: x.cpm_critical_path_days)

    # --- FEASIBILITY CALCULATIONS (#5) ---
    def calculate_feasibility(self, task: TaskFeatures, employees: List[EmployeeCandidate], deadline_days: int = 5) -> List[FeasibilityScore]:
        """
        Complete feasibility scoring across multiple dimensions.
        """
        feasibility_scores = []
        task_skills_set = set(task.skills_required)
        deadline_hours = deadline_days * 8  # Convert to hours
        
        for emp in employees:
            emp_skills_set = set(emp.skills)
            
            # 1. Skill Feasibility (0-1.0)
            if len(task_skills_set) == 0:
                skill_feasibility = 1.0
            else:
                overlap = len(task_skills_set.intersection(emp_skills_set))
                skill_feasibility = overlap / len(task_skills_set)
            
            # 2. Timeline Feasibility (0-1.0)
            base_hours = task.complexity * 8
            learning_factor = 1.0 + (len(task_skills_set - emp_skills_set) * 0.15)
            needed_hours = (base_hours * learning_factor) / emp.efficiency_score
            available_hours = calculate_available_hours(emp)
            timeline_feasibility = min(1.0, available_hours / max(1, needed_hours))
            
            # 3. Capacity Feasibility (0-1.0)
            # Can they fit this in without overload?
            current_load_percent = (emp.current_load / 5.0)  # Max 5 tasks per person
            capacity_feasibility = max(0.0, 1.0 - current_load_percent)
            
            # 4. Learning Feasibility (0-1.0)
            # How quickly can they learn missing skills?
            missing_count = len(task_skills_set - emp_skills_set)
            learning_feasibility = 1.0 / (1.0 + (missing_count * 0.25))
            
            # 5. Overall Feasibility (weighted average)
            overall = (skill_feasibility * 0.25 + timeline_feasibility * 0.35 
                      + capacity_feasibility * 0.25 + learning_feasibility * 0.15)
            
            # 6. Blocker Flags
            blockers = []
            if skill_feasibility < 0.3:
                blockers.append("Critical skill missing")
            if timeline_feasibility < 0.2:
                blockers.append("Insufficient time to complete")
            if capacity_feasibility < 0.1:
                blockers.append("Employee at maximum capacity")
            if task.deadline_hours < needed_hours:
                blockers.append("Deadline impossible to meet")
            
            feasibility_scores.append(FeasibilityScore(
                employee_id=emp.id,
                name=emp.name,
                skill_feasibility=round(skill_feasibility, 2),
                timeline_feasibility=round(timeline_feasibility, 2),
                capacity_feasibility=round(capacity_feasibility, 2),
                learning_feasibility=round(learning_feasibility, 2),
                overall_feasibility=round(overall, 2),
                blocker_flags=blockers
            ))
        
        return sorted(feasibility_scores, key=lambda x: x.overall_feasibility, reverse=True)

    # --- AI INSIGHT GENERATION (#6) ---
    def generate_ai_insights(self, employees: List[EmployeeCandidate], tasks_in_progress: int = 0, overdue_tasks: int = 0) -> List[InsightTrigger]:
        """
        Rule-based insight triggers for Overload, Timeline Risk, Underutilization, Skill Gap.
        """
        insights = []
        
        # 1. OVERLOAD Detection
        overloaded_emps = [e for e in employees if e.current_load >= 5]
        if len(overloaded_emps) > 0:
            severity = "Critical" if len(overloaded_emps) >= len(employees) * 0.5 else "High"
            insights.append(InsightTrigger(
                trigger_type="Overload",
                severity=severity,
                affected_employee_ids=[e.id for e in overloaded_emps],
                description=f"{len(overloaded_emps)} employees have 5+ active tasks",
                recommended_action="Redistribute tasks or hire temporary support"
            ))
        
        # 2. UNDERUTILIZATION Detection
        underutilized = [e for e in employees if e.current_load <= 1]
        if len(underutilized) > 0:
            insights.append(InsightTrigger(
                trigger_type="Underutilization",
                severity="Low",
                affected_employee_ids=[e.id for e in underutilized],
                description=f"{len(underutilized)} employees are underutilized",
                recommended_action="Assign new tasks to improve productivity"
            ))
        
        # 3. SKILL GAP Detection
        all_skills = set()
        skill_coverage = {}
        for emp in employees:
            for skill in emp.skills:
                all_skills.add(skill)
                skill_coverage[skill] = skill_coverage.get(skill, 0) + 1
        
        rare_skills = [s for s, count in skill_coverage.items() if count <= 1]
        if len(rare_skills) > 0:
            insights.append(InsightTrigger(
                trigger_type="Skill Gap",
                severity="Medium",
                affected_employee_ids=[],
                description=f"Single-person dependency: {len(rare_skills)} skills ({', '.join(rare_skills[:3])}...)",
                recommended_action="Cross-train team members on critical skills"
            ))
        
        # 4. TIMELINE RISK Detection
        if overdue_tasks > 0:
            insights.append(InsightTrigger(
                trigger_type="Timeline Risk",
                severity="High",
                affected_employee_ids=[],
                description=f"{overdue_tasks} tasks are overdue",
                recommended_action="Prioritize overdue tasks and reallocate resources"
            ))
        
        return insights

    # --- PTO IMPACT CALCULATIONS (#8) ---
    def calculate_pto_impact(self, task: TaskFeatures, employees: List[EmployeeCandidate]) -> List[PTOImpactAnalysis]:
        """
        Timeline impact from leave (PTO/Holidays).
        """
        analyses = []
        base_hours = task.complexity * 8
        
        for emp in employees:
            # Initial Available Hours (before PTO)
            initial_available = emp.base_productive_hours
            
            # PTO deduction
            pto_deduction = emp.pto_hours_this_week + emp.holiday_hours_this_week
            
            # Net Available After PTO
            net_available = max(0.0, initial_available - pto_deduction)
            
            # Learning factor from missing skills
            missing_skills = len(set(task.skills_required) - set(emp.skills))
            learning_factor = 1.0 + (missing_skills * 0.15)
            needed_hours = (base_hours * learning_factor) / emp.efficiency_score
            
            # Timeline Impact Days
            if net_available > 0:
                completion_days = (needed_hours / net_available) * 5  # Assume 5-day week
            else:
                completion_days = (needed_hours / 8.0) * 5  # Fallback
            
            # If no PTO, how many days?
            if initial_available > 0:
                completion_without_pto = (needed_hours / initial_available) * 5
            else:
                completion_without_pto = completion_days
            
            timeline_impact = completion_days - completion_without_pto
            
            # Task Completion Probability (0-1.0)
            if net_available >= needed_hours:
                completion_prob = 0.95
            elif net_available >= needed_hours * 0.7:
                completion_prob = 0.75
            elif net_available > 0:
                completion_prob = 0.5
            else:
                completion_prob = 0.1
            
            analyses.append(PTOImpactAnalysis(
                employee_id=emp.id,
                name=emp.name,
                initial_available_hours=initial_available,
                pto_deduction_hours=round(pto_deduction, 2),
                net_available_after_pto=round(net_available, 2),
                timeline_impact_days=round(timeline_impact, 2),
                task_completion_probability=round(completion_prob, 2)
            ))
        
        return sorted(analyses, key=lambda x: x.task_completion_probability, reverse=True)

    # --- TIMESHEET-BASED LEARNING (#9) ---
    def calculate_timesheet_learning(self, employees: List[EmployeeCandidate], days_historical: int = 84) -> List[TimesheetLearningMetric]:
        """
        Learning productive hours, capacity prediction accuracy.
        """
        metrics = []
        weeks_back = days_historical / 7
        
        for emp in employees:
            # Productive hours tracked (simulated from available data)
            productive_hours = emp.base_productive_hours * weeks_back
            
            # Learning hours invested (estimated: 10% of productive time for learning)
            learning_hours = productive_hours * 0.1
            
            # Capacity Prediction Accuracy (0-1.0)
            # Based on consistency of efficiency_score (1.0 = perfect predictor)
            capacity_accuracy = min(1.0, emp.efficiency_score / 1.5)
            
            # Skill Improvement Rate (Skills per week)
            # Rough estimate: 0.2 skills per week if learning consistently
            skill_improvement = (learning_hours / 40) * 0.2  # 40 hours per week baseline
            
            # Recommended Training Hours
            # If underperforming (efficiency < 1.0): recommend more training
            training_gap = max(0, (1.0 - emp.efficiency_score) * 10)
            recommended_training = training_gap + 2  # Base 2 hours + gap hours
            
            metrics.append(TimesheetLearningMetric(
                employee_id=emp.id,
                name=emp.name,
                productive_hours_tracked=round(productive_hours, 2),
                learning_hours_invested=round(learning_hours, 2),
                capacity_prediction_accuracy=round(capacity_accuracy, 2),
                skill_improvement_rate=round(skill_improvement, 3),
                recommended_training_hours=round(recommended_training, 2)
            ))
        
        return sorted(metrics, key=lambda x: x.capacity_prediction_accuracy, reverse=True)

    # --- RECOMMENDATION ENGINE (#10) ---
    def generate_recommendations(self, task: TaskFeatures, employees: List[EmployeeCandidate], 
                                current_blockers: List[str] = None, budget_hours: float = None) -> List[Recommendation]:
        """
        Timeline extension, hiring, scope reduction recommendations.
        """
        if current_blockers is None:
            current_blockers = []
        
        recommendations = []
        task_skills_set = set(task.skills_required)
        
        # Get feasibility scores
        feasibility = self.calculate_feasibility(task, employees)
        viable_count = sum(1 for f in feasibility if f.overall_feasibility > 0.5)
        
        # 1. Scope Reduction Recommendation
        if viable_count < 1:
            recommendations.append(Recommendation(
                recommendation_type="scope_reduction",
                description="Reduce task complexity or split into subtasks",
                estimated_cost=task.complexity * 4,  # Estimated reduction in hours
                timeline_impact_days=-2.0,
                risk_mitigation_level="High"
            ))
        
        # 2. Timeline Extension Recommendation
        avg_timeline = sum(f.timeline_feasibility for f in feasibility) / max(1, len(feasibility))
        if avg_timeline < 0.6:
            days_needed = task.complexity * 2  # Rough estimate
            recommendations.append(Recommendation(
                recommendation_type="timeline_extension",
                description=f"Extend deadline by {days_needed} days",
                estimated_cost=0,  # No direct cost
                timeline_impact_days=days_needed,
                risk_mitigation_level="Medium"
            ))
        
        # 3. Skill Training Recommendation
        if len(current_blockers) > 0 and "skill gap" in str(current_blockers).lower():
            recommendations.append(Recommendation(
                recommendation_type="skill_training",
                description="Invest in training for missing critical skills",
                estimated_cost=40,  # 40 training hours
                timeline_impact_days=0,
                risk_mitigation_level="Medium"
            ))
        
        # 4. Hiring Recommendation
        overloaded = sum(1 for e in employees if e.current_load >= 5)
        if overloaded >= len(employees) * 0.4:
            recommendations.append(Recommendation(
                recommendation_type="hiring",
                description=f"Hire 1-2 contractors or FTE to handle current load",
                estimated_cost=None,
                timeline_impact_days=-1.0,
                risk_mitigation_level="High"
            ))
        
        return recommendations

    # --- REALLOCATION IMPACT ANALYSIS (#11) ---
    def analyze_reallocation_impact(self, employee_id: str, reallocation_reason: str, 
                                   current_tasks: List[str], all_employees: List[EmployeeCandidate]) -> ReallocationImpact:
        """
        Cascade impact and risk assessment.
        """
        emp = next((e for e in all_employees if e.id == employee_id), None)
        if not emp:
            emp = EmployeeCandidate(id=employee_id, name="Unknown", current_load=0, 
                                   skills=[], role_level="Unknown", avg_completion_time=0)
        
        # Estimate cascade: employees depending on this person's tasks
        cascade_employees = []
        for task_id in current_tasks:
            # Simulate: each task might be related to 1-2 other employees
            cascade_employees.extend([e.id for e in all_employees[:2] if e.id != employee_id])
        cascade_employees = list(set(cascade_employees))  # Remove duplicates
        
        # Risk Score (0-100)
        load_risk = (emp.current_load / 5.0) * 30
        skill_risk = (len(emp.skills) / 6.0) * 30  # Normalized to 6 known skills
        task_count_risk = (len(current_tasks) / 10.0) * 40
        risk_score = min(100.0, load_risk + skill_risk + task_count_risk)
        
        # Recovery Time Hours
        recovery_hours = len(current_tasks) * 4  # ~4 hours per task to reassign and document
        
        return ReallocationImpact(
            employee_id=employee_id,
            name=emp.name,
            current_tasks=current_tasks,
            cascade_impact_employees=cascade_employees,
            risk_score=round(risk_score, 1),
            recovery_time_hours=recovery_hours
        )

    # --- TEAM AGGREGATIONS (#13) ---
    def calculate_team_metrics(self, department_id: str, employees: List[EmployeeCandidate]) -> TeamMetrics:
        """
        Department/team rollups: total productive hours, utilization, gaps.
        """
        if len(employees) == 0:
            return TeamMetrics(
                department_id=department_id,
                department_name=department_id or "Unknown",
                total_employees=0,
                total_productive_hours=0,
                average_utilization=0,
                overloaded_count=0,
                underutilized_count=0,
                critical_skill_gaps=[],
                team_health_score=0
            )
        
        # Calculate metrics
        total_productive = sum(e.base_productive_hours for e in employees)
        total_load = sum(e.current_load for e in employees)
        overloaded = sum(1 for e in employees if e.current_load >= 5)
        underutilized = sum(1 for e in employees if e.current_load <= 1)
        
        # Average utilization (0-1.0)
        max_capacity = len(employees) * 5
        avg_utilization = (total_load / max_capacity) if max_capacity > 0 else 0
        
        # Critical skill gaps
        all_skills = {}
        for emp in employees:
            for skill in emp.skills:
                all_skills[skill] = all_skills.get(skill, 0) + 1
        critical_gaps = [s for s, count in all_skills.items() if count <= 1]
        
        # Team Health Score (0-100)
        utilization_health = 70 if 0.4 < avg_utilization < 0.9 else 40
        overload_health = 100 - (overloaded / len(employees) * 50)
        skill_health = 100 - (len(critical_gaps) * 5)
        team_health = (utilization_health + overload_health + skill_health) / 3
        
        return TeamMetrics(
            department_id=department_id,
            department_name=department_id or "General",
            total_employees=len(employees),
            total_productive_hours=round(total_productive, 2),
            average_utilization=round(avg_utilization, 2),
            overloaded_count=overloaded,
            underutilized_count=underutilized,
            critical_skill_gaps=critical_gaps,
            team_health_score=round(max(0, min(100, team_health)), 1)
        )

    # --- HISTORICAL TREND CALCULATIONS (#14) ---
    def calculate_historical_trends(self, employees: List[EmployeeCandidate], weeks_back: int = 12) -> List[TrendAnalysis]:
        """
        12-week utilization trends, project velocity trends.
        """
        trends = []
        
        for emp in employees:
            # Simulate 12-week trend (in real system, fetch from timesheet/project data)
            utilization_trend = []
            for week in range(1, weeks_back + 1):
                # Simulate: trending up or down
                base_util = (emp.current_load / 5.0) * 100
                # Add some variance
                variance = (week % 3) * 5 - 7  # -7 to 8 percent variance
                week_util = max(0, min(100, base_util + variance))
                
                tasks_completed = max(1, int(emp.current_load * 0.7 + (week % 3)))
                avg_completion = emp.avg_completion_time
                
                utilization_trend.append(UtilizationTrend(
                    week_number=week,
                    utilization_percent=round(week_util, 1),
                    tasks_completed=tasks_completed,
                    average_completion_time=round(avg_completion, 2)
                ))
            
            # Calculate trend direction and velocity
            first_half_avg = sum(u.utilization_percent for u in utilization_trend[:6]) / 6
            second_half_avg = sum(u.utilization_percent for u in utilization_trend[6:]) / 6
            
            if second_half_avg > first_half_avg + 5:
                trend_direction = "up"
            elif second_half_avg < first_half_avg - 5:
                trend_direction = "down"
            else:
                trend_direction = "stable"
            
            # Velocity: tasks per week average
            total_tasks = sum(u.tasks_completed for u in utilization_trend)
            average_velocity = total_tasks / weeks_back
            
            # Velocity confidence (0-1.0): higher if consistent
            velocity_values = [u.tasks_completed for u in utilization_trend]
            velocity_std = (max(velocity_values) - min(velocity_values)) / 2 if velocity_values else 0
            velocity_confidence = max(0.3, 1.0 - (velocity_std / 5.0))
            
            trends.append(TrendAnalysis(
                employee_id=emp.id,
                name=emp.name,
                utilization_trend_12week=utilization_trend,
                average_velocity=round(average_velocity, 2),
                trend_direction=trend_direction,
                velocity_confidence=round(velocity_confidence, 2)
            ))
        
        return trends