import os
import subprocess
import json
import shutil
import sys
# Add project root to sys.path for modular imports
sys.path.append(os.getcwd())

from core import path_utils

USER_ID = path_utils.get_user_id()

BASE_DIR = path_utils.get_processing_dir()
OUTPUT_DIR = path_utils.get_output_videos_dir()
TEMP_DIR = os.path.join(BASE_DIR, "temp_merge")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

def normalize_chunk(input_path, output_path):
    """
    Normalizes audio to EBU R128 and ensures consistent video format.
    Uses complex filter for audio norm.
    """
    # ... (simplified for brevity, ensuring consistent format)
    # We use a standard target: 1080p? Or keep source? Keep source but re-encode for safety.
    # Audio: loudnorm=I=-16:TP=-1.5:LRA=11
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ]
    # Suppress output unless error
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print(f"Error normalizing {input_path}: {result.stderr.decode()}")
    return result.returncode == 0

def merge_with_demuxer(chunk_paths, output_path):
    import sys
    # Add project root to sys.path for modular imports
    sys.path.append(os.getcwd())

    from core import config as cfg_loader
    config = cfg_loader.load_config()
    list_file = os.path.join(TEMP_DIR, "file_list.txt")
    with open(list_file, "w") as f:
        for p in chunk_paths:
            # ffmpeg concat requires absolute paths or safe relative
            abs_path = os.path.abspath(p)
            f.write(f"file '{abs_path}'\n")
            
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", output_path
    ]
    result = subprocess.run(cmd, stderr=subprocess.PIPE)
    return result.returncode == 0

def process_merge_logic(chunks, output_name):
    print(f"🎞 Normalizing {len(chunks)} chunks for: {output_name}")
    
    # Step 1: Normalize each chunk
    normalized_chunks = []
    # Use output_name as subdir for temp to avoid collisions
    clip_temp_dir = os.path.join(TEMP_DIR, output_name)
    os.makedirs(clip_temp_dir, exist_ok=True)
    
    for i, chunk in enumerate(chunks):
        normalized_path = os.path.join(clip_temp_dir, f"norm_{i:04d}.mp4")
        print(f"   Normalizing chunk {i+1}/{len(chunks)}...")
        if normalize_chunk(chunk, normalized_path):
            normalized_chunks.append(normalized_path)
        else:
            print(f"   ❌ Failed to normalize {chunk}")
    
    if len(normalized_chunks) < 2:
        print(f"   ❌ Not enough normalized chunks")
        return False
    
    # Step 2: Merge using concat demuxer
    output_path = os.path.join(OUTPUT_DIR, f"{output_name}.mp4")
    print(f"   Merging {len(normalized_chunks)} normalized chunks...")
    
    if merge_with_demuxer(normalized_chunks, output_path):
        print(f"✅ Final video created: {output_path}")
        return True
    else:
        print(f"❌ Error merging {output_name}")
        return False

# MAIN ORCHESTRATION
CATEGORIES = ["product_related", "funny", "general", "selected"]

files_found = False

for category in CATEGORIES:
    category_dir = os.path.join(path_utils.get_output_clips_dir(), category)
    
    if os.path.exists(category_dir) and len(os.listdir(category_dir)) > 0:
        print(f"🎬 Merging {category.upper()} clips from {category_dir}...")
        
        chunks = sorted([
            os.path.join(category_dir, f)
            for f in os.listdir(category_dir)
            if f.endswith(".mp4")
        ])
        
        if len(chunks) < 1:
            print(f"   ⚠️ No valid mp4 chunks found in {category}")
        elif len(chunks) == 1:
            print(f"   ℹ️  Single chunk for {category}. Copying directly...")
            output_path = os.path.join(OUTPUT_DIR, f"final_output_{category}.mp4")
            shutil.copy2(chunks[0], output_path)
            files_found = True
        else:
            files_found = True
            process_merge_logic(chunks, f"final_output_{category}")

# NEW: Merge ALL kept categories into one "Master Video"
# Logic moved OUTSIDE the loop to run once.
print(f"🎬 Merging MASTER video (All kept clips)...")

# Track seen basenames to prevent duplicates if file exists in multiple category folders (stale data)
seen_basenames = set()
unique_chunks = []

for category in CATEGORIES:
    category_dir = os.path.join(path_utils.get_output_clips_dir(), category)
    if os.path.exists(category_dir):
        for f in os.listdir(category_dir):
            if f.endswith(".mp4"):
                basename = os.path.basename(f)
                if basename not in seen_basenames:
                    seen_basenames.add(basename)
                    unique_chunks.append(os.path.join(category_dir, f))

# Sort by filename to ensure timeline order (chunk_001, chunk_002...)
sorted_all_chunks = sorted(unique_chunks, key=lambda x: os.path.basename(x))

if len(sorted_all_chunks) > 1:
    process_merge_logic(sorted_all_chunks, "final_output_master_raw")
elif len(sorted_all_chunks) == 1:
    print("   ℹ️  Single chunk Master. Copying...")
    master_path = os.path.join(OUTPUT_DIR, "final_output_master_raw.mp4")
    shutil.copy2(sorted_all_chunks[0], master_path)
else:
    print("   ⚠️ Not enough total clips for Master Video.")

if not files_found:
    print("⚠️ No clips found in any output category folder.")


# Cleanup temp files
shutil.rmtree(TEMP_DIR, ignore_errors=True)
