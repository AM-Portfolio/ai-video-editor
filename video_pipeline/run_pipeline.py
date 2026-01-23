import subprocess
import sys
import time
import os
import shutil
import re

STEPS = [
    ("✂️  Splitting Video", "smart_splitter.py"),
    ("🏃 Motion Filtering", "motion_filter.py"),
    ("🗣️  VAD (Voice) Filtering", "vad_filter.py"),
    ("👤 Face Detection", "face_filter.py"),
    ("🔒 Privacy Blur", "privacy_filter.py"),
    ("🕵️  Debug Visualization", "render_debug.py"),
    ("🎞️  Final Merge", "merge_final.py"),
]

INPUT_CLIPS_DIR = "input_clips"
PROCESSING_DIR = "processing"

def sanitize_filename(name):
    # Remove special chars, spaces to underscores
    name = re.sub(r'[^\w\.-]', '_', name)
    return name

def ingest_files(logger_callback=None):
    if logger_callback:
        logger_callback(f"\n{'='*50}")
        logger_callback(f"   📥 Ingesting Files")
        logger_callback(f"{'='*50}\n")
    else:
        print(f"\n{'='*50}")
        print(f"   📥 Ingesting Files")
        print(f"{'='*50}\n")
    
    if not os.path.exists(INPUT_CLIPS_DIR):
        msg = f"⚠️  {INPUT_CLIPS_DIR} does not exist."
        print(msg)
        if logger_callback: logger_callback(msg)
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
            msg = f"   🧹 Clearing previous data for: {clean_name}"
            print(msg)
            if logger_callback: logger_callback(msg)
            shutil.rmtree(previous_run_dir)
            
        # Also remove the file itself if it exists (overwrite)
        if os.path.exists(dst):
            os.remove(dst)

        msg = f"   -> Moving {filename} to {PROCESSING_DIR}/{clean_name}"
        print(msg)
        if logger_callback: logger_callback(msg)
        shutil.move(src, dst)
        moved_count += 1
        
    if moved_count == 0:
        # Check if processing already has files (maybe re-running?)
        if len([f for f in os.listdir(PROCESSING_DIR) if f.endswith(".mp4") or os.path.isdir(os.path.join(PROCESSING_DIR, f))]) > 0:
             msg = "   ℹ️  No new input files, but 'processing' folder is not empty. Continue."
             print(msg)
             if logger_callback: logger_callback(msg)
             return True
        else:
             msg = "   ⚠️  No .mp4 files found in input_clips/ and processing/ is empty."
             print(msg)
             if logger_callback: logger_callback(msg)
             return False
             
    msg = f"   ✅ Moved {moved_count} files for processing."
    print(msg)
    if logger_callback: logger_callback(msg)
    return True

def run_step(name, script, logger_callback=None):
    if logger_callback:
        logger_callback(f"\n{'='*50}")
        logger_callback(f"   {name}")
        logger_callback(f"{'='*50}\n")
    print(f"\n{'='*50}")
    print(f"   {name}")
    print(f"{'='*50}\n")
    
    start_time = time.time()
    
    try:
        # Check if script exists
        if not os.path.exists(script):
            msg = f"❌ Script not found: {script}"
            print(msg)
            if logger_callback: logger_callback(msg)
            return False

        # Run the script with Popen for real-time output capturing
        process = subprocess.Popen(
            [sys.executable, script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                line = line.strip()
                print(line)
                if logger_callback:
                    logger_callback(line)

        if process.returncode == 0:
            duration = time.time() - start_time
            msg = f"\n✅ {script} finished in {duration:.2f}s"
            print(msg)
            if logger_callback: logger_callback(msg)
            return True
        else:
            msg = f"\n❌ Step failed: {script}\nExit code: {process.returncode}"
            print(msg)
            if logger_callback: logger_callback(msg)
            return False
        
    except Exception as e:
        msg = f"\n❌ Unexpected error running {script}: {e}"
        print(msg)
        if logger_callback: logger_callback(msg)
        return False

def main(logger_callback=None):
    msg = "🚀 Starting AI Video Pipeline..."
    print(msg)
    if logger_callback: logger_callback(msg)
    
    total_start = time.time()
    
    # Step 0: Ingest
    if not ingest_files(logger_callback):
        msg = "\n🛑 Nothing to process. Exiting."
        print(msg)
        if logger_callback: logger_callback(msg)
        # return instead of sys.exit so UI doesn't crash
        return
    
    for name, script in STEPS:
        success = run_step(name, script, logger_callback)
        if not success:
            msg = "\n🛑 Pipeline aborted due to error."
            print(msg)
            if logger_callback: logger_callback(msg)
            return  # Return to stop pipeline but keep UI alive
            
    total_duration = time.time() - total_start
    msg = f"\n✨ Pipeline completed successfully in {total_duration:.2f}s"
    print(msg)
    if logger_callback: logger_callback(msg)

if __name__ == "__main__":
    main()
