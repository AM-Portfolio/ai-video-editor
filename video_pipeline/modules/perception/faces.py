import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import cv2
import os
import shutil
# Add project root to sys.path for modular imports
sys.path.append(os.getcwd())

from core import config as cfg_loader
config = cfg_loader.load_config()

BASE_DIR = "processing"
MODEL_PATH = "data/detector.tflite"

print("🧠 Loading Face Detection Model (Tasks API)...")

# Check if model exists
if not os.path.exists(MODEL_PATH):
    print(f"❌ Model not found at {MODEL_PATH}. Checking absolute path...")
    # fallback to absolute path if needed, assuming current working dir is project root
    abs_model_path = os.path.join(os.getcwd(), "video_pipeline", MODEL_PATH)
    if os.path.exists(abs_model_path):
        MODEL_PATH = abs_model_path
    else:
        # Try just local assuming run from video_pipeline
        if os.path.exists("detector.tflite"):
            MODEL_PATH = "detector.tflite"
        else:
            raise FileNotFoundError("Could not find detector.tflite model.")

base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
FACE_CONFIDENCE = config.get("face_confidence", 0.5)
options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=FACE_CONFIDENCE)
detector = vision.FaceDetector.create_from_options(options)

from core.logging import DecisionLog
from core.scoring import ScoreKeeper
from core import state as state_manager

logger = DecisionLog()
scorer = ScoreKeeper()

def has_face(video_path, num_samples=10):
    """Check if face is present and return visibility ratio (0.0 - 1.0)"""
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if total_frames == 0:
        cap.release()
        return 0.0
    
    # Calculate frame indices to sample evenly throughout the video
    sample_indices = [int(i * total_frames / num_samples) for i in range(num_samples)]
    
    faces_detected = 0
    frames_checked = 0
    
    for frame_idx in sample_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue
            
        frames_checked += 1

        # Convert to RGB and mp.Image
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        
        detection_result = detector.detect(mp_image)
        
        if detection_result.detections:
            faces_detected += 1
            
    cap.release()
    
    if frames_checked == 0:
        return 0.0
        
    return faces_detected / frames_checked


import concurrent.futures

def process_file(args):
    path = args
    filename = os.path.basename(path)
    step_name = "👤 Face Detection Scoring"

    if state_manager.is_step_done(filename, step_name):
        print(f"   ⏩ {filename} -> Resumed (Already Scored)")
        return
    
    if not os.path.exists(path):
        return

    try:
        visibility_score = has_face(path)
        
        # Persist Score
        scorer.update_score(filename, "face_score", visibility_score)
        
        # Log decision
        logger.log(
            module="face_filter",
            decision="scored_clip",
            confidence=1.0, 
            reason="face_analysis",
            metrics={
                "face_visibility": round(visibility_score, 2)
            }
        )
        
        print(f"   - {filename} -> Scored: {visibility_score:.3f}")
        # Mark as done
        state_manager.mark_step_done(filename, step_name)
    except Exception as e:
        print(f"❌ Error processing {filename}: {e}")

if __name__ == "__main__":
    print(f"👤 Scanning {BASE_DIR} for face presence (Scoring Mode)...")
    
    max_workers = max(1, os.cpu_count() - 2)
    files_found = False
    
    for clip in os.listdir(BASE_DIR):
        clip_dir = os.path.join(BASE_DIR, clip)
        if not os.path.isdir(clip_dir):
            continue

        if clip.startswith("output") or clip.startswith("temp"):
            continue

        print(f"   Processing clip folder: {clip}")
        
        tasks = []
        for file in os.listdir(clip_dir):
            if not file.endswith(".mp4"):
                continue
            path = os.path.join(clip_dir, file)
            tasks.append(path) # Only path
            
        if tasks:
            files_found = True
            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                executor.map(process_file, tasks)

    if not files_found:
        print("   ⚠️ No folders/clips found to score.")
