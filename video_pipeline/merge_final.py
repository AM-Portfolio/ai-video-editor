import os
import subprocess
import json
import tempfile

# Try to load config if available
try:
    with open("config.json") as f:
        config = json.load(f)
except FileNotFoundError:
    config = {}

BASE_DIR = "processing"
OUTPUT_DIR = "output_clips"
TEMP_DIR = "temp_normalized"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Loudnorm parameters (EBU R128)
LOUDNORM_PARAMS = "I=-16:LRA=11:TP=-1.5"

def get_duration(video_path):
    """Get video duration in seconds"""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0

def normalize_chunk(input_path, output_path):
    """Re-encode a single chunk to standardized specs with timestamp sanitization and audio fades"""
    # Get crossfade duration from config (default 0.1s)
    crossfade = config.get("crossfade_duration", 0.1)
    
    # Get duration for fade-out calculation
    duration = get_duration(input_path)
    fade_out_start = max(0, duration - crossfade)
    
    # Audio filter chain: reset timestamps, apply micro fade in/out, then loudnorm
    # The fade removes audio pops at cut points
    audio_filter = f"asetpts=PTS-STARTPTS,afade=t=in:st=0:d={crossfade},afade=t=out:st={fade_out_start}:d={crossfade},loudnorm={LOUDNORM_PARAMS}"
    
    cmd = [
        "ffmpeg", "-y",
        "-fflags", "+genpts+igndts",       # Generate clean timestamps, ignore broken DTS
        "-i", input_path,
        "-vf", "setpts=PTS-STARTPTS,fps=30,format=yuv420p,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-af", audio_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-avoid_negative_ts", "make_zero",  # Shift any negative timestamps to zero
        "-movflags", "+faststart",
        output_path
    ]
    result = subprocess.run(cmd, stderr=subprocess.PIPE)
    return result.returncode == 0

def merge_with_demuxer(normalized_chunks, output_path):
    """Use concat demuxer for bulletproof concatenation"""
    # Create concat file list
    concat_file = os.path.join(TEMP_DIR, "concat_list.txt")
    with open(concat_file, "w") as f:
        for chunk in normalized_chunks:
            # Need to escape single quotes in path
            safe_path = os.path.abspath(chunk).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")
    
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c", "copy",  # No re-encoding needed, chunks are identical
        output_path
    ]
    result = subprocess.run(cmd, stderr=subprocess.PIPE)
    return result.returncode == 0

for clip in os.listdir(BASE_DIR):
    # Prefer blurred files if privacy filter was enabled
    blurred_dir = os.path.join(BASE_DIR, clip, "keep", "speech", "face_blurred")
    face_dir = os.path.join(BASE_DIR, clip, "keep", "speech", "face")
    
    # Use blurred dir if it exists and has files, otherwise use face dir
    if os.path.isdir(blurred_dir) and len([f for f in os.listdir(blurred_dir) if f.endswith(".mp4")]) > 0:
        source_dir = blurred_dir
    elif os.path.isdir(face_dir):
        source_dir = face_dir
    else:
        continue

    chunks = sorted([
        os.path.join(source_dir, f)
        for f in os.listdir(source_dir)
        if f.endswith(".mp4")
    ])

    if len(chunks) < 2:
        print(f"   ⚠️ Not enough chunks to merge for {clip} (found {len(chunks)})")
        continue

    print(f"🎞 Normalizing {len(chunks)} chunks for: {clip}")
    
    # Step 1: Normalize each chunk
    normalized_chunks = []
    clip_temp_dir = os.path.join(TEMP_DIR, clip)
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
        continue
    
    # Step 2: Merge using concat demuxer
    output_path = os.path.join(OUTPUT_DIR, f"final_{clip}.mp4")
    print(f"   Merging {len(normalized_chunks)} normalized chunks...")
    
    if merge_with_demuxer(normalized_chunks, output_path):
        print(f"✅ Final video created: {output_path}")
    else:
        print(f"❌ Error merging {clip}")

# Cleanup temp files
import shutil
shutil.rmtree(TEMP_DIR, ignore_errors=True)
