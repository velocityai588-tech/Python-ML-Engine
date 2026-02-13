from typing import List
from app.models.schemas import EmployeeCandidate, TaskFeatures, BottleneckReport, AvailabilityReport

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

analytics_service = AnalyticsService()