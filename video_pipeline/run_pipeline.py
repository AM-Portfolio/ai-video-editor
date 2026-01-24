import subprocess
import sys
import time
import os
import shutil
import re
import state_manager

STEPS = [
    ("✂️  Splitting Video", "smart_splitter.py"),
    ("🏃 Motion Scoring", "motion_filter.py"),
    ("🗣️  VAD (Voice) Scoring", "vad_filter.py"),
    ("👤 Face Detection Scoring", "face_filter.py"),
    ("🔒 Privacy Blur", "privacy_filter.py"),
    ("🏷️  Semantic Tagging", "semantic_tagger.py"),
    ("🧠 The Decider", "decider.py"),
    ("📊 Decision Analytics", "decision_analytics.py"),
    ("🗺️  Action Planner", "action_planner.py"),
    ("🚜 Action Executor", "action_executor.py"),
    ("📝 Run Explainer", "run_explainer.py"),
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
    active_chunks = []

    for filename in os.listdir(INPUT_CLIPS_DIR):
        if not filename.lower().endswith(".mp4"):
            continue
            
        src = os.path.join(INPUT_CLIPS_DIR, filename)
        clean_name = sanitize_filename(filename)
        dst = os.path.join(PROCESSING_DIR, clean_name)
        
        # RESUME CAPABILITY: Check if final output exists
        OUTPUT_CLIPS_DIR = "output_clips"
        final_output_path = os.path.join(OUTPUT_CLIPS_DIR, f"final_{clean_name}")
        
        if os.path.exists(final_output_path):
             msg = f"   ⏩ Skipping {clean_name} (Already processed)"
             print(msg)
             if logger_callback: logger_callback(msg)
             
             # Even if skipped, we should probably mark it as COMPLETED in state
             state_manager.update_chunk_status(clean_name, "COMPLETED", message="Already processed")
             continue

        # Logic to clear previous run data for this specific file
        video_stem = os.path.splitext(clean_name)[0]
        previous_run_dir = os.path.join(PROCESSING_DIR, video_stem)
        
        if os.path.exists(previous_run_dir):
            msg = f"   🧹 Clearing previous data for: {clean_name}"
            print(msg)
            if logger_callback: logger_callback(msg)
            shutil.rmtree(previous_run_dir)
            
        if os.path.exists(dst):
            os.remove(dst)

        msg = f"   -> Copying {filename} to {PROCESSING_DIR}/{clean_name}"
        print(msg)
        if logger_callback: logger_callback(msg)
        shutil.copy2(src, dst)
        moved_count += 1
        active_chunks.append(clean_name)
        
    # Check if we are resuming processing chunks (files already in processing/)
    # If ingest moved nothing, maybe we are just continuing?
    chunks_in_processing = [f for f in os.listdir(PROCESSING_DIR) if f.endswith(".mp4")]
    
    # Initialize State
    all_chunks = set(active_chunks + chunks_in_processing)
    # Also include any that were skipped? No, state_manager handles them via update.
    # But init_state needs the list to create "PENDING" entries.
    state_manager.init_state(list(all_chunks))

    if moved_count == 0:
        if len(chunks_in_processing) > 0:
             msg = "   ℹ️  No new input files, but 'processing' folder is not empty. Continue."
             print(msg)
             if logger_callback: logger_callback(msg)
             return True
        else:
             msg = "   ⚠️  No .mp4 files found to process."
             print(msg)
             if logger_callback: logger_callback(msg)
             return False
             
    msg = f"   ✅ Ready to process {len(all_chunks)} chunks."
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
        if not os.path.exists(script):
            msg = f"❌ Script not found: {script}"
            print(msg)
            if logger_callback: logger_callback(msg)
            return False

        process = subprocess.Popen(
            [sys.executable, script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
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
                
                # STATE TRACKING
                match = re.search(r"(chunk_\d+)", line)
                if match:
                    chunk_name = match.group(1)
                    # Try to match full filename if possible, usually just "chunk_001"
                    # We might need to map "chunk_001" -> "chunk_001.mp4"
                    # But simpler: just use the stem as ID
                    # If file is "chunk_001.mp4", detecting "chunk_001" is enough.
                    # Let's ensure consistency: State keys are filenames "chunk_001.mp4"?
                    # In ingest, we used `clean_name` (filename).
                    # So "chunk_001" needs to be mapped.
                    # HACK: try appending .mp4 if not present
                    key = chunk_name if chunk_name.endswith(".mp4") else f"{chunk_name}.mp4"
                    state_manager.update_chunk_status(key, "PROCESSING", step=name, message=line)

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
    
    if not ingest_files(logger_callback):
        msg = "\n🛑 Nothing to process. Exiting."
        print(msg)
        if logger_callback: logger_callback(msg)
        return
    
    for name, script in STEPS:
        success = run_step(name, script, logger_callback)
        if not success:
            msg = "\n🛑 Pipeline aborted due to error."
            print(msg)
            if logger_callback: logger_callback(msg)
            return
            
    # Mark all valid chunks as COMPLETED at the end?
    # Or merge_final moves them.
    # Ideally checking output_clips again.
    
    total_duration = time.time() - total_start
    msg = f"\n✨ Pipeline completed successfully in {total_duration:.2f}s"
    print(msg)
    if logger_callback: logger_callback(msg)

if __name__ == "__main__":
    main()
