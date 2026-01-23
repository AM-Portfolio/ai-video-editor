import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import cv2
import os
import shutil
import json

with open("config.json") as f:
    config = json.load(f)

BASE_DIR = "processing"
MODEL_PATH = "detector.tflite"

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

def has_face(video_path, num_samples=10):
    """Check if face is present by sampling frames evenly throughout the video"""
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if total_frames == 0:
        cap.release()
        return False
    
    # Calculate frame indices to sample evenly throughout the video
    sample_indices = [int(i * total_frames / num_samples) for i in range(num_samples)]
    
    face_found = False
    for frame_idx in sample_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue

        # Convert to RGB and mp.Image
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        
        detection_result = detector.detect(mp_image)
        
        if detection_result.detections:
            face_found = True
            break
            
    cap.release()
    return face_found


import concurrent.futures

def process_file(args):
    path, face_dir, no_face_dir = args
    filename = os.path.basename(path)
    
    if not os.path.exists(path):
        return

    try:
        is_face = has_face(path)
        target_dir = face_dir if is_face else no_face_dir
        status = "👤 FACE" if is_face else "🚫 NO FACE"
        
        print(f"   - {filename} -> {status}")
        shutil.move(path, os.path.join(target_dir, filename))
    except Exception as e:
        print(f"❌ Error processing {filename}: {e}")

if __name__ == "__main__":
    print(f"👤 Scanning {BASE_DIR} for face presence...")
    
    max_workers = max(1, os.cpu_count() - 2)
    
    for clip in os.listdir(BASE_DIR):
        clip_dir = os.path.join(BASE_DIR, clip)
        if not os.path.isdir(clip_dir):
            continue

        keep_dir = os.path.join(clip_dir, "keep")
        speech_dir = os.path.join(keep_dir, "speech")
        
        if not os.path.isdir(speech_dir):
            continue
        
        face_dir = os.path.join(speech_dir, "face")
        no_face_dir = os.path.join(speech_dir, "no_face")

        os.makedirs(face_dir, exist_ok=True)
        os.makedirs(no_face_dir, exist_ok=True)
        
        print(f"   Processing clip folder: {clip}")

        tasks = []
        for file in os.listdir(speech_dir):
            if not file.endswith(".mp4"):
                continue

            src = os.path.join(speech_dir, file)
            if os.path.exists(src):
                tasks.append((src, face_dir, no_face_dir))
        
        if tasks:
            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                executor.map(process_file, tasks)

