import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import cv2
import os
import shutil
import json

with open("config.json") as f:
    config = json.load(f)

BASE_DIR = "processing"
MOTION_THRESHOLD = config.get("motion_threshold", 30000)

def has_motion(video_path):
    cap = cv2.VideoCapture(video_path)
    ret, prev = cap.read()
    if not ret:
        return False

    prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    motion_sum = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(prev_gray, gray)
        motion_sum += diff.sum()
        prev_gray = gray

    cap.release()
    return motion_sum > MOTION_THRESHOLD


import concurrent.futures

def process_file(args):
    path, keep_dir, drop_dir = args
    filename = os.path.basename(path)
    
    try:
        is_motion = has_motion(path)
        target_dir = keep_dir if is_motion else drop_dir
        status = "KEEP ✅" if is_motion else "DROP 🗑️"
        
        print(f"   - {filename} -> {status}")
        shutil.move(path, os.path.join(target_dir, filename))
    except Exception as e:
        print(f"❌ Error processing {filename}: {e}")

if __name__ == "__main__":
    print(f"🕵️  Scanning {BASE_DIR} for chunks...")
    
    # Determine max workers (leave some cores for system)
    max_workers = max(1, os.cpu_count() - 2)
    
    for clip in os.listdir(BASE_DIR):
        clip_dir = os.path.join(BASE_DIR, clip)

        if not os.path.isdir(clip_dir):
            continue
        
        if clip in ["keep", "drop"]:
            continue

        keep_dir = os.path.join(clip_dir, "keep")
        drop_dir = os.path.join(clip_dir, "drop")

        os.makedirs(keep_dir, exist_ok=True)
        os.makedirs(drop_dir, exist_ok=True)

        print(f"   Processing clip folder: {clip}")

        tasks = []
        for file in os.listdir(clip_dir):
            if not file.endswith(".mp4"):
                continue
            path = os.path.join(clip_dir, file)
            tasks.append((path, keep_dir, drop_dir))
            
        if tasks:
            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                executor.map(process_file, tasks)

