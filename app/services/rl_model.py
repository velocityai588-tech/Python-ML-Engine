import numpy as np
import pickle
import os
import json

class LinUCBModel:
    """
    LinUCB Disjoint implementation with Persistence.
    A: Covariance matrix (Inverse represents uncertainty).
    b: Reward vector (Learned weights).
    """
    def __init__(self, alpha=1.5, n_features=6, model_path="model_checkpoint.pkl"):
        self.alpha = alpha 
        self.n_features = n_features
        self.model_path = model_path
        
        # Initialize Memory
        self.A = {} 
        self.b = {}
        
        # Load existing brain if available
        self.load_model()

    def _get_or_init_arm(self, arm_id: str):
        if arm_id not in self.A:
            # Identity matrix (I) implies initial uncertainty
            self.A[arm_id] = np.identity(self.n_features)
            # Zero vector implies no initial knowledge of reward
            self.b[arm_id] = np.zeros(self.n_features)

    def predict(self, arm_ids: list, context_vectors: np.ndarray) -> list:
        scores = []
        
        for i, arm_id in enumerate(arm_ids):
            self._get_or_init_arm(arm_id)
            x = context_vectors[i]
            
            # LinUCB Math
            try:
                A_inv = np.linalg.inv(self.A[arm_id])
            except np.linalg.LinAlgError:
                # Fallback for singular matrix (rare edge case)
                A_inv = np.linalg.pinv(self.A[arm_id])
                
            theta = A_inv.dot(self.b[arm_id]) # The weights
            
            # Exploitation (Mean estimate)
            mean = theta.dot(x)
            
            # Exploration (Uncertainty)
            # Variance = x^T * A^-1 * x
            uncertainty = self.alpha * np.sqrt(x.dot(A_inv).dot(x))
            
            score = mean + uncertainty
            
            scores.append({
                "id": arm_id,
                "score": float(score),
                "confidence": float(1.0 / (uncertainty + 1e-5))
            })
            
        return sorted(scores, key=lambda k: k['score'], reverse=True)

    def update(self, arm_id: str, context_vector: np.ndarray, reward: float):
        """Train the model on a single event."""
        self._get_or_init_arm(arm_id)
        
        # Update Matrix A: A_new = A_old + x * x^T
        self.A[arm_id] += np.outer(context_vector, context_vector)
        
        # Update Vector b: b_new = b_old + r * x
        self.b[arm_id] += reward * context_vector
        
        # Auto-save after training
        self.save_model()

    def save_model(self):
        """Persist weights to disk (In prod, push to Supabase Storage)"""
        with open(self.model_path, 'wb') as f:
            pickle.dump({'A': self.A, 'b': self.b}, f)
        # print("Brain saved.")

    def load_model(self):
        if os.path.exists(self.model_path):
            try:
                with open(self.model_path, 'rb') as f:
                    data = pickle.load(f)
                    self.A = data['A']
                    self.b = data['b']
                print(f"Brain loaded from {self.model_path}")
            except Exception as e:
                print(f"Failed to load model: {e}. Starting fresh.")

# Singleton
model_instance = LinUCBModel()