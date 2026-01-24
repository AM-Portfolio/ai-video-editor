import json
import os
import time

STATE_FILE = "pipeline_state.json"

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
