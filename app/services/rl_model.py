import numpy as np
import pickle
import os

class LinUCBModel:
    """
    LinUCB Disjoint implementation.
    Each arm (decision) is treated as having its own relationship with the context.
    """
    def __init__(self, alpha=0.5, n_features=6):
        self.alpha = alpha # Exploration parameter (Higher = More exploration)
        self.n_features = n_features
        
        # In a real persistence layer, these would be loaded from Supabase/Disk
        # A: Covariance matrix (d x d) -> Inverse approximates uncertainty
        # b: Reward vector (d x 1) -> Captures learnt weights
        # We use a Dictionary because "Arms" (Employees) are dynamic.
        self.A = {} 
        self.b = {}

    def _get_or_init_arm(self, arm_id: str):
        if arm_id not in self.A:
            self.A[arm_id] = np.identity(self.n_features)
            self.b[arm_id] = np.zeros(self.n_features)

    def predict(self, arm_ids: list, context_vectors: np.ndarray) -> list:
        """
        Returns scores for all candidate arms.
        Score = Mean_Estimate + (Alpha * Uncertainty)
        """
        scores = []
        
        for i, arm_id in enumerate(arm_ids):
            self._get_or_init_arm(arm_id)
            x = context_vectors[i] # Feature vector for this candidate
            
            A_inv = np.linalg.inv(self.A[arm_id])
            theta = A_inv.dot(self.b[arm_id]) # The weights
            
            # 1. Mean Expected Reward (Exploitation)
            mean = theta.dot(x)
            
            # 2. Standard Deviation/Uncertainty (Exploration)
            uncertainty = self.alpha * np.sqrt(x.dot(A_inv).dot(x))
            
            # Upper Confidence Bound
            ucb_score = mean + uncertainty
            scores.append({
                "id": arm_id,
                "score": float(ucb_score),
                "confidence": float(1.0 / (uncertainty + 1e-5)) # Inverse of uncertainty
            })
            
        # Sort descending
        return sorted(scores, key=lambda k: k['score'], reverse=True)

    def update(self, arm_id: str, context_vector: np.ndarray, reward: float):
        """
        Online Learning: Update the weights based on feedback.
        """
        self._get_or_init_arm(arm_id)
        
        # LinUCB Update Rule
        # A = A + x * x^T
        self.A[arm_id] += np.outer(context_vector, context_vector)
        # b = b + reward * x
        self.b[arm_id] += reward * context_vector

# Singleton Instance
model_instance = LinUCBModel()