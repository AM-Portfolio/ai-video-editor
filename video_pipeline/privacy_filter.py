#!/usr/bin/env python3
"""
Privacy Filter - Step 9 of the Video Pipeline
Blurs sensitive content (faces, background, regions) for privacy.
"""

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import cv2
import os
import json
import numpy as np
import re
import easyocr
import state_manager

# Initialize OCR Reader (English)
reader = easyocr.Reader(['en'], gpu=False) # GPU False for better terminal stability in this environment

with open("config.json") as f:
    config = json.load(f)

BASE_DIR = "processing"
MODEL_PATH = "detector.tflite"

# Privacy config with defaults
privacy_config = config.get("privacy_blur", {})
BLUR_ENABLED = privacy_config.get("enabled", False)
BLUR_MODE = privacy_config.get("mode", "none")  # face_blur, background_blur, region_blur, none
BLUR_STRENGTH = privacy_config.get("blur_strength", 25)
EXCLUDE_MAIN_FACE = privacy_config.get("exclude_main_face", True)
BLUR_REGIONS = privacy_config.get("regions", [])  # List of [x1, y1, x2, y2] in percentages
SENSITIVE_KEYWORDS = privacy_config.get("sensitive_keywords", [])

def is_sensitive(text):
    """Check if text contains sensitive patterns or keywords"""
    text = text.lower().strip()
    
    # Check for Email pattern
    email_pattern = r'[a-zA-Z0-9.-]+@[a-z.-]+\.[a-z]{2,}'
    if re.search(email_pattern, text):
        return True
    
    # Check for keywords
    for kw in SENSITIVE_KEYWORDS:
        if kw in text:
            return True
            
    return False

def get_face_center(detection):
    """Get the center point of a face bounding box"""
    bbox = detection.bounding_box
    cx = bbox.origin_x + bbox.width / 2
    cy = bbox.origin_y + bbox.height / 2
    return cx, cy

def get_main_face_score(detection, frame_width, frame_height):
    """
    Calculate a combined score for main speaker detection.
    Higher score = more likely to be main speaker.
    
    Combines:
    - Area (bigger face = higher score)
    - Center proximity (closer to center = higher score)
    """
    bbox = detection.bounding_box
    
    # Area score (normalized by frame area)
    area = bbox.width * bbox.height
    frame_area = frame_width * frame_height
    area_score = area / frame_area
    
    # Center proximity score (0 = edge, 1 = center)
    face_cx, face_cy = get_face_center(detection)
    frame_cx, frame_cy = frame_width / 2, frame_height / 2
    
    # Distance from center (normalized)
    max_dist = ((frame_width / 2) ** 2 + (frame_height / 2) ** 2) ** 0.5
    dist = ((face_cx - frame_cx) ** 2 + (face_cy - frame_cy) ** 2) ** 0.5
    center_score = 1 - (dist / max_dist)
    
    # Combined score: weight area more (70%) than center (30%)
    return (area_score * 0.7) + (center_score * 0.3)

def apply_blur_to_region(frame, x1, y1, x2, y2, strength=25):
    """Apply Gaussian blur to a specific region of the frame"""
    # Ensure coordinates are within frame bounds
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    
    if x2 <= x1 or y2 <= y1:
        return frame
    
    # Extract region, blur it, and put it back
    region = frame[y1:y2, x1:x2]
    # Ensure kernel size is odd
    kernel_size = strength if strength % 2 == 1 else strength + 1
    blurred_region = cv2.GaussianBlur(region, (kernel_size, kernel_size), 0)
    frame[y1:y2, x1:x2] = blurred_region
    return frame

def process_video_face_blur(input_path, output_path):
    """Blur all faces except the main speaker (largest face)"""
    print(f"🔒 Applying face blur to {os.path.basename(input_path)}...")
    
    # Initialize face detector
    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.FaceDetectorOptions(
        base_options=base_options, 
        min_detection_confidence=privacy_config.get("detection_confidence", 0.15)
    )
    detector = vision.FaceDetector.create_from_options(options)
    
    cap = cv2.VideoCapture(input_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        # Detect faces
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        detection_result = detector.detect(mp_image)
        
        if detection_result.detections:
            detections = detection_result.detections
            
            if EXCLUDE_MAIN_FACE and len(detections) > 1:
                # Find the main face using combined score (area + center proximity)
                main_face = max(detections, key=lambda d: get_main_face_score(d, width, height))
                faces_to_blur = [d for d in detections if d != main_face]
            elif EXCLUDE_MAIN_FACE and len(detections) == 1:
                # Only one face, don't blur it
                faces_to_blur = []
            else:
                # Blur all faces
                faces_to_blur = detections
            
            # Apply blur to each non-main face
            for detection in faces_to_blur:
                bbox = detection.bounding_box
                x1 = int(bbox.origin_x)
                y1 = int(bbox.origin_y)
                x2 = int(bbox.origin_x + bbox.width)
                y2 = int(bbox.origin_y + bbox.height)
                
                # Add some padding
                padding = int(bbox.width * 0.2)
                x1 = max(0, x1 - padding)
                y1 = max(0, y1 - padding)
                x2 = min(width, x2 + padding)
                y2 = min(height, y2 + padding)
                
                frame = apply_blur_to_region(frame, x1, y1, x2, y2, BLUR_STRENGTH)
        
        out.write(frame)
    
    cap.release()
    out.release()
    
    # Re-encode with ffmpeg for proper audio handling
    temp_path = output_path + ".temp.mp4"
    os.rename(output_path, temp_path)
    
    import subprocess
    cmd = [
        "ffmpeg", "-y",
        "-i", temp_path,
        "-i", input_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-map", "0:v:0", "-map", "1:a:0?",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path
    ]
    subprocess.run(cmd, stderr=subprocess.DEVNULL)
    os.remove(temp_path)
    
    return True

def process_video_text_blur(input_path, output_path):
    """Detect and blur sensitive text while protecting the main speaker"""
    print(f"🔒 Applying smart text blur to {os.path.basename(input_path)}...")
    
    # Initialize face detector for protection
    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.15)
    detector = vision.FaceDetector.create_from_options(options)
    
    cap = cv2.VideoCapture(input_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    # OCR is heavy - sample every N frames for speed
    frame_interval = 5 
    frame_count = 0
    
    active_blur_boxes = [] # Persist boxes for a few frames to handle flicker

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        
        frame_count += 1
        
        # 1. Detect Speaker Face (to PROTECT it from blur)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        face_result = detector.detect(mp_image)
        
        main_face_bbox = None
        if face_result.detections:
            main_face = max(face_result.detections, key=lambda d: get_main_face_score(d, width, height))
            main_face_bbox = main_face.bounding_box

        # 2. OCR Detection (Every N frames)
        if frame_count % frame_interval == 1:
            active_blur_boxes = []
            ocr_results = reader.readtext(frame)
            
            for (bbox, text, prob) in ocr_results:
                if is_sensitive(text):
                    # Convert easyocr corners to x1,y1,x2,y2
                    (tl, tr, br, bl) = bbox
                    bx1, by1 = int(tl[0]), int(tl[1])
                    bx2, by2 = int(br[0]), int(br[1])
                    
                    # Check for conflict with face
                    if main_face_bbox:
                        fx1, fy1 = int(main_face_bbox.origin_x), int(main_face_bbox.origin_y)
                        fx2, fy2 = fx1 + int(main_face_bbox.width), fy1 + int(main_face_bbox.height)
                        
                        # Simple overlap check: If box is mostly inside face, it might be a false positive or shirt text
                        # We skip blurring if it's too close to the main face
                        if not (bx1 > fx2 or bx2 < fx1 or by1 > fy2 or by2 < fy1):
                            continue
                            
                    active_blur_boxes.append((bx1, by1, bx2, by2))

        # 3. Apply Blurs
        for box in active_blur_boxes:
            frame = apply_blur_to_region(frame, box[0], box[1], box[2], box[3], BLUR_STRENGTH * 2) # Stronger blur for text
            
        out.write(frame)
    
    cap.release()
    out.release()
    
    # Re-encode with audio (ffmpeg map logic same as before)
    temp_path = output_path + ".temp.mp4"
    os.rename(output_path, temp_path)
    import subprocess
    cmd = [
        "ffmpeg", "-y", "-i", temp_path, "-i", input_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-map", "0:v:0", "-map", "1:a:0?", "-c:a", "aac", "-b:a", "192k",
        "-shortest", output_path
    ]
    subprocess.run(cmd, stderr=subprocess.DEVNULL)
    os.remove(temp_path)
    return True

from decision_log import DecisionLog
logger = DecisionLog()

def process_chunk(input_path, output_path):
    """Process a single video chunk based on blur mode"""
    filename = os.path.basename(input_path)
    step_name = "🔒 Privacy Blur"
    
    if state_manager.is_step_done(filename, step_name):
        print(f"   ⏩ {filename} -> Resumed (Already Blurred)")
        return True

    result = False
    metric_type = "none"
    
    if BLUR_MODE == "face_blur":
        metric_type = "face_blur"
        result = process_video_face_blur(input_path, output_path)
    elif BLUR_MODE == "region_blur":
        metric_type = "region_blur"
        result = process_video_region_blur(input_path, output_path)
    elif BLUR_MODE == "text_blur":
        metric_type = "text_blur"
        result = process_video_text_blur(input_path, output_path)
    else:
        # No processing, just copy
        import shutil
        shutil.copy(input_path, output_path)
        metric_type = "passthrough"
        result = True
        
    # Log decision
    logger.log(
        module="privacy_filter",
        decision="apply_privacy" if BLUR_MODE != "none" else "passthrough",
        confidence=1.0,
        reason=f"privacy_mode_{BLUR_MODE}",
        metrics={
            "blur_mode": BLUR_MODE,
            "blur_strength": BLUR_STRENGTH, 
            "processed": result
        }
    )
    
    if result:
        state_manager.mark_step_done(filename, step_name)
        
    return result

if __name__ == "__main__":
    if not BLUR_ENABLED or BLUR_MODE == "none":
        print("🔒 Privacy blur is disabled. Skipping.")
        exit(0)
    
    print(f"🔒 Applying privacy blur (mode: {BLUR_MODE})...")
    
    for clip in os.listdir(BASE_DIR):
        clip_dir = os.path.join(BASE_DIR, clip)
        if not os.path.isdir(clip_dir):
            continue
        
        face_dir = os.path.join(clip_dir, "keep", "speech", "face")
        if not os.path.isdir(face_dir):
            continue
        
        # Create output directory for blurred files
        blurred_dir = os.path.join(clip_dir, "keep", "speech", "face_blurred")
        os.makedirs(blurred_dir, exist_ok=True)
        
        print(f"   Processing clip folder: {clip}")
        
        for file in os.listdir(face_dir):
            if not file.endswith(".mp4"):
                continue
            
            input_path = os.path.join(face_dir, file)
            output_path = os.path.join(blurred_dir, file)
            
            if process_chunk(input_path, output_path):
                print(f"   ✅ {file}")
            else:
                print(f"   ❌ {file}")
