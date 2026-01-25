import json
import os
import time
from pymongo import MongoClient

# Environment
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = "ai_video_pipeline"
COLLECTION_NAME = "pipeline_state"

class StateManager:
    def __init__(self, user_id=None):
        # Auto-detect user from environment if not provided
        self.user_id = user_id or os.getenv("PIPELINE_USER_ID", "default_user")
        self.is_mongo = bool(MONGO_URI)
        
        if self.is_mongo:
            try:
                self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
                self.db = self.client[DB_NAME]
                self.collection = self.db[COLLECTION_NAME]
                # Test connection
                self.client.server_info()
            except Exception as e:
                print(f"⚠️ MongoDB connection failed: {e}. Falling back to file mode.")
                self.is_mongo = False

        if not self.is_mongo:
             # Ensure user directory exists for file mode
             self.state_file = f"data/state_{self.user_id}.json"
             os.makedirs("data", exist_ok=True)

    def _load(self):
        if self.is_mongo:
            doc = self.collection.find_one({"_id": self.user_id})
            return doc if doc else {"_id": self.user_id, "chunks": {}, "last_updated": time.time()}
        else:
            if not os.path.exists(self.state_file):
                return {"chunks": {}, "last_updated": time.time()}
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except:
                return {"chunks": {}, "last_updated": time.time()}

    def _save(self, state):
        state["last_updated"] = time.time()
        if self.is_mongo:
            self.collection.replace_one({"_id": self.user_id}, state, upsert=True)
        else:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=4)

    def init_state(self, chunks):
        """Initialize state if not exists."""
        state = self._load()
        # If chunks are empty in state or we want to merge? 
        # Typically we just load existing. If new chunks come in, we add them?
        # For simplicity, if state exists, return it. Users clear state via UI to reset.
        if state.get("chunks"):
            return state

        state["chunks"] = {}
        for chunk_name in chunks:
            state["chunks"][chunk_name] = {
                "status": "PENDING",
                "step": "Init",
                "message": "Waiting to start..."
            }
        self._save(state)
        return state

    def update_chunk_status(self, chunk_name, status, step=None, message=None):
        state = self._load()
        if chunk_name not in state.get("chunks", {}):
            return # Should not happen

        state["chunks"][chunk_name]["status"] = status
        if step:
            state["chunks"][chunk_name]["step"] = step
        if message:
            state["chunks"][chunk_name]["message"] = message
        self._save(state)

    def get_chunk_status(self, chunk_name):
        state = self._load()
        return state.get("chunks", {}).get(chunk_name, {})

    def is_step_done(self, chunk_name, step_name):
        state = self._load()
        chunk = state.get("chunks", {}).get(chunk_name)
        if not chunk:
            return False
            
        if chunk["status"] == "COMPLETED":
            return True
            
        completed_steps = chunk.get("completed_steps", [])
        return step_name in completed_steps

    def mark_step_done(self, chunk_name, step_name):
        state = self._load()
        if chunk_name not in state.get("chunks", {}):
            return
        
        if "completed_steps" not in state["chunks"][chunk_name]:
            state["chunks"][chunk_name]["completed_steps"] = []
            
        if step_name not in state["chunks"][chunk_name]["completed_steps"]:
            state["chunks"][chunk_name]["completed_steps"].append(step_name)
            
        self._save(state)

# Helper wrapper for backward compatibility (lazy load default user)
# Usage: from core import state; state.get_manager(user_id).update_chunk_status(...)
def get_manager(user_id="default_user"):
    return StateManager(user_id)

# Legacy global functions for existing scripts (mapped to default_user)
# Warning: These are DEPRECATED for multi-user. Scripts should migrate.
_global_manager = StateManager("default_user")
def init_state(chunks): return _global_manager.init_state(chunks)
def load_state(): return _global_manager._load()
def save_state(state): return _global_manager._save(state)
def update_chunk_status(c, s, step=None, message=None): return _global_manager.update_chunk_status(c, s, step, message)
def get_chunk_status(c): return _global_manager.get_chunk_status(c)
def is_step_done(c, s): return _global_manager.is_step_done(c, s)
def mark_step_done(c, s): return _global_manager.mark_step_done(c, s)
