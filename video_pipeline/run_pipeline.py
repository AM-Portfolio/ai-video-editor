import subprocess
import sys
import time
import os

STEPS = [
    ("✂️  Splitting Video", "smart_splitter.py"),
    ("🏃 Motion Filtering", "motion_filter.py"),
    ("🗣️  VAD (Voice) Filtering", "vad_filter.py"),
    ("👤 Face Detection", "face_filter.py"),
    ("🔒 Privacy Blur", "privacy_filter.py"),
    ("🕵️  Debug Visualization", "render_debug.py"),
    ("🎞️  Final Merge", "merge_final.py"),
]

import shutil
import re

INPUT_CLIPS_DIR = "input_clips"
PROCESSING_DIR = "processing"

def sanitize_filename(name):
    # Remove special chars, spaces to underscores
    name = re.sub(r'[^\w\.-]', '_', name)
    return name

def ingest_files():
    print(f"\n{'='*50}")
    print(f"   📥 Ingesting Files")
    print(f"{'='*50}\n")
    
    if not os.path.exists(INPUT_CLIPS_DIR):
        print(f"⚠️  {INPUT_CLIPS_DIR} does not exist.")
        return False
        
    os.makedirs(PROCESSING_DIR, exist_ok=True)
    
    moved_count = 0
    for filename in os.listdir(INPUT_CLIPS_DIR):
        if not filename.lower().endswith(".mp4"):
            continue
            
        src = os.path.join(INPUT_CLIPS_DIR, filename)
        clean_name = sanitize_filename(filename)
        dst = os.path.join(PROCESSING_DIR, clean_name)
        
        # Logic to clear previous run data for this specific file
        # The pipeline creates a folder with the same name (minus extension)
        video_stem = os.path.splitext(clean_name)[0]
        previous_run_dir = os.path.join(PROCESSING_DIR, video_stem)
        
        if os.path.exists(previous_run_dir):
            print(f"   🧹 Clearing previous data for: {clean_name}")
            shutil.rmtree(previous_run_dir)
            
        # Also remove the file itself if it exists (overwrite)
        if os.path.exists(dst):
            os.remove(dst)

        print(f"   -> Moving {filename} to {PROCESSING_DIR}/{clean_name}")
        shutil.move(src, dst)
        moved_count += 1
        
    if moved_count == 0:
        # Check if processing already has files (maybe re-running?)
        if len([f for f in os.listdir(PROCESSING_DIR) if f.endswith(".mp4") or os.path.isdir(os.path.join(PROCESSING_DIR, f))]) > 0:
             print("   ℹ️  No new input files, but 'processing' folder is not empty. Continue.")
             return True
        else:
             print("   ⚠️  No .mp4 files found in input_clips/ and processing/ is empty.")
             return False
             
    print(f"   ✅ Moved {moved_count} files for processing.")
    return True

def run_step(name, script):
    print(f"\n{'='*50}")
    print(f"   {name}")
    print(f"{'='*50}\n")
    
    start_time = time.time()
    
    try:
        # Check if script exists
        if not os.path.exists(script):
            print(f"❌ Script not found: {script}")
            return False

        # Run the script
        result = subprocess.run(
            [sys.executable, script],
            capture_output=False,  # Let it print to stdout directly
            text=True,
            check=True
        )
        
        duration = time.time() - start_time
        print(f"\n✅ {script} finished in {duration:.2f}s")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Step failed: {script}")
        print(f"Exit code: {e.returncode}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error running {script}: {e}")
        return False

def main():
    print("🚀 Starting AI Video Pipeline...")
    total_start = time.time()
    
    # Step 0: Ingest
    if not ingest_files():
        print("\n🛑 Nothing to process. Exiting.")
        sys.exit(0)
    
    for name, script in STEPS:
        success = run_step(name, script)
        if not success:
            print("\n🛑 Pipeline aborted due to error.")
            sys.exit(1)
            
    total_duration = time.time() - total_start
    print(f"\n✨ Pipeline completed successfully in {total_duration:.2f}s")

if __name__ == "__main__":
    main()
