import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os
import sys
# Add project root to sys.path for modular imports
sys.path.append(os.getcwd())

from core.logging import DecisionLog
from core.scoring import ScoreKeeper
BASE_DIR = "processing"
OUTPUT_DIR = "output_clips"
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

for clip in os.listdir(BASE_DIR):
    clip_dir = os.path.join(BASE_DIR, clip)
    if not os.path.isdir(clip_dir):
        continue
        
    # Recursive search for .mp4 files
    all_chunks = []
    for root, dirs, files in os.walk(clip_dir):
        for file in files:
            if file.endswith(".mp4"):
                 all_chunks.append(os.path.join(root, file))
    
    # Sort by filename (chunk_0000, chunk_0001...)
    all_chunks.sort(key=lambda x: os.path.basename(x))
    
    if not all_chunks:
        continue

    print(f"   Analyzing {clip} ({len(all_chunks)} chunks found)...")
    
    inputs, filter_complex = build_filter_complex(all_chunks)
    
    output_path = os.path.join(OUTPUT_DIR, f"debug_{clip}.mp4")
    
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
