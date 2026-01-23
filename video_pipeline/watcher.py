import os
import time
import shutil

INPUT_DIR = "input_clips"
PROCESS_DIR = "processing"

seen_files = set()

print("👀 Watching for new video clips...")

while True:
    for file in os.listdir(INPUT_DIR):
        if not file.endswith(".mp4"):
            continue

        if file in seen_files:
            continue

        src = os.path.join(INPUT_DIR, file)
        dst = os.path.join(PROCESS_DIR, file)

        try:
            shutil.move(src, dst)
            seen_files.add(file)
            print(f"🎬 New clip detected: {file}")
            print(f"➡️  Moved to processing/{file}")
        except Exception as e:
            print(f"❌ Error moving {file}: {e}")

    time.sleep(2)
