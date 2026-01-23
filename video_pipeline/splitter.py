import json

with open("config.json") as f:
    config = json.load(f)

PROCESS_DIR = "processing"
CHUNK_SECONDS = config.get("chunk_seconds", 5)

if not os.path.exists(PROCESS_DIR):
    print(f"❌ Processing directory '{PROCESS_DIR}' not found.")
    exit(1)

print(f"📂 Checking {PROCESS_DIR} for videos...")

for video in os.listdir(PROCESS_DIR):
    video_path = os.path.join(PROCESS_DIR, video)

    if not video.endswith(".mp4") or os.path.isdir(video_path):
        continue

    name = os.path.splitext(video)[0]
    output_dir = os.path.join(PROCESS_DIR, name)

    if os.path.exists(output_dir):
        print(f"⚠️  Skipping {video} (already split)")
        continue 

    os.makedirs(output_dir)

    print(f"✂️  Splitting {video} into {CHUNK_SECONDS}s chunks...")

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-c", "copy",
        "-map", "0",
        "-segment_time", str(CHUNK_SECONDS),
        "-f", "segment",
        f"{output_dir}/chunk_%04d.mp4"
    ]

    try:
        # Run ffmpeg, suppressing standard output but keeping error output for debugging
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"✅ Chunks created in {output_dir}")
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg failed for {video}: {e.stderr.decode()}")
        # Optional: cleanup failed directory
        # shutil.rmtree(output_dir)
