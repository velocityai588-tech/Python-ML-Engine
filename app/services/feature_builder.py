import numpy as np
from typing import List, Dict
from app.models.schemas import TaskFeatures, EmployeeCandidate

class FeatureBuilder:
    """
    Converts Task and Employee objects into a concatenated Context Vector.
    Vector Size = Task_Features + Employee_Features
    """
    
    def __init__(self):
        # Define vocabulary mappings (In production, load these from DB or config)
        self.priority_map = {"Low": 0.2, "Medium": 0.5, "High": 0.8, "Critical": 1.0}
        self.role_map = {"Intern": 0.2, "Junior": 0.4, "Mid": 0.6, "Senior": 0.8, "Lead": 1.0}
        self.known_skills = ["React", "Python", "Node", "Java", "SQL", "Design"]

    def _encode_skills(self, task_skills: List[str], emp_skills: List[str]) -> float:
        """Calculates a skill match overlap score (0.0 to 1.0)"""
        if not task_skills: return 1.0 # No skills needed
        match_count = sum(1 for s in task_skills if s in emp_skills)
        return match_count / len(task_skills)

    def build_context_vector(self, task: TaskFeatures, employee: EmployeeCandidate) -> np.ndarray:
        """
        Creates a numerical vector representing the State (Context) + Action (Employee).
        Format: [Priority, Complexity, Deadline_Inv, Load_Inv, Role, Skill_Match]
        """
        
        # 1. Task Features
        f_priority = self.priority_map.get(task.priority, 0.5)
        f_complexity = task.complexity / 10.0 # Normalize 0-1
        f_deadline = 1.0 / (task.deadline_hours + 1) # Higher = More urgent

        # 2. Employee Features
        f_load = 1.0 / (employee.current_load + 1) # Higher = Less busy (Good)
        f_role = self.role_map.get(employee.role_level, 0.5)
        f_match = self._encode_skills(task.skills_required, employee.skills)

        # 3. Combine into Vector (Dimension = 6)
        return np.array([
            f_priority, 
            f_complexity, 
            f_deadline, 
            f_load, 
            f_role, 
            f_match
        ])