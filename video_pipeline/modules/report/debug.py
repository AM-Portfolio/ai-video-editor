import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os
import json
import subprocess
# Add project root to sys.path for modular imports
sys.path.append(os.getcwd())

from core.logging import DecisionLog
from core.scoring import ScoreKeeper
from core import path_utils

BASE_DIR = path_utils.get_processing_dir()
OUTPUT_DIR = path_utils.get_output_clips_dir()
FINAL_NAME = "debug_preview.mp4"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Status definitions (Priority order for folder searching)
# We need to find *all* chunks. They might be in:
# - <clip>/keep/speech/face/chunk_XXXX.mp4 (ACCEPTED)
# - <clip>/keep/speech/no_face/chunk_XXXX.mp4 (REJECTED: NO FACE)
# - <clip>/keep/silent/chunk_XXXX.mp4 (REJECTED: SILENT)
# - <clip>/drop/chunk_XXXX.mp4 (REJECTED: MOTION)
# - <clip>/chunk_XXXX.mp4 (Initial state? Should be moved already)

def get_chunk_status(path):
    # Determine status from path
    if "/keep/speech/face/" in path:
        return "ACCEPTED", "green"
    elif "/keep/speech/no_face/" in path:
        return "REJECTED: NO FACE", "red"
    elif "/keep/silent/" in path:
        return "REJECTED: SILENT", "yellow"
    elif "/drop/" in path:
        return "REJECTED: MOTION", "gray"
    else:
        return "UNKNOWN", "white"

def build_filter_complex(chunks):
    # We want to concat all chunks.
    # For REJECTED chunks, we apply grayscale + drawtext.
    
    filters = []
    inputs = []
    
    cnt = 0
    concat_v = ""
    concat_a = ""
    
    for i, chunk_path in enumerate(chunks):
        status, color = get_chunk_status(chunk_path)
        inputs.extend(["-i", chunk_path])
        
        # Video filter
        v_in = f"[{i}:v]"
        v_out = f"[v{i}]"
        
        filters_chain = []
        
        if status != "ACCEPTED":
            # Grayscale for all rejected
            filters_chain.append("hue=s=0")
            
            # Simple tinting to distinguish reasons (since drawtext is unavailable)
            if "SILENT" in status:
                # Darken silent clips
                filters_chain.append("eq=brightness=-0.2")
            elif "NO FACE" in status:
                # Slight red tint for no face (using eq to shift contrast/gamma might be complex, keeping simple)
                # Just grayscale is fine for now to separate from accepted.
                pass
        else:
            # Pass through
            filters_chain.append("null")
        
        # Construct chain string: [in]filter1,filter2[out]
        chain = f"{v_in}{','.join(filters_chain)}{v_out}"
        filters.append(chain)
        
        concat_v += v_out
        # concat_a += f"[{i}:a]"
        cnt += 1
        
    # Concat filter (Video only)
    filters.append(f"{concat_v}concat=n={cnt}:v=1:a=0[outv]")
    
    return inputs, ";".join(filters)

print(f"🕵️  Rendering Debug Timeline (Video Only)...")

# Load scores and calculate unique IDs
# Load scores and calculate unique IDs
score_keeper = ScoreKeeper()
try:
    with open(score_keeper.scores_file, "r") as f:
        all_scores = json.load(f)
except Exception as e:
    print(f"⚠️ Warning: Could not load scores for debug: {e}")
    all_scores = {}

# Group chunks by their parent clip/segment
grouped_chunks = {}
for clip_id in sorted(all_scores.keys()):
    # clip_id is now "segment_xxxx/chunk_yyyy.mp4"
    clip_path = os.path.join(BASE_DIR, clip_id)
    if not os.path.exists(clip_path):
        continue

    # Extract the parent clip/segment name (e.g., "segment_xxxx")
    parent_clip_name = clip_id.split(os.sep)[0]
    if parent_clip_name not in grouped_chunks:
        grouped_chunks[parent_clip_name] = []
    grouped_chunks[parent_clip_name].append(clip_path)

for clip_name, all_chunks in grouped_chunks.items():
    # Sort chunks in temporal order
    all_chunks.sort(key=lambda x: os.path.basename(x))
    
    if not all_chunks:
        continue

    print(f"   Analyzing {clip_name} ({len(all_chunks)} chunks found)...")
    
    inputs, filter_complex = build_filter_complex(all_chunks)
    
    output_path = os.path.join(OUTPUT_DIR, f"debug_{clip_name}.mp4")
    
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[outv]", 
        "-c:v", "libx264", "-an",
        output_path
    ]
    
    print(f"   rendering {output_path}...")
    try:
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
        print("   ✅ Done.")
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Error rendering debug video: {e.stderr.decode()[-500:]}")
