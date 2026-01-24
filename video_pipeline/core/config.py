import json
import os

def load_config(path=None):
    if path is None:
        # Default to data/config.json relative to project root
        # Since we run from root, 'data/config.json' works.
        path = "data/config.json"
    
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(config, path="data/config.json"):
    with open(path, 'w') as f:
        json.dump(config, f, indent=4)
