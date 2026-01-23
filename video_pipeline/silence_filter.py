import os
import subprocess
import numpy as np
import shutil
import tempfile
import json

with open("config.json") as f:
    config = json.load(f)

BASE_DIR = "processing"
SILENCE_THRESHOLD = config.get("silence_threshold", 0.01)

def has_speech(video_path):
    # Create temp file, but we need to ensure it's closed/manage by subprocess correctly
    # Windows can vary, but here on Mac it is fine to pass name.
    with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ac", "1",
            "-ar", "16000",
            audio.name
        ]
        # Run ffmpeg
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Read data
        # Check if file has data
        if os.path.getsize(audio.name) == 0:
            return False

        data = np.fromfile(audio.name, dtype=np.int16)
        if len(data) == 0:
            return False

        energy = np.mean(np.abs(data))
        # 16-bit audio range is -32768 to 32767. 
        # Mean absolute amplitude as fraction of full scale * range
        return energy > SILENCE_THRESHOLD * 32768


print(f"🎙️  Scanning {BASE_DIR} for speaking chunks...")

for clip in os.listdir(BASE_DIR):
    # Only look into clips processing
    clip_dir = os.path.join(BASE_DIR, clip)
    if not os.path.isdir(clip_dir):
        continue

    # We only care about chunks that passed Step 4 (motion), which are in 'keep'
    keep_dir = os.path.join(clip_dir, "keep")
    if not os.path.isdir(keep_dir):
        continue

    speech_dir = os.path.join(keep_dir, "speech")
    silent_dir = os.path.join(keep_dir, "silent")

    os.makedirs(speech_dir, exist_ok=True)
    os.makedirs(silent_dir, exist_ok=True)

    print(f"   Processing clip folder: {clip}")

    # Iterate files in 'keep'
    for file in os.listdir(keep_dir):
        if not file.endswith(".mp4"):
            continue

        src = os.path.join(keep_dir, file)
        
        # Don't re-process if already in subfolders (though listdir shouldn't see them if we move immediately, 
        # but listdir snapshot or safety check is good)
        # Actually listdir returns names, if we move them, they are gone from the dir being iterated? 
        # os.listdir returns a list, so iterating it is safe even if we move files.
        
        is_speech = has_speech(src)
        target_dir = speech_dir if is_speech else silent_dir
        
        print(f"   - {file} -> {'🗣️ SPEECH' if is_speech else '🤫 SILENT'}")
        
        try:
            shutil.move(src, os.path.join(target_dir, file))
        except Exception as e:
            print(f"❌ Error moving {file}: {e}")
