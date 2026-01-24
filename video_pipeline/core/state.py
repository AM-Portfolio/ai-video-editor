import json
import os
import time

STATE_FILE = "data/pipeline_state.json"

def init_state(chunks):
    """
    Initialize the state file with a list of chunks.
    Only resets if the file doesn't exist or if forced (handled by UI clearing).
    """
    if os.path.exists(STATE_FILE):
        # We might want to load it to preserve 'COMPLETED' states but ensure all chunks are present?
        # For now, let's assume if it exists, we trust it for resume.
        # But if the user uploaded a NEW file, the orchestrator should have cleared it.
        return load_state()

    state = {
        "chunks": {},
        "last_updated": time.time()
    }
    
    for chunk_name in chunks:
        state["chunks"][chunk_name] = {
            "status": "PENDING", # PENDING, PROCESSING, COMPLETED, FAILED
            "step": "Init",
            "message": "Waiting to start..."
        }
        
    save_state(state)
    return state

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    state["last_updated"] = time.time()
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def update_chunk_status(chunk_name, status, step=None, message=None):
    state = load_state()
    if not state or chunk_name not in state.get("chunks", {}):
        # Should not happen if initialized correctly
        return
    
    state["chunks"][chunk_name]["status"] = status
    if step:
        state["chunks"][chunk_name]["step"] = step
    if message:
        state["chunks"][chunk_name]["message"] = message
        
    save_state(state)

def get_chunk_status(chunk_name):
    state = load_state()
    return state.get("chunks", {}).get(chunk_name, {})

def is_step_done(chunk_name, step_name):
    """
    Check if a specific step is already completed for a chunk.
    This enables 'Resume at every step' capability.
    """
    state = load_state()
    chunk = state.get("chunks", {}).get(chunk_name)
    if not chunk:
        return False
        
    # If the chunk is overall COMPLETED, all steps before are done.
    if chunk["status"] == "COMPLETED":
        return True
        
    # We can also check if the specific step was the last successful one.
    # However, for a more robust check, we'd need a history of steps.
    # Simplest: if status is PENDING/PROCESSING but the artifact exists on disk (checked in scripts).
    # Better: state_manager tracks successful steps.
    completed_steps = chunk.get("completed_steps", [])
    return step_name in completed_steps

def mark_step_done(chunk_name, step_name):
    state = load_state()
    if chunk_name not in state.get("chunks", {}):
        return
    
    if "completed_steps" not in state["chunks"][chunk_name]:
        state["chunks"][chunk_name]["completed_steps"] = []
    
    if step_name not in state["chunks"][chunk_name]["completed_steps"]:
        state["chunks"][chunk_name]["completed_steps"].append(step_name)
        
    save_state(state)
