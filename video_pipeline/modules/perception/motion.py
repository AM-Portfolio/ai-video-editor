import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import cv2
import os
import shutil
# Add project root to sys.path for modular imports
sys.path.append(os.getcwd())

from core import config as cfg_loader
from core.logging import DecisionLog
from core.scoring import ScoreKeeper
from core import state as state_manager
from core import path_utils

config = cfg_loader.load_config()
BASE_DIR = path_utils.get_processing_dir()
MOTION_THRESHOLD = config.get("motion_threshold", 30000)

# Initialize loggers
logger = DecisionLog()
scorer = ScoreKeeper()

def has_motion(video_path):
    cap = cv2.VideoCapture(video_path)
    ret, prev = cap.read()
    if not ret:
        return 0.0

    prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    motion_sum = 0
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(prev_gray, gray)
        motion_sum += diff.sum()
        prev_gray = gray
        frame_count += 1

    cap.release()
    return motion_sum


import concurrent.futures

def process_file(args):
    path = args
    # Unique ID: segment_xxxx/chunk_yyyy.mp4
    clip_id = os.path.relpath(path, BASE_DIR)
    step_name = "🏃 Motion Scoring"
    
    # RESUME CHECK
    if state_manager.is_step_done(clip_id, step_name):
        print(f"   ⏩ {clip_id} -> Resumed (Already Scored)")
        return

    try:
        raw_motion = has_motion(path)
        
        # Normalize motion score (0.0 - 1.0)
        # Heuristic: MOTION_THRESHOLD is the "pass" mark. 
        # Let's say 2x threshold is "perfect" (1.0). 
        # But we need a smooth curve.
        # Simple linear: raw / (threshold * 3) clamped?
        # Let's stick to a simple saturation: 1.0 if > 2*threshold
        # Or just relative to threshold.
        # If raw < threshold, score < 0.5?
        # Let's define score: 0.5 at threshold.
        # score = 0.5 * (raw / threshold) capped at 1.0? 
        # No, "quality_score" usually means higher is better.
        # Let's just normalize to a reasonable max like 1,000,000 or config value.
        # We'll use the threshold as a reference point.
        # score = sigmoid(raw - threshold)?
        # Simpler: raw / (raw + threshold) -> 0.5 at threshold.
        score = raw_motion / (raw_motion + MOTION_THRESHOLD)
        
        # Persist Score
        scorer.update_score(clip_id, "motion_score", score)
        
        # Log Trace
        logger.log(
            module="motion_filter",
            decision="scored_clip",
            confidence=1.0,
            reason="motion_analysis",
            metrics={
                "clip_id": clip_id,
                "raw_motion": float(raw_motion),
                "quality_score": float(score)
            }
        )
        
        print(f"   - {clip_id} -> Scored: {score:.3f}")
        # Mark as done in state
        state_manager.mark_step_done(clip_id, step_name)
    except Exception as e:
        print(f"❌ Error processing {clip_id}: {e}")

if __name__ == "__main__":
    print(f"🕵️  Scanning {BASE_DIR} for chunks (Scoring Mode)...")
    
    max_workers = max(1, os.cpu_count() - 2)
    
    files_found = False
    
    for clip in os.listdir(BASE_DIR):
        clip_dir = os.path.join(BASE_DIR, clip)

        if not os.path.isdir(clip_dir):
            continue
        
        # Skip output/temp dirs if any accidentally here
        if clip.startswith("output") or clip.startswith("temp"):
            continue

        print(f"   Processing clip folder: {clip}")

        tasks = []
        for file in os.listdir(clip_dir):
            if not file.endswith(".mp4"):
                continue
            path = os.path.join(clip_dir, file)
            # Pass only path
            tasks.append(path)
            
        if tasks:
            files_found = True
            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                executor.map(process_file, tasks)

    if not files_found:
        print("   ⚠️ No folders/clips found to score.")
