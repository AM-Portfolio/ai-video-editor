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

def has_face(video_path):
    cap = cv2.VideoCapture(video_path)
    face_found = False
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Convert to RGB and mp.Image
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        
        detection_result = detector.detect(mp_image)
        
        if detection_result.detections:
            face_found = True
            break
            
    cap.release()
    return face_found


print(f"👤 Scanning {BASE_DIR} for face presence...")

for clip in os.listdir(BASE_DIR):
    clip_dir = os.path.join(BASE_DIR, clip)
    if not os.path.isdir(clip_dir):
        continue

    # We only care about chunks that passed Step 5 (speech), which are in 'keep/speech'
    keep_dir = os.path.join(clip_dir, "keep")
    speech_dir = os.path.join(keep_dir, "speech")
    
    if not os.path.isdir(speech_dir):
        continue
    
    face_dir = os.path.join(speech_dir, "face")
    no_face_dir = os.path.join(speech_dir, "no_face")

    os.makedirs(face_dir, exist_ok=True)
    os.makedirs(no_face_dir, exist_ok=True)
    
    print(f"   Processing clip folder: {clip}")

    for file in os.listdir(speech_dir):
        if not file.endswith(".mp4"):
            continue

        src = os.path.join(speech_dir, file)
        
        # Determine if we keep (face) or drop (no_face)
        try:
            is_face = has_face(src)
            target_dir = face_dir if is_face else no_face_dir
            
            print(f"   - {file} -> {'👤 FACE' if is_face else '🚫 NO FACE'}")
            
            shutil.move(src, os.path.join(target_dir, file))
        except Exception as e:
            print(f"❌ Error processing/moving {file}: {e}")
