import os

# Project root (video_pipeline/)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_user_id():
    return os.getenv("PIPELINE_USER_ID", "default_user")

def get_processing_dir():
    user_id = get_user_id()
    path = os.path.join(ROOT_DIR, "processing", user_id)
    os.makedirs(path, exist_ok=True)
    return path

def get_output_clips_dir():
    user_id = get_user_id()
    path = os.path.join(ROOT_DIR, "output_clips", user_id)
    os.makedirs(path, exist_ok=True)
    return path

def get_output_videos_dir():
    user_id = get_user_id()
    path = os.path.join(ROOT_DIR, "output_videos", user_id)
    os.makedirs(path, exist_ok=True)
    return path

def get_input_clips_dir():
    user_id = get_user_id()
    path = os.path.join(ROOT_DIR, "input_clips", user_id)
    os.makedirs(path, exist_ok=True)
    return path

