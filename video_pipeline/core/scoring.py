import json
import os
import fcntl

from core import path_utils

class ScoreKeeper:
    def __init__(self, scores_file=None):
        if scores_file is None:
            proc_dir = path_utils.get_processing_dir()
            scores_file = os.path.join(proc_dir, "scores.json")
        self.scores_file = scores_file
        if not os.path.exists(os.path.dirname(scores_file)):
            os.makedirs(os.path.dirname(scores_file), exist_ok=True)
            
    def update_score(self, chunk_name, metric, score):
        """
        Updates the score for a specific metric (e.g., 'motion_score') for a chunk.
        """
        # Read-Modify-Write with lock
        # Note: Ideally we'd use a database, but JSON is fine for small batch.
        # We need to lock the file to prevent race conditions from parallel processes.
        
        lock_file = self.scores_file + ".lock"
        with open(lock_file, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                data = {}
                if os.path.exists(self.scores_file):
                    try:
                        with open(self.scores_file, "r") as f:
                            data = json.load(f)
                    except json.JSONDecodeError:
                        pass
                
                if chunk_name not in data:
                    data[chunk_name] = {}
                
                data[chunk_name][metric] = max(0.0, min(1.0, float(score))) # Clamp 0-1
                
                with open(self.scores_file, "w") as f:
                    json.dump(data, f, indent=2)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def get_score(self, chunk_name):
        if os.path.exists(self.scores_file):
            with open(self.scores_file, "r") as f:
                data = json.load(f)
                return data.get(chunk_name, {})
        return {}
