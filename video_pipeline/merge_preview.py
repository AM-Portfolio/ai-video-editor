import os
import subprocess

BASE_DIR = "processing"
OUTPUT_DIR = "output_clips"

print(f"🎬 Starting Preview Merge...")
print(f"   Input:  {BASE_DIR}/*/keep/speech/face/")
print(f"   Output: {OUTPUT_DIR}/")

os.makedirs(OUTPUT_DIR, exist_ok=True)

for clip in os.listdir(BASE_DIR):
    clip_dir = os.path.join(BASE_DIR, clip)
    
    # Safety check if it is a directory
    if not os.path.isdir(clip_dir):
        continue

    # Path to the 'face' chunks (end of the pipeline)
    face_dir = os.path.join(clip_dir, "keep", "speech", "face")

    if not os.path.isdir(face_dir):
        # Maybe it got filtered out earlier, skip silently or log verbose
        continue

    # Get sorted chunks to maintain time order
    chunks = sorted([
        f for f in os.listdir(face_dir)
        if f.endswith(".mp4")
    ])

    if not chunks:
        print(f"   ⚠️ No 'face' chunks found for {clip}. Skipping.")
        continue

    # Create the concatenation list file for ffmpeg
    list_file = os.path.join(face_dir, "files.txt")

    with open(list_file, "w") as f:
        for chunk in chunks:
            # ffmpeg requires absolute paths or relative safe paths. 
            # We'll use absolute to be safe, or relative to the list file?
            # Using absolute path in the list file is safest.
            abs_path = os.path.abspath(os.path.join(face_dir, chunk))
            f.write(f"file '{abs_path}'\n")

    output_filename = f"preview_{clip}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    print(f"   🔨 Merging {len(chunks)} chunks for {clip}...")

    # Run ffmpeg concat
    # -safe 0 is needed if using absolute paths or paths with special chars
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output_path
    ]
    
    # Run silently but show errors
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    
    if result.returncode == 0:
        print(f"   ✅ Created: {output_path}")
    else:
        print(f"   ❌ Error merging {clip}: {result.stderr.decode()}")

print("✨ Merge process complete.")
