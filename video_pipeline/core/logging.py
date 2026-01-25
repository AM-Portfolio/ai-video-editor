import json
import os
import fcntl
from datetime import datetime

from core import path_utils

class DecisionLog:
    def __init__(self, log_file=None):
        if log_file is None:
            proc_dir = path_utils.get_processing_dir()
            log_file = os.path.join(proc_dir, "decision_log.json")
        self.log_file = log_file
        # Ensure log file exists (create if not)
        if not os.path.exists(log_file):
            # Create directory if needed
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            # Initialize as empty list if using strict JSON, but JSONL is better for streams.
            # User output structure implies standard JSON object. 
            # If we want a valid JSON file at all times, we'd need to read/modify/write 
            # which is slow and race-condition prone.
            # I will use JSON Lines (one object per line) which is standard for logs.
            pass

    def log(self, module, decision, confidence, reason, metrics=None):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "module": module,
            "decision": decision,
            "confidence": float(confidence),
            "reason": reason,
            "metrics": metrics or {}
        }
        
        # Use file locking to ensure safe concurrent writes from multiple processes
        try:
            with open(self.log_file, "a") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    f.write(json.dumps(entry) + "\n")
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception as e:
            print(f"⚠️ Failed to write to decision log: {e}")
